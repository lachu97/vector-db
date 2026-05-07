# tests/test_graphrag.py
"""
GraphRAG Phase 1 tests — tier gating, graph status/search endpoints,
GraphManager unit tests, LLM extraction fallback, bootstrap key access.
"""
import asyncio
import pytest
import networkx as nx
from unittest.mock import MagicMock, patch

from vectordb.models.db import User, get_session_local


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _register_user(client, email, password="Password123!"):
    """Register a new user and return the API key string."""
    r = client.post("/v1/auth/register", json={"email": email, "password": password})
    data = r.json()
    assert data["status"] == "success", f"Registration failed: {data}"
    return data["data"]["api_key"]["key"]


def _set_user_tier(email: str, tier: str):
    """Directly update the user's tier in the test DB."""
    SessionLocal = get_session_local()
    db = SessionLocal()
    try:
        user = db.query(User).filter_by(email=email).first()
        assert user is not None, f"User {email!r} not found"
        user.tier = tier
        db.commit()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Module-level fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def free_key(client):
    """API key belonging to a free-tier user."""
    email = "graphrag-free@example.com"
    key = _register_user(client, email)
    # free is the default tier, but be explicit
    _set_user_tier(email, "free")
    return key


@pytest.fixture(scope="module")
def pro_key(client):
    """API key belonging to a pro-tier user."""
    email = "graphrag-pro@example.com"
    key = _register_user(client, email)
    _set_user_tier(email, "pro")
    return key


@pytest.fixture(scope="module")
def test_collection(client, pro_key):
    """Create a test collection scoped to the pro user; return its name."""
    name = "graphrag-test-col"
    resp = client.post(
        "/v1/collections",
        json={"name": name, "dim": 4},
        headers={"x-api-key": pro_key},
    )
    # 409 means it already exists from a prior run — that's fine
    assert resp.json()["status"] in ("success",) or resp.status_code == 409
    return name


# ---------------------------------------------------------------------------
# 1. Tier gating tests
# ---------------------------------------------------------------------------

class TestTierGating:

    def test_graph_search_requires_pro_or_scale(self, client, free_key):
        """Free-tier key gets 403 on graph search endpoint."""
        resp = client.post(
            "/v1/collections/any-col/graph/search",
            json={"query": "test"},
            headers={"x-api-key": free_key},
        )
        assert resp.status_code == 403
        assert "Pro or Scale" in resp.json()["detail"]

    def test_graph_status_requires_pro_or_scale(self, client, free_key):
        """Free-tier key gets 403 on graph status endpoint."""
        resp = client.get(
            "/v1/collections/any-col/graph/status",
            headers={"x-api-key": free_key},
        )
        assert resp.status_code == 403
        assert "Pro or Scale" in resp.json()["detail"]

    def test_graph_search_free_key_error_message(self, client, free_key):
        """403 detail message mentions upgrade path."""
        resp = client.post(
            "/v1/collections/any-col/graph/search",
            json={"query": "hello"},
            headers={"x-api-key": free_key},
        )
        assert resp.status_code == 403
        detail = resp.json()["detail"]
        assert "Pro or Scale" in detail


# ---------------------------------------------------------------------------
# 2. Graph status endpoint tests
# ---------------------------------------------------------------------------

