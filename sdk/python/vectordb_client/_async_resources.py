"""Async resource classes used by AsyncVectorDBClient."""

from __future__ import annotations
from typing import Any

import httpx

from vectordb_client._http import _raise_for_response, _unwrap
from vectordb_client.models import (
    ApiKey,
    Collection,
    ExportResult,
    KeyUsageStats,
    UpsertResult,
    BulkUpsertResult,
    SearchResult,
    VectorResult,
    HealthStats,
)


class _AsyncResource:
    def __init__(self, client: httpx.AsyncClient, base_url: str) -> None:
        self._client = client
        self._base_url = base_url.rstrip("/")

    def _url(self, path: str) -> str:
        return f"{self._base_url}{path}"

    async def _request(self, method: str, path: str, **kwargs) -> Any:
        resp = await self._client.request(method, self._url(path), **kwargs)
        body = resp.json()
        if not resp.is_success:
            _raise_for_response(resp.status_code, body)
        # Check body-level errors (app returns HTTP 200 with error envelope)
        return _unwrap(body)


class AsyncCollectionsResource(_AsyncResource):
    async def create(
        self,
        name: str,
        dim: int,
        distance_metric: str = "cosine",
        description: str | None = None,
    ) -> Collection:
        payload: dict[str, Any] = {"name": name, "dim": dim, "distance_metric": distance_metric}
        if description is not None:
            payload["description"] = description
        data = await self._request("POST", "/v1/collections", json=payload)
        return Collection.from_dict(data)

    async def list(self) -> list[Collection]:
        data = await self._request("GET", "/v1/collections")
        items = data.get("collections", data) if isinstance(data, dict) else data
        return [Collection.from_dict(c) for c in items]

    async def get(self, name: str) -> Collection:
        data = await self._request("GET", f"/v1/collections/{name}")
        return Collection.from_dict(data)

    async def update(self, name: str, description: str | None) -> Collection:
        """Update a collection's description. Pass None to clear it."""
        data = await self._request("PATCH", f"/v1/collections/{name}", json={"description": description})
        return Collection.from_dict(data)

    async def export(self, name: str, limit: int = 10000) -> ExportResult:
        """Export all vectors in a collection as float lists."""
        data = await self._request("GET", f"/v1/collections/{name}/export", params={"limit": limit})
        return ExportResult.from_dict(data)

    async def delete(self, name: str) -> dict:
        return await self._request("DELETE", f"/v1/collections/{name}")


class AsyncVectorsResource(_AsyncResource):
    async def upsert(
        self,
        collection: str,
        external_id: str,
        vector: list[float],
        metadata: dict[str, Any] | None = None,
        namespace: str | None = None,
    ) -> UpsertResult:
        payload: dict[str, Any] = {"external_id": external_id, "vector": vector}
        if metadata is not None:
            payload["metadata"] = metadata
        if namespace is not None:
            payload["namespace"] = namespace
        data = await self._request("POST", f"/v1/collections/{collection}/upsert", json=payload)
        return UpsertResult.from_dict(data)

    async def bulk_upsert(self, collection: str, items: list[dict[str, Any]]) -> BulkUpsertResult:
        data = await self._request(
            "POST",
            f"/v1/collections/{collection}/bulk_upsert",
            json={"items": items},
        )
        return BulkUpsertResult.from_dict(data)

    async def delete(self, collection: str, external_id: str) -> dict:
        return await self._request("DELETE", f"/v1/collections/{collection}/delete/{external_id}")

    async def delete_batch(self, collection: str, ids: list[str]) -> dict:
        return await self._request(
            "POST",
            f"/v1/collections/{collection}/delete_batch",
            json={"external_ids": ids},
        )


