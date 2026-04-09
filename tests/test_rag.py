# tests/test_rag.py
"""Tests for RAG layer: chunking, embedding, document upload, query."""
import io
import math

import pytest

from tests.conftest import random_vector


# ====================================================================
# Chunking
# ====================================================================

class TestChunking:
    def test_basic_chunking(self):
        from vectordb.services.chunking import chunk_text
        text = "a" * 1000
        chunks = chunk_text(text, chunk_size=500, overlap=50)
        assert len(chunks) == 3  # 0-500, 450-950, 900-1000

    def test_small_text(self):
        from vectordb.services.chunking import chunk_text
        chunks = chunk_text("short", chunk_size=500, overlap=50)
        assert len(chunks) == 1
        assert chunks[0] == "short"

    def test_empty_text(self):
        from vectordb.services.chunking import chunk_text
        chunks = chunk_text("", chunk_size=500, overlap=50)
        assert chunks == []

    def test_exact_chunk_size(self):
        from vectordb.services.chunking import chunk_text
        text = "a" * 500
        chunks = chunk_text(text, chunk_size=500, overlap=50)
        assert len(chunks) == 2  # 0-500, 450-500

    def test_overlap_content(self):
        from vectordb.services.chunking import chunk_text
        text = "abcdefghij"  # 10 chars
        chunks = chunk_text(text, chunk_size=6, overlap=2)
        # step=4, chunks at 0-6, 4-10
        assert chunks[0] == "abcdef"
        assert chunks[1] == "efghij"
        # overlap: "ef" appears in both
        assert chunks[0][-2:] == chunks[1][:2]


# ====================================================================
# Embedding Service
# ====================================================================

class TestEmbeddingService:
    def test_dummy_provider_dimension(self):
        from vectordb.services.embedding_service import DummyEmbeddingProvider
        provider = DummyEmbeddingProvider(dim=384)
        assert provider.get_dimension() == 384

    def test_dummy_provider_embed_text(self):
        from vectordb.services.embedding_service import DummyEmbeddingProvider
        provider = DummyEmbeddingProvider(dim=384)
        vec = provider.embed_text("hello world")
        assert len(vec) == 384
        assert all(isinstance(v, float) for v in vec)

    def test_dummy_provider_normalized(self):
        from vectordb.services.embedding_service import DummyEmbeddingProvider
        provider = DummyEmbeddingProvider(dim=384)
        vec = provider.embed_text("test query")
        norm = math.sqrt(sum(v * v for v in vec))
        assert abs(norm - 1.0) < 0.01  # approximately unit norm

    def test_dummy_provider_deterministic(self):
        from vectordb.services.embedding_service import DummyEmbeddingProvider
        provider = DummyEmbeddingProvider(dim=384)
        v1 = provider.embed_text("same text")
        v2 = provider.embed_text("same text")
        assert v1 == v2

    def test_dummy_provider_different_texts(self):
        from vectordb.services.embedding_service import DummyEmbeddingProvider
        provider = DummyEmbeddingProvider(dim=384)
        v1 = provider.embed_text("hello")
        v2 = provider.embed_text("world")
        assert v1 != v2

    def test_dummy_provider_batch(self):
        from vectordb.services.embedding_service import DummyEmbeddingProvider
        provider = DummyEmbeddingProvider(dim=384)
        vecs = provider.embed_batch(["hello", "world"])
        assert len(vecs) == 2
        assert len(vecs[0]) == 384
        assert len(vecs[1]) == 384

    def test_normalize_query(self):
        from vectordb.services.embedding_service import normalize_query
        assert normalize_query("What is AI??") == "what is ai"
        assert normalize_query("  Hello   World  ") == "hello world"
        assert normalize_query("test!@#$%") == "test"

    @pytest.fixture(autouse=True)
    def _ensure_provider(self, client):
        """Force app lifespan to run so provider is initialized."""
        pass

    def test_embed_text_uses_provider(self):
        from vectordb.services.embedding_service import embed_text
        vec = embed_text("test")
        assert len(vec) == 384
        assert isinstance(vec, list)

    def test_embed_batch_uses_provider(self):
        from vectordb.services.embedding_service import embed_batch
        vecs = embed_batch(["hello", "world"])
        assert len(vecs) == 2

    def test_embed_text_cached(self):
        from vectordb.services.embedding_service import embed_text_cached
        v1 = embed_text_cached("cached test")
        v2 = embed_text_cached("cached test")
        assert v1 == v2
        assert len(v1) == 384


# ====================================================================
# Document Upload Endpoint
# ====================================================================

