"""Synchronous resource classes used by VectorDBClient."""

from __future__ import annotations
from typing import Any

import requests

from vectordb_client._http import _raise_for_response, _unwrap
from vectordb_client.models import (
    ApiKey,
    Collection,
    DocumentUploadResult,
    ExportResult,
    KeyUsageStats,
    QueryResult,
    RerankResult,
    UpsertResult,
    BulkUpsertResult,
    SearchResult,
    VectorResult,
    HealthStats,
)


class _Resource:
    def __init__(self, session: requests.Session, base_url: str) -> None:
        self._session = session
        self._base_url = base_url.rstrip("/")

    def _url(self, path: str) -> str:
        return f"{self._base_url}{path}"

    def _request(self, method: str, path: str, **kwargs) -> Any:
        resp = self._session.request(method, self._url(path), **kwargs)
        body = resp.json()
        # Check HTTP-level errors (transport/middleware failures)
        http_ok = getattr(resp, "ok", None) or getattr(resp, "is_success", False)
        if not http_ok:
            _raise_for_response(resp.status_code, body)
        # Check body-level errors (app returns HTTP 200 with error envelope)
        return _unwrap(body)


class AuthResource(_Resource):
    """User registration and login (no API key required)."""

    def register(self, email: str, password: str) -> dict[str, Any]:
        """Register a new user. Returns { user: {...}, api_key: {...} }."""
        data = self._request("POST", "/v1/auth/register", json={
            "email": email, "password": password,
        })
        return data

    def login(self, email: str, password: str) -> dict[str, Any]:
        """Login an existing user. Returns { user: {...}, api_key: {...} }."""
        data = self._request("POST", "/v1/auth/login", json={
            "email": email, "password": password,
        })
        return data


class CollectionsResource(_Resource):
    """CRUD for collections."""

    def create(
        self,
        name: str,
        dim: int,
        distance_metric: str = "cosine",
        description: str | None = None,
    ) -> Collection:
        payload: dict[str, Any] = {"name": name, "dim": dim, "distance_metric": distance_metric}
        if description is not None:
            payload["description"] = description
        data = self._request("POST", "/v1/collections", json=payload)
        return Collection.from_dict(data)

    def list(self) -> list[Collection]:
        data = self._request("GET", "/v1/collections")
        items = data.get("collections", data) if isinstance(data, dict) else data
        return [Collection.from_dict(c) for c in items]

    def get(self, name: str) -> Collection:
        data = self._request("GET", f"/v1/collections/{name}")
        return Collection.from_dict(data)

    def update(self, name: str, description: str | None) -> Collection:
        """Update a collection's description. Pass None to clear it."""
        data = self._request("PATCH", f"/v1/collections/{name}", json={"description": description})
        return Collection.from_dict(data)

    def export(self, name: str, limit: int = 10000) -> ExportResult:
        """Export all vectors in a collection as float lists."""
        data = self._request("GET", f"/v1/collections/{name}/export", params={"limit": limit})
        return ExportResult.from_dict(data)

    def delete(self, name: str) -> dict:
        return self._request("DELETE", f"/v1/collections/{name}")


class VectorsResource(_Resource):
    """Upsert, bulk upsert, and delete vectors."""

    def upsert(
        self,
        collection: str,
        external_id: str,
        vector: list[float] | None = None,
        metadata: dict[str, Any] | None = None,
        namespace: str | None = None,
        text: str | None = None,
        include_timing: bool = False,
    ) -> UpsertResult:
        payload: dict[str, Any] = {"external_id": external_id}
        if vector is not None:
            payload["vector"] = vector
        if text is not None:
            payload["text"] = text
        if metadata is not None:
            payload["metadata"] = metadata
        if namespace is not None:
            payload["namespace"] = namespace
        if include_timing:
            payload["include_timing"] = True
        data = self._request("POST", f"/v1/collections/{collection}/upsert", json=payload)
        return UpsertResult.from_dict(data)

    def bulk_upsert(
        self,
        collection: str,
        items: list[dict[str, Any]],
        include_timing: bool = False,
    ) -> BulkUpsertResult:
        """
        items: list of dicts with keys: external_id, vector (or text), metadata (optional), namespace (optional)
        """
        payload: dict[str, Any] = {"items": items}
        if include_timing:
            payload["include_timing"] = True
        data = self._request(
            "POST",
            f"/v1/collections/{collection}/bulk_upsert",
            json=payload,
        )
        return BulkUpsertResult.from_dict(data)

    def delete(self, collection: str, external_id: str) -> dict:
        return self._request("DELETE", f"/v1/collections/{collection}/delete/{external_id}")

    def delete_batch(self, collection: str, ids: list[str]) -> dict:
        return self._request(
            "POST",
            f"/v1/collections/{collection}/delete_batch",
            json={"external_ids": ids},
        )


