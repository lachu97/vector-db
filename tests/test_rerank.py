# tests/test_rerank.py
from tests.conftest import random_vector


def _ensure_collection_with_data(client, headers):
    """Ensure rerank-col exists with test vectors."""
    client.post("/v1/collections", json={
        "name": "rerank-col",
        "dim": 128,
    }, headers=headers)
    for eid in ["rr-1", "rr-2", "rr-3"]:
        client.post("/v1/collections/rerank-col/upsert", json={
            "external_id": eid,
            "vector": random_vector(128),
            "metadata": {"label": eid},
        }, headers=headers)


def test_rerank(client, headers):
    _ensure_collection_with_data(client, headers)
    resp = client.post("/v1/collections/rerank-col/rerank", json={
        "vector": random_vector(128),
        "candidates": ["rr-1", "rr-2", "rr-3"],
    }, headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    results = body["data"]["results"]
    assert len(results) == 3
    # Results should be sorted by score descending
    scores = [r["score"] for r in results]
    assert scores == sorted(scores, reverse=True)


def test_rerank_partial_candidates(client, headers):
    _ensure_collection_with_data(client, headers)
    resp = client.post("/v1/collections/rerank-col/rerank", json={
        "vector": random_vector(128),
        "candidates": ["rr-1", "nonexistent"],
    }, headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    # Only the found candidate should be in results
    assert len(body["data"]["results"]) == 1
    assert body["data"]["results"][0]["external_id"] == "rr-1"


def test_rerank_empty_candidates(client, headers):
    _ensure_collection_with_data(client, headers)
    resp = client.post("/v1/collections/rerank-col/rerank", json={
        "vector": random_vector(128),
        "candidates": [],
    }, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["results"] == []


def test_rerank_wrong_dimension(client, headers):
    _ensure_collection_with_data(client, headers)
    resp = client.post("/v1/collections/rerank-col/rerank", json={
        "vector": random_vector(384),  # wrong dim
        "candidates": ["rr-1"],
    }, headers=headers)
    body = resp.json()
    assert body["status"] == "error"
    assert body["error"]["code"] == 400


def test_rerank_collection_not_found(client, headers):
    resp = client.post("/v1/collections/nonexistent/rerank", json={
        "vector": random_vector(128),
        "candidates": ["x"],
    }, headers=headers)
    body = resp.json()
    assert body["status"] == "error"
    assert body["error"]["code"] == 404


def test_rerank_legacy_endpoint(client, headers):
    """Test that the legacy /v1/rerank endpoint works via default collection."""
    # Seed default collection with vectors
    client.post("/v1/upsert", json={
        "external_id": "legacy-rr-1",
        "vector": random_vector(384),
    }, headers=headers)
    client.post("/v1/upsert", json={
        "external_id": "legacy-rr-2",
        "vector": random_vector(384),
    }, headers=headers)

    resp = client.post("/v1/rerank", json={
        "vector": random_vector(384),
        "candidates": ["legacy-rr-1", "legacy-rr-2"],
    }, headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert len(body["data"]["results"]) == 2
