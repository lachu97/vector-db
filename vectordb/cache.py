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


def _search_key(col: str, vector: list, k: int, offset: int, filters: Optional[dict]) -> str:
    return f"search:{col}:{_hash(vector)}:{k}:{offset}:{_hash(filters)}"


def _recommend_key(col: str, ext_id: str, k: int, ef: int) -> str:
    return f"recommend:{col}:{ext_id}:{k}:{ef}"


def _rerank_key(col: str, vector: list, candidates: list) -> str:
    return f"rerank:{col}:{_hash(vector)}:{_hash(sorted(candidates))}"


def _hybrid_key(col: str, text: str, vector: list, k: int, offset: int, alpha: float,
                filters: Optional[dict]) -> str:
    return f"hybrid:{col}:{_hash(text)}:{_hash(vector)}:{k}:{offset}:{alpha}:{_hash(filters)}"


def _collection_pattern(col: str) -> str:
    return f"*:{col}:*"


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

    async def create_collection(self, name, dim, distance_metric):
        return await self._inner.create_collection(name, dim, distance_metric)

    async def get_collection(self, name):
        return await self._inner.get_collection(name)

    async def list_collections(self):
        return await self._inner.list_collections()

    async def delete_collection(self, name):
        await self._cache.delete_pattern(_collection_pattern(name))
        return await self._inner.delete_collection(name)

    # ------------------------------------------------------------------
    # Vectors (write → invalidate)
    # ------------------------------------------------------------------

    async def upsert(self, collection_name, external_id, vector, metadata, content):
        await self._cache.delete_pattern(_collection_pattern(collection_name))
        return await self._inner.upsert(collection_name, external_id, vector, metadata, content)

    async def bulk_upsert(self, collection_name, items):
        await self._cache.delete_pattern(_collection_pattern(collection_name))
        return await self._inner.bulk_upsert(collection_name, items)

    async def delete_vector(self, collection_name, external_id):
        await self._cache.delete_pattern(_collection_pattern(collection_name))
        return await self._inner.delete_vector(collection_name, external_id)

    async def batch_delete(self, collection_name, external_ids):
        await self._cache.delete_pattern(_collection_pattern(collection_name))
        return await self._inner.batch_delete(collection_name, external_ids)

    # ------------------------------------------------------------------
    # Search (read → cache)
    # ------------------------------------------------------------------

    async def search(self, collection_name, vector, k, offset, filters):
        key = _search_key(collection_name, vector, k, offset, filters)
        cached = await self._cache.get(key)
        if cached is not None:
            logger.debug("cache_hit", op="search", collection=collection_name)
            return cached
        result = await self._inner.search(collection_name, vector, k, offset, filters)
        await self._cache.set(key, result)
        return result

    async def recommend(self, collection_name, external_id, k, ef):
        key = _recommend_key(collection_name, external_id, k, ef)
        cached = await self._cache.get(key)
        if cached is not None:
            logger.debug("cache_hit", op="recommend", collection=collection_name)
            return cached
        result = await self._inner.recommend(collection_name, external_id, k, ef)
        await self._cache.set(key, result)
        return result

    async def similarity(self, collection_name, id1, id2):
        # Similarity is cheap, skip caching
        return await self._inner.similarity(collection_name, id1, id2)

    async def rerank(self, collection_name, query_vector, candidates):
        key = _rerank_key(collection_name, query_vector, candidates)
        cached = await self._cache.get(key)
        if cached is not None:
            logger.debug("cache_hit", op="rerank", collection=collection_name)
            return cached
        result = await self._inner.rerank(collection_name, query_vector, candidates)
        await self._cache.set(key, result)
        return result

    async def hybrid_search(self, collection_name, query_text, vector, k, offset, alpha, filters):
        key = _hybrid_key(collection_name, query_text, vector, k, offset, alpha, filters)
        cached = await self._cache.get(key)
        if cached is not None:
            logger.debug("cache_hit", op="hybrid_search", collection=collection_name)
            return cached
        result = await self._inner.hybrid_search(
            collection_name, query_text, vector, k, offset, alpha, filters
        )
        await self._cache.set(key, result)
        return result

    # ------------------------------------------------------------------
    # Observability
    # ------------------------------------------------------------------

    async def health_stats(self):
        return await self._inner.health_stats()
