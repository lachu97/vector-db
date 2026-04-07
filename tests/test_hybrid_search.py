# tests/test_hybrid_search.py
from tests.conftest import random_vector


def _ensure_hybrid_collection(client, headers):
    """Ensure hybrid-col exists with text+vector data."""
    client.post("/v1/collections", json={
        "name": "hybrid-col",
        "dim": 128,
    }, headers=headers)
    docs = [
        {"external_id": "hy-1", "vector": random_vector(128),
         "metadata": {"cat": "tech"}, "content": "latest news about artificial intelligence and machine learning"},
        {"external_id": "hy-2", "vector": random_vector(128),
         "metadata": {"cat": "sports"}, "content": "football match results and upcoming games schedule"},
        {"external_id": "hy-3", "vector": random_vector(128),
         "metadata": {"cat": "tech"}, "content": "new breakthroughs in quantum computing research"},
        {"external_id": "hy-4", "vector": random_vector(128),
         "metadata": {"cat": "food"}, "content": "best recipes for homemade pasta and italian cuisine"},
    ]
    for doc in docs:
        client.post("/v1/collections/hybrid-col/upsert", json=doc, headers=headers)


def test_hybrid_search(client, headers):
    _ensure_hybrid_collection(client, headers)
    resp = client.post("/v1/collections/hybrid-col/hybrid_search", json={
        "query_text": "artificial intelligence",
        "vector": random_vector(128),
        "k": 3,
    }, headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    results = body["data"]["results"]
    assert len(results) <= 3
    # Each result should have both vector_score and text_score fields
    for r in results:
        assert "external_id" in r
        assert "score" in r


def test_hybrid_search_text_only_match(client, headers):
    _ensure_hybrid_collection(client, headers)
    resp = client.post("/v1/collections/hybrid-col/hybrid_search", json={
        "query_text": "pasta recipes italian",
        "vector": random_vector(128),
        "k": 2,
        "alpha": 0.0,  # text only
    }, headers=headers)
    assert resp.status_code == 200
    results = resp.json()["data"]["results"]
    # hy-4 should rank highly since it contains "pasta" and "italian" and "recipes"
    if results:
        # The food doc should be in results
        eids = [r["external_id"] for r in results]
        assert "hy-4" in eids


def test_hybrid_search_vector_only(client, headers):
    _ensure_hybrid_collection(client, headers)
    resp = client.post("/v1/collections/hybrid-col/hybrid_search", json={
        "query_text": "anything",
        "vector": random_vector(128),
        "k": 2,
        "alpha": 1.0,  # vector only
    }, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"


def test_hybrid_search_with_filters(client, headers):
    _ensure_hybrid_collection(client, headers)
    resp = client.post("/v1/collections/hybrid-col/hybrid_search", json={
        "query_text": "intelligence",
        "vector": random_vector(128),
        "k": 10,
        "filters": {"cat": "tech"},
    }, headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    for r in body["data"]["results"]:
        assert r["metadata"]["cat"] == "tech"


def test_hybrid_search_with_pagination(client, headers):
    _ensure_hybrid_collection(client, headers)
    resp = client.post("/v1/collections/hybrid-col/hybrid_search", json={
        "query_text": "news",
        "vector": random_vector(128),
        "k": 1,
        "offset": 1,
    }, headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()["data"]["results"]) <= 1


def test_hybrid_search_invalid_alpha(client, headers):
    _ensure_hybrid_collection(client, headers)
    resp = client.post("/v1/collections/hybrid-col/hybrid_search", json={
        "query_text": "test",
        "vector": random_vector(128),
        "k": 2,
        "alpha": 1.5,
    }, headers=headers)
    body = resp.json()
    assert body["status"] == "error"


def test_hybrid_search_wrong_dimension(client, headers):
    _ensure_hybrid_collection(client, headers)
    resp = client.post("/v1/collections/hybrid-col/hybrid_search", json={
        "query_text": "test",
        "vector": random_vector(384),  # wrong dim
        "k": 2,
    }, headers=headers)
    body = resp.json()
    assert body["status"] == "error"
    assert body["error"]["code"] == 400


def test_hybrid_search_collection_not_found(client, headers):
    resp = client.post("/v1/collections/nonexistent/hybrid_search", json={
        "query_text": "test",
        "vector": random_vector(128),
        "k": 2,
    }, headers=headers)
    body = resp.json()
    assert body["status"] == "error"


def test_hybrid_search_legacy_endpoint(client, headers):
    """Test legacy /v1/hybrid_search routes to default collection."""
    # Seed with content
    client.post("/v1/upsert", json={
        "external_id": "legacy-hy-1",
        "vector": random_vector(384),
        "content": "machine learning algorithms",
    }, headers=headers)
    resp = client.post("/v1/hybrid_search", json={
        "query_text": "machine learning",
        "vector": random_vector(384),
        "k": 2,
    }, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"
