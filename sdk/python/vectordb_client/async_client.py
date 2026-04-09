"""Async VectorDB client."""

from __future__ import annotations

import httpx

from vectordb_client._async_resources import (
    AsyncAdminKeysResource,
    AsyncAuthResource,
    AsyncCollectionsResource,
    AsyncDocumentsResource,
    AsyncQueryResource,
    AsyncVectorsResource,
    AsyncSearchResource,
    AsyncObservabilityResource,
)


class AsyncVectorDBClient:
    """
    Async client for the VectorDB REST API.

    Args:
        base_url: Base URL of the VectorDB server (e.g. "http://localhost:8000")
        api_key: API key for authentication
        timeout: Request timeout in seconds (default: 30)

    Usage:
        async with AsyncVectorDBClient("http://localhost:8000", "my-key") as client:
            await client.collections.create("my-col", dim=384)
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        timeout: int = 30,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout
        self._http: httpx.AsyncClient | None = None

        # Resources are attached after _http is initialized
        self.auth: AsyncAuthResource
        self.collections: AsyncCollectionsResource
        self.vectors: AsyncVectorsResource
        self.search: AsyncSearchResource
        self.documents: AsyncDocumentsResource
        self.query: AsyncQueryResource
        self.observability: AsyncObservabilityResource
        self.keys: AsyncAdminKeysResource

    def _init_resources(self) -> None:
        assert self._http is not None
        self.auth = AsyncAuthResource(self._http, self._base_url)
        self.collections = AsyncCollectionsResource(self._http, self._base_url)
        self.vectors = AsyncVectorsResource(self._http, self._base_url)
        self.search = AsyncSearchResource(self._http, self._base_url)
        self.documents = AsyncDocumentsResource(self._http, self._base_url)
        self.query = AsyncQueryResource(self._http, self._base_url)
        self.observability = AsyncObservabilityResource(self._http, self._base_url)
        self.keys = AsyncAdminKeysResource(self._http, self._base_url)

    async def __aenter__(self) -> "AsyncVectorDBClient":
        self._http = httpx.AsyncClient(
            headers={
                "x-api-key": self._api_key,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            timeout=self._timeout,
        )
        self._init_resources()
        return self

    async def __aexit__(self, *args) -> None:
        await self.close()

    async def close(self) -> None:
        if self._http:
            await self._http.aclose()
            self._http = None

    async def ping(self) -> bool:
        """Return True if the server is reachable."""
        try:
            assert self._http is not None
            resp = await self._http.get(f"{self._base_url}/", timeout=5)
            return resp.is_success
        except Exception:
            return False
