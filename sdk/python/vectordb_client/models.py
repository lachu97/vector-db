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

    @classmethod
    def from_dict(cls, d: dict) -> "Collection":
        return cls(
            name=d["name"],
            dim=d["dim"],
            distance_metric=d["distance_metric"],
            vector_count=d.get("vector_count", 0),
            created_at=d.get("created_at"),
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
