# tests/test_new_features.py
"""
Tests for 4 new features:
  1. Per-key usage tracking (GET /v1/admin/keys/:id/usage, GET /v1/admin/keys/usage/summary)
  2. total_count in search results
  3. Collection description (create + PATCH /v1/collections/:name)
  4. Vector export (GET /v1/collections/:name/export)
"""
import pytest
from tests.conftest import random_vector

ADMIN = {"x-api-key": "test-key"}
DIM = 384


# ==============================================================================
# Helpers
# ==============================================================================

def make_collection(client, name, dim=DIM, metric="cosine", description=None):
    body = {"name": name, "dim": dim, "distance_metric": metric}
    if description is not None:
        body["description"] = description
    r = client.post("/v1/collections", json=body, headers=ADMIN)
    assert r.status_code == 200, r.text
    return r.json()["data"]


def upsert_vector(client, collection, external_id, vector=None, metadata=None):
    if vector is None:
        vector = random_vector(DIM)
    body = {"external_id": external_id, "vector": vector}
    if metadata:
        body["metadata"] = metadata
    r = client.post(f"/v1/collections/{collection}/upsert", json=body, headers=ADMIN)
    assert r.status_code == 200, r.text
    return r.json()


def create_api_key(client, name, role="readwrite"):
    r = client.post("/v1/admin/keys", json={"name": name, "role": role}, headers=ADMIN)
    assert r.status_code == 200, r.text
    return r.json()["data"]


# ==============================================================================
# 1. Per-key usage tracking
# ==============================================================================

class TestKeyUsage:
    def test_usage_endpoint_exists(self, client):
        key = create_api_key(client, "usage-test-key")
        key_id = key["id"]
        r = client.get(f"/v1/admin/keys/{key_id}/usage", headers=ADMIN)
        assert r.status_code == 200
        data = r.json()["data"]
        assert "total_requests" in data
        assert "last_24h" in data
        assert "last_7d" in data
        assert "last_30d" in data
        assert "by_endpoint" in data

    def test_usage_increments_after_request(self, client):
        key = create_api_key(client, "usage-increment-key")
        key_id = key["id"]
        key_value = key["key"]

        # Make a request using the new key
        r = client.get("/v1/collections", headers={"x-api-key": key_value})
        assert r.status_code == 200

        # Check usage increased
        r = client.get(f"/v1/admin/keys/{key_id}/usage", headers=ADMIN)
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["total_requests"] >= 1

    def test_usage_by_endpoint_populated(self, client):
        key = create_api_key(client, "usage-endpoint-key")
        key_id = key["id"]
        key_value = key["key"]

        # Make a few requests
        client.get("/v1/collections", headers={"x-api-key": key_value})
        client.get("/v1/collections", headers={"x-api-key": key_value})

        r = client.get(f"/v1/admin/keys/{key_id}/usage", headers=ADMIN)
        data = r.json()["data"]
        assert isinstance(data["by_endpoint"], dict)
        assert len(data["by_endpoint"]) >= 1

    def test_usage_summary_endpoint(self, client):
        r = client.get("/v1/admin/keys/usage/summary", headers=ADMIN)
        assert r.status_code == 200
        data = r.json()["data"]
        assert "overall" in data
        assert "by_key" in data
        assert isinstance(data["by_key"], list)

    def test_usage_nonexistent_key(self, client):
        r = client.get("/v1/admin/keys/999999/usage", headers=ADMIN)
        body = r.json()
        assert body["status"] == "error"
        assert body["error"]["code"] == 404

    def test_usage_requires_admin(self, client):
        key = create_api_key(client, "usage-readonly-key", role="readonly")
        key_id = key["id"]
        readonly_headers = {"x-api-key": key["key"]}
        r = client.get(f"/v1/admin/keys/{key_id}/usage", headers=readonly_headers)
        assert r.status_code == 403


# ==============================================================================
# 2. total_count in search results
# ==============================================================================

class TestSearchTotalCount:
    def test_search_returns_total_count(self, client):
        col = make_collection(client, "search-count-col")
        name = col["name"]

        # Insert 5 vectors
        for i in range(5):
            upsert_vector(client, name, f"vec-{i}")

        q = random_vector(DIM)
        r = client.post(f"/v1/collections/{name}/search",
                        json={"vector": q, "k": 3},
                        headers=ADMIN)
        assert r.status_code == 200
        data = r.json()["data"]
        assert "total_count" in data
        assert data["total_count"] >= 5
        assert "k" in data
        assert data["k"] == 3
        assert "offset" in data
        assert data["offset"] == 0

    def test_search_total_count_with_offset(self, client):
        col = make_collection(client, "search-offset-col")
        name = col["name"]

        for i in range(10):
            upsert_vector(client, name, f"off-vec-{i}")

        q = random_vector(DIM)
        r = client.post(f"/v1/collections/{name}/search",
                        json={"vector": q, "k": 5, "offset": 3},
                        headers=ADMIN)
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["total_count"] >= 10
        assert data["offset"] == 3

    def test_legacy_search_returns_total_count(self, client):
        # Insert into default collection via legacy endpoint to ensure it exists
        r = client.post("/v1/upsert",
                        json={"external_id": "legacy-tc-1", "vector": random_vector(DIM)},
                        headers=ADMIN)
        assert r.status_code == 200

        q = random_vector(DIM)
        r = client.post("/v1/search", json={"vector": q, "k": 5}, headers=ADMIN)
        assert r.status_code == 200
        data = r.json()["data"]
        assert "total_count" in data
        assert "k" in data
        assert "offset" in data