class SearchResource(_Resource):
    """Search, recommend, similarity, rerank, and hybrid search."""

    def search(
        self,
        collection: str,
        vector: list[float] | None = None,
        k: int = 10,
        offset: int = 0,
        filters: dict[str, Any] | None = None,
        text: str | None = None,
        include_timing: bool = False,
    ) -> SearchResult:
        payload: dict[str, Any] = {"k": k, "offset": offset}
        if vector is not None:
            payload["vector"] = vector
        if text is not None:
            payload["text"] = text
        if filters is not None:
            payload["filters"] = filters
        if include_timing:
            payload["include_timing"] = True
        data = self._request("POST", f"/v1/collections/{collection}/search", json=payload)
        return SearchResult.from_dict(data, collection=collection, k=k)

    def recommend(
        self,
        collection: str,
        external_id: str,
        k: int = 10,
        offset: int = 0,
    ) -> SearchResult:
        payload: dict[str, Any] = {"k": k, "offset": offset}
        data = self._request(
            "POST",
            f"/v1/collections/{collection}/recommend/{external_id}",
            json=payload,
        )
        return SearchResult.from_dict(data, collection=collection, k=k)

    def similarity(
        self,
        collection: str,
        id1: str,
        id2: str,
    ) -> float:
        """Compute cosine similarity between two stored vectors by their external IDs."""
        data = self._request(
            "POST",
            f"/v1/collections/{collection}/similarity",
            params={"id1": id1, "id2": id2},
            json={},
        )
        return data["score"]

    def rerank(
        self,
        collection: str,
        query_vector: list[float] | None = None,
        candidates: list[str] | None = None,
        text: str | None = None,
        include_timing: bool = False,
    ) -> RerankResult:
        """Re-score a list of candidate IDs against a query vector or text."""
        payload: dict[str, Any] = {}
        if query_vector is not None:
            payload["vector"] = query_vector
        if text is not None:
            payload["text"] = text
        if candidates is not None:
            payload["candidates"] = candidates
        if include_timing:
            payload["include_timing"] = True
        data = self._request(
            "POST",
            f"/v1/collections/{collection}/rerank",
            json=payload,
        )
        return RerankResult.from_dict(data)

    def hybrid_search(
        self,
        collection: str,
        query_text: str,
        vector: list[float] | None = None,
        k: int = 10,
        offset: int = 0,
        alpha: float = 0.5,
        filters: dict[str, Any] | None = None,
        include_timing: bool = False,
    ) -> SearchResult:
        payload: dict[str, Any] = {
            "query_text": query_text,
            "k": k,
            "offset": offset,
            "alpha": alpha,
        }
        if vector is not None:
            payload["vector"] = vector
        if filters is not None:
            payload["filters"] = filters
        if include_timing:
            payload["include_timing"] = True
        data = self._request(
            "POST",
            f"/v1/collections/{collection}/hybrid_search",
            json=payload,
        )
        return SearchResult.from_dict(data, collection=collection, k=k)


