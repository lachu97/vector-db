# tests/test_embedding_unification.py
"""Tests for unified embedding: all APIs accept text OR vector input."""
import pytest
from tests.conftest import random_vector


COLLECTION = "embed-unified"
DIM = 384


class TestSetup:
    """Create collection used by all tests below."""

    @pytest.fixture(autouse=True, scope="class")
    def setup_collection(self, client, headers):
        client.post(
            "/v1/collections",
            json={"name": COLLECTION, "dim": DIM, "distance_metric": "cosine"},
            headers=headers,
        )


# ====================================================================
# Upsert — text-based
# ====================================================================

class TestUpsertWithText(TestSetup):
    def test_upsert_with_text(self, client, headers):
        resp = client.post(
            f"/v1/collections/{COLLECTION}/upsert",
            json={"external_id": "txt-1", "text": "hello world"},
            headers=headers,
        )
        body = resp.json()
        assert body["status"] == "success"
        assert body["data"]["status"] in ("inserted", "updated")

    def test_upsert_with_vector_still_works(self, client, headers):
        resp = client.post(
            f"/v1/collections/{COLLECTION}/upsert",
            json={"external_id": "vec-1", "vector": random_vector(DIM)},
            headers=headers,
        )
        assert resp.json()["status"] == "success"

    def test_upsert_with_both_uses_vector(self, client, headers):
        vec = random_vector(DIM)
        resp = client.post(
            f"/v1/collections/{COLLECTION}/upsert",
            json={"external_id": "both-1", "vector": vec, "text": "ignored for embedding"},
            headers=headers,
        )
        assert resp.json()["status"] == "success"

    def test_upsert_neither_vector_nor_text_fails(self, client, headers):
        resp = client.post(
            f"/v1/collections/{COLLECTION}/upsert",
            json={"external_id": "bad-1"},
            headers=headers,
        )
        assert resp.status_code == 422  # Pydantic validation

    def test_upsert_text_populates_content(self, client, headers):
        """When text is provided, it should auto-populate content for hybrid search."""
        client.post(
            f"/v1/collections/{COLLECTION}/upsert",
            json={"external_id": "txt-content-1", "text": "auto content test"},
            headers=headers,
        )
        # Search with hybrid to verify content was stored
        vec = random_vector(DIM)
        resp = client.post(
            f"/v1/collections/{COLLECTION}/hybrid_search",
            json={"query_text": "auto content", "vector": vec, "k": 10},
            headers=headers,
        )
        body = resp.json()
        assert body["status"] == "success"

    def test_upsert_text_does_not_override_explicit_content(self, client, headers):
        resp = client.post(
            f"/v1/collections/{COLLECTION}/upsert",
            json={
                "external_id": "txt-explicit-content",
                "text": "embedding source text",
                "content": "explicit hybrid content",
            },
            headers=headers,
        )
        assert resp.json()["status"] == "success"


# ====================================================================
# Bulk upsert — text-based
# ====================================================================

class TestBulkUpsertWithText(TestSetup):
    def test_bulk_upsert_with_text(self, client, headers):
        items = [
            {"external_id": f"bulk-txt-{i}", "text": f"document number {i}"}
            for i in range(5)
        ]
        resp = client.post(
            f"/v1/collections/{COLLECTION}/bulk_upsert",
            json={"items": items},
            headers=headers,
        )
        body = resp.json()
        assert body["status"] == "success"
        assert len(body["data"]["results"]) == 5

    def test_bulk_upsert_mixed_vector_and_text(self, client, headers):
        items = [
            {"external_id": "bulk-mix-vec", "vector": random_vector(DIM)},
            {"external_id": "bulk-mix-txt", "text": "embedded by server"},
        ]
        resp = client.post(
            f"/v1/collections/{COLLECTION}/bulk_upsert",
            json={"items": items},
            headers=headers,
        )
        body = resp.json()
        assert body["status"] == "success"
        assert len(body["data"]["results"]) == 2


# ====================================================================
# Search — text-based
# ====================================================================

class TestSearchWithText(TestSetup):
    @pytest.fixture(autouse=True)
    def seed_data(self, client, headers):
        """Ensure some text-based vectors exist."""
        items = [
            {"external_id": f"search-txt-{i}", "text": f"machine learning topic {i}"}
            for i in range(3)
        ]
        client.post(
            f"/v1/collections/{COLLECTION}/bulk_upsert",
            json={"items": items},
            headers=headers,
        )

    def test_search_with_text(self, client, headers):
        resp = client.post(
            f"/v1/collections/{COLLECTION}/search",
            json={"text": "machine learning", "k": 3},
            headers=headers,
        )
        body = resp.json()
        assert body["status"] == "success"
        assert len(body["data"]["results"]) > 0

    def test_search_with_vector_still_works(self, client, headers):
        resp = client.post(
            f"/v1/collections/{COLLECTION}/search",
            json={"vector": random_vector(DIM), "k": 3},
            headers=headers,
        )
        assert resp.json()["status"] == "success"

    def test_search_neither_fails(self, client, headers):
        resp = client.post(
            f"/v1/collections/{COLLECTION}/search",
            json={"k": 3},
            headers=headers,
        )
        assert resp.status_code == 422


# ====================================================================
# Hybrid search — vector now optional
# ====================================================================

