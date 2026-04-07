# vectordb/routers/keys.py
import secrets

import structlog
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from vectordb.auth import ApiKeyInfo, require_admin
from vectordb.models.db import ApiKey, get_db
from vectordb.services.vector_service import success_response, error_response

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/v1/admin/keys", tags=["api-keys"])

VALID_ROLES = {"admin", "readwrite", "readonly"}


class CreateApiKeyRequest(BaseModel):
    name: str
    role: str  # "admin", "readwrite", "readonly"


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

    new_key = secrets.token_urlsafe(32)
    row = ApiKey(key=new_key, name=req.name.strip(), role=req.role, is_active=True)
    db.add(row)
    db.commit()
    db.refresh(row)

    logger.info("api_key_created", key_name=row.name, role=row.role, created_by=auth.name)

    return success_response({
        "id": row.id,
        "name": row.name,
        "role": row.role,
        "key": new_key,  # returned only at creation time
        "is_active": row.is_active,
        "created_at": str(row.created_at),
    })


@router.get("")
def list_api_keys(
    db: Session = Depends(get_db),
    auth: ApiKeyInfo = Depends(require_admin),
):
    rows = db.query(ApiKey).all()
    return success_response({
        "keys": [
            {
                "id": r.id,
                "name": r.name,
                "role": r.role,
                "is_active": r.is_active,
                "created_at": str(r.created_at),
            }
            for r in rows
        ]
    })


@router.delete("/{key_id}")
def delete_api_key(
    key_id: int,
    db: Session = Depends(get_db),
    auth: ApiKeyInfo = Depends(require_admin),
):
    row = db.query(ApiKey).filter_by(id=key_id).first()
    if not row:
        return error_response(404, f"API key with id {key_id} not found")

    db.delete(row)
    db.commit()

    logger.info("api_key_deleted", key_id=key_id, key_name=row.name, deleted_by=auth.name)

    return success_response({"status": "deleted", "id": key_id, "name": row.name})
