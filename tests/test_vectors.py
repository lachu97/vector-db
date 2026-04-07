# tests/test_vectors.py
from tests.conftest import random_vector


def test_upsert_requires_auth(client, bad_headers):
    resp = client.post("/v1/upsert", json={
        "external_id": "noauth",
        "vector": random_vector(),
    }, headers=bad_headers)
    assert resp.status_code == 401


def test_upsert_insert(client, headers):
    resp = client.post("/v1/upsert", json={
        "external_id": "test-doc-1",
        "vector": random_vector(),
        "metadata": {"type": "article", "lang": "en"},
    }, headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert body["data"]["status"] == "inserted"
    assert body["data"]["external_id"] == "test-doc-1"


def test_upsert_update(client, headers):
    resp = client.post("/v1/upsert", json={
        "external_id": "test-doc-1",
        "vector": random_vector(),
        "metadata": {"type": "blog"},
    }, headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["status"] == "updated"


def test_upsert_wrong_dimension(client, headers):
    resp = client.post("/v1/upsert", json={
        "external_id": "bad-dim",
        "vector": [0.1, 0.2, 0.3],
    }, headers=headers)
    body = resp.json()
    assert body["status"] == "error"
    assert body["error"]["code"] == 400


def test_bulk_upsert(client, headers):
    items = [
        {"external_id": "bulk-1", "vector": random_vector(), "metadata": {"type": "blog"}},
        {"external_id": "bulk-2", "vector": random_vector(), "metadata": {"type": "news"}},
    ]
    resp = client.post("/v1/bulk_upsert", json={"items": items}, headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert len(body["data"]["results"]) == 2
    for r in body["data"]["results"]:
        assert r["status"] == "inserted"


def test_bulk_upsert_wrong_dimension(client, headers):
    items = [
        {"external_id": "bad-bulk", "vector": [0.1], "metadata": {}},
    ]
    resp = client.post("/v1/bulk_upsert", json={"items": items}, headers=headers)
    body = resp.json()
    assert body["status"] == "error"


def test_delete(client, headers):
    client.post("/v1/upsert", json={
        "external_id": "to-delete",
        "vector": random_vector(),
    }, headers=headers)

    resp = client.delete("/v1/delete/to-delete", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["status"] == "deleted"


def test_delete_not_found(client, headers):
    resp = client.delete("/v1/delete/nonexistent", headers=headers)
    body = resp.json()
    assert body["status"] == "error"
    assert body["error"]["code"] == 404
