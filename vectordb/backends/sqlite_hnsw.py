# vectordb/backends/sqlite_hnsw.py
"""
SQLite + HNSWlib backend (default).

Uses async SQLAlchemy with the aiosqlite driver so the event loop is never
blocked on DB I/O. HNSWlib operations (add, query) are kept synchronous
because they are CPU-bound in-process operations (typically <5 ms) that do
not benefit from async.
"""
from typing import Any, Dict, List, Optional

import numpy as np
import structlog
from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Integer, JSON,
    LargeBinary, String, Text, UniqueConstraint, event, func, select,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base, relationship

from vectordb.backends.base import (
    VectorBackend,
    CollectionAlreadyExistsError,
    CollectionNotFoundError,
    DimensionMismatchError,
    VectorNotFoundError,
)
from vectordb.indexing.manager import IndexManager
from vectordb.services.vector_service import (
    decode_vector,
    encode_vector,
    normalize_vector,
    safe_add_to_index,
)

logger = structlog.get_logger(__name__)

# Shared ORM base for this backend
Base = declarative_base()

FILTER_OVERSAMPLE = 10


# ---------------------------------------------------------------------------
# ORM Models (mirrored from models/db.py but on their own Base so they
# work with the async engine without conflicting with the sync auth engine)
# ---------------------------------------------------------------------------

class _Collection(Base):
    __tablename__ = "collections"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False, index=True)
    dim = Column(Integer, nullable=False)
    distance_metric = Column(String, nullable=False, default="cosine")
    description = Column(Text, nullable=True)
    user_id = Column(Integer, nullable=True, index=True)  # None = global/bootstrap
    created_at = Column(DateTime, server_default=func.now())
    vectors = relationship("_Vector", back_populates="collection", cascade="all, delete-orphan", lazy="raise")


class _Vector(Base):
    __tablename__ = "vectors"
    internal_id = Column(Integer, primary_key=True, index=True)
    external_id = Column(String, nullable=False, index=True)
    collection_id = Column(Integer, ForeignKey("collections.id"), nullable=False, index=True)
    meta = Column("metadata", JSON, nullable=True)
    vector = Column(LargeBinary, nullable=False)
    content = Column(Text, nullable=True)
    collection = relationship("_Collection", back_populates="vectors", lazy="raise")

    __table_args__ = (
        UniqueConstraint("collection_id", "external_id", name="uq_collection_external_id"),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_async_url(db_url: str) -> str:
    """Convert a sync SQLAlchemy URL to its async equivalent."""
    if db_url.startswith("sqlite:///"):
        return db_url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)
    if db_url.startswith("sqlite://"):
        return db_url.replace("sqlite://", "sqlite+aiosqlite://", 1)
    return db_url


def _matches_filters(meta: Optional[dict], filters: dict) -> bool:
    if not meta:
        return False
    return all(meta.get(k) == v for k, v in filters.items())


def _col_to_dict(col: _Collection, vec_count: int) -> Dict[str, Any]:
    return {
        "name": col.name,
        "dim": col.dim,
        "distance_metric": col.distance_metric,
        "description": col.description,
        "user_id": col.user_id,
        "vector_count": vec_count,
        "created_at": str(col.created_at),
    }


# ---------------------------------------------------------------------------
# Backend implementation
# ---------------------------------------------------------------------------

