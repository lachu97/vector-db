# tests/test_usage_tracking.py
"""
Tests for per-user usage tracking, quota enforcement, RPM rate limiting,
and the /v1/usage endpoints.
"""
import os
import time
from datetime import datetime, timezone

import numpy as np
import pytest
from fastapi import HTTPException

from vectordb import quota
from vectordb.models.db import SessionLocal, User, UserUsageSummary


def rv(dim=384):
    return np.random.rand(dim).tolist()


def _register(client, email, password="password1234"):
    r = client.post("/v1/auth/register", json={"email": email, "password": password})
    return r.json()["data"]


def _ukey(user_data):
    return {"x-api-key": user_data["api_key"]["key"]}


# ------------------------------------------------------------------
# Unit tests — quota.py helpers
# ------------------------------------------------------------------

class TestBillableEndpointMatching:
    def test_billable_collection_upsert(self):
        assert quota.is_billable("/v1/collections/mycoll/upsert")

    def test_billable_collection_search(self):
        assert quota.is_billable("/v1/collections/x/search")

    def test_billable_legacy_upsert(self):
        assert quota.is_billable("/v1/upsert")

    def test_not_billable_health(self):
        assert not quota.is_billable("/v1/health")

    def test_not_billable_collections_list(self):
        assert not quota.is_billable("/v1/collections")

    def test_not_billable_admin_keys(self):
        assert not quota.is_billable("/v1/admin/keys")

    def test_pattern_rejects_subpath_in_name(self):
        # {name} cannot contain a slash
        assert not quota.is_billable("/v1/collections/a/b/search")

    def test_normalize_strips_query_params(self):
        assert quota._normalize_endpoint("/v1/health?foo=bar") == "/v1/health"

    def test_normalize_strips_trailing_slash(self):
        assert quota._normalize_endpoint("/v1/health/") == "/v1/health"

    def test_is_write_endpoint(self):
        assert quota.is_write_endpoint("/v1/collections/x/upsert")
        assert quota.is_write_endpoint("/v1/upsert")
        assert not quota.is_write_endpoint("/v1/collections/x/search")


class TestUsageWarnings:
    def test_no_warning_below_80(self):
        assert quota.check_usage_warnings(500, 1000, "requests", 1) is None

    def test_warning_at_80(self):
        w = quota.check_usage_warnings(800, 1000, "requests", 1)
        assert w is not None
        assert w["level"] == "warning"

    def test_critical_at_90(self):
        w = quota.check_usage_warnings(900, 1000, "requests", 1)
        assert w is not None
        assert w["level"] == "critical"

    def test_zero_limit_returns_none(self):
        assert quota.check_usage_warnings(100, 0, "x", 1) is None


class TestBypassUser:
    def setup_method(self):
        # Reset cache
        quota._bypass_cache = set()
        quota._bypass_loaded_at = 0
        os.environ.pop("BYPASS_EMAILS", None)

    def test_tier_admin_is_bypass(self):
        class U:
            tier = "admin"
            email = "x@x.com"
        assert quota.is_bypass_user(U())

    def test_bypass_email_env(self):
        os.environ["BYPASS_EMAILS"] = "friend@example.com, boss@example.com"
        quota._bypass_loaded_at = 0  # force reload

        class U:
            tier = "free"
            email = "friend@example.com"
        assert quota.is_bypass_user(U())

    def test_none_user(self):
        assert not quota.is_bypass_user(None)

    def test_not_in_bypass(self):
        class U:
            tier = "free"
            email = "random@example.com"
        assert not quota.is_bypass_user(U())


class TestRPMCheck:
    def setup_method(self):
        quota._rpm_windows.clear()

    def test_under_limit_passes(self):
        for _ in range(5):
            quota.check_rpm(user_id=9999, tier="free")  # 30 rpm

    def test_over_limit_raises_429(self):
        for _ in range(30):
            quota.check_rpm(user_id=9998, tier="free")
        with pytest.raises(HTTPException) as exc:
            quota.check_rpm(user_id=9998, tier="free")
        assert exc.value.status_code == 429
        assert exc.value.detail["limit_rpm"] == 30
        assert exc.value.detail["retry_after_seconds"] >= 1

    def test_window_pruned_after_60s(self, monkeypatch):
        # Inject old timestamps
        fake_now = time.time()
        quota._rpm_windows[9997] = [fake_now - 120] * 30  # all too old
        # Should not raise
        quota.check_rpm(user_id=9997, tier="free")
        # Old entries pruned
        assert all(t > fake_now - 60 for t in quota._rpm_windows[9997])

    def test_check_happens_before_append(self):
        # Fill to limit
        for _ in range(30):
            quota.check_rpm(user_id=9996, tier="free")
        assert len(quota._rpm_windows[9996]) == 30
        # Next call raises — must not append
        with pytest.raises(HTTPException):
            quota.check_rpm(user_id=9996, tier="free")
        assert len(quota._rpm_windows[9996]) == 30  # still 30, not 31


