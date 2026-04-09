# vectordb/routers/keys.py
import secrets
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import Optional

import structlog
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from vectordb.auth import ApiKeyInfo, require_admin
from vectordb.models.db import ApiKey, KeyUsageLog, get_db
from vectordb.services.vector_service import success_response, error_response

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/v1/admin/keys", tags=["api-keys"])

VALID_ROLES = {"admin", "readwrite", "readonly"}


def _scoped_key_query(db: Session, auth: ApiKeyInfo):
    """Return a query on ApiKey scoped to the user. Bootstrap (user_id=None) sees all."""
    q = db.query(ApiKey)
    if auth.user_id is not None:
        q = q.filter(ApiKey.user_id == auth.user_id)
    return q


def _format_key(row: ApiKey, include_key: bool = False) -> dict:
    data = {
        "id": row.id,
        "name": row.name,
        "role": row.role,
        "is_active": row.is_active,
        "created_at": str(row.created_at),
        "expires_at": str(row.expires_at) if row.expires_at else None,
        "last_used_at": str(row.last_used_at) if row.last_used_at else None,
    }
    if include_key:
        data["key"] = row.key
    return data


# ------------------------------------------------------------------
# Request schemas
# ------------------------------------------------------------------

class CreateApiKeyRequest(BaseModel):
    name: str
    role: str                        # "admin", "readwrite", "readonly"
    expires_in_days: Optional[int] = None  # None = never expires


