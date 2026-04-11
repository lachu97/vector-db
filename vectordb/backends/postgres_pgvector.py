# vectordb/backends/postgres_pgvector.py
"""
PostgreSQL + pgvector backend.

Shared vector table:
  pg_vectors
Collections registry table:
  pg_collections
"""
from typing import Any, Dict, List, Optional

import numpy as np
import structlog
from pgvector.sqlalchemy import Vector as PgVector
from sqlalchemy import (
    Column, DateTime, Integer, JSON, String, Text,
    UniqueConstraint, func, select, text,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

from vectordb.backends.base import (
    VectorBackend,
    CollectionAlreadyExistsError,
    CollectionNotFoundError,
    DimensionMismatchError,
    VectorNotFoundError,
)

logger = structlog.get_logger(__name__)

PgBase = declarative_base()


class _PgCollection(PgBase):
    __tablename__ = "pg_collections"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, index=True)
    dim = Column(Integer, nullable=False)
    distance_metric = Column(String, nullable=False, default="cosine")
    description = Column(Text, nullable=True)
    user_id = Column(Integer, nullable=True, index=True)  # None = global/bootstrap
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_user_collection"),
    )


class _PgVector(PgBase):
    __tablename__ = "pg_vectors"

    id = Column(Integer, primary_key=True)
    collection_id = Column(Integer, nullable=False, index=True)
    user_id = Column(Integer, nullable=True, index=True)

    external_id = Column(String, nullable=False)
    embedding = Column(PgVector(1536), nullable=False)
    meta = Column(JSON, nullable=True)
    content = Column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint("collection_id", "external_id", name="uq_collection_external_id"),
    )


# pgvector operators return distances (lower = closer).
# We convert to scores (higher = better).
_PG_OPS = {
    "cosine": "<=>",   # cosine distance in [0, 2]
    "l2": "<->",       # Euclidean distance
    "ip": "<#>",       # negative inner product
}

_SCORE_FN = {
    "cosine": lambda d: float(1 - d),
    "l2": lambda d: float(1 / (1 + d)),
    "ip": lambda d: float(-d),  # pgvector stores negative inner product
}


def _to_async_pg_url(db_url: str) -> str:
    """Convert postgresql:// -> postgresql+asyncpg://"""
    for prefix in ("postgresql://", "postgres://"):
        if db_url.startswith(prefix):
            return "postgresql+asyncpg://" + db_url[len(prefix):]
    return db_url