class TestAdjustVectorCount:
    def test_negative_drift_triggers_recount(self, client):
        db = SessionLocal()
        try:
            user = User(email=f"adjust-test-{time.time()}@x.com", password_hash="x", tier="free")
            db.add(user)
            db.commit()
            db.refresh(user)

            period = datetime.now(timezone.utc).strftime("%Y-%m")
            summary = UserUsageSummary(
                user_id=user.id, period=period,
                request_count=0, vector_count=5,
            )
            db.add(summary)
            db.commit()

            # Decrement by more than current count — should recount to 0 (no vectors exist)
            quota.adjust_vector_count(db, user.id, -100)

            row = db.query(UserUsageSummary).filter_by(user_id=user.id).first()
            assert row.vector_count == 0  # recounted from DB
        finally:
            db.close()

    def test_noop_for_none_user(self, client):
        db = SessionLocal()
        try:
            quota.adjust_vector_count(db, None, +5)  # must not raise
        finally:
            db.close()


# ------------------------------------------------------------------
# Integration tests — usage tracking over real endpoints
# ------------------------------------------------------------------

@pytest.fixture
def user(client):
    """Register a fresh user and return their auth headers + id."""
    import uuid
    email = f"usage-{uuid.uuid4().hex[:8]}@example.com"
    data = _register(client, email)
    return {
        "headers": _ukey(data),
        "user_id": data["user"]["id"],
        "email": email,
    }


class TestRegistrationResponse:
    def test_tier_in_response(self, user):
        # Registration response should include tier
        db = SessionLocal()
        try:
            u = db.query(User).filter_by(id=user["user_id"]).first()
            assert u.tier == "free"
        finally:
            db.close()


class TestUsageEndpoint:
    def test_get_usage_empty(self, client, user):
        r = client.get("/v1/usage", headers=user["headers"])
        data = r.json()
        assert data["status"] == "success"
        usage = data["data"]
        assert usage["tier"] == "free"
        assert usage["requests"]["limit"] == 10_000
        assert usage["vectors"]["limit"] == 10_000

    def test_bootstrap_admin_usage(self, client, headers):
        r = client.get("/v1/usage", headers=headers)
        data = r.json()["data"]
        assert data.get("bootstrap") is True

    def test_usage_history_empty(self, client, user):
        r = client.get("/v1/usage/history", headers=user["headers"])
        data = r.json()
        assert data["status"] == "success"
        assert "history" in data["data"]


class TestUsageCounters:
    def test_upsert_increments_vector_count(self, client, user):
        # Create collection
        client.post("/v1/collections", json={"name": "uc1", "dim": 384}, headers=user["headers"])
        # Upsert 3 vectors
        for i in range(3):
            client.post(
                "/v1/collections/uc1/upsert",
                json={"external_id": f"v{i}", "vector": rv()},
                headers=user["headers"],
            )
        # Check usage
        db = SessionLocal()
        try:
            period = datetime.now(timezone.utc).strftime("%Y-%m")
            s = db.query(UserUsageSummary).filter_by(
                user_id=user["user_id"], period=period).first()
            assert s is not None
            assert s.vector_count == 3
            assert s.request_count >= 3  # each upsert is billable
        finally:
            db.close()

    def test_update_does_not_increment(self, client, user):
        client.post("/v1/collections", json={"name": "uc2", "dim": 384}, headers=user["headers"])
        # Insert
        client.post(
            "/v1/collections/uc2/upsert",
            json={"external_id": "same", "vector": rv()},
            headers=user["headers"],
        )
        # Update (same external_id)
        client.post(
            "/v1/collections/uc2/upsert",
            json={"external_id": "same", "vector": rv()},
            headers=user["headers"],
        )
        db = SessionLocal()
        try:
            period = datetime.now(timezone.utc).strftime("%Y-%m")
            s = db.query(UserUsageSummary).filter_by(
                user_id=user["user_id"], period=period).first()
            assert s.vector_count == 1  # second was update, not insert
        finally:
            db.close()

    def test_delete_decrements(self, client, user):
        client.post("/v1/collections", json={"name": "uc3", "dim": 384}, headers=user["headers"])
        client.post(
            "/v1/collections/uc3/upsert",
            json={"external_id": "del-me", "vector": rv()},
            headers=user["headers"],
        )
        db = SessionLocal()
        try:
            period = datetime.now(timezone.utc).strftime("%Y-%m")
            before = db.query(UserUsageSummary).filter_by(
                user_id=user["user_id"], period=period).first().vector_count
        finally:
            db.close()

        client.delete("/v1/collections/uc3/delete/del-me", headers=user["headers"])

        db = SessionLocal()
        try:
            s = db.query(UserUsageSummary).filter_by(
                user_id=user["user_id"], period=period).first()
            assert s.vector_count == before - 1
        finally:
            db.close()

    def test_non_billable_does_not_increment_request_count(self, client, user):
        # Prime the summary row by making one billable call
        client.post("/v1/collections", json={"name": "uc4", "dim": 384}, headers=user["headers"])
        client.post(
            "/v1/collections/uc4/upsert",
            json={"external_id": "a", "vector": rv()},
            headers=user["headers"],
        )

        db = SessionLocal()
        try:
            period = datetime.now(timezone.utc).strftime("%Y-%m")
            before = db.query(UserUsageSummary).filter_by(
                user_id=user["user_id"], period=period).first().request_count
        finally:
            db.close()

        # Hit non-billable endpoints
        client.get("/v1/collections", headers=user["headers"])
        client.get("/v1/collections/uc4", headers=user["headers"])

        db = SessionLocal()
        try:
            after = db.query(UserUsageSummary).filter_by(
                user_id=user["user_id"], period=period).first().request_count
            # request_count should NOT increase for non-billable
            assert after == before
        finally:
            db.close()


