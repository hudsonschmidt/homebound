from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
import sqlalchemy

from ..config import get_settings
from .. import database as db
from .notifications import send_overdue_notifications

settings = get_settings()
log = logging.getLogger(__name__)

# Global scheduler instance
scheduler: Optional[AsyncIOScheduler] = None


async def check_overdue_plans():
    """Check for overdue plans and send notifications."""
    try:
        now = datetime.utcnow()

        with db.engine.begin() as conn:
            # Find active plans that are overdue
            overdue_plans = conn.execute(
                sqlalchemy.text("""
                    SELECT id, user_id, title, eta_at, grace_minutes, location_text, status
                    FROM plans
                    WHERE status = 'active' AND eta_at < :now
                """),
                {"now": now}
            ).fetchall()

            for plan in overdue_plans:
                plan_id = plan.id

                # Check if we've already marked this plan as overdue
                existing_overdue = conn.execute(
                    sqlalchemy.text("""
                        SELECT id FROM events
                        WHERE plan_id = :plan_id AND kind = 'overdue'
                        LIMIT 1
                    """),
                    {"plan_id": plan_id}
                ).fetchone()

                if existing_overdue:
                    # Already marked as overdue, check if grace period expired
                    # Parse eta_at string to datetime
                    if isinstance(plan.eta_at, str):
                        eta_dt = datetime.fromisoformat(plan.eta_at.replace(' ', 'T'))
                    else:
                        eta_dt = plan.eta_at

                    grace_expired = eta_dt + timedelta(minutes=plan.grace_minutes)

                    if now > grace_expired:
                        # Check if we've already notified
                        existing_notify = conn.execute(
                            sqlalchemy.text("""
                                SELECT id FROM events
                                WHERE plan_id = :plan_id AND kind = 'notify'
                                LIMIT 1
                            """),
                            {"plan_id": plan_id}
                        ).fetchone()

                        if not existing_notify:
                            # Get contacts to notify
                            contacts = conn.execute(
                                sqlalchemy.text("""
                                    SELECT name, phone, email
                                    FROM contacts
                                    WHERE plan_id = :plan_id AND notify_on_overdue = 1
                                """),
                                {"plan_id": plan_id}
                            ).fetchall()

                            if contacts:
                                log.info(f"Sending overdue notifications for plan {plan_id} to {len(contacts)} contacts")
                                # Send notifications (this is async but we're in sync context)
                                await send_overdue_notifications(plan, list(contacts))

                                # Mark as notified
                                conn.execute(
                                    sqlalchemy.text("""
                                        INSERT INTO events (plan_id, kind, meta, at)
                                        VALUES (:plan_id, 'notify', :meta, :at)
                                    """),
                                    {
                                        "plan_id": plan_id,
                                        "meta": f"Notified {len(contacts)} contacts",
                                        "at": datetime.utcnow()
                                    }
                                )

                            # Update plan status
                            conn.execute(
                                sqlalchemy.text("""
                                    UPDATE plans SET status = 'overdue_notified'
                                    WHERE id = :plan_id
                                """),
                                {"plan_id": plan_id}
                            )
                else:
                    # Mark as overdue
                    log.info(f"Marking plan {plan_id} as overdue")
                    conn.execute(
                        sqlalchemy.text("""
                            INSERT INTO events (plan_id, kind, at)
                            VALUES (:plan_id, 'overdue', :at)
                        """),
                        {
                            "plan_id": plan_id,
                            "at": datetime.utcnow()
                        }
                    )

                    conn.execute(
                        sqlalchemy.text("""
                            UPDATE plans SET status = 'overdue'
                            WHERE id = :plan_id
                        """),
                        {"plan_id": plan_id}
                    )

    except Exception as e:
        log.error(f"Error checking overdue plans: {e}", exc_info=True)


async def clean_expired_tokens():
    """Clean up expired login tokens."""
    try:
        now = datetime.utcnow()

        with db.engine.begin() as conn:
            result = conn.execute(
                sqlalchemy.text("""
                    DELETE FROM login_tokens
                    WHERE expires_at < :now
                """),
                {"now": now}
            )
            deleted = result.rowcount

            if deleted > 0:
                log.info(f"Cleaned up {deleted} expired login tokens")

    except Exception as e:
        log.error(f"Error cleaning expired tokens: {e}", exc_info=True)


def init_scheduler() -> AsyncIOScheduler:
    """Initialize and configure the scheduler."""
    global scheduler

    if scheduler is not None:
        return scheduler

    scheduler = AsyncIOScheduler(timezone=settings.TIMEZONE)

    # Check for overdue plans every minute
    scheduler.add_job(
        check_overdue_plans,
        IntervalTrigger(minutes=1),
        id="check_overdue",
        name="Check for overdue plans",
        replace_existing=True,
        max_instances=1,
    )

    # Clean expired tokens every 10 minutes
    scheduler.add_job(
        clean_expired_tokens,
        IntervalTrigger(minutes=10),
        id="clean_tokens",
        name="Clean expired tokens",
        replace_existing=True,
        max_instances=1,
    )

    return scheduler


def start_scheduler():
    """Start the scheduler."""
    global scheduler
    if scheduler is None:
        scheduler = init_scheduler()

    if not scheduler.running:
        scheduler.start()
        log.info("Scheduler started")


def stop_scheduler():
    """Stop the scheduler."""
    global scheduler
    if scheduler and scheduler.running:
        scheduler.shutdown()
        log.info("Scheduler stopped")