class PostgresVectorBackend(VectorBackend):
    """PostgreSQL backend using a shared pg_vectors table."""

    def __init__(self, db_url: str, settings):
        self._settings = settings
        async_url = _to_async_pg_url(db_url)
        self._engine = create_async_engine(async_url, pool_pre_ping=True, pool_size=5)
        self._session_factory = async_sessionmaker(
            self._engine, class_=AsyncSession, expire_on_commit=False
        )

    async def startup(self) -> None:
        async with self._engine.begin() as conn:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            await conn.run_sync(PgBase.metadata.create_all)
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_pg_vectors_collection_id "
                "ON pg_vectors(collection_id)"
            ))
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_pg_vectors_user_id "
                "ON pg_vectors(user_id)"
            ))
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_pg_vectors_collection_user "
                "ON pg_vectors(collection_id, user_id)"
            ))
        logger.info("postgres_pgvector_backend_started")

    async def shutdown(self) -> None:
        await self._engine.dispose()
        logger.info("postgres_pgvector_backend_shutdown")

    async def create_collection(
        self, name: str, dim: int, distance_metric: str,
        description: Optional[str] = None, user_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        async with self._session_factory() as session:
            existing_stmt = select(_PgCollection).where(
                _PgCollection.name == name,
                _PgCollection.user_id == user_id,
            )
            existing = await session.execute(existing_stmt)
            if existing.scalar_one_or_none():
                raise CollectionAlreadyExistsError(name)

            col = _PgCollection(
                name=name,
                dim=dim,
                distance_metric=distance_metric,
                description=description,
                user_id=user_id,
            )
            session.add(col)
            await session.commit()
            await session.refresh(col)
            return self._col_dict(col, 0)

    async def get_collection(self, name: str, user_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        async with self._session_factory() as session:
            col = await self._resolve_collection_row(session, name, user_id)
            if not col:
                return None
            count = await self._vec_count(session, col.id)
            return self._col_dict(col, count)

    async def list_collections(self, user_id: Optional[int] = None) -> List[Dict[str, Any]]:
        async with self._session_factory() as session:
            stmt = select(_PgCollection)
            if user_id is not None:
                stmt = stmt.where(_PgCollection.user_id == user_id)
            result = await session.execute(stmt)
            cols = result.scalars().all()
            out: List[Dict[str, Any]] = []
            for col in cols:
                count = await self._vec_count(session, col.id)
                out.append(self._col_dict(col, count))
            return out

    async def delete_collection(self, name: str, user_id: Optional[int] = None) -> None:
        async with self._session_factory() as session:
            col = await self._require_collection_row(session, name, user_id)
            await session.execute(
                _PgVector.__table__.delete().where(_PgVector.collection_id == col.id)
            )
            await session.delete(col)
            await session.commit()
        logger.info("pg_collection_deleted", name=name)

    async def update_collection(
        self, name: str, description: Optional[str], user_id: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        async with self._session_factory() as session:
            col = await self._resolve_collection_row(session, name, user_id)
            if not col:
                return None
            col.description = description
            await session.commit()
            await session.refresh(col)
            count = await self._vec_count(session, col.id)
            return self._col_dict(col, count)

    async def count_vectors(
        self, collection_name: str, filters: Optional[Dict[str, Any]] = None,
        user_id: Optional[int] = None,
    ) -> int:
        async with self._session_factory() as session:
            col = await self._require_collection_row(session, collection_name, user_id)
            if not filters:
                return await self._vec_count(session, col.id)

            stmt = select(func.count()).select_from(_PgVector).where(
                _PgVector.collection_id == col.id
            )
            for key, val in filters.items():
                if isinstance(val, str):
                    stmt = stmt.where(_PgVector.meta[key].astext == val)
                else:
                    stmt = stmt.where(_PgVector.meta[key].astext == str(val))

            result = await session.execute(stmt)
            return result.scalar() or 0

    async def export_vectors(
        self, collection_name: str, limit: int = 10000, user_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        async with self._session_factory() as session:
            col = await self._require_collection_row(session, collection_name, user_id)
            result = await session.execute(
                select(_PgVector.external_id, _PgVector.embedding, _PgVector.meta)
                .where(_PgVector.collection_id == col.id)
                .order_by(_PgVector.id)
                .limit(limit)
            )
            rows = result.fetchall()

        return [
            {
                "external_id": r.external_id,
                "vector": list(r.embedding) if r.embedding is not None else [],
                "metadata": r.meta or {},
            }
            for r in rows
        ]

    async def upsert(
        self,
        collection_name: str,
        external_id: str,
        vector: List[float],
        metadata: Optional[Dict[str, Any]],
        content: Optional[str],
        user_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        async with self._session_factory() as session:
            col = await self._require_collection_row(session, collection_name, user_id)
            if len(vector) != col.dim:
                raise DimensionMismatchError(col.dim, len(vector))

            vec_np = normalize_vector(np.array(vector, dtype=np.float32))
            existing = await session.execute(
                select(_PgVector).where(
                    _PgVector.collection_id == col.id,
                    _PgVector.external_id == external_id,
                )
            )
            row = existing.scalar_one_or_none()
            if row:
                row.embedding = vec_np.tolist()
                row.meta = metadata if metadata is not None else row.meta
                if content is not None:
                    row.content = content
                await session.commit()
                return {"external_id": external_id, "status": "updated"}

            session.add(_PgVector(
                collection_id=col.id,
                user_id=col.user_id,
                external_id=external_id,
                embedding=vec_np.tolist(),
                meta=metadata or {},
                content=content,
            ))
            await session.commit()
            return {"external_id": external_id, "status": "inserted"}

    async def bulk_upsert(
        self, collection_name: str, items: List[Dict[str, Any]], user_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        async with self._session_factory() as session:
            col = await self._require_collection_row(session, collection_name, user_id)
            for it in items:
                if len(it["vector"]) != col.dim:
                    raise DimensionMismatchError(col.dim, len(it["vector"]))

            results = []
            for it in items:
                vec_np = normalize_vector(np.array(it["vector"], dtype=np.float32))
                ext_id = it["external_id"]
                existing = await session.execute(
                    select(_PgVector).where(
                        _PgVector.collection_id == col.id,
                        _PgVector.external_id == ext_id,
                    )
                )
                row = existing.scalar_one_or_none()
                if row:
                    row.embedding = vec_np.tolist()
                    row.meta = it.get("metadata") or row.meta
                    if it.get("content") is not None:
                        row.content = it["content"]
                    results.append({"external_id": ext_id, "status": "updated"})
                else:
                    session.add(_PgVector(
                        collection_id=col.id,
                        user_id=col.user_id,
                        external_id=ext_id,
                        embedding=vec_np.tolist(),
                        meta=it.get("metadata") or {},
                        content=it.get("content"),
                    ))
                    results.append({"external_id": ext_id, "status": "inserted"})
            await session.commit()
            return results

    async def delete_vector(
        self, collection_name: str, external_id: str, user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        async with self._session_factory() as session:
            col = await self._require_collection_row(session, collection_name, user_id)
            existing = await session.execute(
                select(_PgVector).where(
                    _PgVector.collection_id == col.id,
                    _PgVector.external_id == external_id,
                )
            )
            row = existing.scalar_one_or_none()
            if not row:
                raise VectorNotFoundError(external_id)
            await session.delete(row)
            await session.commit()
            return {"status": "deleted", "external_id": external_id}

    async def batch_delete(
        self, collection_name: str, external_ids: List[str], user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        async with self._session_factory() as session:
            col = await self._require_collection_row(session, collection_name, user_id)
            deleted = []
            not_found = []
            for eid in external_ids:
                existing = await session.execute(
                    select(_PgVector).where(
                        _PgVector.collection_id == col.id,
                        _PgVector.external_id == eid,
                    )
                )
                row = existing.scalar_one_or_none()
                if not row:
                    not_found.append(eid)
                else:
                    await session.delete(row)
                    deleted.append(eid)
            await session.commit()
            return {"deleted": deleted, "not_found": not_found, "deleted_count": len(deleted)}

    async def search(
        self,
        collection_name: str,
        vector: List[float],
        k: int,
        offset: int,
        filters: Optional[Dict[str, Any]],
        user_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        async with self._session_factory() as session:
            col = await self._require_collection_row(session, collection_name, user_id)
            if len(vector) != col.dim:
                raise DimensionMismatchError(col.dim, len(vector))

            vec_np = normalize_vector(np.array(vector, dtype=np.float32))
            op = _PG_OPS.get(col.distance_metric, "<=>")
            score_fn = _SCORE_FN.get(col.distance_metric, lambda d: float(1 - d))

            stmt = (
                select(_PgVector.external_id, _PgVector.meta, text(f"embedding {op} CAST(:vec AS vector) AS _dist"))
                .where(_PgVector.collection_id == col.id)
                .order_by(text(f"embedding {op} CAST(:vec AS vector)"))
                .limit(k + offset)
            )
            if filters:
                for key, val in filters.items():
                    if isinstance(val, str):
                        stmt = stmt.where(_PgVector.meta[key].astext == val)
                    else:
                        stmt = stmt.where(_PgVector.meta[key].astext == str(val))

            result = await session.execute(stmt, {"vec": vec_np.tolist()})
            rows = result.fetchall()

        return [
            {"external_id": r.external_id, "score": score_fn(r._dist), "metadata": r.meta}
            for r in rows[offset: offset + k]
        ]

    async def recommend(
        self, collection_name: str, external_id: str, k: int, ef: int, user_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        async with self._session_factory() as session:
            col = await self._require_collection_row(session, collection_name, user_id)
            op = _PG_OPS.get(col.distance_metric, "<=>")
            score_fn = _SCORE_FN.get(col.distance_metric, lambda d: float(1 - d))

            res = await session.execute(
                select(_PgVector.embedding).where(
                    _PgVector.collection_id == col.id,
                    _PgVector.external_id == external_id,
                )
            )
            row = res.fetchone()
            if not row:
                raise VectorNotFoundError(external_id)

            vec = row.embedding
            stmt = (
                select(_PgVector.external_id, _PgVector.meta, text(f"embedding {op} CAST(:vec AS vector) AS _dist"))
                .where(_PgVector.collection_id == col.id)
                .where(_PgVector.external_id != external_id)
                .order_by(text(f"embedding {op} CAST(:vec AS vector)"))
                .limit(k)
            )
            result = await session.execute(stmt, {"vec": vec})
            rows = result.fetchall()

        return [
            {"external_id": r.external_id, "score": score_fn(r._dist), "metadata": r.meta}
            for r in rows
        ]

    async def similarity(
        self, collection_name: str, id1: str, id2: str, user_id: Optional[int] = None
    ) -> float:
        async with self._session_factory() as session:
            col = await self._require_collection_row(session, collection_name, user_id)
            r1 = await session.execute(
                select(_PgVector.embedding).where(
                    _PgVector.collection_id == col.id,
                    _PgVector.external_id == id1,
                )
            )
            r2 = await session.execute(
                select(_PgVector.embedding).where(
                    _PgVector.collection_id == col.id,
                    _PgVector.external_id == id2,
                )
            )
            v1 = r1.fetchone()
            v2 = r2.fetchone()
            if not v1 or not v2:
                raise VectorNotFoundError(id1 if not v1 else id2)

            vec1 = normalize_vector(np.array(v1.embedding, dtype=np.float32))
            vec2 = normalize_vector(np.array(v2.embedding, dtype=np.float32))
            return float(np.dot(vec1, vec2))

    async def rerank(
        self,
        collection_name: str,
        query_vector: List[float],
        candidates: List[str],
        user_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        async with self._session_factory() as session:
            col = await self._require_collection_row(session, collection_name, user_id)
            if len(query_vector) != col.dim:
                raise DimensionMismatchError(col.dim, len(query_vector))

            qv = normalize_vector(np.array(query_vector, dtype=np.float32))
            result = await session.execute(
                select(_PgVector.external_id, _PgVector.embedding, _PgVector.meta)
                .where(_PgVector.collection_id == col.id)
                .where(_PgVector.external_id.in_(candidates))
            )
            rows = result.fetchall()

        results = []
        for r in rows:
            cvec = normalize_vector(np.array(r.embedding, dtype=np.float32))
            score = float(np.dot(qv, cvec))
            results.append({"external_id": r.external_id, "score": score, "metadata": r.meta})
        results.sort(key=lambda x: -x["score"])
        return results

    async def hybrid_search(
        self,
        collection_name: str,
        query_text: str,
        vector: List[float],
        k: int,
        offset: int,
        alpha: float,
        filters: Optional[Dict[str, Any]],
        user_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        async with self._session_factory() as session:
            col = await self._require_collection_row(session, collection_name, user_id)
            if len(vector) != col.dim:
                raise DimensionMismatchError(col.dim, len(vector))

            vec_np = normalize_vector(np.array(vector, dtype=np.float32))
            op = _PG_OPS.get(col.distance_metric, "<=>")
            score_fn = _SCORE_FN.get(col.distance_metric, lambda d: float(1 - d))

            vec_stmt = (
                select(_PgVector.external_id, _PgVector.meta, text(f"embedding {op} CAST(:vec AS vector) AS _dist"))
                .where(_PgVector.collection_id == col.id)
                .order_by(text(f"embedding {op} CAST(:vec AS vector)"))
                .limit((k + offset) * 3)
            )
            if filters:
                for key, val in filters.items():
                    if isinstance(val, str):
                        vec_stmt = vec_stmt.where(_PgVector.meta[key].astext == val)
                    else:
                        vec_stmt = vec_stmt.where(_PgVector.meta[key].astext == str(val))

            vr = await session.execute(vec_stmt, {"vec": vec_np.tolist()})
            vector_results = {
                r.external_id: {"score": score_fn(r._dist), "metadata": r.meta}
                for r in vr.fetchall()
            }

            text_results: Dict[str, Any] = {}
            query_words = query_text.lower().split()
            if query_words:
                tr_stmt = (
                    select(_PgVector.external_id, _PgVector.content, _PgVector.meta)
                    .where(_PgVector.collection_id == col.id)
                    .where(_PgVector.content.isnot(None))
                )
                if filters:
                    for key, val in filters.items():
                        if isinstance(val, str):
                            tr_stmt = tr_stmt.where(_PgVector.meta[key].astext == val)
                        else:
                            tr_stmt = tr_stmt.where(_PgVector.meta[key].astext == str(val))

                tr = await session.execute(tr_stmt)
                for row in tr.fetchall():
                    content_lower = (row.content or "").lower()
                    matches = sum(1 for w in query_words if w in content_lower)
                    if matches > 0:
                        text_results[row.external_id] = {
                            "score": matches / len(query_words),
                            "metadata": row.meta,
                        }

        rrf_k = 60
        all_ids = set(vector_results) | set(text_results)
        vec_ranked = sorted(vector_results, key=lambda x: -vector_results[x]["score"])
        text_ranked = sorted(text_results, key=lambda x: -text_results[x]["score"])
        vec_rank = {eid: r + 1 for r, eid in enumerate(vec_ranked)}
        text_rank = {eid: r + 1 for r, eid in enumerate(text_ranked)}

        merged = []
        for eid in all_ids:
            vr_s = alpha * (1.0 / (rrf_k + vec_rank[eid])) if eid in vec_rank else 0.0
            tr_s = (1 - alpha) * (1.0 / (rrf_k + text_rank[eid])) if eid in text_rank else 0.0
            meta = vector_results.get(eid, text_results.get(eid, {})).get("metadata")
            merged.append({
                "external_id": eid,
                "score": round(vr_s + tr_s, 6),
                "metadata": meta,
                "vector_score": vector_results.get(eid, {}).get("score"),
                "text_score": text_results.get(eid, {}).get("score"),
            })
        merged.sort(key=lambda x: -x["score"])
        return merged[offset: offset + k]

    async def get_vector(
        self, collection_name: str, external_id: str, user_id: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        async with self._session_factory() as session:
            col = await self._require_collection_row(session, collection_name, user_id)
            result = await session.execute(
                select(_PgVector).where(
                    _PgVector.collection_id == col.id,
                    _PgVector.external_id == external_id,
                )
            )
            row = result.scalar_one_or_none()
            if not row:
                return None
            return {
                "external_id": row.external_id,
                "metadata": row.meta,
                "vector": list(row.embedding) if row.embedding is not None else [],
                "content": row.content,
            }

    async def batch_get_vectors(
        self, collection_name: str, ids: List[str],
        include_vectors: bool = True, user_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        async with self._session_factory() as session:
            col = await self._require_collection_row(session, collection_name, user_id)
            if include_vectors:
                result = await session.execute(
                    select(_PgVector).where(
                        _PgVector.collection_id == col.id,
                        _PgVector.external_id.in_(ids),
                    )
                )
                rows = result.scalars().all()
                rows_by_eid = {r.external_id: r for r in rows}
            else:
                result = await session.execute(
                    select(_PgVector.external_id, _PgVector.meta, _PgVector.content).where(
                        _PgVector.collection_id == col.id,
                        _PgVector.external_id.in_(ids),
                    )
                )
                rows_by_eid = {r.external_id: r for r in result.fetchall()}

        out = []
        for eid in ids:
            row = rows_by_eid.get(eid)
            if not row:
                continue
            item = {
                "external_id": row.external_id,
                "metadata": row.meta,
                "content": row.content,
            }
            if include_vectors:
                item["vector"] = list(row.embedding) if row.embedding is not None else []
            out.append(item)
        return out

    async def scroll(
        self, collection_name: str, cursor: Optional[int] = None,
        limit: int = 100, filters: Optional[Dict[str, Any]] = None,
        include_vectors: bool = True, user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        async with self._session_factory() as session:
            col = await self._require_collection_row(session, collection_name, user_id)
            start_id = cursor if cursor is not None else 0
            max_scan = limit * 5

            collected = []
            scanned = 0
            current_cursor = start_id

            while len(collected) < limit and scanned < max_scan:
                fetch_size = (limit - len(collected)) * 2 if filters else limit - len(collected) + 1
                fetch_size = min(fetch_size, max_scan - scanned)
                if fetch_size <= 0:
                    break

                if include_vectors:
                    stmt = (
                        select(_PgVector)
                        .where(_PgVector.collection_id == col.id)
                        .where(_PgVector.id > current_cursor)
                        .order_by(_PgVector.id)
                        .limit(fetch_size)
                    )
                    result = await session.execute(stmt)
                    rows = result.scalars().all()
                else:
                    stmt = (
                        select(_PgVector.id, _PgVector.external_id, _PgVector.meta, _PgVector.content)
                        .where(_PgVector.collection_id == col.id)
                        .where(_PgVector.id > current_cursor)
                        .order_by(_PgVector.id)
                        .limit(fetch_size)
                    )
                    result = await session.execute(stmt)
                    rows = result.fetchall()

                if not rows:
                    break

                scanned += len(rows)
                for row in rows:
                    current_cursor = row.id
                    if filters and not self._meta_matches(row.meta, filters):
                        continue
                    item = {
                        "external_id": row.external_id,
                        "metadata": row.meta,
                        "content": row.content,
                    }
                    if include_vectors:
                        item["vector"] = list(row.embedding) if row.embedding is not None else []
                    collected.append((row.id, item))
                    if len(collected) >= limit + 1:
                        break

            if len(collected) > limit:
                vectors_out = [item for _, item in collected[:limit]]
                next_cursor_id = collected[limit - 1][0]
            elif len(collected) == limit:
                check = await session.execute(
                    select(_PgVector.id)
                    .where(_PgVector.collection_id == col.id)
                    .where(_PgVector.id > current_cursor)
                    .limit(1)
                )
                has_more = check.fetchone() is not None
                vectors_out = [item for _, item in collected]
                next_cursor_id = collected[-1][0] if has_more else None
            else:
                vectors_out = [item for _, item in collected]
                next_cursor_id = None

            import base64
            next_cursor = base64.b64encode(str(next_cursor_id).encode()).decode() if next_cursor_id else None
            return {"vectors": vectors_out, "next_cursor": next_cursor}

    async def health_stats(self) -> Dict[str, Any]:
        async with self._session_factory() as session:
            result = await session.execute(select(_PgCollection))
            collections = result.scalars().all()
            total_vectors = 0
            col_stats = []
            for col in collections:
                count = await self._vec_count(session, col.id)
                total_vectors += count
                col_stats.append({
                    "name": col.name,
                    "dim": col.dim,
                    "distance_metric": col.distance_metric,
                    "vector_count": count,
                    "index_size": count,
                })
            return {
                "total_vectors": total_vectors,
                "total_collections": len(collections),
                "collections": col_stats,
            }

    async def _resolve_collection_row(
        self, session: AsyncSession, name: str, user_id: Optional[int]
    ) -> Optional[_PgCollection]:
        stmt = select(_PgCollection).where(_PgCollection.name == name)
        if user_id is not None:
            stmt = stmt.where(_PgCollection.user_id == user_id)

        result = await session.execute(stmt)
        rows = result.scalars().all()
        if len(rows) == 1:
            return rows[0]
        if len(rows) == 0:
            return None
        return None

    async def _require_collection_row(
        self, session: AsyncSession, name: str, user_id: Optional[int]
    ) -> _PgCollection:
        col = await self._resolve_collection_row(session, name, user_id)
        if not col:
            raise CollectionNotFoundError(name)
        return col

    async def _vec_count(self, session: AsyncSession, collection_id: int) -> int:
        result = await session.execute(
            select(func.count()).select_from(_PgVector).where(_PgVector.collection_id == collection_id)
        )
        return result.scalar() or 0

    async def _lookup_collection_id(self, name: str, user_id: Optional[int]) -> Optional[int]:
        async with self._session_factory() as session:
            col = await self._resolve_collection_row(session, name, user_id)
            return col.id if col else None

    @staticmethod
    def _meta_matches(meta: Optional[dict], filters: dict) -> bool:
        if not meta:
            return False
        return all(meta.get(k) == v for k, v in filters.items())

    @staticmethod
    def _col_dict(col: _PgCollection, vec_count: int) -> Dict[str, Any]:
        return {
            "name": col.name,
            "dim": col.dim,
            "distance_metric": col.distance_metric,
            "description": col.description,
            "user_id": col.user_id,
            "vector_count": vec_count,
            "created_at": str(col.created_at),
        }


def normalize_vector(vec: np.ndarray) -> np.ndarray:
    return vec / (np.linalg.norm(vec) + 1e-10)
