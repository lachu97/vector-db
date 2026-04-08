"""
VectorDB Python SDK — synchronous and async clients for the VectorDB REST API.

Usage (sync):
    from vectordb_client import VectorDBClient
    client = VectorDBClient(base_url="http://localhost:8000", api_key="your-key")
    client.collections.create("my-col", dim=384, distance_metric="cosine")

Usage (async):
    from vectordb_client import AsyncVectorDBClient
    async with AsyncVectorDBClient(base_url="http://localhost:8000", api_key="your-key") as client:
        await client.collections.create("my-col", dim=384)
"""

from vectordb_client.client import VectorDBClient
from vectordb_client.async_client import AsyncVectorDBClient
from vectordb_client.exceptions import (
    VectorDBError,
    NotFoundError,
    AlreadyExistsError,
    DimensionMismatchError,
    AuthenticationError,
    RateLimitError,
)
from vectordb_client.models import (
    ApiKey,
    Collection,
    ExportResult,
    ExportedVector,
    KeyUsageStats,
    VectorResult,
    SearchResult,
    UpsertResult,
    BulkUpsertResult,
    HealthStats,
)

__version__ = "0.2.0"
__all__ = [
    "VectorDBClient",
    "AsyncVectorDBClient",
    "VectorDBError",
    "NotFoundError",
    "AlreadyExistsError",
    "DimensionMismatchError",
    "AuthenticationError",
    "RateLimitError",
    "ApiKey",
    "Collection",
    "ExportResult",
    "ExportedVector",
    "KeyUsageStats",
    "VectorResult",
    "SearchResult",
    "UpsertResult",
    "BulkUpsertResult",
    "HealthStats",
]