class TestDocumentUpload:
    @pytest.fixture(autouse=True)
    def setup_collection(self, client, headers):
        """Ensure a collection exists for upload tests."""
        client.post(
            "/v1/collections",
            json={"name": "rag-docs", "dim": 384, "distance_metric": "cosine"},
            headers=headers,
        )

    def test_upload_txt_file(self, client, headers):
        content = "This is a test document for RAG processing. " * 20
        resp = client.post(
            "/v1/documents/upload",
            data={"collection_name": "rag-docs"},
            files={"file": ("test.txt", io.BytesIO(content.encode()), "text/plain")},
            headers=headers,
        )
        body = resp.json()
        assert body["status"] == "success"
        assert "document_id" in body["data"]
        assert body["data"]["chunks_created"] > 0

    def test_upload_no_file(self, client, headers):
        resp = client.post(
            "/v1/documents/upload",
            data={"collection_name": "rag-docs"},
            headers=headers,
        )
        assert resp.status_code == 422  # FastAPI validation

    def test_upload_non_txt_file(self, client, headers):
        resp = client.post(
            "/v1/documents/upload",
            data={"collection_name": "rag-docs"},
            files={"file": ("test.pdf", io.BytesIO(b"fake pdf"), "application/pdf")},
            headers=headers,
        )
        body = resp.json()
        assert body["status"] == "error"
        assert "Only .txt" in body["error"]["message"]

    def test_upload_empty_file(self, client, headers):
        resp = client.post(
            "/v1/documents/upload",
            data={"collection_name": "rag-docs"},
            files={"file": ("empty.txt", io.BytesIO(b""), "text/plain")},
            headers=headers,
        )
        body = resp.json()
        assert body["status"] == "error"
        assert "empty" in body["error"]["message"].lower()

    def test_upload_collection_not_found(self, client, headers):
        resp = client.post(
            "/v1/documents/upload",
            data={"collection_name": "nonexistent-collection"},
            files={"file": ("test.txt", io.BytesIO(b"some text"), "text/plain")},
            headers=headers,
        )
        body = resp.json()
        assert body["status"] == "error"
        assert body["error"]["code"] == 404

    def test_upload_requires_auth(self, client, bad_headers):
        resp = client.post(
            "/v1/documents/upload",
            data={"collection_name": "rag-docs"},
            files={"file": ("test.txt", io.BytesIO(b"text"), "text/plain")},
            headers=bad_headers,
        )
        assert resp.status_code == 401


# ====================================================================
# Query Endpoint
# ====================================================================

class TestQuery:
    @pytest.fixture(autouse=True)
    def setup_collection_with_docs(self, client, headers):
        """Ensure collection exists and has documents for query tests."""
        client.post(
            "/v1/collections",
            json={"name": "rag-query", "dim": 384, "distance_metric": "cosine"},
            headers=headers,
        )
        # Upload a document
        content = "Machine learning is a subset of artificial intelligence. " * 20
        client.post(
            "/v1/documents/upload",
            data={"collection_name": "rag-query"},
            files={"file": ("ml.txt", io.BytesIO(content.encode()), "text/plain")},
            headers=headers,
        )

    def test_query_returns_results(self, client, headers):
        resp = client.post(
            "/v1/query",
            json={"query": "machine learning", "collection_name": "rag-query", "top_k": 3},
            headers=headers,
        )
        body = resp.json()
        assert body["status"] == "success"
        assert "results" in body["data"]
        assert len(body["data"]["results"]) > 0

    def test_query_result_has_text(self, client, headers):
        resp = client.post(
            "/v1/query",
            json={"query": "artificial intelligence", "collection_name": "rag-query"},
            headers=headers,
        )
        body = resp.json()
        results = body["data"]["results"]
        for r in results:
            assert "text" in r
            assert "score" in r
            assert "external_id" in r
            assert "metadata" in r

    def test_query_empty_string(self, client, headers):
        resp = client.post(
            "/v1/query",
            json={"query": "   ", "collection_name": "rag-query"},
            headers=headers,
        )
        body = resp.json()
        assert body["status"] == "error"
        assert "empty" in body["error"]["message"].lower()

    def test_query_too_long(self, client, headers):
        resp = client.post(
            "/v1/query",
            json={"query": "a" * 1001, "collection_name": "rag-query"},
            headers=headers,
        )
        body = resp.json()
        assert body["status"] == "error"
        assert "maximum length" in body["error"]["message"].lower()

    def test_query_collection_not_found(self, client, headers):
        resp = client.post(
            "/v1/query",
            json={"query": "test", "collection_name": "no-such-collection"},
            headers=headers,
        )
        body = resp.json()
        assert body["status"] == "error"
        assert body["error"]["code"] == 404

    def test_query_requires_auth(self, client, bad_headers):
        resp = client.post(
            "/v1/query",
            json={"query": "test", "collection_name": "rag-query"},
            headers=bad_headers,
        )
        assert resp.status_code == 401

    def test_query_with_top_k(self, client, headers):
        resp = client.post(
            "/v1/query",
            json={"query": "machine learning", "collection_name": "rag-query", "top_k": 1},
            headers=headers,
        )
        body = resp.json()
        assert body["status"] == "success"
        assert len(body["data"]["results"]) <= 1

    def test_query_response_shape(self, client, headers):
        resp = client.post(
            "/v1/query",
            json={"query": "test", "collection_name": "rag-query"},
            headers=headers,
        )
        body = resp.json()
        assert body["data"]["query"] == "test"
        assert body["data"]["collection"] == "rag-query"
