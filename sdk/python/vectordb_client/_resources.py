"""Synchronous resource classes used by VectorDBClient."""

from __future__ import annotations
from typing import Any

import requests

from vectordb_client._http import _raise_for_response, _unwrap
from vectordb_client.models import (
    Collection,
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


class CollectionsResource(_Resource):
    """CRUD for collections."""

    def create(
        self,
        name: str,
        dim: int,
        distance_metric: str = "cosine",
    ) -> Collection:
        data = self._request("POST", "/v1/collections", json={
            "name": name,
            "dim": dim,
            "distance_metric": distance_metric,
        })
        return Collection.from_dict(data)

    def list(self) -> list[Collection]:
        data = self._request("GET", "/v1/collections")
        # API returns {"collections": [...]}
        items = data.get("collections", data) if isinstance(data, dict) else data
        return [Collection.from_dict(c) for c in items]

    def get(self, name: str) -> Collection:
        data = self._request("GET", f"/v1/collections/{name}")
        return Collection.from_dict(data)

    def delete(self, name: str) -> dict:
        return self._request("DELETE", f"/v1/collections/{name}")


class VectorsResource(_Resource):
    """Upsert, bulk upsert, and delete vectors."""

    def upsert(
        self,
        collection: str,
        external_id: str,
        vector: list[float],
        metadata: dict[str, Any] | None = None,
        namespace: str | None = None,
    ) -> UpsertResult:
        payload: dict[str, Any] = {
            "external_id": external_id,
            "vector": vector,
        }
        if metadata is not None:
            payload["metadata"] = metadata
        if namespace is not None:
            payload["namespace"] = namespace
        data = self._request("POST", f"/v1/collections/{collection}/upsert", json=payload)
        return UpsertResult.from_dict(data)

    def bulk_upsert(
        self,
        collection: str,
        items: list[dict[str, Any]],
    ) -> BulkUpsertResult:
        """
        items: list of dicts with keys: external_id, vector, metadata (optional), namespace (optional)
        """
        data = self._request(
            "POST",
            f"/v1/collections/{collection}/bulk_upsert",
            json={"items": items},
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
        vector: list[float],
        k: int = 10,
        offset: int = 0,
        filters: dict[str, Any] | None = None,
    ) -> SearchResult:
        payload: dict[str, Any] = {"vector": vector, "k": k, "offset": offset}
        if filters is not None:
            payload["filters"] = filters
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
        query_vector: list[float],
        candidates: list[str],
    ) -> list[VectorResult]:
        """Re-score a list of candidate IDs against a query vector."""
        data = self._request(
            "POST",
            f"/v1/collections/{collection}/rerank",
            json={"vector": query_vector, "candidates": candidates},
        )
        return [VectorResult.from_dict(r) for r in data["results"]]

    def hybrid_search(
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
        data = self._request(
            "POST",
            f"/v1/collections/{collection}/hybrid_search",
            json=payload,
        )
        return SearchResult.from_dict(data, collection=collection, k=k)


class ObservabilityResource(_Resource):
    """Health and metrics."""

    def health(self) -> HealthStats:
        data = self._request("GET", "/v1/health")
        return HealthStats.from_dict(data)
