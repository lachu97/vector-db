# tests/test_batch_delete.py
from tests.conftest import random_vector


def _ensure_collection(client, headers):
    """Ensure the batch-test collection exists."""
    client.post("/v1/collections", json={
        "name": "batch-del-col",
        "dim": 128,
    }, headers=headers)


def test_batch_delete(client, headers):
    _ensure_collection(client, headers)

    # Seed vectors
    for eid in ["bd-1", "bd-2", "bd-3"]:
        client.post("/v1/collections/batch-del-col/upsert", json={
            "external_id": eid,
            "vector": random_vector(128),
        }, headers=headers)

    resp = client.post("/v1/collections/batch-del-col/delete_batch", json={
        "external_ids": ["bd-1", "bd-2", "nonexistent"],
    }, headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert body["data"]["deleted_count"] == 2
    assert "bd-1" in body["data"]["deleted"]
    assert "bd-2" in body["data"]["deleted"]
    assert "nonexistent" in body["data"]["not_found"]


def test_batch_delete_collection_not_found(client, headers):
    resp = client.post("/v1/collections/nonexistent/delete_batch", json={
        "external_ids": ["x"],
    }, headers=headers)
    body = resp.json()
    assert body["status"] == "error"
    assert body["error"]["code"] == 404


def test_batch_delete_empty_list(client, headers):
    _ensure_collection(client, headers)
    resp = client.post("/v1/collections/batch-del-col/delete_batch", json={
        "external_ids": [],
    }, headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["deleted_count"] == 0
