# tests/test_multi_tenancy.py
"""
Tests for multi-tenancy: user registration, login, key scoping,
collection scoping, and user isolation.
"""
import numpy as np
import pytest


def random_vector(dim=384):
    return np.random.rand(dim).tolist()


class TestAuthRegisterLogin:
    """Test /v1/auth/register and /v1/auth/login endpoints."""

    def test_register_new_user(self, client):
        r = client.post("/v1/auth/register", json={
            "email": "tenancy-test@example.com",
            "password": "password123",
        })
        data = r.json()
        assert data["status"] == "success"
        result = data["data"]
        assert "user" in result
        assert "api_key" in result
        assert result["user"]["email"] == "tenancy-test@example.com"
        assert result["api_key"]["role"] == "admin"
        assert result["api_key"]["key"]  # key is returned

    def test_register_duplicate_email(self, client):
        r = client.post("/v1/auth/register", json={
            "email": "tenancy-test@example.com",
            "password": "password123",
        })
        data = r.json()
        assert data["status"] == "error"
        assert data["error"]["code"] == 409

    def test_register_short_password(self, client):
        r = client.post("/v1/auth/register", json={
            "email": "short-pw@example.com",
            "password": "1234567",
        })
        data = r.json()
        assert data["status"] == "error"
        assert data["error"]["code"] == 400

    def test_login_valid(self, client):
        # Register first
        client.post("/v1/auth/register", json={
            "email": "login-test@example.com",
            "password": "password123",
        })
        # Login
        r = client.post("/v1/auth/login", json={
            "email": "login-test@example.com",
            "password": "password123",
        })
        data = r.json()
        assert data["status"] == "success"
        assert data["data"]["user"]["email"] == "login-test@example.com"
        assert data["data"]["api_key"]["key"]

    def test_login_wrong_password(self, client):
        r = client.post("/v1/auth/login", json={
            "email": "login-test@example.com",
            "password": "wrongpassword",
        })
        data = r.json()
        assert data["status"] == "error"
        assert data["error"]["code"] == 401

    def test_login_nonexistent_user(self, client):
        r = client.post("/v1/auth/login", json={
            "email": "nobody@example.com",
            "password": "password123",
        })
        data = r.json()
        assert data["status"] == "error"
        assert data["error"]["code"] == 401


def _register_or_login(client, email, password="password123"):
    """Register a user; if already registered, login instead. Returns API key."""
    r = client.post("/v1/auth/register", json={"email": email, "password": password})
    data = r.json()
    if data["status"] == "success":
        return data["data"]["api_key"]["key"]
    # Already registered — login
    r = client.post("/v1/auth/login", json={"email": email, "password": password})
    return r.json()["data"]["api_key"]["key"]


class TestKeyScopingByUser:
    """Test that API keys are scoped to the user who created them."""

    @pytest.fixture(autouse=True)
    def setup_users(self, client):
        self.user_a_key = _register_or_login(client, "keyscope-a@example.com")
        self.user_b_key = _register_or_login(client, "keyscope-b@example.com")

    def test_user_can_list_own_keys(self, client):
        r = client.get("/v1/admin/keys", headers={"x-api-key": self.user_a_key})
        data = r.json()
        assert data["status"] == "success"
        keys = data["data"]["keys"]
        assert len(keys) >= 1
        # All keys should belong to user A's scope
        for k in keys:
            assert "keyscope-a" in k["name"]

    def test_user_cannot_see_other_users_keys(self, client):
        r = client.get("/v1/admin/keys", headers={"x-api-key": self.user_b_key})
        data = r.json()
        keys = data["data"]["keys"]
        for k in keys:
            assert "keyscope-a" not in k["name"]

    def test_user_can_create_key(self, client):
        r = client.post("/v1/admin/keys", json={
            "name": "keyscope-a-extra",
            "role": "readonly",
        }, headers={"x-api-key": self.user_a_key})
        data = r.json()
        assert data["status"] == "success"
        assert data["data"]["name"] == "keyscope-a-extra"
        assert data["data"]["role"] == "readonly"

    def test_bootstrap_key_sees_all_keys(self, client, headers):
        r = client.get("/v1/admin/keys", headers=headers)
        data = r.json()
        assert data["status"] == "success"
        # Bootstrap key (user_id=None) should see all keys
        names = [k["name"] for k in data["data"]["keys"]]
        assert any("keyscope-a" in n for n in names)
        assert any("keyscope-b" in n for n in names)


