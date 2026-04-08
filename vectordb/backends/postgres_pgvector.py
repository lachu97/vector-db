# vectordb/backends/postgres_pgvector.py
"""
PostgreSQL + pgvector backend.

Each collection gets its own table: vectors_{collection_name}
with a native pgvector Vector(dim) column and an HNSW index.
The collections registry table is shared.

Requires:
  pip install asyncpg pgvector
  DB_URL=postgresql://user:pass@host/db
  CREATE EXTENSION IF NOT EXISTS vector;  -- run once in your PostgreSQL DB
"""
from typing import Any, Dict, List, Optional

import numpy as np
import structlog
from pgvector.sqlalchemy import Vector as PgVector
from sqlalchemy import (
    Boolean, Column, DateTime, Integer, JSON, MetaData, String, Table,
    Text, UniqueConstraint, func, select, text,
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


# ---------------------------------------------------------------------------
# Collections registry table
# ---------------------------------------------------------------------------

class _PgCollection(PgBase):
    __tablename__ = "pg_collections"
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False, index=True)
    dim = Column(Integer, nullable=False)
    distance_metric = Column(String, nullable=False, default="cosine")
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())


# ---------------------------------------------------------------------------
# Distance helpers
# ---------------------------------------------------------------------------

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

_PG_INDEX_OPS = {
    "cosine": "vector_cosine_ops",
    "l2": "vector_l2_ops",
    "ip": "vector_ip_ops",
}


def _to_async_pg_url(db_url: str) -> str:
    """Convert postgresql:// → postgresql+asyncpg://"""
    for prefix in ("postgresql://", "postgres://"):
        if db_url.startswith(prefix):
            return "postgresql+asyncpg://" + db_url[len(prefix):]
    return db_url


# ---------------------------------------------------------------------------
# Backend implementation
# ---------------------------------------------------------------------------

