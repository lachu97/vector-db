# tests/test_phase3.py
"""
Phase 3: Security & Auth tests.

Covers:
- Multi-API key system with roles (admin, readwrite, readonly)
- Rate limiting per API key
- CORS headers
- Request validation hardening (batch size, metadata size, vector dim)
"""
import pytest
from tests.conftest import random_vector


# ---------------------------------------------------------------------------
# Fixtures: role-specific clients / headers
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def admin_headers():
    return {"x-api-key": "test-key"}  # bootstrap admin key from conftest


@pytest.fixture(scope="module")
def readwrite_key(client, admin_headers):
    """Create a readwrite API key, return plain-text key."""
    resp = client.post(
        "/v1/admin/keys",
        json={"name": "rw-test", "role": "readwrite"},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    return resp.json()["data"]["key"]


@pytest.fixture(scope="module")
def readonly_key(client, admin_headers):
    """Create a readonly API key, return plain-text key."""
    resp = client.post(
        "/v1/admin/keys",
        json={"name": "ro-test", "role": "readonly"},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    return resp.json()["data"]["key"]


@pytest.fixture(scope="module")
def rw_headers(readwrite_key):
    return {"x-api-key": readwrite_key}


@pytest.fixture(scope="module")
def ro_headers(readonly_key):
    return {"x-api-key": readonly_key}


# ---------------------------------------------------------------------------
# Setup: collection used across role tests
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module", autouse=True)
def phase3_collection(client, admin_headers):
    """Create a collection for Phase 3 tests (admin only)."""
    client.post("/v1/collections", json={
        "name": "phase3-col",
        "dim": 32,
        "distance_metric": "cosine",
    }, headers=admin_headers)
    # Insert a vector so search/recommend have something to work with
    client.post("/v1/collections/phase3-col/upsert", json={
        "external_id": "p3-vec-1",
        "vector": random_vector(32),
        "metadata": {"tag": "test"},
    }, headers=admin_headers)


# ===========================================================================
# 1. API Key Management Endpoints
# ===========================================================================

class TestApiKeyManagement:
    def test_create_key_admin_only(self, client, admin_headers):
        resp = client.post(
            "/v1/admin/keys",
            json={"name": "temp-key", "role": "readonly"},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["role"] == "readonly"
        assert "key" in data
        assert len(data["key"]) > 10  # non-trivial key

    def test_create_key_invalid_role(self, client, admin_headers):
        resp = client.post(
            "/v1/admin/keys",
            json={"name": "bad", "role": "superuser"},
            headers=admin_headers,
        )
        body = resp.json()
        assert body["status"] == "error"
        assert body["error"]["code"] == 400

    def test_create_key_empty_name(self, client, admin_headers):
        resp = client.post(
            "/v1/admin/keys",
            json={"name": "  ", "role": "readonly"},
            headers=admin_headers,
        )
        body = resp.json()
        assert body["status"] == "error"
        assert body["error"]["code"] == 400

    def test_list_keys_admin_only(self, client, admin_headers):
        resp = client.get("/v1/admin/keys", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "keys" in data
        assert isinstance(data["keys"], list)

    def test_list_keys_no_key_values(self, client, admin_headers):
        """Listing keys must not expose the raw key values."""
        resp = client.get("/v1/admin/keys", headers=admin_headers)
        for entry in resp.json()["data"]["keys"]:
            assert "key" not in entry

    def test_delete_key(self, client, admin_headers):
        # Create a key to delete
        create_resp = client.post(
            "/v1/admin/keys",
            json={"name": "to-delete", "role": "readonly"},
            headers=admin_headers,
        )
        key_id = create_resp.json()["data"]["id"]
        delete_resp = client.delete(f"/v1/admin/keys/{key_id}", headers=admin_headers)
        assert delete_resp.status_code == 200
        assert delete_resp.json()["data"]["status"] == "deleted"

    def test_delete_key_not_found(self, client, admin_headers):
        resp = client.delete("/v1/admin/keys/99999", headers=admin_headers)
        body = resp.json()
        assert body["status"] == "error"
        assert body["error"]["code"] == 404

    def test_deleted_key_no_longer_works(self, client, admin_headers):
        """A deleted key should receive 401 on subsequent requests."""
        create_resp = client.post(
            "/v1/admin/keys",
            json={"name": "revoke-test", "role": "readonly"},
            headers=admin_headers,
        )
        key_val = create_resp.json()["data"]["key"]
        key_id = create_resp.json()["data"]["id"]

        # Key works before deletion
        resp1 = client.get("/v1/health", headers={"x-api-key": key_val})
        assert resp1.status_code == 200

        # Delete the key
        client.delete(f"/v1/admin/keys/{key_id}", headers=admin_headers)

        # Key no longer works
        resp2 = client.get("/v1/health", headers={"x-api-key": key_val})
        assert resp2.status_code == 401


# ===========================================================================
# 2. Role Enforcement
# ===========================================================================

class TestRoleEnforcement:
    # --- Admin-only endpoints ---

    def test_create_collection_requires_admin(self, client, rw_headers, ro_headers):
        for hdrs in (rw_headers, ro_headers):
            resp = client.post("/v1/collections", json={
                "name": "should-not-create",
                "dim": 32,
            }, headers=hdrs)
            assert resp.status_code == 403

    def test_delete_collection_requires_admin(self, client, rw_headers, ro_headers):
        for hdrs in (rw_headers, ro_headers):
            resp = client.delete("/v1/collections/phase3-col", headers=hdrs)
            assert resp.status_code == 403

    def test_create_key_requires_admin(self, client, rw_headers, ro_headers):
        for hdrs in (rw_headers, ro_headers):
            resp = client.post(
                "/v1/admin/keys",
                json={"name": "x", "role": "readonly"},
                headers=hdrs,
            )
            assert resp.status_code == 403

    def test_list_keys_requires_admin(self, client, rw_headers, ro_headers):
        for hdrs in (rw_headers, ro_headers):
            resp = client.get("/v1/admin/keys", headers=hdrs)
            assert resp.status_code == 403

    def test_delete_key_requires_admin(self, client, rw_headers, ro_headers):
        for hdrs in (rw_headers, ro_headers):
            resp = client.delete("/v1/admin/keys/1", headers=hdrs)
            assert resp.status_code == 403

    # --- Readwrite+ endpoints ---

    def test_upsert_requires_readwrite(self, client, ro_headers):
        resp = client.post("/v1/collections/phase3-col/upsert", json={
            "external_id": "ro-attempt",
            "vector": random_vector(32),
        }, headers=ro_headers)
        assert resp.status_code == 403

    def test_bulk_upsert_requires_readwrite(self, client, ro_headers):
        resp = client.post("/v1/collections/phase3-col/bulk_upsert", json={
            "items": [{"external_id": "x", "vector": random_vector(32)}]
        }, headers=ro_headers)
        assert resp.status_code == 403

    def test_delete_vector_requires_readwrite(self, client, ro_headers):
        resp = client.delete("/v1/collections/phase3-col/delete/p3-vec-1", headers=ro_headers)
        assert resp.status_code == 403

    def test_batch_delete_requires_readwrite(self, client, ro_headers):
        resp = client.post("/v1/collections/phase3-col/delete_batch", json={
            "external_ids": ["p3-vec-1"]
        }, headers=ro_headers)
        assert resp.status_code == 403

    def test_upsert_allowed_for_readwrite(self, client, rw_headers):
        resp = client.post("/v1/collections/phase3-col/upsert", json={
            "external_id": "rw-insert",
            "vector": random_vector(32),
        }, headers=rw_headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "inserted"

    def test_upsert_allowed_for_admin(self, client, admin_headers):
        resp = client.post("/v1/collections/phase3-col/upsert", json={
            "external_id": "admin-insert",
            "vector": random_vector(32),
        }, headers=admin_headers)
        assert resp.status_code == 200

    # --- Readonly+ endpoints ---

    def test_search_allowed_for_readonly(self, client, ro_headers):
        resp = client.post("/v1/collections/phase3-col/search", json={
            "vector": random_vector(32),
            "k": 2,
        }, headers=ro_headers)
        assert resp.status_code == 200

    def test_health_allowed_for_readonly(self, client, ro_headers):
        resp = client.get("/v1/health", headers=ro_headers)
        assert resp.status_code == 200

    def test_list_collections_allowed_for_readonly(self, client, ro_headers):
        resp = client.get("/v1/collections", headers=ro_headers)
        assert resp.status_code == 200

    def test_get_collection_allowed_for_readonly(self, client, ro_headers):
        resp = client.get("/v1/collections/phase3-col", headers=ro_headers)
        assert resp.status_code == 200

    def test_recommend_allowed_for_readonly(self, client, ro_headers):
        resp = client.post(
            "/v1/collections/phase3-col/recommend/p3-vec-1?k=1",
            headers=ro_headers,
        )
        assert resp.status_code == 200

    # --- No key at all ---

    def test_no_key_returns_401(self, client):
        resp = client.get("/v1/health")
        assert resp.status_code == 401

    def test_wrong_key_returns_401(self, client, bad_headers):
        resp = client.get("/v1/health", headers=bad_headers)
        assert resp.status_code == 401


# ===========================================================================
# 3. CORS Headers
# ===========================================================================

class TestCORS:
    def test_cors_preflight(self, client):
        """OPTIONS preflight should return CORS headers."""
        resp = client.options(
            "/v1/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "x-api-key",
            },
        )
        # CORS middleware should handle preflight (200 or 204)
        assert resp.status_code in (200, 204)
        assert "access-control-allow-origin" in resp.headers

    def test_cors_header_on_response(self, client, admin_headers):
        """Regular requests should include CORS allow-origin header."""
        resp = client.get(
            "/v1/health",
            headers={**admin_headers, "Origin": "http://localhost:3000"},
        )
        assert resp.status_code == 200
        assert "access-control-allow-origin" in resp.headers


# ===========================================================================
# 4. Request Validation Hardening
# ===========================================================================

class TestValidationHardening:
    def test_create_collection_dim_too_large(self, client, admin_headers):
        """Dimension exceeding max_vector_dim should be rejected."""
        resp = client.post("/v1/collections", json={
            "name": "too-big",
            "dim": 99999,  # exceeds default max of 10000
        }, headers=admin_headers)
        body = resp.json()
        assert body["status"] == "error"
        assert body["error"]["code"] == 400

    def test_create_collection_dim_zero(self, client, admin_headers):
        resp = client.post("/v1/collections", json={
            "name": "zero-dim",
            "dim": 0,
        }, headers=admin_headers)
        body = resp.json()
        assert body["status"] == "error"
        assert body["error"]["code"] == 400

    def test_bulk_upsert_batch_too_large(self, client, admin_headers):
        """Bulk upsert exceeding max_batch_size should be rejected."""
        # conftest sets MAX_ELEMENTS=1000 but we need to test batch size limit
        # We override via env in conftest: MAX_BATCH_SIZE is default 1000
        # Create 1001 items (one over the default limit)
        items = [
            {"external_id": f"batch-{i}", "vector": random_vector(32)}
            for i in range(1001)
        ]
        resp = client.post(
            "/v1/collections/phase3-col/bulk_upsert",
            json={"items": items},
            headers=admin_headers,
        )
        body = resp.json()
        assert body["status"] == "error"
        assert body["error"]["code"] == 400
        assert "batch size" in body["error"]["message"].lower()

    def test_batch_delete_too_large(self, client, admin_headers):
        """Batch delete exceeding max_batch_size should be rejected."""
        ids = [f"del-{i}" for i in range(1001)]
        resp = client.post(
            "/v1/collections/phase3-col/delete_batch",
            json={"external_ids": ids},
            headers=admin_headers,
        )
        body = resp.json()
        assert body["status"] == "error"
        assert body["error"]["code"] == 400

    def test_upsert_metadata_too_large(self, client, admin_headers):
        """Metadata with too many keys should be rejected."""
        big_meta = {f"key_{i}": i for i in range(51)}  # 51 keys > default max of 50
        resp = client.post("/v1/collections/phase3-col/upsert", json={
            "external_id": "big-meta",
            "vector": random_vector(32),
            "metadata": big_meta,
        }, headers=admin_headers)
        body = resp.json()
        assert body["status"] == "error"
        assert body["error"]["code"] == 400
        assert "metadata" in body["error"]["message"].lower()

    def test_upsert_metadata_at_limit_is_ok(self, client, admin_headers):
        """Metadata with exactly max keys should succeed."""
        ok_meta = {f"key_{i}": i for i in range(50)}  # exactly 50 = default max
        resp = client.post("/v1/collections/phase3-col/upsert", json={
            "external_id": "ok-meta",
            "vector": random_vector(32),
            "metadata": ok_meta,
        }, headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "inserted"

    def test_bulk_upsert_item_metadata_too_large(self, client, admin_headers):
        """Bulk upsert item with oversized metadata should be rejected."""
        big_meta = {f"k_{i}": i for i in range(51)}
        resp = client.post("/v1/collections/phase3-col/bulk_upsert", json={
            "items": [
                {"external_id": "bulk-meta-ok", "vector": random_vector(32)},
                {"external_id": "bulk-meta-bad", "vector": random_vector(32), "metadata": big_meta},
            ]
        }, headers=admin_headers)
        body = resp.json()
        assert body["status"] == "error"
        assert body["error"]["code"] == 400


# ===========================================================================
# 5. Rate Limiting
# ===========================================================================

class TestRateLimiting:
    def test_rate_limit_triggers(self, client):
        """Exceeding rate limit should return 429."""
        # Create a dedicated key for this test to avoid polluting shared state
        admin_hdrs = {"x-api-key": "test-key"}
        create_resp = client.post(
            "/v1/admin/keys",
            json={"name": "rate-limit-test", "role": "readonly"},
            headers=admin_hdrs,
        )
        key = create_resp.json()["data"]["key"]
        hdrs = {"x-api-key": key}

        # Override the rate limit by sending many requests.
        # The test app uses default rate_limit_per_minute=100, but we can
        # test the mechanism by monkey-patching the middleware.
        # Instead, verify the 429 response structure by calling the middleware
        # directly via a low-limit middleware instance.
        from vectordb.middleware import RateLimitMiddleware
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        mini_app = FastAPI()

        @mini_app.get("/ping")
        def ping():
            return {"ok": True}

        mini_app.add_middleware(RateLimitMiddleware, requests_per_minute=3)

        with TestClient(mini_app) as mini_client:
            for i in range(3):
                r = mini_client.get("/ping", headers={"x-api-key": "rl-key"})
                assert r.status_code == 200
            # 4th request should be rate-limited
            r = mini_client.get("/ping", headers={"x-api-key": "rl-key"})
            assert r.status_code == 429
            body = r.json()
            assert body["error"]["code"] == 429
            assert "rate limit" in body["error"]["message"].lower()

    def test_rate_limit_per_key_independent(self):
        """Different API keys should have independent rate limit counters."""
        from vectordb.middleware import RateLimitMiddleware
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        mini_app = FastAPI()

        @mini_app.get("/ping")
        def ping():
            return {"ok": True}

        mini_app.add_middleware(RateLimitMiddleware, requests_per_minute=2)

        with TestClient(mini_app) as mini_client:
            # Exhaust key-A's limit
            for _ in range(2):
                mini_client.get("/ping", headers={"x-api-key": "key-A"})
            assert mini_client.get("/ping", headers={"x-api-key": "key-A"}).status_code == 429

            # key-B should still be fine
            assert mini_client.get("/ping", headers={"x-api-key": "key-B"}).status_code == 200