class TestGraphStatus:

    def test_graph_status_empty(self, client, pro_key, test_collection):
        """New collection has zero entities, edges, all job counts zero."""
        resp = client.get(
            f"/v1/collections/{test_collection}/graph/status",
            headers={"x-api-key": pro_key},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["entity_count"] == 0
        assert data["edge_count"] == 0
        jobs = data["jobs"]
        assert jobs["pending"] == 0
        assert jobs["processing"] == 0
        assert jobs["completed"] == 0
        assert jobs["failed"] == 0

    def test_graph_status_collection_not_found(self, client, pro_key):
        """404 returned when collection does not exist."""
        resp = client.get(
            "/v1/collections/nonexistent-graphrag-col/graph/status",
            headers={"x-api-key": pro_key},
        )
        assert resp.status_code == 200  # envelope-wrapped 404
        body = resp.json()
        assert body["status"] == "error"
        assert body["error"]["code"] == 404

    def test_graph_status_response_shape(self, client, pro_key, test_collection):
        """Response always contains jobs, entity_count, edge_count keys."""
        resp = client.get(
            f"/v1/collections/{test_collection}/graph/status",
            headers={"x-api-key": pro_key},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "jobs" in data
        assert "entity_count" in data
        assert "edge_count" in data


# ---------------------------------------------------------------------------
# 3. Graph search endpoint tests
# ---------------------------------------------------------------------------

class TestGraphSearch:

    def test_graph_search_empty_collection(self, client, pro_key, test_collection):
        """Search on empty graph returns empty entities list."""
        resp = client.post(
            f"/v1/collections/{test_collection}/graph/search",
            json={"query": "Apple", "k": 5},
            headers={"x-api-key": pro_key},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["entities"] == []

    def test_graph_search_collection_not_found(self, client, pro_key):
        """404 envelope when collection does not exist."""
        resp = client.post(
            "/v1/collections/nonexistent-graphrag-col/graph/search",
            json={"query": "test"},
            headers={"x-api-key": pro_key},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "error"
        assert body["error"]["code"] == 404

    def test_graph_search_response_has_timing(self, client, pro_key, test_collection):
        """Response includes timing_ms dict."""
        resp = client.post(
            f"/v1/collections/{test_collection}/graph/search",
            json={"query": "anything"},
            headers={"x-api-key": pro_key},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "timing_ms" in data
        assert "search_ms" in data["timing_ms"]

    def test_graph_search_default_k(self, client, pro_key, test_collection):
        """Request without k field is accepted (uses default)."""
        resp = client.post(
            f"/v1/collections/{test_collection}/graph/search",
            json={"query": "test query"},
            headers={"x-api-key": pro_key},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "success"

    def test_graph_search_no_query_fails(self, client, pro_key, test_collection):
        """Missing query field returns validation error."""
        resp = client.post(
            f"/v1/collections/{test_collection}/graph/search",
            json={"k": 5},
            headers={"x-api-key": pro_key},
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 4. GraphManager unit tests
# ---------------------------------------------------------------------------

class TestGraphManager:

    def test_lazy_load_not_in_cache_before_access(self):
        """Graph is NOT loaded at construction time."""
        from vectordb.services.graph_manager import GraphManager

        manager = GraphManager()
        assert 0 not in manager._graphs

    def test_lazy_load_caches_after_first_access(self):
        """Graph is cached after first get_graph() call."""
        from vectordb.services.graph_manager import GraphManager

        manager = GraphManager()

        mock_db = MagicMock()
        mock_db.query.return_value.filter_by.return_value.all.return_value = []

        graph = asyncio.run(manager.get_graph(0, mock_db))
        assert isinstance(graph, nx.MultiDiGraph)
        assert 0 in manager._graphs

    def test_lazy_load_returns_same_instance_on_second_call(self):
        """Repeated get_graph() returns cached instance."""
        from vectordb.services.graph_manager import GraphManager

        manager = GraphManager()

        mock_db = MagicMock()
        mock_db.query.return_value.filter_by.return_value.all.return_value = []

        g1 = asyncio.run(manager.get_graph(0, mock_db))
        g2 = asyncio.run(manager.get_graph(0, mock_db))
        assert g1 is g2

    def test_invalidate_removes_from_cache(self):
        """invalidate_graph() removes the collection from the in-memory cache."""
        from vectordb.services.graph_manager import GraphManager

        manager = GraphManager()
        manager._graphs[1] = nx.MultiDiGraph()
        asyncio.run(manager.invalidate_graph(1))
        assert 1 not in manager._graphs

    def test_invalidate_nonexistent_is_noop(self):
        """invalidate_graph() on uncached id does not raise."""
        from vectordb.services.graph_manager import GraphManager

        manager = GraphManager()
        # Should not raise KeyError
        asyncio.run(manager.invalidate_graph(999))

    def test_multidi_graph_parallel_edges(self):
        """MultiDiGraph preserves parallel edges between the same node pair."""
        G = nx.MultiDiGraph()
        G.add_node(1, entity_text="Apple", entity_type="ORG")
        G.add_node(2, entity_text="Beats", entity_type="ORG")
        G.add_edge(1, 2, relation_type="acquired", weight=1.0)
        G.add_edge(1, 2, relation_type="partnered_with", weight=0.8)

        edges = list(G.edges(1, keys=True, data=True))
        assert len(edges) == 2
        relation_types = {e[3]["relation_type"] for e in edges}
        assert relation_types == {"acquired", "partnered_with"}

    def test_graph_populated_from_entities_and_edges(self):
        """_load_graph_from_db builds correct nodes and edges from ORM objects."""
        from vectordb.services.graph_manager import GraphManager

        manager = GraphManager()

        # Build mock entity
        mock_entity = MagicMock()
        mock_entity.id = 10
        mock_entity.entity_text = "Tesla"
        mock_entity.entity_type = "ORG"
        mock_entity.chunk_id = "chunk-1"
        mock_entity.vector_external_id = None
        mock_entity.document_id = "doc-1"

        # Build mock edge
        mock_edge = MagicMock()
        mock_edge.source_entity_id = 10
        mock_edge.target_entity_id = 10  # self-loop for simplicity
        mock_edge.relation_type = "mentions"
        mock_edge.weight = 1.0
        mock_edge.document_id = "doc-1"
        mock_edge.chunk_id = "chunk-1"

        mock_db = MagicMock()
        mock_db.query.return_value.filter_by.return_value.all.side_effect = [
            [mock_entity],  # first call — entities
            [mock_edge],    # second call — edges
        ]

        G = manager._load_graph_from_db(42, mock_db)
        assert 10 in G.nodes
        assert G.nodes[10]["entity_text"] == "Tesla"
        assert G.number_of_edges() == 1


# ---------------------------------------------------------------------------
# 5. LLM extraction fallback test
# ---------------------------------------------------------------------------

class TestLLMExtract:

    def test_llm_extract_no_api_key_returns_empty(self):
        """Returns empty lists when no OpenAI key configured."""
        from vectordb.services.graph_extraction import llm_extract

        settings = MagicMock()
        settings.openai_api_key = ""

        entities, edges = asyncio.run(llm_extract("some text about Apple and Beats", settings, client=None))
        assert entities == []
        assert edges == []

    def test_llm_extract_no_client_returns_empty(self):
        """Returns empty lists when client is None, even if key is set."""
        from vectordb.services.graph_extraction import llm_extract

        settings = MagicMock()
        settings.openai_api_key = "sk-fake"

        entities, edges = asyncio.run(llm_extract("some text", settings, client=None))
        assert entities == []
        assert edges == []

    def test_llm_extract_empty_text_returns_empty(self):
        """Returns empty lists for empty text (no API key)."""
        from vectordb.services.graph_extraction import llm_extract

        settings = MagicMock()
        settings.openai_api_key = ""

        entities, edges = asyncio.run(llm_extract("", settings, client=None))
        assert entities == []
        assert edges == []


# ---------------------------------------------------------------------------
# 6. Bootstrap key allowed through tier gate
# ---------------------------------------------------------------------------

class TestBootstrapKeyAccess:

    def test_bootstrap_key_allowed_on_graph_status(self, client):
        """Bootstrap admin key (test-key) bypasses tier gate on graph status."""
        # Create a fresh collection with bootstrap key
        client.post(
            "/v1/collections",
            json={"name": "bootstrap-graphrag-test", "dim": 4},
            headers={"x-api-key": "test-key"},
        )
        resp = client.get(
            "/v1/collections/bootstrap-graphrag-test/graph/status",
            headers={"x-api-key": "test-key"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "success"

    def test_bootstrap_key_allowed_on_graph_search(self, client):
        """Bootstrap admin key (test-key) bypasses tier gate on graph search."""
        resp = client.post(
            "/v1/collections/bootstrap-graphrag-test/graph/search",
            json={"query": "test"},
            headers={"x-api-key": "test-key"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "success"

    def test_bootstrap_key_graph_search_returns_empty_on_empty_graph(self, client):
        """Bootstrap key search returns empty entities list on empty graph."""
        resp = client.post(
            "/v1/collections/bootstrap-graphrag-test/graph/search",
            json={"query": "Apple", "k": 5},
            headers={"x-api-key": "test-key"},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["entities"] == []


# ---------------------------------------------------------------------------
# 7. Graph path endpoint tests
# ---------------------------------------------------------------------------

class TestGraphPath:
    def test_graph_path_not_found_collection(self, client):
        resp = client.post(
            "/v1/collections/nonexistent/graph/path",
            json={"source": "A", "target": "B"},
            headers={"x-api-key": "test-key"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "error"
        assert body["error"]["code"] == 404

    def test_graph_path_empty_graph(self, client):
        # Create collection, search with no entities → empty paths
        client.post("/v1/collections", json={"name": "path-test", "dim": 4},
                    headers={"x-api-key": "test-key"})
        resp = client.post(
            "/v1/collections/path-test/graph/path",
            json={"source": "Apple", "target": "Microsoft"},
            headers={"x-api-key": "test-key"},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["path_count"] == 0
        assert data["paths"] == []

    def test_graph_path_requires_pro_or_scale(self, client):
        # Need a free-tier user
        import uuid
        email = f"free-{uuid.uuid4()}@test.com"
        reg = client.post("/v1/auth/register",
                          json={"email": email, "password": "password123"})
        free_key = reg.json()["data"]["api_key"]["key"]
        resp = client.post(
            "/v1/collections/any/graph/path",
            json={"source": "A", "target": "B"},
            headers={"x-api-key": free_key},
        )
        assert resp.status_code == 403

    def test_graph_path_unit_simple(self):
        """Unit test path_analysis directly with a built graph."""
        import networkx as nx
        from vectordb.services.graph_retrieval import path_analysis

        G = nx.MultiDiGraph()
        G.add_node(1, entity_text="Apple", entity_type="ORG")
        G.add_node(2, entity_text="Beats", entity_type="ORG")
        G.add_node(3, entity_text="Music", entity_type="CONCEPT")
        G.add_edge(1, 2, relation_type="acquired", weight=1.0)
        G.add_edge(2, 3, relation_type="produces", weight=1.0)

        result = path_analysis(G, "Apple", "Music", max_hops=4)
        assert result["path_count"] == 1
        assert result["shortest_hop_count"] == 2
        # Path: Apple → acquired → Beats → produces → Music
        path = result["paths"][0]
        assert path[0]["entity"] == "Apple"
        assert path[1]["relation"] == "acquired"
        assert path[2]["entity"] == "Beats"

    def test_graph_path_unit_no_path(self):
        """Returns empty when no path exists."""
        import networkx as nx
        from vectordb.services.graph_retrieval import path_analysis

        G = nx.MultiDiGraph()
        G.add_node(1, entity_text="Apple", entity_type="ORG")
        G.add_node(2, entity_text="Google", entity_type="ORG")
        # No edges → no path

        result = path_analysis(G, "Apple", "Google", max_hops=4)
        assert result["path_count"] == 0
        assert result["paths"] == []

    def test_graph_path_unit_missing_entity(self):
        """Returns empty when source or target not in graph."""
        import networkx as nx
        from vectordb.services.graph_retrieval import path_analysis

        G = nx.MultiDiGraph()
        G.add_node(1, entity_text="Apple", entity_type="ORG")

        result = path_analysis(G, "Apple", "NonExistent", max_hops=4)
        assert result["path_count"] == 0


# ---------------------------------------------------------------------------
# Phase 3: Community Detection + /graph/summarize
# ---------------------------------------------------------------------------

class TestGraphSummarize:
    def test_summarize_requires_scale(self, client):
        # Pro tier should get 403
        import uuid
        email = f"pro-{uuid.uuid4()}@test.com"
        reg = client.post("/v1/auth/register",
                          json={"email": email, "password": "password123"})
        pro_key = reg.json()["data"]["api_key"]["key"]
        # Manually set tier to 'pro' via DB
        from vectordb.models.db import get_db, User
        from vectordb.models.db import ApiKey
        db = next(get_db())
        try:
            key_row = db.query(ApiKey).filter_by(key=pro_key).first()
            if key_row and key_row.user_id:
                user = db.query(User).filter_by(id=key_row.user_id).first()
                if user:
                    user.tier = "pro"
                    db.commit()
        finally:
            db.close()
        client.post("/v1/collections", json={"name": "sum-test-pro", "dim": 4},
                    headers={"x-api-key": pro_key})
        resp = client.post(
            "/v1/collections/sum-test-pro/graph/summarize",
            json={"max_communities": 5},
            headers={"x-api-key": pro_key},
        )
        assert resp.status_code == 403

    def test_summarize_bootstrap_key_allowed(self, client):
        client.post("/v1/collections", json={"name": "sum-bootstrap", "dim": 4},
                    headers={"x-api-key": "test-key"})
        resp = client.post(
            "/v1/collections/sum-bootstrap/graph/summarize",
            json={"max_communities": 5},
            headers={"x-api-key": "test-key"},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "communities" in data
        assert data["total_communities"] == 0  # empty graph

    def test_summarize_collection_not_found(self, client):
        resp = client.post(
            "/v1/collections/nonexistent/graph/summarize",
            json={"max_communities": 5},
            headers={"x-api-key": "test-key"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "error"

    def test_community_detection_unit(self):
        """Unit test community_detection with a simple graph."""
        import networkx as nx
        from vectordb.services.graph_retrieval import community_detection

        G = nx.MultiDiGraph()
        # Cluster 1: Apple, Beats, Music (connected)
        G.add_node(1, entity_text="Apple", entity_type="ORG")
        G.add_node(2, entity_text="Beats", entity_type="ORG")
        G.add_node(3, entity_text="Music", entity_type="CONCEPT")
        G.add_edge(1, 2, relation_type="acquired", weight=1.0)
        G.add_edge(2, 3, relation_type="produces", weight=1.0)
        # Cluster 2: Google, YouTube (connected)
        G.add_node(4, entity_text="Google", entity_type="ORG")
        G.add_node(5, entity_text="YouTube", entity_type="ORG")
        G.add_edge(4, 5, relation_type="owns", weight=1.0)

        result = community_detection(G, max_communities=10)
        # Should detect communities (at least 1, probably 2)
        assert len(result) >= 1
        assert all("id" in c and "size" in c and "entities" in c for c in result)

    def test_community_detection_empty_graph(self):
        import networkx as nx
        from vectordb.services.graph_retrieval import community_detection

        G = nx.MultiDiGraph()
        result = community_detection(G)
        assert result == []
