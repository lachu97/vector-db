#!/usr/bin/env python3
"""
Seed script — creates admin users with scale tier + admin API key.
Run once: python scripts/seed_admin_users.py
Idempotent: skips existing users, skips if admin key already exists.
"""
import secrets
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bcrypt
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from vectordb.models.db import Base, User, ApiKey
from vectordb.config import get_settings

ADMIN_USERS = [
    {"email": "stellarworks03@gmail.com", "name": "stellarworks-admin"},
    {"email": "lakshmansar@gmail.com",    "name": "lakshmansar-admin"},
]
PASSWORD = "Lakshu@123"
TIER = "scale"
ROLE = "admin"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def main():
    settings = get_settings()
    # Use sync URL (strip +aiosqlite for seeding)
    db_url = settings.db_url.replace("+aiosqlite", "").replace("sqlite:///./", "sqlite:///")
    if db_url.startswith("sqlite:///") and not db_url.startswith("sqlite:////"):
        # relative path — resolve from project root
        db_url = f"sqlite:///{os.path.join(os.getcwd(), 'vectors.db')}"

    engine = create_engine(db_url)
    Session = sessionmaker(bind=engine)
    db = Session()

    try:
        for u in ADMIN_USERS:
            existing = db.query(User).filter(User.email == u["email"]).first()
            if existing:
                user = existing
                # Upgrade tier if not already scale
                if user.tier != TIER:
                    user.tier = TIER
                    db.commit()
                    print(f"[updated] {u['email']} → tier=scale")
                else:
                    print(f"[exists]  {u['email']} (tier={user.tier})")
            else:
                user = User(
                    email=u["email"],
                    password_hash=hash_password(PASSWORD),
                    tier=TIER,
                )
                db.add(user)
                db.commit()
                db.refresh(user)
                print(f"[created] {u['email']} (tier=scale)")

            # Check if admin key already exists for this user
            existing_key = (
                db.query(ApiKey)
                .filter(ApiKey.user_id == user.id, ApiKey.role == ROLE, ApiKey.is_active == True)
                .first()
            )
            if existing_key:
                print(f"          API key already exists: {existing_key.key}")
            else:
                new_key = secrets.token_urlsafe(32)
                api_key = ApiKey(
                    key=new_key,
                    name=u["name"],
                    role=ROLE,
                    user_id=user.id,
                    is_active=True,
                )
                db.add(api_key)
                db.commit()
                print(f"          API key created:        {new_key}")

    finally:
        db.close()

    print("\nDone. Use the API key above in x-api-key header for admin access.")
    print("Login via POST /v1/auth/login with email + password to get the key from the API.")


if __name__ == "__main__":
    main()
