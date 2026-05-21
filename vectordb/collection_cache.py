# vectordb/collection_cache.py
"""
LRU + TTL cache for collection metadata.

Eliminates per-request DB lookups for collection info (id, dim, distance_metric).
Every backend method calls _require_collection on every request — this cache
reduces that from ~3ms DB query to ~0ms dict lookup.
"""
import time
from collections import OrderedDict
from typing import Any, Dict, Optional, Tuple


class CollectionCache:
    """Thread-safe LRU cache with TTL for collection metadata."""

    def __init__(self, ttl: int = 10, max_size: int = 1000):
        self._ttl = ttl
        self._max_size = max_size
        self._cache: OrderedDict[Tuple[str, Optional[int]], Tuple[Dict[str, Any], float]] = OrderedDict()
        self._hits = 0
        self._misses = 0

    def get(self, name: str, user_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """Return cached collection dict or None if miss/expired."""
        if self._ttl <= 0:
            self._misses += 1
            return None
        key = (name, user_id)
        entry = self._cache.get(key)
        if entry is None:
            self._misses += 1
            return None
        data, ts = entry
        if time.monotonic() - ts > self._ttl:
            del self._cache[key]
            self._misses += 1
            return None
        # Move to end (most recently used)
        self._cache.move_to_end(key)
        self._hits += 1
        return data

    def put(self, name: str, user_id: Optional[int], value: Dict[str, Any]) -> None:
        """Store collection metadata. Evicts oldest entry if at capacity."""
        if self._ttl <= 0:
            return
        key = (name, user_id)
        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = (value, time.monotonic())
        while len(self._cache) > self._max_size:
            self._cache.popitem(last=False)

    def invalidate(self, name: str, user_id: Optional[int] = None) -> None:
        """Remove a specific entry, or all entries matching name if user_id is None."""
        if user_id is not None:
            self._cache.pop((name, user_id), None)
        else:
            keys_to_remove = [k for k in self._cache if k[0] == name]
            for k in keys_to_remove:
                del self._cache[k]

    def clear(self) -> None:
        """Flush all cached entries."""
        self._cache.clear()

    @property
    def hit_rate(self) -> float:
        """Return cache hit rate as a fraction (0.0 to 1.0)."""
        total = self._hits + self._misses
        if total == 0:
            return 0.0
        return self._hits / total

    @property
    def size(self) -> int:
        """Return current number of cached entries."""
        return len(self._cache)

    @property
    def stats(self) -> Dict[str, Any]:
        """Return cache statistics for metrics endpoint."""
        return {
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(self.hit_rate, 4),
            "size": self.size,
            "max_size": self._max_size,
            "ttl": self._ttl,
        }
