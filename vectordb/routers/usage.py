# vectordb/routers/usage.py
"""
Per-user usage + tier endpoints.

  GET  /v1/usage              — current period usage with warnings
  GET  /v1/usage/history      — monthly history for the authenticated user
  PATCH /v1/admin/users/{id}/tier — admin-only tier change
"""
import structlog
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from vectordb.auth import ApiKeyInfo, require_admin, require_readonly
from vectordb.cleanup import cleanup_inactive_users
from vectordb.models.db import User, UserUsageSummary, get_db
from vectordb.quota import VALID_TIERS, get_user_usage
from vectordb.services.vector_service import error_response, success_response

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/v1", tags=["usage"])


# ------------------------------------------------------------------
# GET /v1/usage — current period usage + warnings
# ------------------------------------------------------------------

@router.get("/usage")
def get_current_usage(
    db: Session = Depends(get_db),
    auth: ApiKeyInfo = Depends(require_readonly),
):
    if auth.user_id is None:
        # Bootstrap admin — no tier, no limits
        return success_response({
            "tier": "admin",
            "period": None,
            "requests": {"used": 0, "limit": None, "remaining": None},
            "vectors": {"used": 0, "limit": None, "remaining": None},
            "warnings": None,
            "bootstrap": True,
        })
    return success_response(get_user_usage(db, auth.user_id))


# ------------------------------------------------------------------
# GET /v1/usage/history — all monthly rows for the authenticated user
# ------------------------------------------------------------------

@router.get("/usage/history")
def get_usage_history(
    db: Session = Depends(get_db),
    auth: ApiKeyInfo = Depends(require_readonly),
):
    if auth.user_id is None:
        return success_response({"history": []})

    rows = (
        db.query(UserUsageSummary)
        .filter_by(user_id=auth.user_id)
        .order_by(UserUsageSummary.period.desc())
        .all()
    )
    history = [
        {
            "period": r.period,
            "request_count": r.request_count,
            "vector_count": r.vector_count,
        }
        for r in rows
    ]
    return success_response({"history": history})


# ------------------------------------------------------------------
# PATCH /v1/admin/users/{id}/tier — admin-only tier change
# ------------------------------------------------------------------

class UpdateTierRequest(BaseModel):
    tier: str


@router.patch("/admin/users/{user_id}/tier")
def update_user_tier(
    user_id: int,
    req: UpdateTierRequest,
    db: Session = Depends(get_db),
    auth: ApiKeyInfo = Depends(require_admin),
):
    # Only bootstrap admin can change tiers
    if auth.user_id is not None:
        return error_response(403, "Only the bootstrap admin can change user tiers")

    if req.tier not in VALID_TIERS:
        return error_response(
            400, f"Invalid tier. Must be one of: {', '.join(sorted(VALID_TIERS))}"
        )

    user = db.query(User).filter_by(id=user_id).first()
    if not user:
        return error_response(404, f"User {user_id} not found")

    old_tier = user.tier
    user.tier = req.tier
    db.commit()

    logger.info(
        "user_tier_updated",
        user_id=user_id,
        email=user.email,
        old_tier=old_tier,
        new_tier=req.tier,
        updated_by=auth.name,
    )

    return success_response({
        "user_id": user.id,
        "email": user.email,
        "tier": user.tier,
    })


# ------------------------------------------------------------------
# POST /v1/admin/cleanup — manually trigger inactive user cleanup
# ------------------------------------------------------------------

@router.post("/admin/cleanup")
def trigger_cleanup(
    db: Session = Depends(get_db),
    auth: ApiKeyInfo = Depends(require_admin),
):
    if auth.user_id is not None:
        return error_response(403, "Only the bootstrap admin can trigger cleanup")

    result = cleanup_inactive_users(db)
    return success_response(result)
