# vectordb/cache.py
"""
Redis-backed search cache layer.

CachingBackend wraps any VectorBackend and caches the results of read
operations (search, recommend, rerank, hybrid_search). Write operations
(upsert, delete, create/delete collection) automatically invalidate the
relevant cache entries.

When REDIS_URL is empty (default) the cache is disabled and every call
goes straight to the underlying backend — zero overhead, zero Redis dep.
"""
import hashlib
import json
from typing import Any, Dict, List, Optional

import structlog

from vectordb.backends.base import VectorBackend

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Internal Redis client wrapper
# ---------------------------------------------------------------------------

class _RedisCache:
    """Thin async wrapper around redis.asyncio."""

    def __init__(self, redis_url: str, ttl: int):
        import redis.asyncio as aioredis
        self._client = aioredis.from_url(redis_url, decode_responses=True)
        self._ttl = ttl

    async def get(self, key: str) -> Optional[Any]:
        try:
            raw = await self._client.get(key)
            return json.loads(raw) if raw is not None else None
        except Exception as exc:
            logger.warning("cache_get_error", key=key, error=str(exc))
            return None

    async def set(self, key: str, value: Any) -> None:
        try:
            await self._client.setex(key, self._ttl, json.dumps(value))
        except Exception as exc:
            logger.warning("cache_set_error", key=key, error=str(exc))

    async def delete_pattern(self, pattern: str) -> None:
        """Delete all keys matching a pattern (e.g. 'search:my-col:*')."""
        try:
            keys = await self._client.keys(pattern)
            if keys:
                await self._client.delete(*keys)
        except Exception as exc:
            logger.warning("cache_invalidate_error", pattern=pattern, error=str(exc))

    async def close(self) -> None:
        await self._client.aclose()


# ---------------------------------------------------------------------------
# Cache key helpers
# ---------------------------------------------------------------------------

def _hash(obj: Any) -> str:
    return hashlib.md5(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:12]


def _search_key(collection_id: int, vector: list, k: int, offset: int, filters: Optional[dict]) -> str:
    return f"search:{collection_id}:{_hash(vector)}:{k}:{offset}:{_hash(filters)}"


def _recommend_key(collection_id: int, ext_id: str, k: int, ef: int) -> str:
    return f"recommend:{collection_id}:{ext_id}:{k}:{ef}"


def _rerank_key(collection_id: int, vector: list, candidates: list) -> str:
    return f"rerank:{collection_id}:{_hash(vector)}:{_hash(sorted(candidates))}"


def _hybrid_key(collection_id: int, text: str, vector: list, k: int, offset: int, alpha: float,
                filters: Optional[dict]) -> str:
    return f"hybrid:{collection_id}:{_hash(text)}:{_hash(vector)}:{k}:{offset}:{alpha}:{_hash(filters)}"


def _collection_pattern(collection_id: int) -> str:
    return f"*:{collection_id}:*"


# ---------------------------------------------------------------------------
# Caching backend decorator
# ---------------------------------------------------------------------------