class AsyncSearchResource(_AsyncResource):
    async def search(
        self,
        collection: str,
        vector: list[float],
        k: int = 10,
        offset: int = 0,
        filters: dict[str, Any] | None = None,
    ) -> SearchResult:
        payload: dict[str, Any] = {"vector": vector, "k": k, "offset": offset}
        if filters is not None:
            payload["filters"] = filters
        data = await self._request("POST", f"/v1/collections/{collection}/search", json=payload)
        return SearchResult.from_dict(data, collection=collection, k=k)

    async def recommend(
        self,
        collection: str,
        external_id: str,
        k: int = 10,
        offset: int = 0,
    ) -> SearchResult:
        data = await self._request(
            "POST",
            f"/v1/collections/{collection}/recommend/{external_id}",
            json={"k": k, "offset": offset},
        )
        return SearchResult.from_dict(data, collection=collection, k=k)

    async def similarity(
        self,
        collection: str,
        id1: str,
        id2: str,
    ) -> float:
        """Compute cosine similarity between two stored vectors by their external IDs."""
        data = await self._request(
            "POST",
            f"/v1/collections/{collection}/similarity",
            params={"id1": id1, "id2": id2},
            json={},
        )
        return data["score"]

    async def rerank(
        self,
        collection: str,
        query_vector: list[float],
        candidates: list[str],
    ) -> list[VectorResult]:
        """Re-score a list of candidate IDs against a query vector."""
        data = await self._request(
            "POST",
            f"/v1/collections/{collection}/rerank",
            json={"vector": query_vector, "candidates": candidates},
        )
        return [VectorResult.from_dict(r) for r in data["results"]]

    async def hybrid_search(
        self,
        collection: str,
        query_text: str,
        vector: list[float],
        k: int = 10,
        offset: int = 0,
        alpha: float = 0.5,
        filters: dict[str, Any] | None = None,
    ) -> SearchResult:
        payload: dict[str, Any] = {
            "query_text": query_text,
            "vector": vector,
            "k": k,
            "offset": offset,
            "alpha": alpha,
        }
        if filters is not None:
            payload["filters"] = filters
        data = await self._request(
            "POST",
            f"/v1/collections/{collection}/hybrid_search",
            json=payload,
        )
        return SearchResult.from_dict(data, collection=collection, k=k)


class AsyncAdminKeysResource(_AsyncResource):
    """API key lifecycle management."""

    async def create(
        self,
        name: str,
        role: str = "readwrite",
        expires_in_days: int | None = None,
    ) -> ApiKey:
        payload: dict[str, Any] = {"name": name, "role": role}
        if expires_in_days is not None:
            payload["expires_in_days"] = expires_in_days
        data = await self._request("POST", "/v1/admin/keys", json=payload)
        return ApiKey.from_dict(data)

    async def list(self) -> list[ApiKey]:
        data = await self._request("GET", "/v1/admin/keys")
        return [ApiKey.from_dict(k) for k in data["keys"]]

    async def get(self, key_id: int) -> ApiKey:
        data = await self._request("GET", f"/v1/admin/keys/{key_id}")
        return ApiKey.from_dict(data)

    async def update(
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
        data = await self._request("PATCH", f"/v1/admin/keys/{key_id}", json=payload)
        return ApiKey.from_dict(data)

    async def revoke(self, key_id: int) -> ApiKey:
        return await self.update(key_id, is_active=False)

    async def restore(self, key_id: int) -> ApiKey:
        return await self.update(key_id, is_active=True)

    async def rotate(self, key_id: int) -> ApiKey:
        data = await self._request("POST", f"/v1/admin/keys/{key_id}/rotate")
        return ApiKey.from_dict(data)

    async def delete(self, key_id: int) -> dict:
        return await self._request("DELETE", f"/v1/admin/keys/{key_id}")

    async def get_usage(self, key_id: int) -> KeyUsageStats:
        data = await self._request("GET", f"/v1/admin/keys/{key_id}/usage")
        return KeyUsageStats.from_dict(data)

    async def get_usage_summary(self) -> dict[str, Any]:
        return await self._request("GET", "/v1/admin/keys/usage/summary")


class AsyncObservabilityResource(_AsyncResource):
    async def health(self) -> HealthStats:
        data = await self._request("GET", "/v1/health")
        return HealthStats.from_dict(data)
