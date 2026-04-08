"""Synchronous VectorDB client."""

from __future__ import annotations

import requests

from vectordb_client._resources import (
    AdminKeysResource,
    CollectionsResource,
    VectorsResource,
    SearchResource,
    ObservabilityResource,
)


class VectorDBClient:
    """
    Synchronous client for the VectorDB REST API.

    Args:
        base_url: Base URL of the VectorDB server (e.g. "http://localhost:8000")
        api_key: API key for authentication
        timeout: Request timeout in seconds (default: 30)
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        timeout: int = 30,
    ) -> None:
        self._session = requests.Session()
        self._session.headers.update({
            "x-api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        })
        self._session.timeout = timeout  # type: ignore[assignment]

        self.collections = CollectionsResource(self._session, base_url)
        self.vectors = VectorsResource(self._session, base_url)
        self.search = SearchResource(self._session, base_url)
        self.observability = ObservabilityResource(self._session, base_url)
        self.keys = AdminKeysResource(self._session, base_url)

    def close(self) -> None:
        """Close the underlying HTTP session."""
        self._session.close()

    def __enter__(self) -> "VectorDBClient":
        return self

    def __exit__(self, *args) -> None:
        self.close()

    def ping(self) -> bool:
        """Return True if the server is reachable."""
        try:
            resp = self._session.get(
                self.collections._url("/"),
                timeout=5,
            )
            return resp.ok
        except Exception:
            return False
