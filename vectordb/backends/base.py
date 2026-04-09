# vectordb/backends/base.py
"""
Abstract base class for all vector storage backends.

Each backend must implement every async method below.
The routers depend only on this interface — swapping backends
requires no router changes.
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Domain exceptions
# ---------------------------------------------------------------------------

class CollectionNotFoundError(Exception):
    def __init__(self, name: str):
        self.name = name
        super().__init__(f"Collection '{name}' not found")


class CollectionAlreadyExistsError(Exception):
    def __init__(self, name: str):
        self.name = name
        super().__init__(f"Collection '{name}' already exists")


class DimensionMismatchError(Exception):
    def __init__(self, expected: int, got: int):
        self.expected = expected
        self.got = got
        super().__init__(f"Vector dimension must be {expected}, got {got}")


class VectorNotFoundError(Exception):
    def __init__(self, external_id: str):
        self.external_id = external_id
        super().__init__(f"Vector '{external_id}' not found")


# ---------------------------------------------------------------------------
# Backend interface
# ---------------------------------------------------------------------------

class VectorBackend(ABC):
    """All methods are async. Implementations must not block the event loop."""

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    @abstractmethod
    async def startup(self) -> None:
        """Called once at application startup (create tables, warm up pools)."""

    @abstractmethod
    async def shutdown(self) -> None:
        """Called once at application shutdown (persist indexes, close pools)."""

    # ------------------------------------------------------------------
    # Collections
    # ------------------------------------------------------------------

    @abstractmethod
    async def create_collection(
        self, name: str, dim: int, distance_metric: str,
        description: Optional[str] = None, user_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Create a new collection. Raises CollectionAlreadyExistsError if it exists."""

    @abstractmethod
    async def get_collection(self, name: str, user_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """Return collection info dict or None if not found.
        If user_id is set, only return collections owned by that user or global (user_id=None).
        If user_id param is None (bootstrap), return any collection."""

    @abstractmethod
    async def list_collections(self, user_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Return list of collection info dicts.
        If user_id is set, only return collections owned by that user or global (user_id=None).
        If user_id param is None (bootstrap), return all."""

    @abstractmethod
    async def delete_collection(self, name: str, user_id: Optional[int] = None) -> None:
        """Delete a collection and all its vectors. Raises CollectionNotFoundError.
        If user_id is set, only delete if the collection belongs to that user (not global)."""

    # ------------------------------------------------------------------
    # Vectors
    # ------------------------------------------------------------------

    @abstractmethod
    async def upsert(
        self,
        collection_name: str,
        external_id: str,
        vector: List[float],
        metadata: Optional[Dict[str, Any]],
        content: Optional[str],
    ) -> Dict[str, Any]:
        """
        Insert or update a vector.
        Raises CollectionNotFoundError, DimensionMismatchError.
        Returns {"external_id", "status": "inserted"|"updated"}.
        """

    @abstractmethod
    async def bulk_upsert(
        self, collection_name: str, items: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Batch insert/update.
        Raises CollectionNotFoundError, DimensionMismatchError.
        Returns list of {"external_id", "status"}.
        """

    @abstractmethod
    async def delete_vector(self, collection_name: str, external_id: str) -> Dict[str, Any]:
        """
        Delete a single vector.
        Raises CollectionNotFoundError, VectorNotFoundError.
        Returns {"status": "deleted", "external_id"}.
        """

    @abstractmethod
    async def batch_delete(
        self, collection_name: str, external_ids: List[str]
    ) -> Dict[str, Any]:
        """
        Delete multiple vectors.
        Raises CollectionNotFoundError.
        Returns {"deleted": [...], "not_found": [...], "deleted_count": int}.
        """

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    @abstractmethod
    async def search(
        self,
        collection_name: str,
        vector: List[float],
        k: int,
        offset: int,
        filters: Optional[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """KNN search. Returns list of {"external_id", "score", "metadata"}."""

    @abstractmethod
    async def recommend(
        self, collection_name: str, external_id: str, k: int, ef: int
    ) -> List[Dict[str, Any]]:
        """Similar vectors excluding self. Returns list of {"external_id", "score", "metadata"}."""

    @abstractmethod
    async def similarity(
        self, collection_name: str, id1: str, id2: str
    ) -> float:
        """Cosine similarity between two vectors. Raises VectorNotFoundError."""

    @abstractmethod
    async def rerank(
        self,
        collection_name: str,
        query_vector: List[float],
        candidates: List[str],
    ) -> List[Dict[str, Any]]:
        """Re-score candidates by similarity to query. Returns sorted list."""

    @abstractmethod
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
        """Combined vector + text search via RRF."""

    # ------------------------------------------------------------------
    # Observability
    # ------------------------------------------------------------------

    @abstractmethod
    async def health_stats(self) -> Dict[str, Any]:
        """
        Return {"total_vectors", "total_collections", "collections": [...]}.
        Used by the health endpoint.
        """

    # ------------------------------------------------------------------
    # Optional extensions (non-abstract — backends return None/[] if unsupported)
    # ------------------------------------------------------------------

    async def update_collection(
        self, name: str, description: Optional[str], user_id: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """Update collection metadata. Returns updated dict or None if unsupported.
        If user_id is set, only update if the collection belongs to that user."""
        return None

    async def count_vectors(
        self, collection_name: str, filters: Optional[Dict[str, Any]] = None
    ) -> int:
        """Return total number of vectors matching optional filters. Returns -1 if unsupported."""
        return -1

    async def export_vectors(
        self, collection_name: str, limit: int = 10000
    ) -> List[Dict[str, Any]]:
        """Export vectors as list of {external_id, vector, metadata}. Returns [] if unsupported."""
        return []