class PostgresVectorBackend(VectorBackend):
    """
    PostgreSQL backend using pgvector for native vector similarity search.

    Vector search uses pgvector's HNSW index for ANN queries. Each collection
    has its own table (vectors_{name}) so the vector dimension is fixed at
    the column level, which pgvector requires for indexing.
    """

    def __init__(self, db_url: str, settings):
        self._settings = settings
        async_url = _to_async_pg_url(db_url)
        self._engine = create_async_engine(async_url, pool_pre_ping=True, pool_size=5)
        self._session_factory = async_sessionmaker(
            self._engine, class_=AsyncSession, expire_on_commit=False
        )
        # Shared metadata for dynamic table definitions
        self._metadata = MetaData()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def startup(self) -> None:
        async with self._engine.begin() as conn:
            # Ensure pgvector extension exists
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            # Create the collections registry table
            await conn.run_sync(PgBase.metadata.create_all)

        # Pre-create vector tables for any existing collections
        async with self._session_factory() as session:
            result = await session.execute(select(_PgCollection))
            for col in result.scalars().all():
                self._ensure_vector_table(col.name, col.dim)
                async with self._engine.begin() as conn:
                    await conn.run_sync(self._metadata.create_all)
        logger.info("postgres_pgvector_backend_started")

    async def shutdown(self) -> None:
        await self._engine.dispose()
        logger.info("postgres_pgvector_backend_shutdown")

    # ------------------------------------------------------------------
    # Collections
    # ------------------------------------------------------------------

    async def create_collection(
        self, name: str, dim: int, distance_metric: str, description: Optional[str] = None
    ) -> Dict[str, Any]:
        async with self._session_factory() as session:
            existing = await session.execute(
                select(_PgCollection).where(_PgCollection.name == name)
            )
            if existing.scalar_one_or_none():
                raise CollectionAlreadyExistsError(name)
            col = _PgCollection(name=name, dim=dim, distance_metric=distance_metric, description=description)
            session.add(col)
            await session.commit()
            await session.refresh(col)

        # Create the per-collection vector table + HNSW index
        vt = self._ensure_vector_table(name, dim)
        idx_ops = _PG_INDEX_OPS.get(distance_metric, "vector_cosine_ops")
        async with self._engine.begin() as conn:
            await conn.run_sync(self._metadata.create_all)
            # Create HNSW index
            m = self._settings.m
            ef = self._settings.ef_construction
            await conn.execute(text(
                f"CREATE INDEX IF NOT EXISTS idx_{name}_hnsw "
                f"ON vectors_{name} USING hnsw (embedding {idx_ops}) "
                f"WITH (m = {m}, ef_construction = {ef})"
            ))

        logger.info("pg_collection_created", name=name, dim=dim, metric=distance_metric)
        return self._col_dict(col, 0)

    async def get_collection(self, name: str) -> Optional[Dict[str, Any]]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(_PgCollection).where(_PgCollection.name == name)
            )
            col = result.scalar_one_or_none()
            if not col:
                return None
            count = await self._vec_count(session, name)
            return self._col_dict(col, count)

    async def list_collections(self) -> List[Dict[str, Any]]:
        async with self._session_factory() as session:
            result = await session.execute(select(_PgCollection))
            cols = result.scalars().all()
            out = []
            for col in cols:
                count = await self._vec_count(session, col.name)
                out.append(self._col_dict(col, count))
            return out

    async def delete_collection(self, name: str) -> None:
        async with self._session_factory() as session:
            result = await session.execute(
                select(_PgCollection).where(_PgCollection.name == name)
            )
            col = result.scalar_one_or_none()
            if not col:
                raise CollectionNotFoundError(name)
            await session.delete(col)
            await session.commit()

        # Drop the per-collection vector table
        vt = self._metadata.tables.get(f"vectors_{name}")
        if vt is not None:
            async with self._engine.begin() as conn:
                await conn.run_sync(vt.drop)
            self._metadata.remove(vt)
        logger.info("pg_collection_deleted", name=name)

    async def update_collection(self, name: str, description: Optional[str]) -> Optional[Dict[str, Any]]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(_PgCollection).where(_PgCollection.name == name)
            )
            col = result.scalar_one_or_none()
            if not col:
                return None
            col.description = description
            await session.commit()
            await session.refresh(col)
            count = await self._vec_count(session, name)
            return self._col_dict(col, count)

    async def count_vectors(
        self, collection_name: str, filters: Optional[Dict[str, Any]] = None
    ) -> int:
        async with self._session_factory() as session:
            return await self._vec_count(session, collection_name)

    async def export_vectors(
        self, collection_name: str, limit: int = 10000
    ) -> List[Dict[str, Any]]:
        col = await self._require_collection_row(collection_name)
        vt = self._ensure_vector_table(collection_name, col.dim)

        async with self._engine.connect() as conn:
            result = await conn.execute(
                select(vt.c.external_id, vt.c.embedding, vt.c.meta)
                .order_by(vt.c.id)
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

    # ------------------------------------------------------------------
    # Vectors
    # ------------------------------------------------------------------

    async def upsert(
        self,
        collection_name: str,
        external_id: str,
        vector: List[float],
        metadata: Optional[Dict[str, Any]],
        content: Optional[str],
    ) -> Dict[str, Any]:
        col = await self._require_collection_row(collection_name)
        if len(vector) != col.dim:
            raise DimensionMismatchError(col.dim, len(vector))

        vt = self._ensure_vector_table(collection_name, col.dim)
        vec_np = normalize_vector(np.array(vector, dtype=np.float32))

        async with self._engine.begin() as conn:
            existing = await conn.execute(
                select(vt).where(vt.c.external_id == external_id)
            )
            row = existing.fetchone()
            if row:
                await conn.execute(
                    vt.update()
                    .where(vt.c.external_id == external_id)
                    .values(
                        embedding=vec_np.tolist(),
                        meta=metadata if metadata is not None else row.meta,
                        content=content if content is not None else row.content,
                    )
                )
                return {"external_id": external_id, "status": "updated"}
            else:
                await conn.execute(
                    vt.insert().values(
                        external_id=external_id,
                        embedding=vec_np.tolist(),
                        meta=metadata or {},
                        content=content,
                    )
                )
                return {"external_id": external_id, "status": "inserted"}

    async def bulk_upsert(
        self, collection_name: str, items: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        col = await self._require_collection_row(collection_name)
        for it in items:
            if len(it["vector"]) != col.dim:
                raise DimensionMismatchError(col.dim, len(it["vector"]))

        vt = self._ensure_vector_table(collection_name, col.dim)
        results = []

        async with self._engine.begin() as conn:
            for it in items:
                vec_np = normalize_vector(np.array(it["vector"], dtype=np.float32))
                ext_id = it["external_id"]

                existing = await conn.execute(
                    select(vt).where(vt.c.external_id == ext_id)
                )
                row = existing.fetchone()
                if row:
                    await conn.execute(
                        vt.update()
                        .where(vt.c.external_id == ext_id)
                        .values(
                            embedding=vec_np.tolist(),
                            meta=it.get("metadata") or row.meta,
                            content=it["content"] if it.get("content") is not None else row.content,
                        )
                    )
                    results.append({"external_id": ext_id, "status": "updated"})
                else:
                    await conn.execute(
                        vt.insert().values(
                            external_id=ext_id,
                            embedding=vec_np.tolist(),
                            meta=it.get("metadata") or {},
                            content=it.get("content"),
                        )
                    )
                    results.append({"external_id": ext_id, "status": "inserted"})

        return results

    async def delete_vector(self, collection_name: str, external_id: str) -> Dict[str, Any]:
        col = await self._require_collection_row(collection_name)
        vt = self._ensure_vector_table(collection_name, col.dim)

        async with self._engine.begin() as conn:
            existing = await conn.execute(select(vt).where(vt.c.external_id == external_id))
            if not existing.fetchone():
                raise VectorNotFoundError(external_id)
            await conn.execute(vt.delete().where(vt.c.external_id == external_id))

        return {"status": "deleted", "external_id": external_id}

    async def batch_delete(
        self, collection_name: str, external_ids: List[str]
    ) -> Dict[str, Any]:
        col = await self._require_collection_row(collection_name)
        vt = self._ensure_vector_table(collection_name, col.dim)
        deleted = []
        not_found = []

        async with self._engine.begin() as conn:
            for eid in external_ids:
                existing = await conn.execute(select(vt).where(vt.c.external_id == eid))
                if not existing.fetchone():
                    not_found.append(eid)
                else:
                    await conn.execute(vt.delete().where(vt.c.external_id == eid))
                    deleted.append(eid)

        return {"deleted": deleted, "not_found": not_found, "deleted_count": len(deleted)}

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    async def search(
        self,
        collection_name: str,
        vector: List[float],
        k: int,
        offset: int,
        filters: Optional[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        col = await self._require_collection_row(collection_name)
        if len(vector) != col.dim:
            raise DimensionMismatchError(col.dim, len(vector))

        vt = self._ensure_vector_table(collection_name, col.dim)
        vec_np = normalize_vector(np.array(vector, dtype=np.float32))
        op = _PG_OPS.get(col.distance_metric, "<=>")
        score_fn = _SCORE_FN.get(col.distance_metric, lambda d: float(1 - d))
        to_score = score_fn

        async with self._engine.connect() as conn:
            distance_expr = text(f"embedding {op} CAST(:vec AS vector) AS _dist")
            stmt = (
                select(vt.c.external_id, vt.c.meta, text(f"embedding {op} CAST(:vec AS vector) AS _dist"))
                .order_by(text(f"embedding {op} CAST(:vec AS vector)"))
                .limit(k + offset)
            )
            if filters:
                # Apply metadata filters server-side via JSON containment
                for key, val in filters.items():
                    if isinstance(val, str):
                        stmt = stmt.where(
                            vt.c.meta[key].astext == val
                        )
                    else:
                        stmt = stmt.where(vt.c.meta[key].astext == str(val))

            result = await conn.execute(stmt, {"vec": vec_np.tolist()})
            rows = result.fetchall()

        out = [
            {"external_id": r.external_id, "score": to_score(r._dist), "metadata": r.meta}
            for r in rows[offset: offset + k]
        ]
        return out

    async def recommend(
        self, collection_name: str, external_id: str, k: int, ef: int
    ) -> List[Dict[str, Any]]:
        col = await self._require_collection_row(collection_name)
        vt = self._ensure_vector_table(collection_name, col.dim)
        op = _PG_OPS.get(col.distance_metric, "<=>")
        score_fn = _SCORE_FN.get(col.distance_metric, lambda d: float(1 - d))

        async with self._engine.connect() as conn:
            res = await conn.execute(
                select(vt.c.embedding).where(vt.c.external_id == external_id)
            )
            row = res.fetchone()
            if not row:
                raise VectorNotFoundError(external_id)

            vec = row.embedding
            stmt = (
                select(vt.c.external_id, vt.c.meta,
                       text(f"embedding {op} CAST(:vec AS vector) AS _dist"))
                .where(vt.c.external_id != external_id)
                .order_by(text(f"embedding {op} CAST(:vec AS vector)"))
                .limit(k)
            )
            result = await conn.execute(stmt, {"vec": vec})
            rows = result.fetchall()

        return [
            {"external_id": r.external_id, "score": score_fn(r._dist), "metadata": r.meta}
            for r in rows
        ]

    async def similarity(self, collection_name: str, id1: str, id2: str) -> float:
        col = await self._require_collection_row(collection_name)
        vt = self._ensure_vector_table(collection_name, col.dim)

        async with self._engine.connect() as conn:
            r1 = await conn.execute(select(vt.c.embedding).where(vt.c.external_id == id1))
            r2 = await conn.execute(select(vt.c.embedding).where(vt.c.external_id == id2))
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
    ) -> List[Dict[str, Any]]:
        col = await self._require_collection_row(collection_name)
        if len(query_vector) != col.dim:
            raise DimensionMismatchError(col.dim, len(query_vector))

        vt = self._ensure_vector_table(collection_name, col.dim)
        qv = normalize_vector(np.array(query_vector, dtype=np.float32))

        async with self._engine.connect() as conn:
            result = await conn.execute(
                select(vt.c.external_id, vt.c.embedding, vt.c.meta)
                .where(vt.c.external_id.in_(candidates))
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
    ) -> List[Dict[str, Any]]:
        col = await self._require_collection_row(collection_name)
        if len(vector) != col.dim:
            raise DimensionMismatchError(col.dim, len(vector))

        vt = self._ensure_vector_table(collection_name, col.dim)
        vec_np = normalize_vector(np.array(vector, dtype=np.float32))
        op = _PG_OPS.get(col.distance_metric, "<=>")
        score_fn = _SCORE_FN.get(col.distance_metric, lambda d: float(1 - d))

        async with self._engine.connect() as conn:
            # Vector results
            vec_stmt = (
                select(vt.c.external_id, vt.c.meta,
                       text(f"embedding {op} CAST(:vec AS vector) AS _dist"))
                .order_by(text(f"embedding {op} CAST(:vec AS vector)"))
                .limit((k + offset) * 3)
            )
            vr = await conn.execute(vec_stmt, {"vec": vec_np.tolist()})
            vector_results = {
                r.external_id: {"score": score_fn(r._dist), "metadata": r.meta}
                for r in vr.fetchall()
                if not filters or self._meta_matches(r.meta, filters)
            }

            # Text results
            text_results: Dict[str, Any] = {}
            query_words = query_text.lower().split()
            if query_words:
                tr = await conn.execute(
                    select(vt.c.external_id, vt.c.content, vt.c.meta)
                    .where(vt.c.content.isnot(None))
                )
                for row in tr.fetchall():
                    if filters and not self._meta_matches(row.meta, filters):
                        continue
                    content_lower = (row.content or "").lower()
                    matches = sum(1 for w in query_words if w in content_lower)
                    if matches > 0:
                        text_results[row.external_id] = {
                            "score": matches / len(query_words),
                            "metadata": row.meta,
                        }

        # RRF
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

    # ------------------------------------------------------------------
    # Observability
    # ------------------------------------------------------------------

    async def health_stats(self) -> Dict[str, Any]:
        async with self._session_factory() as session:
            result = await session.execute(select(_PgCollection))
            collections = result.scalars().all()
            total_vectors = 0
            col_stats = []
            for col in collections:
                count = await self._vec_count(session, col.name)
                total_vectors += count
                col_stats.append({
                    "name": col.name,
                    "dim": col.dim,
                    "distance_metric": col.distance_metric,
                    "vector_count": count,
                    "index_size": count,  # pgvector index is always in sync
                })
            return {
                "total_vectors": total_vectors,
                "total_collections": len(collections),
                "collections": col_stats,
            }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_vector_table(self, name: str, dim: int) -> Table:
        """Return (and register) the SQLAlchemy Table for a collection."""
        table_name = f"vectors_{name}"
        if table_name in self._metadata.tables:
            return self._metadata.tables[table_name]
        return Table(
            table_name,
            self._metadata,
            Column("id", Integer, primary_key=True, autoincrement=True),
            Column("external_id", String, nullable=False, unique=True, index=True),
            Column("embedding", PgVector(dim), nullable=False),
            Column("meta", JSON, nullable=True),
            Column("content", Text, nullable=True),
        )

    async def _require_collection_row(self, name: str) -> _PgCollection:
        async with self._session_factory() as session:
            result = await session.execute(
                select(_PgCollection).where(_PgCollection.name == name)
            )
            col = result.scalar_one_or_none()
            if not col:
                raise CollectionNotFoundError(name)
            return col

    async def _vec_count(self, session: AsyncSession, collection_name: str) -> int:
        vt = self._metadata.tables.get(f"vectors_{collection_name}")
        if vt is None:
            return 0
        from sqlalchemy import func as sa_func
        result = await session.execute(select(sa_func.count()).select_from(vt))
        return result.scalar() or 0

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
            "vector_count": vec_count,
            "created_at": str(col.created_at),
        }


def normalize_vector(vec: np.ndarray) -> np.ndarray:
    return vec / (np.linalg.norm(vec) + 1e-10)