class TestCollectionScopingByUser:
    """Test that collections are scoped to the user who created them."""

    @pytest.fixture(autouse=True)
    def setup_users(self, client):
        self.user_a_key = _register_or_login(client, "colscope-a@example.com")
        self.user_b_key = _register_or_login(client, "colscope-b@example.com")

    def test_user_creates_collection(self, client):
        r = client.post("/v1/collections", json={
            "name": "user-a-coll",
            "dim": 4,
            "distance_metric": "cosine",
        }, headers={"x-api-key": self.user_a_key})
        data = r.json()
        assert data["status"] == "success"
        assert data["data"]["name"] == "user-a-coll"

    def test_user_can_see_own_collection(self, client):
        # Create it first
        client.post("/v1/collections", json={
            "name": "user-a-visible",
            "dim": 4,
            "distance_metric": "cosine",
        }, headers={"x-api-key": self.user_a_key})

        r = client.get("/v1/collections/user-a-visible",
                       headers={"x-api-key": self.user_a_key})
        data = r.json()
        assert data["status"] == "success"
        assert data["data"]["name"] == "user-a-visible"

    def test_other_user_cannot_see_collection(self, client):
        # Create collection as user A
        client.post("/v1/collections", json={
            "name": "user-a-private",
            "dim": 4,
            "distance_metric": "cosine",
        }, headers={"x-api-key": self.user_a_key})

        # User B tries to get it
        r = client.get("/v1/collections/user-a-private",
                       headers={"x-api-key": self.user_b_key})
        data = r.json()
        assert data["status"] == "error"
        assert data["error"]["code"] == 404

    def test_other_user_cannot_list_collection(self, client):
        # Create collection as user A
        client.post("/v1/collections", json={
            "name": "user-a-hidden",
            "dim": 4,
            "distance_metric": "cosine",
        }, headers={"x-api-key": self.user_a_key})

        # User B lists collections
        r = client.get("/v1/collections",
                       headers={"x-api-key": self.user_b_key})
        data = r.json()
        names = [c["name"] for c in data["data"]["collections"]]
        assert "user-a-hidden" not in names

    def test_bootstrap_key_sees_all_collections(self, client, headers):
        # Create a collection as user A
        client.post("/v1/collections", json={
            "name": "user-a-bootstrap-test",
            "dim": 4,
            "distance_metric": "cosine",
        }, headers={"x-api-key": self.user_a_key})

        # Bootstrap key lists all
        r = client.get("/v1/collections", headers=headers)
        data = r.json()
        names = [c["name"] for c in data["data"]["collections"]]
        assert "user-a-bootstrap-test" in names

    def test_other_user_cannot_delete_collection(self, client):
        # Create as user A
        client.post("/v1/collections", json={
            "name": "user-a-nodelete",
            "dim": 4,
            "distance_metric": "cosine",
        }, headers={"x-api-key": self.user_a_key})

        # User B tries to delete it — should fail (404)
        r = client.delete("/v1/collections/user-a-nodelete",
                          headers={"x-api-key": self.user_b_key})
        data = r.json()
        assert data["status"] == "error"
        assert data["error"]["code"] == 404

    def test_user_can_delete_own_collection(self, client):
        # Create as user A
        client.post("/v1/collections", json={
            "name": "user-a-todelete",
            "dim": 4,
            "distance_metric": "cosine",
        }, headers={"x-api-key": self.user_a_key})

        r = client.delete("/v1/collections/user-a-todelete",
                          headers={"x-api-key": self.user_a_key})
        data = r.json()
        assert data["status"] == "success"


