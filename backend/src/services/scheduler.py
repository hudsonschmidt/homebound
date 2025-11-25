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


async def check_overdue_trips():
    """Check for overdue trips and send notifications."""
    try:
        now = datetime.utcnow()

        with db.engine.begin() as conn:
            # Find active trips that are past their ETA
            overdue_trips = conn.execute(
                sqlalchemy.text("""
                    SELECT id, user_id, title, eta, grace_min, location_text, status
                    FROM trips
                    WHERE status = 'active' AND eta < :now
                """),
                {"now": now}
            ).fetchall()

            for trip in overdue_trips:
                trip_id = trip.id

                # Check if we've already marked this trip as overdue
                existing_overdue = conn.execute(
                    sqlalchemy.text("""
                        SELECT id FROM events
                        WHERE trip_id = :trip_id AND what = 'overdue'
                        LIMIT 1
                    """),
                    {"trip_id": trip_id}
                ).fetchone()

                if existing_overdue:
                    # Already marked as overdue, check if grace period expired
                    # Parse eta string to datetime
                    if isinstance(trip.eta, str):
                        eta_dt = datetime.fromisoformat(trip.eta.replace(' ', 'T').replace('Z', '+00:00'))
                    else:
                        eta_dt = trip.eta

                    grace_expired = eta_dt + timedelta(minutes=trip.grace_min)

                    if now > grace_expired:
                        # Check if we've already notified
                        existing_notify = conn.execute(
                            sqlalchemy.text("""
                                SELECT id FROM events
                                WHERE trip_id = :trip_id AND what = 'notify'
                                LIMIT 1
                            """),
                            {"trip_id": trip_id}
                        ).fetchone()

                        if not existing_notify:
                            # Get contacts to notify (via trip's contact1/2/3 foreign keys)
                            contacts = conn.execute(
                                sqlalchemy.text("""
                                    SELECT c.name, c.phone, c.email
                                    FROM contacts c
                                    JOIN trips t ON (
                                        c.id = t.contact1 OR
                                        c.id = t.contact2 OR
                                        c.id = t.contact3
                                    )
                                    WHERE t.id = :trip_id AND c.email IS NOT NULL
                                """),
                                {"trip_id": trip_id}
                            ).fetchall()

                            # Fetch user name for notification
                            user = conn.execute(
                                sqlalchemy.text("SELECT first_name, last_name FROM users WHERE id = :user_id"),
                                {"user_id": trip.user_id}
                            ).fetchone()
                            user_name = f"{user.first_name} {user.last_name}".strip() if user else "Someone"
                            if not user_name:
                                user_name = "A Homebound user"

                            if contacts:
                                log.info(f"Sending overdue notifications for trip {trip_id} to {len(contacts)} contacts")
                                # Send notifications
                                await send_overdue_notifications(trip, list(contacts), user_name)

                                # Mark as notified
                                conn.execute(
                                    sqlalchemy.text("""
                                        INSERT INTO events (user_id, trip_id, what, timestamp)
                                        VALUES (:user_id, :trip_id, 'notify', :timestamp)
                                    """),
                                    {
                                        "user_id": trip.user_id,
                                        "trip_id": trip_id,
                                        "timestamp": datetime.utcnow()
                                    }
                                )

                            # Update trip status
                            conn.execute(
                                sqlalchemy.text("""
                                    UPDATE trips SET status = 'overdue_notified'
                                    WHERE id = :trip_id
                                """),
                                {"trip_id": trip_id}
                            )
                else:
                    # Mark as overdue
                    log.info(f"Marking trip {trip_id} as overdue")
                    conn.execute(
                        sqlalchemy.text("""
                            INSERT INTO events (user_id, trip_id, what, timestamp)
                            VALUES (:user_id, :trip_id, 'overdue', :timestamp)
                        """),
                        {
                            "user_id": trip.user_id,
                            "trip_id": trip_id,
                            "timestamp": datetime.utcnow()
                        }
                    )

                    conn.execute(
                        sqlalchemy.text("""
                            UPDATE trips SET status = 'overdue'
                            WHERE id = :trip_id
                        """),
                        {"trip_id": trip_id}
                    )

    except Exception as e:
        log.error(f"Error checking overdue trips: {e}", exc_info=True)


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

    # Check for overdue trips every minute
    scheduler.add_job(
        check_overdue_trips,
        IntervalTrigger(minutes=1),
        id="check_overdue",
        name="Check for overdue trips",
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
