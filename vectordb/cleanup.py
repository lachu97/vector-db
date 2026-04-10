# vectordb/cleanup.py
"""
Automatic cleanup of inactive users.
Users with no activity for 3 months are deleted along with their
API keys, collections, vectors, and usage data.
"""
import asyncio
from datetime import datetime, timezone, timedelta

import structlog
from sqlalchemy.orm import Session

from vectordb.models.db import User, Collection, ApiKey, SessionLocal
from vectordb.quota import is_bypass_user

logger = structlog.get_logger(__name__)

INACTIVE_THRESHOLD_DAYS = 90  # 3 months
CLEANUP_INTERVAL_HOURS = 24   # run once per day


def cleanup_inactive_users(db: Session) -> dict:
    """
    Delete users who haven't been active for 3+ months.
    Skips bypass users and users with no last_active_at (recently created).

    Returns summary of what was deleted.
    """
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=INACTIVE_THRESHOLD_DAYS)

    # Find inactive users: last_active_at is set and older than cutoff
    inactive_users = (
        db.query(User)
        .filter(User.last_active_at.isnot(None))
        .filter(User.last_active_at < cutoff)
        .all()
    )

    deleted = []
    skipped = []

    for user in inactive_users:
        if is_bypass_user(user):
            skipped.append(user.email)
            continue

        email = user.email
        user_id = user.id

        # Delete user's collections and their vectors
        collections = db.query(Collection).filter_by(user_id=user_id).all()
        collection_count = len(collections)
        for col in collections:
            db.delete(col)  # cascades to vectors

        # Delete user (cascades to api_keys + usage_summaries)
        db.delete(user)

        deleted.append({"email": email, "user_id": user_id, "collections_deleted": collection_count})
        logger.info("inactive_user_deleted", email=email, user_id=user_id,
                     collections=collection_count, inactive_days=INACTIVE_THRESHOLD_DAYS)

    if deleted:
        db.commit()

    summary = {
        "deleted_count": len(deleted),
        "skipped_count": len(skipped),
        "deleted": deleted,
        "skipped_bypass": skipped,
        "cutoff_date": str(cutoff),
    }

    if deleted:
        logger.info("cleanup_complete", **{k: v for k, v in summary.items() if k != "deleted"})
    else:
        logger.debug("cleanup_no_inactive_users")

    return summary


async def cleanup_loop():
    """Background task — runs cleanup once per day."""
    while True:
        await asyncio.sleep(CLEANUP_INTERVAL_HOURS * 3600)
        try:
            db = SessionLocal()
            try:
                cleanup_inactive_users(db)
            finally:
                db.close()
        except Exception as e:
            logger.error("cleanup_loop_failed", error=str(e))
