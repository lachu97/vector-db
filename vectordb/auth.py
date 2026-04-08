# vectordb/auth.py
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, HTTPException, Request
from fastapi.security.api_key import APIKeyHeader
from sqlalchemy.orm import Session

from vectordb.config import get_settings
from vectordb.models.db import ApiKey, KeyUsageLog, get_db

api_key_header = APIKeyHeader(name="x-api-key", auto_error=False)

# Role hierarchy: higher value = more permissions
ROLE_LEVELS = {"readonly": 0, "readwrite": 1, "admin": 2}


@dataclass
class ApiKeyInfo:
    key: str
    name: str
    role: str  # "admin", "readwrite", "readonly"


def _lookup_key(api_key: Optional[str], db: Session) -> ApiKeyInfo:
    """
    Look up an API key. Checks the api_keys table first, then falls back
    to the bootstrap admin key from settings.
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

        # Update last_used_at (best-effort, don't fail the request if this errors)
        try:
            key_row.last_used_at = datetime.now(timezone.utc).replace(tzinfo=None)
            db.commit()
        except Exception:
            db.rollback()

        return ApiKeyInfo(key=key_row.key, name=key_row.name, role=key_row.role)

    # Fallback: bootstrap admin key from environment
    settings = get_settings()
    if api_key == settings.api_key:
        return ApiKeyInfo(key=api_key, name="bootstrap-admin", role="admin")

    raise HTTPException(status_code=401, detail="Invalid or missing API key")


def _log_usage(db: Session, info: ApiKeyInfo, request: Request, status_code: int = 200):
    """Best-effort usage log — never raises."""
    try:
        from fastapi import Request  # local import to avoid circular
        key_id = None
        # Try to find key_id for managed keys (not bootstrap)
        if info.name != "bootstrap-admin":
            row = db.query(ApiKey).filter_by(key=info.key, is_active=True).first()
            if row:
                key_id = row.id
        log = KeyUsageLog(
            key_id=key_id,
            key_name=info.name,
            endpoint=request.url.path,
            method=request.method,
            status_code=status_code,
        )
        db.add(log)
        db.commit()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass


def _require_role(minimum_role: str):
    """Return a FastAPI dependency that enforces a minimum role level."""
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
        _log_usage(db, info, request)
        return info
    return dependency


# Ready-to-use FastAPI dependency callables
require_readonly = _require_role("readonly")
require_readwrite = _require_role("readwrite")
require_admin = _require_role("admin")

# Legacy alias for backward compatibility with any code still using verify_api_key
verify_api_key = require_readonly
