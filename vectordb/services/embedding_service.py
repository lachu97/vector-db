# vectordb/services/embedding_service.py
"""
Pluggable embedding service with LRU + Redis caching, concurrency control,
and query normalization. Designed for P95 < 80ms query latency.
"""
import asyncio
import hashlib
import re
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from typing import List, Optional

import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Query normalization
# ---------------------------------------------------------------------------

def normalize_query(text: str) -> str:
    """Lowercase, strip, remove punctuation, collapse spaces.

    >>> normalize_query("What is AI??")
    'what is ai'
    """
    text = text.strip().lower()
    text = re.sub(r'[^\w\s]', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text


# ---------------------------------------------------------------------------
# Provider ABC
# ---------------------------------------------------------------------------

class EmbeddingProvider(ABC):
    @abstractmethod
    def embed_text(self, text: str) -> List[float]: ...

    @abstractmethod
    def embed_batch(self, texts: List[str]) -> List[List[float]]: ...

    @abstractmethod
    def get_dimension(self) -> int: ...


class SentenceTransformerProvider(EmbeddingProvider):
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        from sentence_transformers import SentenceTransformer
        self._model = SentenceTransformer(model_name)
        self._dim = self._model.get_sentence_embedding_dimension()

    def embed_text(self, text: str) -> List[float]:
        return self._model.encode(
            text,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        ).tolist()

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        return self._model.encode(
            texts,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        ).tolist()

    def get_dimension(self) -> int:
        return self._dim


class DummyEmbeddingProvider(EmbeddingProvider):
    """Deterministic hash-based embeddings for testing. No model download."""

    def __init__(self, dim: int = 384):
        self._dim = dim

    def embed_text(self, text: str) -> List[float]:
        import hashlib as hl
        import math
        import struct

        h = hl.sha512(text.encode()).digest()
        while len(h) < self._dim * 4:
            h += hl.sha512(h).digest()
        values = list(struct.unpack(f'{self._dim}f', h[:self._dim * 4]))
        values = [0.0 if not math.isfinite(v) else v for v in values]
        norm = math.sqrt(sum(v * v for v in values)) + 1e-10
        return [v / norm for v in values]

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        return [self.embed_text(t) for t in texts]

    def get_dimension(self) -> int:
        return self._dim


# ---------------------------------------------------------------------------
# Singleton state
# ---------------------------------------------------------------------------

_provider: Optional[EmbeddingProvider] = None
_semaphore: Optional[asyncio.Semaphore] = None
_executor: Optional[ThreadPoolExecutor] = None
_redis_client = None
_cache_ttl: int = 3600


def initialize_provider() -> None:
    """Called once at app startup. Loads model, inits cache, warms up."""
    global _provider, _semaphore, _executor, _redis_client, _cache_ttl
    from vectordb.config import get_settings
    settings = get_settings()

    # Provider
    if settings.embedding_provider == "sentence-transformers":
        _provider = SentenceTransformerProvider(settings.embedding_model)
    elif settings.embedding_provider == "dummy":
        _provider = DummyEmbeddingProvider(settings.vector_dim)
    else:
        raise ValueError(f"Unknown embedding provider: {settings.embedding_provider}")

    # Concurrency: bounded thread pool + semaphore
    _executor = ThreadPoolExecutor(max_workers=settings.max_concurrent_embeddings)
    _semaphore = asyncio.Semaphore(settings.max_concurrent_embeddings)
    _cache_ttl = settings.embedding_cache_ttl

    # Update LRU cache size
    _make_lru_cache(settings.embedding_cache_size)

    # Optional Redis cache
    if settings.redis_url:
        try:
            import redis
            _redis_client = redis.from_url(settings.redis_url, decode_responses=False)
            _redis_client.ping()
            logger.info("embedding_redis_cache_enabled")
        except Exception as e:
            logger.warning("embedding_redis_cache_failed", error=str(e))
            _redis_client = None

    # Warmup: 2 calls to ensure model is fully loaded
    _provider.embed_text("warmup query one")
    _provider.embed_text("warmup query two")

    logger.info("embedding_provider_ready", provider=settings.embedding_provider)


def get_embedding_provider() -> EmbeddingProvider:
    if _provider is None:
        raise RuntimeError("Call initialize_provider() first")
    return _provider


# ---------------------------------------------------------------------------
# Redis helpers (msgpack serialization, sha256 keys)
# ---------------------------------------------------------------------------

def _redis_key(normalized_query: str) -> str:
    return "emb:" + hashlib.sha256(normalized_query.encode()).hexdigest()


def _redis_get(key: str) -> Optional[List[float]]:
    try:
        import msgpack
        raw = _redis_client.get(key)
        if raw is not None:
            return msgpack.unpackb(raw, raw=False)
    except Exception as e:
        logger.warning("embedding_redis_get_failed", key=key, error=str(e))
    return None


def _redis_set(key: str, value: List[float]) -> None:
    try:
        import msgpack
        _redis_client.setex(key, _cache_ttl, msgpack.packb(value, use_bin_type=True))
    except Exception as e:
        logger.warning("embedding_redis_set_failed", key=key, error=str(e))


# ---------------------------------------------------------------------------
# LRU cache (in-memory, tier 2)
# ---------------------------------------------------------------------------

_lru_embed_fn = None


def _make_lru_cache(maxsize: int):
    """Create LRU-cached embed function with configurable size."""
    global _lru_embed_fn

    @lru_cache(maxsize=maxsize)
    def _cached(normalized_key: str) -> tuple:
        return tuple(get_embedding_provider().embed_text(normalized_key))

    _lru_embed_fn = _cached
    return _cached


# Initialize with default size (overridden in initialize_provider)
_make_lru_cache(1000)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def embed_text(text: str) -> List[float]:
    """Uncached embedding — for document upload."""
    return get_embedding_provider().embed_text(text)


def embed_batch(texts: List[str]) -> List[List[float]]:
    """Uncached batch embedding — for document upload."""
    return get_embedding_provider().embed_batch(texts)


def embed_text_cached(query: str) -> List[float]:
    """Sync cached query embedding. Flow: Redis -> LRU -> compute."""
    key = normalize_query(query)

    # Tier 1: Redis
    if _redis_client:
        rkey = _redis_key(key)
        cached = _redis_get(rkey)
        if cached is not None:
            return cached

    # Tier 2: LRU
    result = list(_lru_embed_fn(key))

    # Backfill Redis
    if _redis_client:
        _redis_set(_redis_key(key), result)

    return result


async def embed_text_cached_async(query: str) -> List[float]:
    """Async, non-blocking, concurrency-limited cached embedding."""
    async with _semaphore:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(_executor, embed_text_cached, query)
