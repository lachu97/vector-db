"""Data models returned by the VectorDB SDK."""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Collection:
    name: str
    dim: int
    distance_metric: str
    vector_count: int = 0
    created_at: str | None = None
    description: str | None = None

    @classmethod
    def from_dict(cls, d: dict) -> "Collection":
        return cls(
            name=d["name"],
            dim=d["dim"],
            distance_metric=d["distance_metric"],
            vector_count=d.get("vector_count", 0),
            created_at=d.get("created_at"),
            description=d.get("description"),
        )


@dataclass
class UpsertResult:
    external_id: str
    status: str  # "inserted" | "updated"

    @classmethod
    def from_dict(cls, d: dict) -> "UpsertResult":
        return cls(external_id=d["external_id"], status=d["status"])


@dataclass
class BulkUpsertResult:
    results: list[UpsertResult]

    @property
    def inserted(self) -> list[UpsertResult]:
        return [r for r in self.results if r.status == "inserted"]

    @property
    def updated(self) -> list[UpsertResult]:
        return [r for r in self.results if r.status == "updated"]

    @classmethod
    def from_dict(cls, d: dict) -> "BulkUpsertResult":
        return cls(results=[UpsertResult.from_dict(r) for r in d["results"]])


@dataclass
class VectorResult:
    external_id: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict) -> "VectorResult":
        return cls(
            external_id=d["external_id"],
            score=d.get("score", 0.0),
            metadata=d.get("metadata") or {},
        )


@dataclass
class SearchResult:
    results: list[VectorResult]
    collection: str
    k: int
    total_count: int = -1
    offset: int = 0

    def __iter__(self):
        return iter(self.results)

    def __len__(self):
        return len(self.results)

    def __getitem__(self, idx):
        return self.results[idx]

    @classmethod
    def from_dict(cls, d: dict, collection: str, k: int) -> "SearchResult":
        return cls(
            results=[VectorResult.from_dict(r) for r in d["results"]],
            collection=collection,
            k=k,
            total_count=d.get("total_count", -1),
            offset=d.get("offset", 0),
        )


@dataclass
class ExportedVector:
    external_id: str
    vector: list[float]
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict) -> "ExportedVector":
        return cls(
            external_id=d["external_id"],
            vector=d["vector"],
            metadata=d.get("metadata") or {},
        )


@dataclass
class ExportResult:
    collection: str
    dim: int
    distance_metric: str
    count: int
    vectors: list[ExportedVector]

    @classmethod
    def from_dict(cls, d: dict) -> "ExportResult":
        return cls(
            collection=d["collection"],
            dim=d["dim"],
            distance_metric=d["distance_metric"],
            count=d["count"],
            vectors=[ExportedVector.from_dict(v) for v in d["vectors"]],
        )


@dataclass
class ApiKey:
    id: int
    name: str
    role: str
    is_active: bool
    created_at: str
    expires_at: str | None = None
    last_used_at: str | None = None
    key: str | None = None  # only present at creation/rotation

    @classmethod
    def from_dict(cls, d: dict) -> "ApiKey":
        return cls(
            id=d["id"],
            name=d["name"],
            role=d["role"],
            is_active=d["is_active"],
            created_at=d["created_at"],
            expires_at=d.get("expires_at"),
            last_used_at=d.get("last_used_at"),
            key=d.get("key"),
        )


@dataclass
class KeyUsageStats:
    total_requests: int
    last_24h: int
    last_7d: int
    last_30d: int
    by_endpoint: dict[str, int]
    last_request_at: str | None = None
    key_id: int | None = None
    key_name: str | None = None

    @classmethod
    def from_dict(cls, d: dict) -> "KeyUsageStats":
        return cls(
            total_requests=d.get("total_requests", 0),
            last_24h=d.get("last_24h", 0),
            last_7d=d.get("last_7d", 0),
            last_30d=d.get("last_30d", 0),
            by_endpoint=d.get("by_endpoint", {}),
            last_request_at=d.get("last_request_at"),
            key_id=d.get("key_id"),
            key_name=d.get("key_name"),
        )


@dataclass
class HealthStats:
    status: str
    total_vectors: int
    total_collections: int
    collections: list[dict]
    uptime_seconds: float | None = None

    @classmethod
    def from_dict(cls, d: dict) -> "HealthStats":
        return cls(
            status=d.get("status", "ok"),
            total_vectors=d.get("total_vectors", 0),
            total_collections=d.get("total_collections", 0),
            collections=d.get("collections", []),
            uptime_seconds=d.get("uptime_seconds"),
        )
