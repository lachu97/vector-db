# vectordb/auth.py
import calendar
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, HTTPException, Request
from fastapi.security.api_key import APIKeyHeader
from sqlalchemy.orm import Session

from vectordb.config import get_settings
from vectordb.models.db import ApiKey, KeyUsageLog, User, UserUsageSummary, get_db

api_key_header = APIKeyHeader(name="x-api-key", auto_error=False)

# Role hierarchy: higher value = more permissions
ROLE_LEVELS = {"readonly": 0, "readwrite": 1, "admin": 2}


@dataclass
class ApiKeyInfo:
    key: str
    name: str
    role: str  # "admin", "readwrite", "readonly"
    user_id: Optional[int] = None  # None = bootstrap superadmin (sees everything)
    key_id: Optional[int] = None   # DB row id for usage logging


def _lookup_key(api_key: Optional[str], db: Session) -> ApiKeyInfo:
    """
    Look up an API key. Checks the api_keys table first, then falls back
    to the bootstrap admin key from settings.
    Defers last_used_at update — caller batches it in a single commit.
    """
    if not api_key:
        raise HTTPException(status_code=401, detail="API key required")

    # Check DB for managed keys
    key_row = db.query(ApiKey).filter_by(key=api_key, is_active=True).first()
    if key_row:
        # Check expiry
        if key_row.expires_at is not None:
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            if key_row.expires_at < now:
                raise HTTPException(status_code=401, detail="API key has expired")

        # Mark dirty — will be committed later in the single batch commit
        key_row.last_used_at = datetime.now(timezone.utc).replace(tzinfo=None)

        return ApiKeyInfo(
            key=key_row.key, name=key_row.name, role=key_row.role,
            user_id=key_row.user_id, key_id=key_row.id,
        )

    # Fallback: bootstrap admin key from environment
    settings = get_settings()
    if api_key == settings.api_key:
        return ApiKeyInfo(key=api_key, name="bootstrap-admin", role="admin", user_id=None)

    raise HTTPException(status_code=401, detail="Invalid or missing API key")


def _require_role(minimum_role: str):
    """
    Return a FastAPI dependency that enforces a minimum role level.

    Consolidated flow — fetches each DB entity at most once, does a single commit:
      1. _lookup_key: fetch ApiKey row, mark last_used_at dirty
      2. Role check
      3. Quota check: fetch User + UserUsageSummary (if user_id)
      4. Log usage: write KeyUsageLog + increment request_count (reuses summary)
      5. Touch last_active_at (reuses User)
      6. Single commit
    """
    def dependency(
        request: Request,
        api_key: Optional[str] = Depends(api_key_header),
        db: Session = Depends(get_db),
    ) -> ApiKeyInfo:
        info = _lookup_key(api_key, db)
        if ROLE_LEVELS.get(info.role, -1) < ROLE_LEVELS[minimum_role]:
            raise HTTPException(
                status_code=403,
                detail=f"Insufficient permissions. Required role: {minimum_role}",
            )

        # --- All remaining work shares fetched entities + single commit ---
        try:
            _auth_post_check(db, info, request)
        except HTTPException:
            raise
        except Exception:
            try:
                db.rollback()
            except Exception:
                pass

        return info
    return dependency


def _auth_post_check(db: Session, info: ApiKeyInfo, request: Request):
    """Quota check + usage log + last_active — single commit, each entity fetched once."""
    from vectordb.quota import (
        TIER_LIMITS, is_billable, is_write_endpoint,
        _normalize_endpoint, check_rpm, is_bypass_user, recount_user_vectors,
    )

    endpoint = _normalize_endpoint(request.url.path)
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    period = now_utc.strftime("%Y-%m")

    # Fetch User + summary ONCE (only if scoped user)
    user = None
    summary = None
    if info.user_id is not None:
        user = db.query(User).filter_by(id=info.user_id).first()
        if user:
            summary = db.query(UserUsageSummary).filter_by(
                user_id=info.user_id, period=period).first()

    # --- Quota enforcement ---
    if user and not is_bypass_user(user):
        check_rpm(info.user_id, user.tier)

        if is_billable(endpoint) and summary:
            limits = TIER_LIMITS.get(user.tier, TIER_LIMITS["free"])

            if summary.request_count >= limits["max_requests_per_month"]:
                now = datetime.now(timezone.utc)
                days_in_month = calendar.monthrange(now.year, now.month)[1]
                seconds_left = int((days_in_month - now.day) * 86400)
                raise HTTPException(429, detail={
                    "error": "Monthly request limit reached",
                    "limit": limits["max_requests_per_month"],
                    "used": summary.request_count,
                    "retry_after_seconds": max(1, seconds_left),
                    "upgrade_url": "/pricing",
                })

            if is_write_endpoint(endpoint) and summary.vector_count >= limits["max_vectors"]:
                raise HTTPException(429, detail={
                    "error": "Vector storage limit reached",
                    "limit": limits["max_vectors"],
                    "used": summary.vector_count,
                    "retry_after_seconds": None,
                    "upgrade_url": "/pricing",
                })

    # --- Usage log (reuses key_id from lookup — no second query) ---
    log = KeyUsageLog(
        key_id=info.key_id,
        key_name=info.name,
        endpoint=endpoint,
        method=request.method,
        status_code=200,
        user_id=info.user_id,
    )
    db.add(log)

    # Increment billable request counter (reuses summary)
    if info.user_id and is_billable(endpoint):
        if summary:
            summary.request_count += 1
        else:
            vec_count = recount_user_vectors(db, info.user_id)
            summary = UserUsageSummary(
                user_id=info.user_id, period=period,
                request_count=1, vector_count=vec_count)
            db.add(summary)

    # Touch last_active_at (reuses User — no second query)
    if user:
        user.last_active_at = now_utc

    # Single commit for everything: last_used_at + log + counter + last_active
    db.commit()


# Ready-to-use FastAPI dependency callables
require_readonly = _require_role("readonly")
require_readwrite = _require_role("readwrite")
require_admin = _require_role("admin")

# Legacy alias for backward compatibility with any code still using verify_api_key
verify_api_key = require_readonly
