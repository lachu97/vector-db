# tests/test_api_keys.py
"""
Tests for the API key management endpoints:
  POST   /v1/admin/keys
  GET    /v1/admin/keys
  GET    /v1/admin/keys/:id
  PATCH  /v1/admin/keys/:id
  POST   /v1/admin/keys/:id/rotate
  DELETE /v1/admin/keys/:id
"""
import pytest
from fastapi.testclient import TestClient


ADMIN = {"x-api-key": "test-key"}


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def create_key(client, name="test-key-1", role="readwrite", expires_in_days=None):
    body = {"name": name, "role": role}
    if expires_in_days is not None:
        body["expires_in_days"] = expires_in_days
    r = client.post("/v1/admin/keys", json=body, headers=ADMIN)
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "success"
    return data["data"]


# ------------------------------------------------------------------
# Create
# ------------------------------------------------------------------

class TestCreateApiKey:
    def test_create_readwrite(self, client):
        key = create_key(client, name="rw-key", role="readwrite")
        assert key["role"] == "readwrite"
        assert key["is_active"] is True
        assert "key" in key           # returned only at creation
        assert key["expires_at"] is None
        assert key["last_used_at"] is None

    def test_create_readonly(self, client):
        key = create_key(client, name="ro-key", role="readonly")
        assert key["role"] == "readonly"

    def test_create_admin(self, client):
        key = create_key(client, name="admin-key-2", role="admin")
        assert key["role"] == "admin"

    def test_create_with_expiry(self, client):
        key = create_key(client, name="expiring-key", role="readwrite", expires_in_days=30)
        assert key["expires_at"] is not None

    def test_create_invalid_role(self, client):
        r = client.post("/v1/admin/keys", json={"name": "bad", "role": "superuser"}, headers=ADMIN)
        data = r.json()
        assert data["status"] == "error"
        assert data["error"]["code"] == 400

    def test_create_empty_name(self, client):
        r = client.post("/v1/admin/keys", json={"name": "  ", "role": "readwrite"}, headers=ADMIN)
        data = r.json()
        assert data["status"] == "error"
        assert data["error"]["code"] == 400

    def test_create_invalid_expiry(self, client):
        r = client.post(
            "/v1/admin/keys",
            json={"name": "x", "role": "readwrite", "expires_in_days": 0},
            headers=ADMIN,
        )
        data = r.json()
        assert data["status"] == "error"
        assert data["error"]["code"] == 400

    def test_create_requires_admin(self, client):
        # Create a readwrite key and try to create another key with it
        rw = create_key(client, name="rw-no-create", role="readwrite")
        r = client.post(
            "/v1/admin/keys",
            json={"name": "should-fail", "role": "readonly"},
            headers={"x-api-key": rw["key"]},
        )
        assert r.status_code == 403


# ------------------------------------------------------------------
# List
# ------------------------------------------------------------------

class TestListApiKeys:
    def test_list_returns_keys(self, client):
        r = client.get("/v1/admin/keys", headers=ADMIN)
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "success"
        assert "keys" in data["data"]
        assert isinstance(data["data"]["keys"], list)

    def test_list_does_not_include_key_value(self, client):
        r = client.get("/v1/admin/keys", headers=ADMIN)
        for k in r.json()["data"]["keys"]:
            assert "key" not in k

    def test_list_requires_admin(self, client):
        rw = create_key(client, name="rw-no-list", role="readwrite")
        r = client.get("/v1/admin/keys", headers={"x-api-key": rw["key"]})
        assert r.status_code == 403


# ------------------------------------------------------------------
# Get one
# ------------------------------------------------------------------

class TestGetApiKey:
    def test_get_existing(self, client):
        key = create_key(client, name="get-test")
        r = client.get(f"/v1/admin/keys/{key['id']}", headers=ADMIN)
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["id"] == key["id"]
        assert data["name"] == "get-test"
        assert "key" not in data

    def test_get_not_found(self, client):
        r = client.get("/v1/admin/keys/999999", headers=ADMIN)
        assert r.json()["error"]["code"] == 404


# ------------------------------------------------------------------
# Update (PATCH)
# ------------------------------------------------------------------