class UpdateApiKeyRequest(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None


# ------------------------------------------------------------------
# POST /v1/admin/keys — create
# ------------------------------------------------------------------

@router.post("")
def create_api_key(
    req: CreateApiKeyRequest,
    db: Session = Depends(get_db),
    auth: ApiKeyInfo = Depends(require_admin),
):
    if req.role not in VALID_ROLES:
        return error_response(400, f"Invalid role. Must be one of: {', '.join(sorted(VALID_ROLES))}")

    if not req.name.strip():
        return error_response(400, "Name must not be empty")

    if req.expires_in_days is not None and req.expires_in_days < 1:
        return error_response(400, "expires_in_days must be at least 1")

    expires_at = None
    if req.expires_in_days:
        expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=req.expires_in_days)

    new_key = secrets.token_urlsafe(32)
    row = ApiKey(
        key=new_key,
        name=req.name.strip(),
        role=req.role,
        is_active=True,
        user_id=auth.user_id,
        expires_at=expires_at,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    logger.info("api_key_created", key_name=row.name, role=row.role, created_by=auth.name)

    return success_response(_format_key(row, include_key=True))


# ------------------------------------------------------------------
# GET /v1/admin/keys — list
# ------------------------------------------------------------------

@router.get("")
def list_api_keys(
    db: Session = Depends(get_db),
    auth: ApiKeyInfo = Depends(require_admin),
):
    rows = _scoped_key_query(db, auth).order_by(ApiKey.created_at.desc()).all()
    return success_response({"keys": [_format_key(r) for r in rows]})


# ------------------------------------------------------------------
# GET /v1/admin/keys/:id — get one
# ------------------------------------------------------------------

@router.get("/{key_id}")
def get_api_key(
    key_id: int,
    db: Session = Depends(get_db),
    auth: ApiKeyInfo = Depends(require_admin),
):
    row = _scoped_key_query(db, auth).filter_by(id=key_id).first()
    if not row:
        return error_response(404, f"API key {key_id} not found")
    return success_response(_format_key(row))


# ------------------------------------------------------------------
# PATCH /v1/admin/keys/:id — update name, role, or is_active
# ------------------------------------------------------------------

@router.patch("/{key_id}")
def update_api_key(
    key_id: int,
    req: UpdateApiKeyRequest,
    db: Session = Depends(get_db),
    auth: ApiKeyInfo = Depends(require_admin),
):
    row = _scoped_key_query(db, auth).filter_by(id=key_id).first()
    if not row:
        return error_response(404, f"API key {key_id} not found")

    if req.name is not None:
        if not req.name.strip():
            return error_response(400, "Name must not be empty")
        row.name = req.name.strip()

    if req.role is not None:
        if req.role not in VALID_ROLES:
            return error_response(400, f"Invalid role. Must be one of: {', '.join(sorted(VALID_ROLES))}")
        row.role = req.role

    if req.is_active is not None:
        row.is_active = req.is_active

    db.commit()
    db.refresh(row)

    action = "revoked" if req.is_active is False else "updated"
    logger.info(f"api_key_{action}", key_id=key_id, key_name=row.name, updated_by=auth.name)

    return success_response(_format_key(row))


# ------------------------------------------------------------------
# POST /v1/admin/keys/:id/rotate — regenerate key value
# ------------------------------------------------------------------

@router.post("/{key_id}/rotate")
def rotate_api_key(
    key_id: int,
    db: Session = Depends(get_db),
    auth: ApiKeyInfo = Depends(require_admin),
):
    row = _scoped_key_query(db, auth).filter_by(id=key_id).first()
    if not row:
        return error_response(404, f"API key {key_id} not found")

    new_key = secrets.token_urlsafe(32)
    row.key = new_key
    row.last_used_at = None
    db.commit()
    db.refresh(row)

    logger.info("api_key_rotated", key_id=key_id, key_name=row.name, rotated_by=auth.name)

    data = _format_key(row, include_key=True)
    data["rotated"] = True
    return success_response(data)


# ------------------------------------------------------------------
# GET /v1/admin/keys/:id/usage — usage stats for one key
# ------------------------------------------------------------------

def _build_usage_stats(logs: list) -> dict:
    """Build usage stats dict from a list of KeyUsageLog rows."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    last_24h = sum(1 for l in logs if l.timestamp and (now - l.timestamp).total_seconds() < 86400)
    last_7d = sum(1 for l in logs if l.timestamp and (now - l.timestamp).days < 7)
    last_30d = sum(1 for l in logs if l.timestamp and (now - l.timestamp).days < 30)

    by_endpoint = defaultdict(int)
    for l in logs:
        by_endpoint[l.endpoint] += 1

    return {
        "total_requests": len(logs),
        "last_24h": last_24h,
        "last_7d": last_7d,
        "last_30d": last_30d,
        "by_endpoint": dict(sorted(by_endpoint.items(), key=lambda x: -x[1])),
        "last_request_at": str(logs[-1].timestamp) if logs else None,
    }


@router.get("/{key_id}/usage")
def get_key_usage(
    key_id: int,
    db: Session = Depends(get_db),
    auth: ApiKeyInfo = Depends(require_admin),
):
    row = _scoped_key_query(db, auth).filter_by(id=key_id).first()
    if not row:
        return error_response(404, f"API key {key_id} not found")

    logs = db.query(KeyUsageLog).filter_by(key_id=key_id).order_by(KeyUsageLog.timestamp).all()
    return success_response({"key_id": key_id, "key_name": row.name, **_build_usage_stats(logs)})


# ------------------------------------------------------------------
# GET /v1/admin/usage — usage stats across all keys
# ------------------------------------------------------------------

@router.get("/usage/summary")
def get_usage_summary(
    db: Session = Depends(get_db),
    auth: ApiKeyInfo = Depends(require_admin),
):
    # Scope: only show usage for keys belonging to this user
    if auth.user_id is not None:
        user_key_ids = [k.id for k in db.query(ApiKey).filter_by(user_id=auth.user_id).all()]
        logs = db.query(KeyUsageLog).filter(KeyUsageLog.key_id.in_(user_key_ids)).order_by(KeyUsageLog.timestamp).all()
    else:
        logs = db.query(KeyUsageLog).order_by(KeyUsageLog.timestamp).all()
    by_key = defaultdict(list)
    for l in logs:
        by_key[l.key_name].append(l)

    keys_summary = [
        {"key_name": name, **_build_usage_stats(key_logs)}
        for name, key_logs in by_key.items()
    ]
    keys_summary.sort(key=lambda x: -x["total_requests"])

    return success_response({
        "overall": _build_usage_stats(logs),
        "by_key": keys_summary,
    })


# ------------------------------------------------------------------
# DELETE /v1/admin/keys/:id — hard delete
# ------------------------------------------------------------------

@router.delete("/{key_id}")
def delete_api_key(
    key_id: int,
    db: Session = Depends(get_db),
    auth: ApiKeyInfo = Depends(require_admin),
):
    row = _scoped_key_query(db, auth).filter_by(id=key_id).first()
    if not row:
        return error_response(404, f"API key {key_id} not found")

    db.delete(row)
    db.commit()

    logger.info("api_key_deleted", key_id=key_id, key_name=row.name, deleted_by=auth.name)

    return success_response({"deleted": True, "id": key_id, "name": row.name})