class TestQuotaEnforcement:
    def test_bulk_upsert_precheck_rejects_over_limit(self, client, user):
        client.post("/v1/collections", json={"name": "qc1", "dim": 384}, headers=user["headers"])

        # Simulate user already at 9,999 vectors (free tier = 10,000)
        db = SessionLocal()
        try:
            period = datetime.now(timezone.utc).strftime("%Y-%m")
            s = UserUsageSummary(
                user_id=user["user_id"], period=period,
                request_count=0, vector_count=9_999,
            )
            db.add(s)
            db.commit()
        finally:
            db.close()

        # Try to upsert 10 at once — should be rejected by pre-check
        items = [{"external_id": f"b{i}", "vector": rv()} for i in range(10)]
        r = client.post(
            "/v1/collections/qc1/bulk_upsert",
            json={"items": items},
            headers=user["headers"],
        )
        data = r.json()
        assert data["status"] == "error"
        assert data["error"]["code"] == 429

    def test_vector_limit_blocks_single_upsert(self, client, user):
        client.post("/v1/collections", json={"name": "qc2", "dim": 384}, headers=user["headers"])

        db = SessionLocal()
        try:
            period = datetime.now(timezone.utc).strftime("%Y-%m")
            s = UserUsageSummary(
                user_id=user["user_id"], period=period,
                request_count=0, vector_count=10_000,  # at limit
            )
            db.add(s)
            db.commit()
        finally:
            db.close()

        # _check_quota in auth.py should reject this write
        r = client.post(
            "/v1/collections/qc2/upsert",
            json={"external_id": "over", "vector": rv()},
            headers=user["headers"],
        )
        # Should be 429 (raised as HTTPException)
        assert r.status_code == 429

    def test_search_still_works_at_vector_limit(self, client, user):
        client.post("/v1/collections", json={"name": "qc3", "dim": 384}, headers=user["headers"])
        # Put in a real vector first (while under limit)
        client.post(
            "/v1/collections/qc3/upsert",
            json={"external_id": "a", "vector": rv()},
            headers=user["headers"],
        )

        # Now pin vector_count to limit
        db = SessionLocal()
        try:
            period = datetime.now(timezone.utc).strftime("%Y-%m")
            s = db.query(UserUsageSummary).filter_by(
                user_id=user["user_id"], period=period).first()
            s.vector_count = 10_000
            db.commit()
        finally:
            db.close()

        # Search should NOT be blocked by vector limit
        r = client.post(
            "/v1/collections/qc3/search",
            json={"vector": rv(), "top_k": 1},
            headers=user["headers"],
        )
        assert r.status_code == 200

    def test_request_limit_blocks_billable_call(self, client, user):
        client.post("/v1/collections", json={"name": "qc4", "dim": 384}, headers=user["headers"])

        db = SessionLocal()
        try:
            period = datetime.now(timezone.utc).strftime("%Y-%m")
            s = UserUsageSummary(
                user_id=user["user_id"], period=period,
                request_count=10_000, vector_count=0,  # at request limit
            )
            db.add(s)
            db.commit()
        finally:
            db.close()

        r = client.post(
            "/v1/collections/qc4/upsert",
            json={"external_id": "x", "vector": rv()},
            headers=user["headers"],
        )
        assert r.status_code == 429


class TestBootstrapBypass:
    def test_bootstrap_admin_bypasses_vector_limit(self, client, headers):
        # Bootstrap admin has user_id=None → no quota checks
        client.post("/v1/collections", json={"name": "boot-qc", "dim": 384}, headers=headers)
        r = client.post(
            "/v1/collections/boot-qc/upsert",
            json={"external_id": "a", "vector": rv()},
            headers=headers,
        )
        assert r.status_code == 200