class TestUpdateApiKey:
    def test_rename(self, client):
        key = create_key(client, name="old-name")
        r = client.patch(f"/v1/admin/keys/{key['id']}", json={"name": "new-name"}, headers=ADMIN)
        assert r.json()["data"]["name"] == "new-name"

    def test_change_role(self, client):
        key = create_key(client, name="role-change", role="readwrite")
        r = client.patch(f"/v1/admin/keys/{key['id']}", json={"role": "readonly"}, headers=ADMIN)
        assert r.json()["data"]["role"] == "readonly"

    def test_revoke(self, client):
        key = create_key(client, name="to-revoke", role="readwrite")
        # Key works before revoke
        r = client.get("/v1/collections", headers={"x-api-key": key["key"]})
        assert r.json()["status"] == "success"

        # Revoke it
        client.patch(f"/v1/admin/keys/{key['id']}", json={"is_active": False}, headers=ADMIN)

        # Key no longer works
        r = client.get("/v1/collections", headers={"x-api-key": key["key"]})
        assert r.status_code == 401

    def test_restore(self, client):
        key = create_key(client, name="to-restore", role="readwrite")
        client.patch(f"/v1/admin/keys/{key['id']}", json={"is_active": False}, headers=ADMIN)
        client.patch(f"/v1/admin/keys/{key['id']}", json={"is_active": True}, headers=ADMIN)

        r = client.get("/v1/collections", headers={"x-api-key": key["key"]})
        assert r.json()["status"] == "success"

    def test_patch_invalid_role(self, client):
        key = create_key(client, name="patch-bad-role")
        r = client.patch(f"/v1/admin/keys/{key['id']}", json={"role": "god"}, headers=ADMIN)
        assert r.json()["error"]["code"] == 400

    def test_patch_not_found(self, client):
        r = client.patch("/v1/admin/keys/999999", json={"name": "x"}, headers=ADMIN)
        assert r.json()["error"]["code"] == 404


# ------------------------------------------------------------------
# Rotate
# ------------------------------------------------------------------

class TestRotateApiKey:
    def test_rotate_changes_key_value(self, client):
        key = create_key(client, name="to-rotate", role="readwrite")
        old_key_value = key["key"]

        r = client.post(f"/v1/admin/keys/{key['id']}/rotate", headers=ADMIN)
        data = r.json()
        assert data["status"] == "success"
        assert data["data"]["key"] != old_key_value
        assert data["data"]["rotated"] is True
        assert data["data"]["id"] == key["id"]      # same id
        assert data["data"]["name"] == key["name"]  # same name
        assert data["data"]["role"] == key["role"]  # same role

    def test_old_key_invalid_after_rotate(self, client):
        key = create_key(client, name="rotate-invalidate", role="readwrite")
        old_key_value = key["key"]

        client.post(f"/v1/admin/keys/{key['id']}/rotate", headers=ADMIN)

        r = client.get("/v1/collections", headers={"x-api-key": old_key_value})
        assert r.status_code == 401

    def test_new_key_works_after_rotate(self, client):
        key = create_key(client, name="rotate-new-works", role="readwrite")
        r = client.post(f"/v1/admin/keys/{key['id']}/rotate", headers=ADMIN)
        new_key_value = r.json()["data"]["key"]

        r = client.get("/v1/collections", headers={"x-api-key": new_key_value})
        assert r.json()["status"] == "success"

    def test_rotate_not_found(self, client):
        r = client.post("/v1/admin/keys/999999/rotate", headers=ADMIN)
        assert r.json()["error"]["code"] == 404

    def test_rotate_requires_admin(self, client):
        key = create_key(client, name="rotate-no-perm", role="readwrite")
        rw = create_key(client, name="rw-rotate-caller", role="readwrite")
        r = client.post(
            f"/v1/admin/keys/{key['id']}/rotate",
            headers={"x-api-key": rw["key"]},
        )
        assert r.status_code == 403


# ------------------------------------------------------------------
# Delete
# ------------------------------------------------------------------

class TestDeleteApiKey:
    def test_delete(self, client):
        key = create_key(client, name="to-delete")
        r = client.delete(f"/v1/admin/keys/{key['id']}", headers=ADMIN)
        assert r.json()["data"]["deleted"] is True
        assert r.json()["data"]["id"] == key["id"]

    def test_deleted_key_not_found(self, client):
        key = create_key(client, name="delete-twice")
        client.delete(f"/v1/admin/keys/{key['id']}", headers=ADMIN)
        r = client.delete(f"/v1/admin/keys/{key['id']}", headers=ADMIN)
        assert r.json()["error"]["code"] == 404

    def test_deleted_key_unauthorized(self, client):
        key = create_key(client, name="delete-then-use", role="readwrite")
        key_value = key["key"]
        client.delete(f"/v1/admin/keys/{key['id']}", headers=ADMIN)

        r = client.get("/v1/collections", headers={"x-api-key": key_value})
        assert r.status_code == 401

    def test_delete_requires_admin(self, client):
        key = create_key(client, name="delete-no-perm")
        rw = create_key(client, name="rw-delete-caller", role="readwrite")
        r = client.delete(
            f"/v1/admin/keys/{key['id']}",
            headers={"x-api-key": rw["key"]},
        )
        assert r.status_code == 403


# ------------------------------------------------------------------
# last_used_at tracking
# ------------------------------------------------------------------

class TestLastUsedAt:
    def test_last_used_at_updates_on_request(self, client):
        key = create_key(client, name="track-last-used", role="readwrite")
        assert key["last_used_at"] is None

        # Make a request with the key
        client.get("/v1/collections", headers={"x-api-key": key["key"]})

        # Check last_used_at is now set
        r = client.get(f"/v1/admin/keys/{key['id']}", headers=ADMIN)
        assert r.json()["data"]["last_used_at"] is not None
