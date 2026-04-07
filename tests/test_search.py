# tests/test_search.py
from tests.conftest import random_vector


def _seed_vectors(client, headers):
    """Ensure we have vectors to search against."""
    for eid in ["search-1", "search-2", "search-3"]:
        client.post("/v1/upsert", json={
            "external_id": eid,
            "vector": random_vector(),
            "metadata": {"type": "article" if eid != "search-3" else "blog"},
        }, headers=headers)


def test_search(client, headers):
    _seed_vectors(client, headers)
    resp = client.post("/v1/search", json={
        "vector": random_vector(),
        "k": 2,
    }, headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert len(body["data"]["results"]) <= 2
    for r in body["data"]["results"]:
        assert "external_id" in r
        assert "score" in r


def test_search_with_filters(client, headers):
    _seed_vectors(client, headers)
    resp = client.post("/v1/search", json={
        "vector": random_vector(),
        "k": 10,
        "filters": {"type": "blog"},
    }, headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    for r in body["data"]["results"]:
        assert r["metadata"]["type"] == "blog"


def test_search_wrong_dimension(client, headers):
    resp = client.post("/v1/search", json={
        "vector": [0.1, 0.2],
        "k": 2,
    }, headers=headers)
    body = resp.json()
    assert body["status"] == "error"


def test_search_with_pagination(client, headers):
    _seed_vectors(client, headers)
    # Get all results
    resp_all = client.post("/v1/search", json={
        "vector": random_vector(),
        "k": 10,
    }, headers=headers)
    all_results = resp_all.json()["data"]["results"]

    # Get with offset
    resp_offset = client.post("/v1/search", json={
        "vector": random_vector(),
        "k": 2,
        "offset": 1,
    }, headers=headers)
    assert resp_offset.status_code == 200
    offset_results = resp_offset.json()["data"]["results"]
    assert len(offset_results) <= 2


def test_recommend(client, headers):
    _seed_vectors(client, headers)
    resp = client.post("/v1/recommend/search-1?k=2", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    for r in body["data"]["results"]:
        assert r["external_id"] != "search-1"


def test_recommend_not_found(client, headers):
    resp = client.post("/v1/recommend/nonexistent?k=2", headers=headers)
    body = resp.json()
    assert body["status"] == "error"
    assert body["error"]["code"] == 404


def test_similarity(client, headers):
    _seed_vectors(client, headers)
    resp = client.post("/v1/similarity?id1=search-1&id2=search-2", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert "score" in body["data"]
    assert -1.0 <= body["data"]["score"] <= 1.0


def test_similarity_not_found(client, headers):
    resp = client.post("/v1/similarity?id1=search-1&id2=nonexistent", headers=headers)
    body = resp.json()
    assert body["status"] == "error"
