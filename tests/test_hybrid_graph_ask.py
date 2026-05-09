"""Tests for POST /v1/collections/{name}/graph/hybrid_ask"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import networkx as nx
import pytest

from vectordb.models.db import User, get_session_local


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _register_user(client, email, password="Password123!"):
    r = client.post("/v1/auth/register", json={"email": email, "password": password})
    data = r.json()
    assert data["status"] == "success", f"Registration failed: {data}"
    return data["data"]["api_key"]["key"]


def _set_user_tier(email: str, tier: str):
    SessionLocal = get_session_local()
    db = SessionLocal()
    try:
        user = db.query(User).filter_by(email=email).first()
        assert user is not None, f"User {email} not found"
        user.tier = tier
        db.commit()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def free_key(client):
    email = "hybrid-ask-free@example.com"
    key = _register_user(client, email)
    _set_user_tier(email, "free")
    return key


@pytest.fixture(scope="module")
def pro_key(client):
    email = "hybrid-ask-pro@example.com"
    key = _register_user(client, email)
    _set_user_tier(email, "pro")
    return key


@pytest.fixture(scope="module")
def scale_key(client):
    email = "hybrid-ask-scale@example.com"
    key = _register_user(client, email)
    _set_user_tier(email, "scale")
    return key


@pytest.fixture(scope="module")
def hybrid_collection(client, scale_key):
    """Collection with 3 upserted vectors (no graph entities — empty graph)."""
    name = "hybrid-ask-col"
    client.post(
        "/v1/collections",
        json={"name": name, "dim": 384},
        headers={"x-api-key": scale_key},
    )
    for i in range(3):
        client.post(
            f"/v1/collections/{name}/upsert",
            json={
                "external_id": f"doc-{i}",
                "text": f"Sample document {i} about artificial intelligence and machine learning",
                "content": f"Sample document {i} about artificial intelligence and machine learning",
            },
            headers={"x-api-key": scale_key},
        )
    return name


# ---------------------------------------------------------------------------
# Test classes
# ---------------------------------------------------------------------------

class TestHybridAskTierGating:
    PAYLOAD = {"query": "artificial intelligence", "k": 2}

    def test_free_tier_rejected(self, client, free_key):
        resp = client.post(
            "/v1/collections/any/graph/hybrid_ask",
            json=self.PAYLOAD,
            headers={"x-api-key": free_key},
        )
        assert resp.status_code == 403

    def test_pro_tier_allowed(self, client, pro_key, hybrid_collection):
        resp = client.post(
            f"/v1/collections/{hybrid_collection}/graph/hybrid_ask",
            json=self.PAYLOAD,
            headers={"x-api-key": pro_key},
        )
        # pro user doesn't own this collection — expect 404 in body, not 403
        assert resp.status_code == 200
        body = resp.json()
        # Either success or 404 (collection belongs to scale user) — never 403
        assert not (body.get("status") == "error" and body.get("error", {}).get("code") == 403)

    def test_bootstrap_admin_allowed(self, client, headers, hybrid_collection):
        resp = client.post(
            f"/v1/collections/{hybrid_collection}/graph/hybrid_ask",
            json=self.PAYLOAD,
            headers=headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert not (body.get("status") == "error" and body.get("error", {}).get("code") == 403)

    def test_scale_tier_allowed(self, client, scale_key, hybrid_collection):
        resp = client.post(
            f"/v1/collections/{hybrid_collection}/graph/hybrid_ask",
            json=self.PAYLOAD,
            headers={"x-api-key": scale_key},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "success"


class TestHybridAskSchemaValidation:
    def test_missing_query_rejected(self, client, headers, hybrid_collection):
        resp = client.post(
            f"/v1/collections/{hybrid_collection}/graph/hybrid_ask",
            json={"k": 3},
            headers=headers,
        )
        assert resp.status_code == 422

    def test_k_too_large_rejected(self, client, headers, hybrid_collection):
        resp = client.post(
            f"/v1/collections/{hybrid_collection}/graph/hybrid_ask",
            json={"query": "test", "k": 25},
            headers=headers,
        )
        assert resp.status_code == 422

    def test_vector_weight_out_of_range_rejected(self, client, headers, hybrid_collection):
        resp = client.post(
            f"/v1/collections/{hybrid_collection}/graph/hybrid_ask",
            json={"query": "test", "vector_weight": 1.5},
            headers=headers,
        )
        assert resp.status_code == 422

    def test_graph_hops_out_of_range_rejected(self, client, headers, hybrid_collection):
        resp = client.post(
            f"/v1/collections/{hybrid_collection}/graph/hybrid_ask",
            json={"query": "test", "graph_hops": 5},
            headers=headers,
        )
        assert resp.status_code == 422

    def test_empty_query_rejected(self, client, headers, hybrid_collection):
        resp = client.post(
            f"/v1/collections/{hybrid_collection}/graph/hybrid_ask",
            json={"query": "   "},
            headers=headers,
        )
        assert resp.status_code == 422

    def test_defaults_accepted(self, client, headers, hybrid_collection):
        resp = client.post(
            f"/v1/collections/{hybrid_collection}/graph/hybrid_ask",
            json={"query": "artificial intelligence"},
            headers=headers,
        )
        assert resp.status_code == 200


class TestHybridAskEmptyGraph:
    def test_succeeds_with_no_graph_entities(self, client, scale_key, hybrid_collection):
        resp = client.post(
            f"/v1/collections/{hybrid_collection}/graph/hybrid_ask",
            json={"query": "artificial intelligence", "k": 3, "vector_weight": 0.5},
            headers={"x-api-key": scale_key},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["answer"] is not None

    def test_sources_have_valid_source_type(self, client, scale_key, hybrid_collection):
        resp = client.post(
            f"/v1/collections/{hybrid_collection}/graph/hybrid_ask",
            json={"query": "machine learning", "k": 3},
            headers={"x-api-key": scale_key},
        )
        assert resp.status_code == 200
        for s in resp.json()["data"]["sources"]:
            assert s["source_type"] in ("vector", "graph", "both")

    def test_graph_context_structure_present(self, client, scale_key, hybrid_collection):
        resp = client.post(
            f"/v1/collections/{hybrid_collection}/graph/hybrid_ask",
            json={"query": "test", "include_graph_context": True},
            headers={"x-api-key": scale_key},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "graph_context" in data
        assert "entities_used" in data["graph_context"]
        assert "relations_used" in data["graph_context"]


class TestHybridAskResponseShape:
    def test_all_top_level_keys_present(self, client, scale_key, hybrid_collection):
        resp = client.post(
            f"/v1/collections/{hybrid_collection}/graph/hybrid_ask",
            json={"query": "intelligence", "k": 2},
            headers={"x-api-key": scale_key},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        for key in ("answer", "sources", "graph_context", "retrieval_stats", "timing_ms"):
            assert key in data, f"Missing key: {key}"

    def test_timing_ms_has_hybrid_ask_key(self, client, scale_key, hybrid_collection):
        resp = client.post(
            f"/v1/collections/{hybrid_collection}/graph/hybrid_ask",
            json={"query": "test", "k": 2},
            headers={"x-api-key": scale_key},
        )
        timing = resp.json()["data"]["timing_ms"]
        assert "hybrid_ask_ms" in timing
        assert timing["hybrid_ask_ms"] >= 0

    def test_retrieval_stats_has_required_keys(self, client, scale_key, hybrid_collection):
        resp = client.post(
            f"/v1/collections/{hybrid_collection}/graph/hybrid_ask",
            json={"query": "test", "k": 2},
            headers={"x-api-key": scale_key},
        )
        stats = resp.json()["data"]["retrieval_stats"]
        for key in ("vector_chunks", "graph_chunks", "fused_chunks"):
            assert key in stats
            assert isinstance(stats[key], int)

    def test_each_source_has_required_fields(self, client, scale_key, hybrid_collection):
        resp = client.post(
            f"/v1/collections/{hybrid_collection}/graph/hybrid_ask",
            json={"query": "artificial", "k": 2},
            headers={"x-api-key": scale_key},
        )
        for s in resp.json()["data"]["sources"]:
            assert "external_id" in s
            assert "score" in s
            assert "source_type" in s
            assert s["source_type"] in ("vector", "graph", "both")

    def test_missing_collection_returns_404_envelope(self, client, headers):
        resp = client.post(
            "/v1/collections/nonexistent-xyz/graph/hybrid_ask",
            json={"query": "test"},
            headers=headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "error"
        assert body["error"]["code"] == 404


class TestRRFFusion:
    """Unit tests for RRF math — no HTTP, no DB."""

    def test_vector_weight_1_zeros_graph_contribution(self):
        vec_rank = {"eid-a": 1}
        graph_rank = {"eid-b": 1}
        RRF_K = 60
        vector_weight = 1.0

        scores = {}
        for eid in set(vec_rank) | set(graph_rank):
            vr = vector_weight * (1.0 / (RRF_K + vec_rank[eid])) if eid in vec_rank else 0.0
            gr = (1 - vector_weight) * (1.0 / (RRF_K + graph_rank[eid])) if eid in graph_rank else 0.0
            scores[eid] = vr + gr

        assert scores["eid-a"] > 0
        assert scores["eid-b"] == 0.0

    def test_vector_weight_0_zeros_vector_contribution(self):
        vec_rank = {"eid-a": 1}
        graph_rank = {"eid-b": 1}
        RRF_K = 60
        vector_weight = 0.0

        scores = {}
        for eid in set(vec_rank) | set(graph_rank):
            vr = vector_weight * (1.0 / (RRF_K + vec_rank[eid])) if eid in vec_rank else 0.0
            gr = (1 - vector_weight) * (1.0 / (RRF_K + graph_rank[eid])) if eid in graph_rank else 0.0
            scores[eid] = vr + gr

        assert scores["eid-b"] > 0
        assert scores["eid-a"] == 0.0

    def test_shared_eid_gets_source_type_both(self):
        vec_rank = {"shared": 1, "vec-only": 2}
        graph_rank = {"shared": 1, "graph-only": 2}

        source_types = {}
        for eid in set(vec_rank) | set(graph_rank):
            in_v = eid in vec_rank
            in_g = eid in graph_rank
            source_types[eid] = "both" if (in_v and in_g) else ("vector" if in_v else "graph")

        assert source_types["shared"] == "both"
        assert source_types["vec-only"] == "vector"
        assert source_types["graph-only"] == "graph"

    def test_higher_rank_yields_higher_rrf_score(self):
        RRF_K = 60
        score_rank1 = 1.0 / (RRF_K + 1)
        score_rank5 = 1.0 / (RRF_K + 5)
        assert score_rank1 > score_rank5


class TestGraphHybridAskPipelineUnit:
    """Unit tests for graph_hybrid_ask_pipeline — mocked backend, no HTTP."""

    def test_empty_backend_returns_valid_dict(self):
        from vectordb.services.graph_retrieval import graph_hybrid_ask_pipeline

        mock_backend = AsyncMock()
        mock_backend.search.return_value = []
        mock_backend.batch_get_vectors.return_value = []

        G = nx.MultiDiGraph()

        with patch(
            "vectordb.services.embedding_service.embed_text_cached_async",
            new=AsyncMock(return_value=[0.1] * 384),
        ):
            with patch(
                "vectordb.services.llm_service.generate_answer",
                new=AsyncMock(return_value="No relevant info found."),
            ):
                result = asyncio.run(
                    graph_hybrid_ask_pipeline(
                        query="test query",
                        collection_name="test-col",
                        collection_id=1,
                        graph=G,
                        db=MagicMock(),
                        backend=mock_backend,
                        k=3,
                    )
                )

        assert "answer" in result
        assert "sources" in result
        assert "graph_context" in result
        assert "retrieval_stats" in result
        assert result["retrieval_stats"]["vector_chunks"] == 0
        assert result["retrieval_stats"]["graph_chunks"] == 0
        assert result["retrieval_stats"]["fused_chunks"] == 0

    def test_vector_results_produce_vector_sources(self):
        from vectordb.services.graph_retrieval import graph_hybrid_ask_pipeline

        mock_backend = AsyncMock()
        mock_backend.search.return_value = [
            {"external_id": "v1", "score": 0.9, "metadata": {"title": "doc1"}},
            {"external_id": "v2", "score": 0.8, "metadata": {"title": "doc2"}},
        ]
        mock_backend.batch_get_vectors.return_value = [
            {"external_id": "v1", "content": "Content of doc1", "metadata": {"title": "doc1"}},
            {"external_id": "v2", "content": "Content of doc2", "metadata": {"title": "doc2"}},
        ]

        G = nx.MultiDiGraph()  # empty graph → source_type=vector for all

        with patch(
            "vectordb.services.embedding_service.embed_text_cached_async",
            new=AsyncMock(return_value=[0.1] * 384),
        ):
            with patch(
                "vectordb.services.llm_service.generate_answer",
                new=AsyncMock(return_value="The answer."),
            ):
                result = asyncio.run(
                    graph_hybrid_ask_pipeline(
                        query="test",
                        collection_name="test-col",
                        collection_id=1,
                        graph=G,
                        db=MagicMock(),
                        backend=mock_backend,
                        k=5,
                        vector_weight=1.0,
                    )
                )

        assert len(result["sources"]) == 2
        for s in result["sources"]:
            assert s["source_type"] == "vector"
        assert result["retrieval_stats"]["vector_chunks"] == 2
        assert result["retrieval_stats"]["graph_chunks"] == 0
