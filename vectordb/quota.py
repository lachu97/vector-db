# vectordb/quota.py
"""
Per-user usage tracking, tier limits, quota enforcement, and rate limiting.
"""
import os
import time
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

from fastapi import HTTPException
from sqlalchemy import func
import structlog

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Tier configuration
# ---------------------------------------------------------------------------

TIER_LIMITS = {
    "free":    {"max_vectors": 10_000,     "max_requests_per_month": 10_000,     "rpm": 30},
    "starter": {"max_vectors": 100_000,    "max_requests_per_month": 100_000,    "rpm": 60},
    "pro":     {"max_vectors": 1_000_000,  "max_requests_per_month": 1_000_000,  "rpm": 120},
    "scale":   {"max_vectors": 10_000_000, "max_requests_per_month": 10_000_000, "rpm": 300},
}
VALID_TIERS = set(TIER_LIMITS.keys())

# ---------------------------------------------------------------------------
# Bypass whitelist — env-based, comma-separated emails, cached 60s
# ---------------------------------------------------------------------------

_bypass_cache: set = set()
_bypass_loaded_at: float = 0
_BYPASS_REFRESH_INTERVAL = 60  # seconds


def _get_bypass_emails() -> set:
    """Load bypass emails from env. Cached, refreshed every 60 seconds."""
    global _bypass_cache, _bypass_loaded_at
    now = time.time()
    if now - _bypass_loaded_at < _BYPASS_REFRESH_INTERVAL:
        return _bypass_cache
    raw = os.environ.get("BYPASS_EMAILS", "")
    _bypass_cache = {e.strip().lower() for e in raw.split(",") if e.strip()} if raw.strip() else set()
    _bypass_loaded_at = now
    return _bypass_cache


def is_bypass_user(user) -> bool:
    """Check if user bypasses quota/rate limits.
    Bypassed if email is in BYPASS_EMAILS env var or tier is 'admin'."""
    if user is None:
        return False
    if getattr(user, "tier", None) == "admin":
        return True
    email = getattr(user, "email", "")
    if not email:
        return False
    return email.lower() in _get_bypass_emails()


# ---------------------------------------------------------------------------
# Bulk operation safeguard
# ---------------------------------------------------------------------------

MAX_BULK_SIZE = int(os.environ.get("MAX_BULK_SIZE", "10000"))

# ---------------------------------------------------------------------------
# Billable endpoints — only these count toward monthly request quota
# ---------------------------------------------------------------------------

BILLABLE_ENDPOINTS = {
    # Search/query
    "/v1/collections/{name}/search",
    "/v1/query",
    "/v1/collections/{name}/recommend",
    "/v1/collections/{name}/hybrid_search",
    "/v1/collections/{name}/rerank",
    "/v1/collections/{name}/similarity",
    # Write
    "/v1/collections/{name}/upsert",
    "/v1/collections/{name}/bulk_upsert",
    "/v1/documents/upload",
    # Legacy
    "/v1/search",
    "/v1/upsert",
    "/v1/bulk_upsert",
    "/v1/recommend",
    "/v1/hybrid_search",
    "/v1/rerank",
    "/v1/similarity",
}

WRITE_ENDPOINTS = {
    "/v1/collections/{name}/upsert",
    "/v1/collections/{name}/bulk_upsert",
    "/v1/documents/upload",
    "/v1/upsert",
    "/v1/bulk_upsert",
}


def _normalize_endpoint(endpoint: str) -> str:
    """Strip query params and trailing slash before matching."""
    path = urlparse(endpoint).path
    return path.rstrip("/")


def _match_pattern(endpoint: str, patterns: set) -> bool:
    """Match normalized endpoint against pattern set."""
    endpoint = _normalize_endpoint(endpoint)
    for pattern in patterns:
        parts = pattern.split("{name}")
        if len(parts) == 2:
            prefix, suffix = parts
            if endpoint.startswith(prefix) and endpoint.endswith(suffix):
                middle = endpoint[len(prefix):len(endpoint) - len(suffix)] if suffix else endpoint[len(prefix):]
                if middle and "/" not in middle:
                    return True
        elif endpoint == pattern:
            return True
    return False


def is_billable(endpoint: str) -> bool:
    return _match_pattern(endpoint, BILLABLE_ENDPOINTS)


def is_write_endpoint(endpoint: str) -> bool:
    return _match_pattern(endpoint, WRITE_ENDPOINTS)


# ---------------------------------------------------------------------------
# Usage warnings
# ---------------------------------------------------------------------------

WARNING_THRESHOLD = 0.80
CRITICAL_THRESHOLD = 0.90


def check_usage_warnings(used: int, limit: int, resource: str, user_id: int) -> Optional[dict]:
    if limit <= 0:
        return None
    ratio = used / limit
    if ratio >= CRITICAL_THRESHOLD:
        logger.warning("quota_critical", user_id=user_id, resource=resource,
                       used=used, limit=limit, pct=round(ratio * 100, 1))
        return {"level": "critical", "message": f"{resource} at {round(ratio * 100)}% of limit",
                "used": used, "limit": limit}
    elif ratio >= WARNING_THRESHOLD:
        logger.info("quota_warning", user_id=user_id, resource=resource,
                    used=used, limit=limit, pct=round(ratio * 100, 1))
        return {"level": "warning", "message": f"{resource} at {round(ratio * 100)}% of limit",
                "used": used, "limit": limit}
    return None


