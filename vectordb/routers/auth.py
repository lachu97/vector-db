# vectordb/routers/auth.py
"""
Public authentication endpoints — no x-api-key required.
Handles user registration, login, and bootstrap key creation.
"""
import secrets

import bcrypt
import structlog
from fastapi import APIRouter, Depends
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from vectordb.models.db import User, ApiKey, get_db
from vectordb.services.vector_service import success_response, error_response

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/v1/auth", tags=["auth"])


# ------------------------------------------------------------------
# Request schemas
# ------------------------------------------------------------------

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _check_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))


def _create_admin_key_for_user(db: Session, user: User) -> ApiKey:
    """Create an admin API key scoped to the given user."""
    new_key = secrets.token_urlsafe(32)
    key_row = ApiKey(
        key=new_key,
        name=f"{user.email}-admin",
        role="admin",
        is_active=True,
        user_id=user.id,
    )
    db.add(key_row)
    db.commit()
    db.refresh(key_row)
    return key_row


def _format_user_response(user: User, key_row: ApiKey) -> dict:
    return {
        "user": {
            "id": user.id,
            "email": user.email,
            "tier": user.tier,
            "created_at": str(user.created_at),
        },
        "api_key": {
            "id": key_row.id,
            "key": key_row.key,
            "name": key_row.name,
            "role": key_row.role,
        },
    }


# ------------------------------------------------------------------
# POST /v1/auth/register
# ------------------------------------------------------------------

@router.post("/register")
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    if len(req.password) < 8:
        return error_response(400, "Password must be at least 8 characters")

    existing = db.query(User).filter_by(email=req.email).first()
    if existing:
        return error_response(409, "Email already registered")

    user = User(
        email=req.email,
        password_hash=_hash_password(req.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    key_row = _create_admin_key_for_user(db, user)

    logger.info("user_registered", email=user.email, user_id=user.id)
    return success_response(_format_user_response(user, key_row))


# ------------------------------------------------------------------
# POST /v1/auth/login
# ------------------------------------------------------------------

@router.post("/login")
def login(req: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter_by(email=req.email).first()
    if not user:
        return error_response(401, "Invalid email or password")

    if not _check_password(req.password, user.password_hash):
        return error_response(401, "Invalid email or password")

    # Find existing active admin key for this user, or create one
    key_row = (
        db.query(ApiKey)
        .filter_by(user_id=user.id, role="admin", is_active=True)
        .first()
    )
    if not key_row:
        key_row = _create_admin_key_for_user(db, user)

    logger.info("user_logged_in", email=user.email, user_id=user.id)
    return success_response(_format_user_response(user, key_row))
