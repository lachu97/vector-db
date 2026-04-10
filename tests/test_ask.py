# tests/test_ask.py
"""Tests for POST /v1/ask — RAG answer generation endpoint."""
import numpy as np


def rv(dim=384):
    return np.random.rand(dim).tolist()


COLLECTION = "test-ask-rag"


class TestAskSetup:
    """Create collection and seed vectors with content."""

    def test_create_collection(self, client, headers):
        r = client.post("/v1/collections", json={"name": COLLECTION, "dim": 384}, headers=headers)
        assert r.status_code == 200

    def test_seed_vectors_with_content(self, client, headers):
        items = [
            {
                "external_id": f"doc-{i}",
                "vector": rv(),
                "metadata": {"text": f"This is document {i} about topic {i % 3}", "source": "test"},
            }
            for i in range(5)
        ]
        r = client.post(f"/v1/collections/{COLLECTION}/bulk_upsert", json={"items": items}, headers=headers)
        assert r.status_code == 200


class TestAskValidation:
    """Input validation tests."""

    def test_empty_query_422(self, client, headers):
        r = client.post("/v1/ask", json={"query": "  ", "collection": COLLECTION}, headers=headers)
        assert r.status_code == 422

    def test_k_too_high_422(self, client, headers):
        r = client.post("/v1/ask", json={"query": "test", "collection": COLLECTION, "k": 21}, headers=headers)
        assert r.status_code == 422

    def test_k_zero_422(self, client, headers):
        r = client.post("/v1/ask", json={"query": "test", "collection": COLLECTION, "k": 0}, headers=headers)
        assert r.status_code == 422

    def test_invalid_collection_404(self, client, headers):
        r = client.post("/v1/ask", json={"query": "test", "collection": "nonexistent"}, headers=headers)
        assert r.status_code == 200
        body = r.json()
        assert body.get("error", {}).get("code") == 404


class TestAskEndpoint:
    """Functional tests for /v1/ask."""

    def test_ask_returns_answer_and_sources(self, client, headers):
        r = client.post("/v1/ask", json={"query": "what is topic 1", "collection": COLLECTION}, headers=headers)
        assert r.status_code == 200
        data = r.json()["data"]
        assert "answer" in data
        assert isinstance(data["answer"], str)
        assert len(data["answer"]) > 0
        assert "sources" in data
        assert isinstance(data["sources"], list)
        assert len(data["sources"]) > 0

    def test_ask_sources_shape(self, client, headers):
        r = client.post("/v1/ask", json={"query": "documents", "collection": COLLECTION, "k": 3}, headers=headers)
        assert r.status_code == 200
        sources = r.json()["data"]["sources"]
        assert len(sources) == 3
        for s in sources:
            assert "external_id" in s
            assert "score" in s
            assert "content" in s
            assert "metadata" in s

    def test_ask_respects_k(self, client, headers):
        r = client.post("/v1/ask", json={"query": "test", "collection": COLLECTION, "k": 2}, headers=headers)
        assert r.status_code == 200
        sources = r.json()["data"]["sources"]
        assert len(sources) == 2

    def test_ask_no_results_graceful(self, client, headers):
        # Create empty collection
        client.post("/v1/collections", json={"name": "ask-empty", "dim": 384}, headers=headers)
        r = client.post("/v1/ask", json={"query": "anything", "collection": "ask-empty"}, headers=headers)
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["answer"] == "No relevant information found."
        assert data["sources"] == []

    def test_ask_placeholder_when_no_llm(self, client, headers):
        """Without OPENAI_API_KEY, answer should be a placeholder string."""
        r = client.post("/v1/ask", json={"query": "test query", "collection": COLLECTION}, headers=headers)
        assert r.status_code == 200
        answer = r.json()["data"]["answer"]
        # Should contain placeholder text since no LLM is configured in test env
        assert "[LLM not configured]" in answer

    def test_ask_requires_auth(self, client):
        r = client.post("/v1/ask", json={"query": "test", "collection": COLLECTION})
        assert r.status_code == 401 or r.status_code == 403