class AdminKeysResource(_Resource):
    """API key lifecycle management."""

    def create(
        self,
        name: str,
        role: str = "readwrite",
        expires_in_days: int | None = None,
    ) -> ApiKey:
        payload: dict[str, Any] = {"name": name, "role": role}
        if expires_in_days is not None:
            payload["expires_in_days"] = expires_in_days
        data = self._request("POST", "/v1/admin/keys", json=payload)
        return ApiKey.from_dict(data)

    def list(self) -> list[ApiKey]:
        data = self._request("GET", "/v1/admin/keys")
        return [ApiKey.from_dict(k) for k in data["keys"]]

    def get(self, key_id: int) -> ApiKey:
        data = self._request("GET", f"/v1/admin/keys/{key_id}")
        return ApiKey.from_dict(data)

    def update(
        self,
        key_id: int,
        name: str | None = None,
        role: str | None = None,
        is_active: bool | None = None,
    ) -> ApiKey:
        payload: dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if role is not None:
            payload["role"] = role
        if is_active is not None:
            payload["is_active"] = is_active
        data = self._request("PATCH", f"/v1/admin/keys/{key_id}", json=payload)
        return ApiKey.from_dict(data)

    def revoke(self, key_id: int) -> ApiKey:
        """Deactivate a key without deleting it."""
        return self.update(key_id, is_active=False)

    def restore(self, key_id: int) -> ApiKey:
        """Re-activate a previously revoked key."""
        return self.update(key_id, is_active=True)

    def rotate(self, key_id: int) -> ApiKey:
        """Regenerate the key value. Returns the new key value (shown once)."""
        data = self._request("POST", f"/v1/admin/keys/{key_id}/rotate")
        return ApiKey.from_dict(data)

    def delete(self, key_id: int) -> dict:
        return self._request("DELETE", f"/v1/admin/keys/{key_id}")

    def get_usage(self, key_id: int) -> KeyUsageStats:
        data = self._request("GET", f"/v1/admin/keys/{key_id}/usage")
        return KeyUsageStats.from_dict(data)

    def get_usage_summary(self) -> dict[str, Any]:
        """Returns overall stats and per-key breakdown."""
        return self._request("GET", "/v1/admin/keys/usage/summary")


class DocumentsResource(_Resource):
    """Document upload for RAG pipelines."""

    def upload(
        self,
        collection_name: str,
        file_path: str,
        include_timing: bool = False,
    ) -> DocumentUploadResult:
        """Upload a .txt file to be chunked and stored in a collection.

        Args:
            collection_name: Target collection name.
            file_path: Path to a .txt file on the local filesystem.
            include_timing: When True, the result includes a timing_ms breakdown.

        Returns:
            DocumentUploadResult with document_id and chunks_created count.
        """
        form: dict[str, Any] = {"collection_name": collection_name}
        if include_timing:
            form["include_timing"] = "true"
        with open(file_path, "rb") as f:
            # Multipart upload — do NOT send the default Content-Type header;
            # requests will set the correct multipart boundary automatically.
            resp = self._session.post(
                self._url("/v1/documents/upload"),
                data=form,
                files={"file": (f.name.split("/")[-1], f, "text/plain")},
            )
        body = resp.json()
        http_ok = getattr(resp, "ok", None) or getattr(resp, "is_success", False)
        if not http_ok:
            _raise_for_response(resp.status_code, body)
        data = _unwrap(body)
        return DocumentUploadResult.from_dict(data)


class QueryResource(_Resource):
    """RAG query — semantic search that returns text chunks."""

    def query(
        self,
        query: str,
        collection_name: str,
        top_k: int = 5,
        filters: dict[str, Any] | None = None,
        include_timing: bool = False,
    ) -> QueryResult:
        """Run a natural-language query against a collection.

        Args:
            query: The query text.
            collection_name: Collection to search in.
            top_k: Number of results to return (default 5).
            filters: Optional metadata filters.
            include_timing: When True, the result includes a timing_ms breakdown.

        Returns:
            QueryResult containing matching text chunks with scores.
        """
        payload: dict[str, Any] = {
            "query": query,
            "collection_name": collection_name,
            "top_k": top_k,
        }
        if filters is not None:
            payload["filters"] = filters
        if include_timing:
            payload["include_timing"] = True
        data = self._request("POST", "/v1/query", json=payload)
        return QueryResult.from_dict(data)


class ObservabilityResource(_Resource):
    """Health and metrics."""

    def health(self) -> HealthStats:
        data = self._request("GET", "/v1/health")
        return HealthStats.from_dict(data)