class TestInactiveUserCleanup:
    def test_cleanup_deletes_inactive_user(self, client):
        # Register a user
        data = _register(client, f"inactive-{time.time()}@example.com")
        uid = data["user"]["id"]
        headers = _ukey(data)

        # Create a collection for this user
        client.post("/v1/collections", json={"name": f"cleanup-col-{uid}", "dim": 3}, headers=headers)

        # Set last_active_at to 4 months ago
        db = SessionLocal()
        try:
            from datetime import timedelta
            user = db.query(User).filter_by(id=uid).first()
            user.last_active_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=120)
            db.commit()
        finally:
            db.close()

        # Run cleanup
        from vectordb.cleanup import cleanup_inactive_users
        db = SessionLocal()
        try:
            result = cleanup_inactive_users(db)
            assert result["deleted_count"] >= 1
            deleted_ids = [d["user_id"] for d in result["deleted"]]
            assert uid in deleted_ids

            # User should be gone
            assert db.query(User).filter_by(id=uid).first() is None
        finally:
            db.close()

    def test_cleanup_skips_bypass_user(self, client):
        import os
        email = f"bypass-cleanup-{time.time()}@example.com"
        os.environ["BYPASS_EMAILS"] = email
        quota._bypass_loaded_at = 0  # force reload

        data = _register(client, email)
        uid = data["user"]["id"]

        # Set last_active_at to 4 months ago
        db = SessionLocal()
        try:
            from datetime import timedelta
            user = db.query(User).filter_by(id=uid).first()
            user.last_active_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=120)
            db.commit()
        finally:
            db.close()

        # Run cleanup — bypass user should be skipped
        from vectordb.cleanup import cleanup_inactive_users
        db = SessionLocal()
        try:
            result = cleanup_inactive_users(db)
            assert email in result["skipped_bypass"]
            assert db.query(User).filter_by(id=uid).first() is not None
        finally:
            db.close()

        # Reset
        os.environ.pop("BYPASS_EMAILS", None)
        quota._bypass_loaded_at = 0

    def test_cleanup_skips_recently_active(self, client):
        data = _register(client, f"active-{time.time()}@example.com")
        uid = data["user"]["id"]

        # Set last_active_at to yesterday
        db = SessionLocal()
        try:
            from datetime import timedelta
            user = db.query(User).filter_by(id=uid).first()
            user.last_active_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1)
            db.commit()
        finally:
            db.close()

        from vectordb.cleanup import cleanup_inactive_users
        db = SessionLocal()
        try:
            result = cleanup_inactive_users(db)
            deleted_ids = [d["user_id"] for d in result["deleted"]]
            assert uid not in deleted_ids
        finally:
            db.close()

    def test_cleanup_skips_null_last_active(self, client):
        data = _register(client, f"new-{time.time()}@example.com")
        uid = data["user"]["id"]

        # Ensure last_active_at is None (freshly registered, no API calls yet)
        db = SessionLocal()
        try:
            user = db.query(User).filter_by(id=uid).first()
            user.last_active_at = None
            db.commit()
        finally:
            db.close()

        from vectordb.cleanup import cleanup_inactive_users
        db = SessionLocal()
        try:
            result = cleanup_inactive_users(db)
            deleted_ids = [d["user_id"] for d in result["deleted"]]
            assert uid not in deleted_ids
        finally:
            db.close()

    def test_cleanup_admin_endpoint(self, client, headers):
        r = client.post("/v1/admin/cleanup", headers=headers)
        data = r.json()
        assert data["status"] == "success"
        assert "deleted_count" in data["data"]

    def test_cleanup_endpoint_requires_bootstrap(self, client, user):
        r = client.post("/v1/admin/cleanup", headers=user["headers"])
        assert r.json()["error"]["code"] == 403


class TestTierUpdate:
    def test_regular_admin_cannot_update_tier(self, client, user):
        # User's api key has admin role but is scoped (user_id not None)
        r = client.patch(
            f"/v1/admin/users/{user['user_id']}/tier",
            json={"tier": "pro"},
            headers=user["headers"],
        )
        assert r.json()["error"]["code"] == 403

    def test_bootstrap_can_update_tier(self, client, headers, user):
        r = client.patch(
            f"/v1/admin/users/{user['user_id']}/tier",
            json={"tier": "pro"},
            headers=headers,
        )
        assert r.json()["status"] == "success"
        assert r.json()["data"]["tier"] == "pro"

    def test_invalid_tier_rejected(self, client, headers, user):
        r = client.patch(
            f"/v1/admin/users/{user['user_id']}/tier",
            json={"tier": "enterprise"},  # not a valid tier
            headers=headers,
        )
        assert r.json()["error"]["code"] == 400
