# vectordb/indexing/manager.py
import os
import threading

import structlog

from vectordb.indexing.hnsw import HNSWIndexer
from vectordb.config import get_settings

logger = structlog.get_logger(__name__)


class IndexManager:
    """Manages per-collection HNSW indexes."""

    def __init__(self):
        self.settings = get_settings()
        self._indexes: dict[str, HNSWIndexer] = {}
        self._lock = threading.Lock()
        # Base directory for index files
        self._base_dir = os.path.dirname(self.settings.index_path)
        os.makedirs(self._base_dir, exist_ok=True)

    def _index_path(self, collection_name: str) -> str:
        return os.path.join(self._base_dir, f"{collection_name}.bin")

    def get_or_create(self, collection_name: str, dim: int, space: str = "cosine") -> HNSWIndexer:
        """Get an existing indexer or create a new one for the collection."""
        with self._lock:
            if collection_name not in self._indexes:
                idx_path = self._index_path(collection_name)
                indexer = HNSWIndexer(
                    dim=dim,
                    space=space,
                    max_elements=self.settings.max_elements,
                    ef_construction=self.settings.ef_construction,
                    m=self.settings.m,
                    ef_query=self.settings.ef_query,
                    index_path=idx_path,
                )
                self._indexes[collection_name] = indexer
                logger.info("index_loaded_or_created", collection=collection_name, dim=dim, space=space)
            return self._indexes[collection_name]

    def get(self, collection_name: str) -> HNSWIndexer | None:
        """Get an existing indexer, returns None if not loaded."""
        return self._indexes.get(collection_name)

    def remove(self, collection_name: str):
        """Remove an indexer and delete its index file."""
        with self._lock:
            indexer = self._indexes.pop(collection_name, None)
            idx_path = self._index_path(collection_name)
            if os.path.exists(idx_path):
                os.remove(idx_path)
                logger.info("index_file_deleted", collection=collection_name)

    def save_all(self):
        """Save all indexes to disk."""
        with self._lock:
            for name, indexer in self._indexes.items():
                try:
                    indexer.save()
                except Exception as e:
                    logger.error("index_save_failed", collection=name, error=str(e))

    def collection_names(self) -> list[str]:
        """Return names of all loaded collections."""
        return list(self._indexes.keys())