# ==============================================================================
# 3. Collection description
# ==============================================================================

class TestCollectionDescription:
    def test_create_collection_with_description(self, client):
        col = make_collection(client, "desc-col-1", description="My test collection")
        assert col["description"] == "My test collection"

    def test_create_collection_without_description(self, client):
        col = make_collection(client, "desc-col-2")
        assert col.get("description") is None or col["description"] is None

    def test_get_collection_includes_description(self, client):
        make_collection(client, "desc-col-3", description="Fetch me")
        r = client.get("/v1/collections/desc-col-3", headers=ADMIN)
        assert r.status_code == 200
        assert r.json()["data"]["description"] == "Fetch me"

    def test_list_collections_includes_description(self, client):
        make_collection(client, "desc-col-4", description="Listed desc")
        r = client.get("/v1/collections", headers=ADMIN)
        assert r.status_code == 200
        cols = r.json()["data"]["collections"]
        found = next((c for c in cols if c["name"] == "desc-col-4"), None)
        assert found is not None
        assert found["description"] == "Listed desc"

    def test_patch_collection_description(self, client):
        make_collection(client, "desc-col-5")
        r = client.patch("/v1/collections/desc-col-5",
                         json={"description": "Updated!"},
                         headers=ADMIN)
        assert r.status_code == 200
        assert r.json()["data"]["description"] == "Updated!"

    def test_patch_collection_clears_description(self, client):
        make_collection(client, "desc-col-6", description="Will be cleared")
        r = client.patch("/v1/collections/desc-col-6",
                         json={"description": None},
                         headers=ADMIN)
        assert r.status_code == 200
        assert r.json()["data"]["description"] is None

    def test_patch_nonexistent_collection(self, client):
        r = client.patch("/v1/collections/no-such-col-xyz",
                         json={"description": "X"},
                         headers=ADMIN)
        body = r.json()
        assert body["status"] == "error"
        assert body["error"]["code"] == 404

    def test_patch_requires_admin(self, client):
        make_collection(client, "desc-col-7")
        key = create_api_key(client, "desc-readonly", role="readonly")
        r = client.patch("/v1/collections/desc-col-7",
                         json={"description": "Unauthorized"},
                         headers={"x-api-key": key["key"]})
        assert r.status_code == 403


# ==============================================================================
# 4. Vector export
# ==============================================================================

class TestVectorExport:
    def test_export_basic(self, client):
        col = make_collection(client, "export-col-1")
        name = col["name"]

        vecs = {}
        for i in range(5):
            v = random_vector(DIM)
            vecs[f"exp-{i}"] = v
            upsert_vector(client, name, f"exp-{i}", vector=v)

        r = client.get(f"/v1/collections/{name}/export", headers=ADMIN)
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["collection"] == name
        assert data["dim"] == DIM
        assert data["count"] == 5
        assert len(data["vectors"]) == 5

    def test_export_vector_fields(self, client):
        col = make_collection(client, "export-col-2")
        name = col["name"]
        upsert_vector(client, name, "exp-field-1", metadata={"tag": "hello"})

        r = client.get(f"/v1/collections/{name}/export", headers=ADMIN)
        assert r.status_code == 200
        v = r.json()["data"]["vectors"][0]
        assert "external_id" in v
        assert "vector" in v
        assert isinstance(v["vector"], list)
        assert len(v["vector"]) == DIM

    def test_export_empty_collection(self, client):
        col = make_collection(client, "export-empty")
        r = client.get(f"/v1/collections/{col['name']}/export", headers=ADMIN)
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["count"] == 0
        assert data["vectors"] == []

    def test_export_with_limit(self, client):
        col = make_collection(client, "export-limit-col")
        name = col["name"]

        for i in range(10):
            upsert_vector(client, name, f"lim-{i}")

        r = client.get(f"/v1/collections/{name}/export?limit=3", headers=ADMIN)
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["count"] <= 3

    def test_export_limit_validation(self, client):
        col = make_collection(client, "export-limit-val")
        name = col["name"]

        r = client.get(f"/v1/collections/{name}/export?limit=0", headers=ADMIN)
        body = r.json()
        assert body["status"] == "error"
        assert body["error"]["code"] == 400

        r = client.get(f"/v1/collections/{name}/export?limit=200000", headers=ADMIN)
        body = r.json()
        assert body["status"] == "error"
        assert body["error"]["code"] == 400

    def test_export_nonexistent_collection(self, client):
        r = client.get("/v1/collections/does-not-exist-xyz/export", headers=ADMIN)
        body = r.json()
        assert body["status"] == "error"
        assert body["error"]["code"] == 404

    def test_export_requires_auth(self, client):
        col = make_collection(client, "export-auth-col")
        r = client.get(f"/v1/collections/{col['name']}/export")
        assert r.status_code in (401, 403)