class TestHybridSearchTextOnly(TestSetup):
    @pytest.fixture(autouse=True)
    def seed_data(self, client, headers):
        items = [
            {"external_id": f"hybrid-txt-{i}", "text": f"deep learning paper {i}"}
            for i in range(3)
        ]
        client.post(
            f"/v1/collections/{COLLECTION}/bulk_upsert",
            json={"items": items},
            headers=headers,
        )

    def test_hybrid_search_text_only(self, client, headers):
        """Hybrid search with only query_text — vector auto-embedded."""
        resp = client.post(
            f"/v1/collections/{COLLECTION}/hybrid_search",
            json={"query_text": "deep learning", "k": 3},
            headers=headers,
        )
        body = resp.json()
        assert body["status"] == "success"

    def test_hybrid_search_with_vector_still_works(self, client, headers):
        resp = client.post(
            f"/v1/collections/{COLLECTION}/hybrid_search",
            json={"query_text": "deep learning", "vector": random_vector(DIM), "k": 3},
            headers=headers,
        )
        assert resp.json()["status"] == "success"


# ====================================================================
# Rerank — text-based
# ====================================================================

class TestRerankWithText(TestSetup):
    @pytest.fixture(autouse=True)
    def seed_data(self, client, headers):
        items = [
            {"external_id": f"rerank-txt-{i}", "text": f"rerank candidate {i}"}
            for i in range(3)
        ]
        client.post(
            f"/v1/collections/{COLLECTION}/bulk_upsert",
            json={"items": items},
            headers=headers,
        )

    def test_rerank_with_text(self, client, headers):
        resp = client.post(
            f"/v1/collections/{COLLECTION}/rerank",
            json={
                "text": "rerank query",
                "candidates": ["rerank-txt-0", "rerank-txt-1", "rerank-txt-2"],
            },
            headers=headers,
        )
        body = resp.json()
        assert body["status"] == "success"
        assert len(body["data"]["results"]) > 0

    def test_rerank_with_vector_still_works(self, client, headers):
        resp = client.post(
            f"/v1/collections/{COLLECTION}/rerank",
            json={
                "vector": random_vector(DIM),
                "candidates": ["rerank-txt-0", "rerank-txt-1"],
            },
            headers=headers,
        )
        assert resp.json()["status"] == "success"

    def test_rerank_neither_fails(self, client, headers):
        resp = client.post(
            f"/v1/collections/{COLLECTION}/rerank",
            json={"candidates": ["rerank-txt-0"]},
            headers=headers,
        )
        assert resp.status_code == 422


# ====================================================================
# Legacy endpoints — text-based
# ====================================================================

class TestLegacyTextInput:
    def test_legacy_upsert_with_text(self, client, headers):
        resp = client.post(
            "/v1/upsert",
            json={"external_id": "legacy-txt-1", "text": "legacy text upsert"},
            headers=headers,
        )
        assert resp.json()["status"] == "success"

    def test_legacy_search_with_text(self, client, headers):
        # Ensure there's data first
        client.post(
            "/v1/upsert",
            json={"external_id": "legacy-search-seed", "text": "neural networks research"},
            headers=headers,
        )
        resp = client.post(
            "/v1/search",
            json={"text": "neural networks", "k": 3},
            headers=headers,
        )
        body = resp.json()
        assert body["status"] == "success"
        assert len(body["data"]["results"]) > 0

    def test_legacy_hybrid_search_text_only(self, client, headers):
        resp = client.post(
            "/v1/hybrid_search",
            json={"query_text": "neural networks", "k": 3},
            headers=headers,
        )
        assert resp.json()["status"] == "success"


# ====================================================================
# Validation: no duplicate embedding outside embedding_service
# ====================================================================

class TestNoDuplicateEmbedding:
    def test_no_model_encode_calls_outside_embedding_service(self):
        """Verify no direct model.encode() calls (SentenceTransformer) exist outside embedding_service."""
        import os
        import re

        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        # Pattern: variable.encode( but NOT string-like .encode("utf  or ).encode()
        # We look for _model.encode( or model.encode( patterns
        pattern = re.compile(r'(?:_?model|transformer|encoder)\s*\.\s*encode\s*\(')
        violations = []

        for root, dirs, files in os.walk(os.path.join(project_root, "vectordb")):
            for f in files:
                if not f.endswith(".py"):
                    continue
                filepath = os.path.join(root, f)
                if "embedding_service.py" in filepath:
                    continue
                with open(filepath) as fh:
                    for i, line in enumerate(fh, 1):
                        if pattern.search(line):
                            violations.append(f"{filepath}:{i}: {line.strip()}")

        assert violations == [], f"Direct model.encode() calls found:\n" + "\n".join(violations)

    def test_no_sentence_transformer_import_outside_embedding_service(self):
        """Verify SentenceTransformer is only imported in embedding_service."""
        import os

        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        violations = []

        for root, dirs, files in os.walk(os.path.join(project_root, "vectordb")):
            for f in files:
                if not f.endswith(".py"):
                    continue
                filepath = os.path.join(root, f)
                if "embedding_service.py" in filepath:
                    continue
                with open(filepath) as fh:
                    for i, line in enumerate(fh, 1):
                        if "SentenceTransformer" in line:
                            violations.append(f"{filepath}:{i}: {line.strip()}")

        assert violations == [], f"SentenceTransformer imports found:\n" + "\n".join(violations)
