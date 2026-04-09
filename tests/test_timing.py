# tests/test_timing.py
"""Tests for optional timing metrics in API responses."""
import io

import pytest
from tests.conftest import random_vector

COLLECTION = "timing-test"
DIM = 384


@pytest.fixture(scope="class")
def timing_collection(client, headers):
    client.post(
        "/v1/collections",
        json={"name": COLLECTION, "dim": DIM, "distance_metric": "cosine"},
        headers=headers,
    )
    # Seed data
    items = [
        {"external_id": f"timing-{i}", "text": f"timing test document {i}"}
        for i in range(3)
    ]
    client.post(
        f"/v1/collections/{COLLECTION}/bulk_upsert",
        json={"items": items},
        headers=headers,
    )


class TestUpsertTiming:
    @pytest.fixture(autouse=True)
    def setup(self, timing_collection):
        pass

    def test_upsert_no_timing_by_default(self, client, headers):
        resp = client.post(
            f"/v1/collections/{COLLECTION}/upsert",
            json={"external_id": "no-timing", "text": "test"},
            headers=headers,
        )
        data = resp.json()["data"]
        assert "timing_ms" not in data

    def test_upsert_with_timing(self, client, headers):
        resp = client.post(
            f"/v1/collections/{COLLECTION}/upsert",
            json={"external_id": "with-timing", "text": "test", "include_timing": True},
            headers=headers,
        )
        data = resp.json()["data"]
        assert "timing_ms" in data
        t = data["timing_ms"]
        assert "embedding_ms" in t
        assert "storage_ms" in t
        assert "total_ms" in t
        assert t["embedding_ms"] >= 0
        assert t["storage_ms"] >= 0
        assert t["total_ms"] >= t["embedding_ms"]

    def test_upsert_vector_timing_zero_embedding(self, client, headers):
        resp = client.post(
            f"/v1/collections/{COLLECTION}/upsert",
            json={"external_id": "vec-timing", "vector": random_vector(DIM), "include_timing": True},
            headers=headers,
        )
        t = resp.json()["data"]["timing_ms"]
        assert t["embedding_ms"] == 0.0


class TestBulkUpsertTiming:
    @pytest.fixture(autouse=True)
    def setup(self, timing_collection):
        pass

    def test_bulk_upsert_no_timing_by_default(self, client, headers):
        resp = client.post(
            f"/v1/collections/{COLLECTION}/bulk_upsert",
            json={"items": [{"external_id": "bulk-no-t", "text": "test"}]},
            headers=headers,
        )
        assert "timing_ms" not in resp.json()["data"]

    def test_bulk_upsert_with_timing(self, client, headers):
        resp = client.post(
            f"/v1/collections/{COLLECTION}/bulk_upsert",
            json={
                "items": [{"external_id": f"bulk-t-{i}", "text": f"doc {i}"} for i in range(3)],
                "include_timing": True,
            },
            headers=headers,
        )
        t = resp.json()["data"]["timing_ms"]
        assert t["embedding_ms"] > 0
        assert t["total_ms"] >= t["embedding_ms"]


class TestSearchTiming:
    @pytest.fixture(autouse=True)
    def setup(self, timing_collection):
        pass

    def test_search_no_timing_by_default(self, client, headers):
        resp = client.post(
            f"/v1/collections/{COLLECTION}/search",
            json={"text": "test", "k": 3},
            headers=headers,
        )
        assert "timing_ms" not in resp.json()["data"]

    def test_search_with_timing(self, client, headers):
        resp = client.post(
            f"/v1/collections/{COLLECTION}/search",
            json={"text": "test", "k": 3, "include_timing": True},
            headers=headers,
        )
        t = resp.json()["data"]["timing_ms"]
        assert "embedding_ms" in t
        assert "search_ms" in t
        assert "total_ms" in t

    def test_search_vector_timing_zero_embedding(self, client, headers):
        resp = client.post(
            f"/v1/collections/{COLLECTION}/search",
            json={"vector": random_vector(DIM), "k": 3, "include_timing": True},
            headers=headers,
        )
        t = resp.json()["data"]["timing_ms"]
        assert t["embedding_ms"] == 0.0


class TestHybridSearchTiming:
    @pytest.fixture(autouse=True)
    def setup(self, timing_collection):
        pass

    def test_hybrid_search_with_timing(self, client, headers):
        resp = client.post(
            f"/v1/collections/{COLLECTION}/hybrid_search",
            json={"query_text": "test", "k": 3, "include_timing": True},
            headers=headers,
        )
        t = resp.json()["data"]["timing_ms"]
        assert t["embedding_ms"] > 0
        assert "search_ms" in t


class TestRerankTiming:
    @pytest.fixture(autouse=True)
    def setup(self, timing_collection):
        pass

    def test_rerank_with_timing(self, client, headers):
        resp = client.post(
            f"/v1/collections/{COLLECTION}/rerank",
            json={
                "text": "test",
                "candidates": ["timing-0", "timing-1"],
                "include_timing": True,
            },
            headers=headers,
        )
        t = resp.json()["data"]["timing_ms"]
        assert "embedding_ms" in t
        assert "search_ms" in t


class TestQueryTiming:
    @pytest.fixture(autouse=True)
    def setup(self, timing_collection):
        pass

    def test_query_no_timing_by_default(self, client, headers):
        resp = client.post(
            "/v1/query",
            json={"query": "test", "collection_name": COLLECTION},
            headers=headers,
        )
        assert "timing_ms" not in resp.json()["data"]

    def test_query_with_timing(self, client, headers):
        resp = client.post(
            "/v1/query",
            json={"query": "test", "collection_name": COLLECTION, "include_timing": True},
            headers=headers,
        )
        t = resp.json()["data"]["timing_ms"]
        assert "embedding_ms" in t
        assert "search_ms" in t
        assert "total_ms" in t


class TestDocumentUploadTiming:
    @pytest.fixture(autouse=True)
    def setup(self, timing_collection):
        pass

    def test_upload_no_timing_by_default(self, client, headers):
        content = "Test document for timing. " * 20
        resp = client.post(
            "/v1/documents/upload",
            data={"collection_name": COLLECTION},
            files={"file": ("test.txt", io.BytesIO(content.encode()), "text/plain")},
            headers=headers,
        )
        assert "timing_ms" not in resp.json()["data"]

    def test_upload_with_timing(self, client, headers):
        content = "Test document for timing metrics. " * 20
        resp = client.post(
            "/v1/documents/upload",
            data={"collection_name": COLLECTION, "include_timing": "true"},
            files={"file": ("timing.txt", io.BytesIO(content.encode()), "text/plain")},
            headers=headers,
        )
        t = resp.json()["data"]["timing_ms"]
        assert "embedding_ms" in t
        assert "storage_ms" in t
        assert "total_ms" in t
        assert t["total_ms"] >= t["embedding_ms"]