class TestVectorIsolation:
    """Test that users cannot access other users' vectors."""

    @pytest.fixture(autouse=True)
    def setup_users_and_collections(self, client):
        self.user_a_key = _register_or_login(client, "veciso-a@example.com")
        self.user_b_key = _register_or_login(client, "veciso-b@example.com")

        # User A creates a collection (ignore if already exists) and inserts a vector
        client.post("/v1/collections", json={
            "name": "veciso-a-coll",
            "dim": 4,
            "distance_metric": "cosine",
        }, headers={"x-api-key": self.user_a_key})

        client.post("/v1/collections/veciso-a-coll/upsert", json={
            "external_id": "v1",
            "vector": [1.0, 0.0, 0.0, 0.0],
            "metadata": {"tag": "a"},
        }, headers={"x-api-key": self.user_a_key})

    def test_owner_can_search(self, client):
        r = client.post("/v1/collections/veciso-a-coll/search", json={
            "vector": [1.0, 0.0, 0.0, 0.0],
            "k": 5,
        }, headers={"x-api-key": self.user_a_key})
        data = r.json()
        assert data["status"] == "success"
        assert len(data["data"]["results"]) == 1

    def test_other_user_cannot_search(self, client):
        r = client.post("/v1/collections/veciso-a-coll/search", json={
            "vector": [1.0, 0.0, 0.0, 0.0],
            "k": 5,
        }, headers={"x-api-key": self.user_b_key})
        data = r.json()
        assert data["status"] == "error"
        assert data["error"]["code"] == 404

    def test_other_user_cannot_upsert(self, client):
        r = client.post("/v1/collections/veciso-a-coll/upsert", json={
            "external_id": "v-intruder",
            "vector": [0.0, 1.0, 0.0, 0.0],
            "metadata": {},
        }, headers={"x-api-key": self.user_b_key})
        data = r.json()
        assert data["status"] == "error"
        assert data["error"]["code"] == 404

    def test_other_user_cannot_delete_vector(self, client):
        r = client.delete("/v1/collections/veciso-a-coll/delete/v1",
                          headers={"x-api-key": self.user_b_key})
        data = r.json()
        assert data["status"] == "error"
        assert data["error"]["code"] == 404


class TestBootstrapSuperadmin:
    """Test that the bootstrap key (user_id=None) has full access."""

    def test_bootstrap_creates_global_collection(self, client, headers):
        r = client.post("/v1/collections", json={
            "name": "global-coll",
            "dim": 4,
            "distance_metric": "cosine",
        }, headers=headers)
        data = r.json()
        assert data["status"] == "success"

    def test_registered_user_sees_global_collection(self, client):
        # Register a new user
        r = client.post("/v1/auth/register", json={
            "email": "global-vis@example.com",
            "password": "password123",
        })
        key = r.json()["data"]["api_key"]["key"]

        # Should see global collections (user_id=None)
        r = client.get("/v1/collections/global-coll",
                       headers={"x-api-key": key})
        data = r.json()
        assert data["status"] == "success"
        assert data["data"]["name"] == "global-coll"

    def test_bootstrap_can_access_any_user_collection(self, client, headers):
        # Register user and create collection
        r = client.post("/v1/auth/register", json={
            "email": "bootstrap-access@example.com",
            "password": "password123",
        })
        key = r.json()["data"]["api_key"]["key"]
        client.post("/v1/collections", json={
            "name": "user-owned-coll",
            "dim": 4,
            "distance_metric": "cosine",
        }, headers={"x-api-key": key})

        # Bootstrap key can see it
        r = client.get("/v1/collections/user-owned-coll", headers=headers)
        data = r.json()
        assert data["status"] == "success"
