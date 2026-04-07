# tests/test_collections.py
from tests.conftest import random_vector


def test_create_collection(client, headers):
    resp = client.post("/v1/collections", json={
        "name": "test-col",
        "dim": 128,
        "distance_metric": "cosine",
    }, headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert body["data"]["name"] == "test-col"
    assert body["data"]["dim"] == 128
    assert body["data"]["distance_metric"] == "cosine"


def test_create_collection_l2(client, headers):
    resp = client.post("/v1/collections", json={
        "name": "test-l2",
        "dim": 64,
        "distance_metric": "l2",
    }, headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["distance_metric"] == "l2"


def test_create_collection_ip(client, headers):
    resp = client.post("/v1/collections", json={
        "name": "test-ip",
        "dim": 64,
        "distance_metric": "ip",
    }, headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["distance_metric"] == "ip"


def test_create_collection_invalid_metric(client, headers):
    resp = client.post("/v1/collections", json={
        "name": "bad-metric",
        "dim": 128,
        "distance_metric": "manhattan",
    }, headers=headers)
    body = resp.json()
    assert body["status"] == "error"
    assert body["error"]["code"] == 400


def test_create_collection_duplicate(client, headers):
    resp = client.post("/v1/collections", json={
        "name": "test-col",
        "dim": 128,
    }, headers=headers)
    body = resp.json()
    assert body["status"] == "error"
    assert body["error"]["code"] == 409


def test_list_collections(client, headers):
    resp = client.get("/v1/collections", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    names = [c["name"] for c in body["data"]["collections"]]
    assert "test-col" in names


def test_get_collection(client, headers):
    resp = client.get("/v1/collections/test-col", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["name"] == "test-col"
    assert body["data"]["dim"] == 128


def test_get_collection_not_found(client, headers):
    resp = client.get("/v1/collections/nonexistent", headers=headers)
    body = resp.json()
    assert body["status"] == "error"
    assert body["error"]["code"] == 404


def test_collection_scoped_upsert(client, headers):
    resp = client.post("/v1/collections/test-col/upsert", json={
        "external_id": "col-doc-1",
        "vector": random_vector(128),
        "metadata": {"type": "test"},
    }, headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["status"] == "inserted"


def test_collection_scoped_upsert_wrong_dim(client, headers):
    resp = client.post("/v1/collections/test-col/upsert", json={
        "external_id": "col-doc-bad",
        "vector": random_vector(384),  # wrong dim for this collection
    }, headers=headers)
    body = resp.json()
    assert body["status"] == "error"
    assert body["error"]["code"] == 400


def test_collection_scoped_bulk_upsert(client, headers):
    items = [
        {"external_id": "col-bulk-1", "vector": random_vector(128), "metadata": {"cat": "a"}},
        {"external_id": "col-bulk-2", "vector": random_vector(128), "metadata": {"cat": "b"}},
        {"external_id": "col-bulk-3", "vector": random_vector(128), "metadata": {"cat": "a"}},
    ]
    resp = client.post("/v1/collections/test-col/bulk_upsert", json={"items": items}, headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert len(body["data"]["results"]) == 3


def test_collection_scoped_search(client, headers):
    resp = client.post("/v1/collections/test-col/search", json={
        "vector": random_vector(128),
        "k": 2,
    }, headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert len(body["data"]["results"]) <= 2


def test_collection_scoped_search_with_filters(client, headers):
    resp = client.post("/v1/collections/test-col/search", json={
        "vector": random_vector(128),
        "k": 10,
        "filters": {"cat": "a"},
    }, headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    for r in body["data"]["results"]:
        assert r["metadata"]["cat"] == "a"


def test_collection_scoped_search_pagination(client, headers):
    resp = client.post("/v1/collections/test-col/search", json={
        "vector": random_vector(128),
        "k": 1,
        "offset": 1,
    }, headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["data"]["results"]) <= 1


def test_collection_scoped_recommend(client, headers):
    resp = client.post("/v1/collections/test-col/recommend/col-doc-1?k=2", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    for r in body["data"]["results"]:
        assert r["external_id"] != "col-doc-1"


def test_collection_scoped_similarity(client, headers):
    resp = client.post("/v1/collections/test-col/similarity?id1=col-bulk-1&id2=col-bulk-2", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "score" in body["data"]


def test_collection_scoped_delete(client, headers):
    # Insert then delete
    client.post("/v1/collections/test-col/upsert", json={
        "external_id": "col-del",
        "vector": random_vector(128),
    }, headers=headers)
    resp = client.delete("/v1/collections/test-col/delete/col-del", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "deleted"


def test_collection_not_found_on_scoped_ops(client, headers):
    resp = client.post("/v1/collections/nonexistent/upsert", json={
        "external_id": "x",
        "vector": random_vector(128),
    }, headers=headers)
    body = resp.json()
    assert body["status"] == "error"
    assert body["error"]["code"] == 404


def test_delete_collection(client, headers):
    # Create a temporary collection to delete
    client.post("/v1/collections", json={
        "name": "to-delete-col",
        "dim": 64,
    }, headers=headers)
    # Add a vector
    client.post("/v1/collections/to-delete-col/upsert", json={
        "external_id": "temp",
        "vector": random_vector(64),
    }, headers=headers)
    # Delete the collection
    resp = client.delete("/v1/collections/to-delete-col", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "deleted"

    # Verify it's gone
    resp2 = client.get("/v1/collections/to-delete-col", headers=headers)
    assert resp2.json()["status"] == "error"


def test_delete_collection_not_found(client, headers):
    resp = client.delete("/v1/collections/nonexistent", headers=headers)
    body = resp.json()
    assert body["status"] == "error"
    assert body["error"]["code"] == 404
