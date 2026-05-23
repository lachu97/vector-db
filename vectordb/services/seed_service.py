import secrets

import bcrypt
import structlog

from vectordb.config import get_settings
from vectordb.models.db import ApiKey, SessionLocal, User

logger = structlog.get_logger(__name__)

ADMIN_USERS = [
    {"email": "stellarworks03@gmail.com", "name": "stellarworks-admin"},
    {"email": "lakshmansar@gmail.com",    "name": "lakshmansar-admin"},
]
TIER = "scale"
ROLE = "admin"


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def seed_admin_users() -> None:
    """Idempotent: create admin users + keys if they don't exist. Safe on every startup."""
    settings = get_settings()
    password = settings.seed_admin_password
    db = SessionLocal()
    try:
        for u in ADMIN_USERS:
            user = db.query(User).filter(User.email == u["email"]).first()
            if user:
                if user.tier != TIER:
                    user.tier = TIER
                    db.commit()
                    logger.info("seed_user_upgraded", email=u["email"], tier=TIER)
                else:
                    logger.info("seed_user_exists", email=u["email"])
            else:
                user = User(
                    email=u["email"],
                    password_hash=_hash_password(password),
                    tier=TIER,
                )
                db.add(user)
                db.commit()
                db.refresh(user)
                logger.info("seed_user_created", email=u["email"])

            existing_key = (
                db.query(ApiKey)
                .filter(ApiKey.user_id == user.id, ApiKey.role == ROLE, ApiKey.is_active == True)
                .first()
            )
            if existing_key:
                logger.info("seed_key_exists", email=u["email"])
            else:
                api_key = ApiKey(
                    key=secrets.token_urlsafe(32),
                    name=u["name"],
                    role=ROLE,
                    user_id=user.id,
                    is_active=True,
                )
                db.add(api_key)
                db.commit()
                logger.info("seed_key_created", email=u["email"])
    except Exception as e:
        logger.warning("seed_admin_users_failed", error=str(e))
    finally:
        db.close()