class SQLiteHNSWBackend(VectorBackend):
    """
    Async SQLite backend using HNSWlib for approximate nearest-neighbour search.
    This is the default backend. No external services required.
    """

    DEFAULT_COLLECTION = "default"

    def __init__(self, db_url: str, settings):
        self._settings = settings
        async_url = _to_async_url(db_url)
        self._engine = create_async_engine(
            async_url,
            connect_args={"check_same_thread": False},
            pool_pre_ping=True,
        )
        # Enable WAL mode for SQLite async engine via the underlying sync driver
        @event.listens_for(self._engine.sync_engine, "connect")
        def _set_wal(dbapi_conn, _record):
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA synchronous=NORMAL")
            cur.close()

        self._session_factory = async_sessionmaker(
            self._engine, class_=AsyncSession, expire_on_commit=False
        )
        self._index_manager = IndexManager()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def startup(self) -> None:
        """Create tables and rebuild HNSW indexes from stored vectors."""
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with self._session_factory() as session:
            result = await session.execute(select(_Collection))
            collections = result.scalars().all()
            for col in collections:
                indexer = self._index_manager.get_or_create(col.name, col.dim, col.distance_metric)
                if indexer.get_current_count() == 0:
                    vecs_result = await session.execute(
                        select(_Vector).where(_Vector.collection_id == col.id)
                    )
                    rows = vecs_result.scalars().all()
                    for row in rows:
                        safe_add_to_index(indexer, decode_vector(row.vector), row.internal_id)
                    if rows:
                        logger.info("index_rebuilt", collection=col.name, count=len(rows))
                else:
                    logger.info("index_loaded", collection=col.name)

    async def shutdown(self) -> None:
        """Persist HNSW indexes to disk."""
        self._index_manager.save_all()
        await self._engine.dispose()
        logger.info("sqlite_hnsw_backend_shutdown")

    # ------------------------------------------------------------------
    # Collections
    # ------------------------------------------------------------------

    async def create_collection(
        self, name: str, dim: int, distance_metric: str,
        description: Optional[str] = None, user_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        async with self._session_factory() as session:
            existing = await session.execute(select(_Collection).where(_Collection.name == name))
            if existing.scalar_one_or_none():
                raise CollectionAlreadyExistsError(name)
            col = _Collection(
                name=name, dim=dim, distance_metric=distance_metric,
                description=description, user_id=user_id,
            )
            session.add(col)
            await session.commit()
            await session.refresh(col)
            self._index_manager.get_or_create(col.name, col.dim, col.distance_metric)
            return _col_to_dict(col, 0)

    async def get_collection(self, name: str, user_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        async with self._session_factory() as session:
            stmt = select(_Collection).where(_Collection.name == name)
            if user_id is not None:
                from sqlalchemy import or_
                stmt = stmt.where(
                    or_(_Collection.user_id == user_id, _Collection.user_id.is_(None))
                )
            result = await session.execute(stmt)
            col = result.scalar_one_or_none()
            if not col:
                return None
            count = await self._vec_count(session, col.id)
            return _col_to_dict(col, count)

    async def list_collections(self, user_id: Optional[int] = None) -> List[Dict[str, Any]]:
        async with self._session_factory() as session:
            from sqlalchemy import func as sa_func, outerjoin

            stmt = select(_Collection)
            if user_id is not None:
                stmt = stmt.where(_Collection.user_id == user_id)
            result = await session.execute(stmt)
            cols = result.scalars().all()

            if not cols:
                return []

            # Batch count: single GROUP BY query for all collection IDs
            col_ids = [c.id for c in cols]
            count_result = await session.execute(
                select(
                    _Vector.collection_id,
                    sa_func.count(_Vector.internal_id),
                ).where(_Vector.collection_id.in_(col_ids))
                .group_by(_Vector.collection_id)
            )
            counts = dict(count_result.all())

            return [_col_to_dict(col, counts.get(col.id, 0)) for col in cols]

    async def delete_collection(self, name: str, user_id: Optional[int] = None) -> None:
        async with self._session_factory() as session:
            stmt = select(_Collection).where(_Collection.name == name)
            if user_id is not None:
                stmt = stmt.where(_Collection.user_id == user_id)
            result = await session.execute(stmt)
            col = result.scalar_one_or_none()
            if not col:
                raise CollectionNotFoundError(name)
            # Delete vectors first (avoid ORM relationship lazy-load)
            vecs = await session.execute(select(_Vector).where(_Vector.collection_id == col.id))
            for v in vecs.scalars().all():
                await session.delete(v)
            await session.delete(col)
            await session.commit()
        self._index_manager.remove(name)

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
        user_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        col = await self._require_collection(collection_name, user_id=user_id)
        if len(vector) != col.dim:
            raise DimensionMismatchError(col.dim, len(vector))
        vec_np = normalize_vector(np.array(vector, dtype=np.float32))
        indexer = self._index_manager.get_or_create(col.name, col.dim, col.distance_metric)

        async with self._session_factory() as session:
            result = await session.execute(
                select(_Vector).where(
                    _Vector.collection_id == col.id,
                    _Vector.external_id == external_id,
                )
            )
            row = result.scalar_one_or_none()
            if row:
                row.vector = encode_vector(vec_np)
                row.meta = metadata if metadata is not None else row.meta
                if content is not None:
                    row.content = content
                try:
                    indexer.mark_deleted(row.internal_id)
                except Exception:
                    pass
                safe_add_to_index(indexer, vec_np, row.internal_id)
                await session.commit()
                return {"external_id": external_id, "status": "updated"}
            else:
                row = _Vector(
                    external_id=external_id,
                    collection_id=col.id,
                    vector=encode_vector(vec_np),
                    meta=metadata or {},
                    content=content,
                )
                session.add(row)
                await session.flush()
                safe_add_to_index(indexer, vec_np, row.internal_id)
                await session.commit()
                return {"external_id": external_id, "status": "inserted"}

    async def bulk_upsert(
        self, collection_name: str, items: List[Dict[str, Any]], user_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        col = await self._require_collection(collection_name, user_id=user_id)
        for it in items:
            if len(it["vector"]) != col.dim:
                raise DimensionMismatchError(col.dim, len(it["vector"]))

        indexer = self._index_manager.get_or_create(col.name, col.dim, col.distance_metric)
        results = []
        all_vecs: List[np.ndarray] = []
        all_ids: List[int] = []

        async with self._session_factory() as session:
            for it in items:
                vec_np = normalize_vector(np.array(it["vector"], dtype=np.float32))
                ext_id = it["external_id"]

                existing = await session.execute(
                    select(_Vector).where(
                        _Vector.collection_id == col.id,
                        _Vector.external_id == ext_id,
                    )
                )
                row = existing.scalar_one_or_none()
                if row:
                    row.vector = encode_vector(vec_np)
                    row.meta = it.get("metadata") or row.meta
                    if it.get("content") is not None:
                        row.content = it["content"]
                    try:
                        indexer.mark_deleted(row.internal_id)
                    except Exception:
                        pass
                    all_vecs.append(vec_np)
                    all_ids.append(row.internal_id)
                    results.append({"external_id": ext_id, "status": "updated"})
                else:
                    row = _Vector(
                        external_id=ext_id,
                        collection_id=col.id,
                        vector=encode_vector(vec_np),
                        meta=it.get("metadata") or {},
                        content=it.get("content"),
                    )
                    session.add(row)
                    await session.flush()
                    all_vecs.append(vec_np)
                    all_ids.append(row.internal_id)
                    results.append({"external_id": ext_id, "status": "inserted"})

            await session.commit()

        if all_vecs:
            mat = np.vstack(all_vecs)
            ids = np.array(all_ids, dtype=np.int32)
            indexer.add_items(mat, ids)

        return results

    async def delete_vector(
        self, collection_name: str, external_id: str, user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        col = await self._require_collection(collection_name, user_id=user_id)
        indexer = self._index_manager.get_or_create(col.name, col.dim, col.distance_metric)

        async with self._session_factory() as session:
            result = await session.execute(
                select(_Vector).where(
                    _Vector.collection_id == col.id,
                    _Vector.external_id == external_id,
                )
            )
            row = result.scalar_one_or_none()
            if not row:
                raise VectorNotFoundError(external_id)
            try:
                indexer.mark_deleted(int(row.internal_id))
            except Exception as e:
                logger.warning("mark_deleted_failed", internal_id=row.internal_id, error=str(e))
            await session.delete(row)
            await session.commit()
        return {"status": "deleted", "external_id": external_id}

    async def batch_delete(
        self, collection_name: str, external_ids: List[str], user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        col = await self._require_collection(collection_name, user_id=user_id)
        indexer = self._index_manager.get_or_create(col.name, col.dim, col.distance_metric)
        deleted = []
        not_found = []

        async with self._session_factory() as session:
            # Batch fetch all vectors in one query
            result = await session.execute(
                select(_Vector).where(
                    _Vector.collection_id == col.id,
                    _Vector.external_id.in_(external_ids),
                )
            )
            rows_by_eid = {r.external_id: r for r in result.scalars().all()}

            for eid in external_ids:
                row = rows_by_eid.get(eid)
                if not row:
                    not_found.append(eid)
                    continue
                try:
                    indexer.mark_deleted(int(row.internal_id))
                except Exception as e:
                    logger.warning("mark_deleted_failed", internal_id=row.internal_id, error=str(e))
                await session.delete(row)
                deleted.append(eid)
            await session.commit()

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
        user_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        col = await self._require_collection(collection_name, user_id=user_id)
        if len(vector) != col.dim:
            raise DimensionMismatchError(col.dim, len(vector))

        indexer = self._index_manager.get_or_create(col.name, col.dim, col.distance_metric)
        q = np.array(vector, dtype=np.float32)
        cur = indexer.get_current_count()
        if cur == 0:
            return []

        async with self._session_factory() as session:
            if filters:
                fetch_k = min((k + offset) * FILTER_OVERSAMPLE, cur)
                labels, distances = indexer.knn_query(q, k=fetch_k)

                # Batch fetch all candidate rows in one query
                int_ids = [int(lbl) for lbl in labels]
                res = await session.execute(
                    select(_Vector).where(
                        _Vector.internal_id.in_(int_ids),
                        _Vector.collection_id == col.id,
                    )
                )
                rows_by_id = {r.internal_id: r for r in res.scalars().all()}

                out = []
                for lbl, dist in zip(labels, distances):
                    db_row = rows_by_id.get(int(lbl))
                    if db_row and _matches_filters(db_row.meta, filters):
                        out.append({"external_id": db_row.external_id, "score": float(1 - dist), "metadata": db_row.meta})
                    if len(out) >= k + offset:
                        break

                # DB fallback if not enough HNSW results — use LIMIT to avoid full table scan
                if len(out) < k + offset:
                    found_ids = {r["external_id"] for r in out}
                    needed = (k + offset) - len(out)
                    # Fetch a bounded set of candidates rather than entire collection
                    fallback_limit = needed * FILTER_OVERSAMPLE
                    all_rows_res = await session.execute(
                        select(_Vector).where(
                            _Vector.collection_id == col.id,
                            _Vector.external_id.notin_(found_ids) if found_ids else True,
                        ).limit(fallback_limit)
                    )
                    cand_rows = [
                        r for r in all_rows_res.scalars().all()
                        if r.external_id not in found_ids and _matches_filters(r.meta, filters)
                    ]
                    if cand_rows:
                        qn = normalize_vector(q)
                        mat = np.vstack([decode_vector(r.vector) for r in cand_rows])
                        matn = mat / (np.linalg.norm(mat, axis=1, keepdims=True) + 1e-10)
                        scores = matn.dot(qn)
                        idxs = np.argsort(-scores)[:needed]
                        for i in idxs:
                            out.append({
                                "external_id": cand_rows[i].external_id,
                                "score": float(scores[i]),
                                "metadata": cand_rows[i].meta,
                            })
                return out[offset: offset + k]
            else:
                k_safe = min(k + offset, max(1, cur))
                labels, distances = indexer.knn_query(q, k=k_safe)

                # Batch fetch all result rows in one query
                int_ids = [int(lbl) for lbl in labels]
                res = await session.execute(
                    select(_Vector).where(
                        _Vector.internal_id.in_(int_ids),
                        _Vector.collection_id == col.id,
                    )
                )
                rows_by_id = {r.internal_id: r for r in res.scalars().all()}

                out = []
                for lbl, dist in zip(labels, distances):
                    db_row = rows_by_id.get(int(lbl))
                    if db_row:
                        out.append({"external_id": db_row.external_id, "score": float(1 - dist), "metadata": db_row.meta})
                return out[offset: offset + k]

    async def recommend(
        self, collection_name: str, external_id: str, k: int, ef: int, user_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        col = await self._require_collection(collection_name, user_id=user_id)
        indexer = self._index_manager.get_or_create(col.name, col.dim, col.distance_metric)

        async with self._session_factory() as session:
            res = await session.execute(
                select(_Vector).where(
                    _Vector.collection_id == col.id,
                    _Vector.external_id == external_id,
                )
            )
            row = res.scalar_one_or_none()
            if not row:
                raise VectorNotFoundError(external_id)

            vec = normalize_vector(decode_vector(row.vector))
            total = indexer.get_current_count()
            k_safe = min(k, max(1, total - 1))
            if k_safe < 1:
                return []

            indexer.set_ef(ef)
            labels, distances = indexer.knn_query(vec, k=k_safe + 1)

            # Batch fetch all candidate rows in one query
            int_ids = [int(lbl) for lbl in labels if lbl != row.internal_id]
            res = await session.execute(
                select(_Vector).where(
                    _Vector.internal_id.in_(int_ids),
                    _Vector.collection_id == col.id,
                )
            )
            rows_by_id = {r.internal_id: r for r in res.scalars().all()}

            out = []
            for lbl, dist in zip(labels, distances):
                if lbl == row.internal_id:
                    continue
                db_row = rows_by_id.get(int(lbl))
                if db_row:
                    out.append({"external_id": db_row.external_id, "score": float(1 - dist), "metadata": db_row.meta})
                if len(out) >= k_safe:
                    break
            return out

    async def similarity(
        self, collection_name: str, id1: str, id2: str, user_id: Optional[int] = None
    ) -> float:
        col = await self._require_collection(collection_name, user_id=user_id)

        async with self._session_factory() as session:
            r1 = await session.execute(
                select(_Vector).where(_Vector.collection_id == col.id, _Vector.external_id == id1)
            )
            r2 = await session.execute(
                select(_Vector).where(_Vector.collection_id == col.id, _Vector.external_id == id2)
            )
            v1 = r1.scalar_one_or_none()
            v2 = r2.scalar_one_or_none()
            if not v1 or not v2:
                raise VectorNotFoundError(id1 if not v1 else id2)

            vec1 = normalize_vector(decode_vector(v1.vector))
            vec2 = normalize_vector(decode_vector(v2.vector))
            return float(np.dot(vec1, vec2))

    async def rerank(
        self,
        collection_name: str,
        query_vector: List[float],
        candidates: List[str],
        user_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        col = await self._require_collection(collection_name, user_id=user_id)
        if len(query_vector) != col.dim:
            raise DimensionMismatchError(col.dim, len(query_vector))

        qv = normalize_vector(np.array(query_vector, dtype=np.float32))

        async with self._session_factory() as session:
            res = await session.execute(
                select(_Vector).where(
                    _Vector.collection_id == col.id,
                    _Vector.external_id.in_(candidates),
                )
            )
            rows = res.scalars().all()
            results = []
            for r in rows:
                cvec = normalize_vector(decode_vector(r.vector))
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
        col = await self._require_collection(collection_name, user_id=user_id)
        if len(vector) != col.dim:
            raise DimensionMismatchError(col.dim, len(vector))

        indexer = self._index_manager.get_or_create(col.name, col.dim, col.distance_metric)
        q = np.array(vector, dtype=np.float32)

        async with self._session_factory() as session:
            # Vector search — batch fetch
            vector_results: Dict[str, Any] = {}
            cur = indexer.get_current_count()
            if cur > 0:
                fetch_k = min((k + offset) * 3, cur)
                labels, distances = indexer.knn_query(q, k=fetch_k)

                int_ids = [int(lbl) for lbl in labels]
                res = await session.execute(
                    select(_Vector).where(
                        _Vector.internal_id.in_(int_ids),
                        _Vector.collection_id == col.id,
                    )
                )
                rows_by_id = {r.internal_id: r for r in res.scalars().all()}

                for lbl, dist in zip(labels, distances):
                    db_row = rows_by_id.get(int(lbl))
                    if db_row:
                        if filters and not _matches_filters(db_row.meta, filters):
                            continue
                        vector_results[db_row.external_id] = {
                            "score": float(1 - dist),
                            "metadata": db_row.meta,
                        }

            # Text search
            text_results: Dict[str, Any] = {}
            query_words = query_text.lower().split()
            if query_words:
                rows_res = await session.execute(
                    select(_Vector).where(
                        _Vector.collection_id == col.id,
                        _Vector.content.isnot(None),
                    )
                )
                for row in rows_res.scalars().all():
                    if filters and not _matches_filters(row.meta, filters):
                        continue
                    content_lower = (row.content or "").lower()
                    matches = sum(1 for w in query_words if w in content_lower)
                    if matches > 0:
                        text_results[row.external_id] = {
                            "score": matches / len(query_words),
                            "metadata": row.meta,
                        }

        # RRF merge
        rrf_k = 60
        all_ids = set(vector_results) | set(text_results)
        vec_ranked = sorted(vector_results, key=lambda x: -vector_results[x]["score"])
        text_ranked = sorted(text_results, key=lambda x: -text_results[x]["score"])
        vec_rank = {eid: r + 1 for r, eid in enumerate(vec_ranked)}
        text_rank = {eid: r + 1 for r, eid in enumerate(text_ranked)}

        merged = []
        for eid in all_ids:
            vr = alpha * (1.0 / (rrf_k + vec_rank[eid])) if eid in vec_rank else 0.0
            tr = (1 - alpha) * (1.0 / (rrf_k + text_rank[eid])) if eid in text_rank else 0.0
            meta = vector_results.get(eid, text_results.get(eid, {})).get("metadata")
            merged.append({
                "external_id": eid,
                "score": round(vr + tr, 6),
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
            from sqlalchemy import func as sa_func

            result = await session.execute(select(_Collection))
            collections = result.scalars().all()

            # Batch count: single GROUP BY query
            col_ids = [c.id for c in collections]
            counts = {}
            if col_ids:
                count_result = await session.execute(
                    select(
                        _Vector.collection_id,
                        sa_func.count(_Vector.internal_id),
                    ).where(_Vector.collection_id.in_(col_ids))
                    .group_by(_Vector.collection_id)
                )
                counts = dict(count_result.all())

            total_vectors = 0
            col_stats = []
            for col in collections:
                count = counts.get(col.id, 0)
                total_vectors += count
                indexer = self._index_manager.get(col.name)
                index_size = indexer.get_current_count() if indexer else 0
                col_stats.append({
                    "name": col.name,
                    "dim": col.dim,
                    "distance_metric": col.distance_metric,
                    "vector_count": count,
                    "index_size": index_size,
                })
            return {
                "total_vectors": total_vectors,
                "total_collections": len(collections),
                "collections": col_stats,
            }

    # ------------------------------------------------------------------
    # Extensions
    # ------------------------------------------------------------------

    async def update_collection(
        self, name: str, description: Optional[str], user_id: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        async with self._session_factory() as session:
            stmt = select(_Collection).where(_Collection.name == name)
            if user_id is not None:
                stmt = stmt.where(_Collection.user_id == user_id)
            result = await session.execute(stmt)
            col = result.scalar_one_or_none()
            if not col:
                return None
            col.description = description
            await session.commit()
            await session.refresh(col)
            count = await self._vec_count(session, col.id)
            return _col_to_dict(col, count)

    async def count_vectors(
        self, collection_name: str, filters: Optional[Dict[str, Any]] = None,
        user_id: Optional[int] = None,
    ) -> int:
        async with self._session_factory() as session:
            col = await self._resolve_collection(session, collection_name, user_id=user_id)
            if not col:
                return 0
            if not filters:
                return await self._vec_count(session, col.id)
            # Filtered count: must scan metadata
            rows_res = await session.execute(
                select(_Vector).where(_Vector.collection_id == col.id)
            )
            return sum(
                1 for r in rows_res.scalars().all()
                if _matches_filters(r.meta, filters)
            )

    async def export_vectors(
        self, collection_name: str, limit: int = 10000, user_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        async with self._session_factory() as session:
            col = await self._resolve_collection(session, collection_name, user_id=user_id)
            if not col:
                return []
            rows_res = await session.execute(
                select(_Vector)
                .where(_Vector.collection_id == col.id)
                .limit(limit)
            )
            out = []
            for row in rows_res.scalars().all():
                out.append({
                    "external_id": row.external_id,
                    "vector": decode_vector(row.vector).tolist(),
                    "metadata": row.meta,
                })
            return out

    # ------------------------------------------------------------------
    # Get / Fetch / Scroll
    # ------------------------------------------------------------------

    async def get_vector(
        self, collection_name: str, external_id: str, user_id: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        col = await self._require_collection(collection_name, user_id=user_id)
        async with self._session_factory() as session:
            result = await session.execute(
                select(_Vector).where(
                    _Vector.collection_id == col.id,
                    _Vector.external_id == external_id,
                )
            )
            row = result.scalar_one_or_none()
            if not row:
                return None
            return {
                "external_id": row.external_id,
                "metadata": row.meta,
                "vector": decode_vector(row.vector).tolist(),
                "content": row.content,
            }

    async def batch_get_vectors(
        self, collection_name: str, ids: List[str],
        include_vectors: bool = True, user_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        col = await self._require_collection(collection_name, user_id=user_id)
        async with self._session_factory() as session:
            if include_vectors:
                result = await session.execute(
                    select(_Vector).where(
                        _Vector.collection_id == col.id,
                        _Vector.external_id.in_(ids),
                    )
                )
            else:
                result = await session.execute(
                    select(
                        _Vector.external_id, _Vector.meta, _Vector.content,
                    ).where(
                        _Vector.collection_id == col.id,
                        _Vector.external_id.in_(ids),
                    )
                )

            if include_vectors:
                rows_by_eid = {r.external_id: r for r in result.scalars().all()}
            else:
                rows_by_eid = {r.external_id: r for r in result.all()}

            out = []
            for eid in ids:
                row = rows_by_eid.get(eid)
                if not row:
                    continue
                item = {
                    "external_id": row.external_id if hasattr(row, 'external_id') else eid,
                    "metadata": row.meta,
                    "content": row.content,
                }
                if include_vectors:
                    item["vector"] = decode_vector(row.vector).tolist()
                out.append(item)
            return out

    async def scroll(
        self, collection_name: str, cursor: Optional[int] = None,
        limit: int = 100, filters: Optional[Dict[str, Any]] = None,
        include_vectors: bool = True, user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        col = await self._require_collection(collection_name, user_id=user_id)
        start_id = cursor if cursor is not None else 0
        max_scan = limit * 5  # MAX_SCAN_MULTIPLIER

        async with self._session_factory() as session:
            collected = []
            scanned = 0
            current_cursor = start_id

            while len(collected) < limit and scanned < max_scan:
                fetch_size = (limit - len(collected)) * 2 if filters else limit - len(collected) + 1
                fetch_size = min(fetch_size, max_scan - scanned)
                if fetch_size <= 0:
                    break

                stmt = (
                    select(_Vector)
                    .where(
                        _Vector.collection_id == col.id,
                        _Vector.internal_id > current_cursor,
                    )
                    .order_by(_Vector.internal_id)
                    .limit(fetch_size)
                )
                result = await session.execute(stmt)
                rows = result.scalars().all()

                if not rows:
                    break

                scanned += len(rows)
                for row in rows:
                    current_cursor = row.internal_id
                    if filters and not _matches_filters(row.meta, filters):
                        continue
                    item = {
                        "external_id": row.external_id,
                        "metadata": row.meta,
                        "content": row.content,
                    }
                    if include_vectors:
                        item["vector"] = decode_vector(row.vector).tolist()
                    collected.append((row.internal_id, item))
                    if len(collected) >= limit + 1:
                        break

            # Determine next_cursor
            if len(collected) > limit:
                vectors_out = [item for _, item in collected[:limit]]
                next_cursor_id = collected[limit - 1][0]
            elif len(collected) == limit:
                # Check if there are more rows
                check = await session.execute(
                    select(_Vector.internal_id)
                    .where(
                        _Vector.collection_id == col.id,
                        _Vector.internal_id > current_cursor,
                    )
                    .limit(1)
                )
                has_more = check.scalar_one_or_none() is not None
                vectors_out = [item for _, item in collected]
                next_cursor_id = collected[-1][0] if has_more else None
            else:
                vectors_out = [item for _, item in collected]
                next_cursor_id = None

            import base64
            next_cursor = base64.b64encode(str(next_cursor_id).encode()).decode() if next_cursor_id else None
            return {"vectors": vectors_out, "next_cursor": next_cursor}

    # ------------------------------------------------------------------
    # Legacy: ensure default collection exists (for legacy endpoints)
    # ------------------------------------------------------------------

    async def ensure_default_collection(self, user_id: Optional[int] = None) -> Dict[str, Any]:
        """Get or create the 'default' collection for legacy endpoints."""
        col = await self.get_collection(self.DEFAULT_COLLECTION, user_id=user_id)
        if col:
            return col
        try:
            return await self.create_collection(
                self.DEFAULT_COLLECTION, self._settings.vector_dim, "cosine", user_id=user_id
            )
        except CollectionAlreadyExistsError:
            return await self.get_collection(self.DEFAULT_COLLECTION, user_id=user_id)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _require_collection(self, name: str, user_id: Optional[int] = None) -> "_Collection":
        """Return the ORM _Collection row or raise CollectionNotFoundError."""
        async with self._session_factory() as session:
            col = await self._resolve_collection(session, name, user_id=user_id)
            if not col:
                raise CollectionNotFoundError(name)
            return col

    async def _resolve_collection(
        self, session: AsyncSession, name: str, user_id: Optional[int] = None
    ) -> Optional["_Collection"]:
        stmt = select(_Collection).where(_Collection.name == name)
        if user_id is not None:
            stmt = stmt.where(_Collection.user_id == user_id)
        result = await session.execute(stmt)
        rows = result.scalars().all()
        if len(rows) == 1:
            return rows[0]
        return None

    async def _lookup_collection_id(self, name: str, user_id: Optional[int]) -> Optional[int]:
        async with self._session_factory() as session:
            col = await self._resolve_collection(session, name, user_id=user_id)
            return col.id if col else None

    async def _vec_count(self, session: AsyncSession, collection_id: int) -> int:
        from sqlalchemy import func as sa_func
        result = await session.execute(
            select(sa_func.count(_Vector.internal_id)).where(_Vector.collection_id == collection_id)
        )
        return result.scalar() or 0