# ---------------------------------------------------------------------------
# Vector count helpers
# ---------------------------------------------------------------------------

_SYNC_INTERVAL = 300  # seconds — recount from DB at most once per 5 min per user
_last_synced: dict = {}  # user_id -> timestamp


def recount_user_vectors(db, user_id: int) -> int:
    """Compute actual vector count from DB."""
    from vectordb.models.db import Collection, Vector
    total = (
        db.query(func.count(Vector.internal_id))
        .join(Collection, Vector.collection_id == Collection.id)
        .filter(Collection.user_id == user_id)
        .scalar()
    ) or 0
    return total


def adjust_vector_count(db, user_id: Optional[int], delta: int):
    """Adjust current month's vector_count by delta. Best-effort, never raises."""
    if user_id is None or delta == 0:
        return
    try:
        from vectordb.models.db import UserUsageSummary
        period = datetime.now(timezone.utc).strftime("%Y-%m")
        summary = db.query(UserUsageSummary).filter_by(
            user_id=user_id, period=period).first()
        if summary:
            new_count = summary.vector_count + delta
            if new_count < 0:
                # Drift detected — recount from DB
                new_count = recount_user_vectors(db, user_id)
            summary.vector_count = new_count
        else:
            # First mutation this month — recount from DB for accuracy
            actual = recount_user_vectors(db, user_id)
            actual = max(0, actual + delta)
            summary = UserUsageSummary(
                user_id=user_id, period=period,
                request_count=0, vector_count=actual)
            db.add(summary)
        db.commit()
    except Exception as e:
        logger.warning("adjust_vector_count_failed", user_id=user_id, delta=delta, error=str(e))
        try:
            db.rollback()
        except Exception:
            pass


def sync_vector_count_if_stale(db, user_id: int):
    """Recount from DB only if last sync was > _SYNC_INTERVAL ago."""
    now = time.time()
    last = _last_synced.get(user_id, 0)
    if now - last < _SYNC_INTERVAL:
        return
    try:
        from vectordb.models.db import UserUsageSummary
        period = datetime.now(timezone.utc).strftime("%Y-%m")
        actual = recount_user_vectors(db, user_id)
        summary = db.query(UserUsageSummary).filter_by(
            user_id=user_id, period=period).first()
        if summary:
            summary.vector_count = actual
        else:
            summary = UserUsageSummary(
                user_id=user_id, period=period,
                request_count=0, vector_count=actual)
            db.add(summary)
        db.commit()
        _last_synced[user_id] = now
    except Exception as e:
        logger.warning("sync_vector_count_failed", user_id=user_id, error=str(e))
        try:
            db.rollback()
        except Exception:
            pass


def get_user_usage(db, user_id: int) -> dict:
    """Get current usage for a user, with warnings. Syncs vector count if stale."""
    from vectordb.models.db import User, UserUsageSummary

    sync_vector_count_if_stale(db, user_id)

    user = db.query(User).filter_by(id=user_id).first()
    if not user:
        return {}
    limits = TIER_LIMITS.get(user.tier, TIER_LIMITS["free"])
    period = datetime.now(timezone.utc).strftime("%Y-%m")
    summary = db.query(UserUsageSummary).filter_by(
        user_id=user_id, period=period).first()

    req_used = summary.request_count if summary else 0
    vec_used = summary.vector_count if summary else 0
    req_limit = limits["max_requests_per_month"]
    vec_limit = limits["max_vectors"]

    warnings = []
    w = check_usage_warnings(req_used, req_limit, "requests", user_id)
    if w:
        warnings.append(w)
    w = check_usage_warnings(vec_used, vec_limit, "vectors", user_id)
    if w:
        warnings.append(w)

    return {
        "tier": user.tier,
        "period": period,
        "requests": {"used": req_used, "limit": req_limit, "remaining": max(0, req_limit - req_used)},
        "vectors": {"used": vec_used, "limit": vec_limit, "remaining": max(0, vec_limit - vec_used)},
        "warnings": warnings if warnings else None,
    }


# ---------------------------------------------------------------------------
# Per-user RPM (in-memory sliding window)
# ---------------------------------------------------------------------------

_rpm_windows: dict = {}  # user_id -> list of timestamps


def check_rpm(user_id: int, tier: str):
    """In-memory sliding window RPM per user. Raises HTTPException(429)."""
    limits = TIER_LIMITS.get(tier, TIER_LIMITS["free"])
    rpm_limit = limits["rpm"]
    now = time.time()
    cutoff = now - 60

    # Prune old entries, cap window size
    window = [t for t in _rpm_windows.get(user_id, []) if t > cutoff][-rpm_limit:]

    # Manage memory: remove empty, update non-empty
    if window:
        _rpm_windows[user_id] = window
    else:
        _rpm_windows.pop(user_id, None)
        window = []

    # Check BEFORE appending
    if len(window) >= rpm_limit:
        retry_after = max(1, int(window[0] + 60 - now))
        raise HTTPException(429, detail={
            "error": "Rate limit exceeded",
            "limit_rpm": rpm_limit,
            "retry_after_seconds": retry_after,
        })

    # Append only after passing the check
    _rpm_windows.setdefault(user_id, []).append(now)