class CachingBackend(VectorBackend):
    """
    Transparent caching layer that wraps any VectorBackend.

    Read operations are cached; write operations invalidate the cache for
    the affected collection.
    """

    def __init__(self, inner: VectorBackend, redis_url: str, ttl: int):
        self._inner = inner
        self._cache = _RedisCache(redis_url, ttl)

    async def _resolve_collection_id(self, collection_name: str, user_id: Optional[int]) -> Optional[int]:
        if hasattr(self._inner, "_lookup_collection_id"):
            try:
                return await self._inner._lookup_collection_id(collection_name, user_id)  # type: ignore[attr-defined]
            except Exception:
                return None
        col = await self._inner.get_collection(collection_name, user_id=user_id)
        if not col:
            return None
        return col.get("id")

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def startup(self) -> None:
        await self._inner.startup()

    async def shutdown(self) -> None:
        await self._cache.close()
        await self._inner.shutdown()

    # ------------------------------------------------------------------
    # Collections (no caching — metadata is cheap)
    # ------------------------------------------------------------------

    async def create_collection(self, name, dim, distance_metric, description=None, user_id=None):
        return await self._inner.create_collection(name, dim, distance_metric, description, user_id)

    async def get_collection(self, name, user_id=None):
        return await self._inner.get_collection(name, user_id)

    async def list_collections(self, user_id=None):
        return await self._inner.list_collections(user_id)

    async def delete_collection(self, name, user_id=None):
        cid = await self._resolve_collection_id(name, user_id)
        if cid is not None:
            await self._cache.delete_pattern(_collection_pattern(cid))
        return await self._inner.delete_collection(name, user_id)

    async def update_collection(self, name, description, user_id=None):
        return await self._inner.update_collection(name, description, user_id)

    async def count_vectors(self, collection_name, filters=None, user_id=None):
        return await self._inner.count_vectors(collection_name, filters, user_id=user_id)

    async def export_vectors(self, collection_name, limit=10000, user_id=None):
        return await self._inner.export_vectors(collection_name, limit, user_id=user_id)

    # ------------------------------------------------------------------
    # Vectors (write → invalidate)
    # ------------------------------------------------------------------

    async def upsert(self, collection_name, external_id, vector, metadata, content, user_id=None):
        cid = await self._resolve_collection_id(collection_name, user_id)
        if cid is not None:
            await self._cache.delete_pattern(_collection_pattern(cid))
        return await self._inner.upsert(collection_name, external_id, vector, metadata, content, user_id=user_id)

    async def bulk_upsert(self, collection_name, items, user_id=None):
        cid = await self._resolve_collection_id(collection_name, user_id)
        if cid is not None:
            await self._cache.delete_pattern(_collection_pattern(cid))
        return await self._inner.bulk_upsert(collection_name, items, user_id=user_id)

    async def delete_vector(self, collection_name, external_id, user_id=None):
        cid = await self._resolve_collection_id(collection_name, user_id)
        if cid is not None:
            await self._cache.delete_pattern(_collection_pattern(cid))
        return await self._inner.delete_vector(collection_name, external_id, user_id=user_id)

    async def batch_delete(self, collection_name, external_ids, user_id=None):
        cid = await self._resolve_collection_id(collection_name, user_id)
        if cid is not None:
            await self._cache.delete_pattern(_collection_pattern(cid))
        return await self._inner.batch_delete(collection_name, external_ids, user_id=user_id)

    # ------------------------------------------------------------------
    # Search (read → cache)
    # ------------------------------------------------------------------

    async def search(self, collection_name, vector, k, offset, filters, user_id=None):
        cid = await self._resolve_collection_id(collection_name, user_id)
        if cid is None:
            return await self._inner.search(collection_name, vector, k, offset, filters, user_id=user_id)
        key = _search_key(cid, vector, k, offset, filters)
        cached = await self._cache.get(key)
        if cached is not None:
            logger.debug("cache_hit", op="search", collection=collection_name)
            return cached
        result = await self._inner.search(collection_name, vector, k, offset, filters, user_id=user_id)
        await self._cache.set(key, result)
        return result

    async def recommend(self, collection_name, external_id, k, ef, user_id=None):
        cid = await self._resolve_collection_id(collection_name, user_id)
        if cid is None:
            return await self._inner.recommend(collection_name, external_id, k, ef, user_id=user_id)
        key = _recommend_key(cid, external_id, k, ef)
        cached = await self._cache.get(key)
        if cached is not None:
            logger.debug("cache_hit", op="recommend", collection=collection_name)
            return cached
        result = await self._inner.recommend(collection_name, external_id, k, ef, user_id=user_id)
        await self._cache.set(key, result)
        return result

    async def similarity(self, collection_name, id1, id2, user_id=None):
        # Similarity is cheap, skip caching
        return await self._inner.similarity(collection_name, id1, id2, user_id=user_id)

    async def rerank(self, collection_name, query_vector, candidates, user_id=None):
        cid = await self._resolve_collection_id(collection_name, user_id)
        if cid is None:
            return await self._inner.rerank(collection_name, query_vector, candidates, user_id=user_id)
        key = _rerank_key(cid, query_vector, candidates)
        cached = await self._cache.get(key)
        if cached is not None:
            logger.debug("cache_hit", op="rerank", collection=collection_name)
            return cached
        result = await self._inner.rerank(collection_name, query_vector, candidates, user_id=user_id)
        await self._cache.set(key, result)
        return result

    async def hybrid_search(self, collection_name, query_text, vector, k, offset, alpha, filters, user_id=None):
        cid = await self._resolve_collection_id(collection_name, user_id)
        if cid is None:
            return await self._inner.hybrid_search(
                collection_name, query_text, vector, k, offset, alpha, filters, user_id=user_id
            )
        key = _hybrid_key(cid, query_text, vector, k, offset, alpha, filters)
        cached = await self._cache.get(key)
        if cached is not None:
            logger.debug("cache_hit", op="hybrid_search", collection=collection_name)
            return cached
        result = await self._inner.hybrid_search(
            collection_name, query_text, vector, k, offset, alpha, filters, user_id=user_id
        )
        await self._cache.set(key, result)
        return result

    # ------------------------------------------------------------------
    # Observability
    # ------------------------------------------------------------------

    async def health_stats(self):
        return await self._inner.health_stats()
