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
        log.info(f"[Scheduler] Checking for overdue trips at {now}")

        with db.engine.begin() as conn:
            # First, activate any planned trips whose start time has passed
            activated = conn.execute(
                sqlalchemy.text("""
                    UPDATE trips
                    SET status = 'active'
                    WHERE status = 'planned' AND start < :now
                    RETURNING id
                """),
                {"now": now}
            ).fetchall()

            if activated:
                log.info(f"[Scheduler] Activated {len(activated)} planned trips: {[t.id for t in activated]}")

            # Find active or overdue trips that are past their ETA
            # Include 'overdue' status so we can check if grace period expired and send notifications
            overdue_trips = conn.execute(
                sqlalchemy.text("""
                    SELECT t.id, t.user_id, t.title, t.eta, t.grace_min, t.location_text, t.status, t.timezone
                    FROM trips t
                    WHERE t.status IN ('active', 'overdue') AND t.eta < :now
                """),
                {"now": now}
            ).fetchall()

            log.info(f"[Scheduler] Found {len(overdue_trips)} trips past ETA")

            for trip in overdue_trips:
                trip_id = trip.id
                log.info(f"[Scheduler] Processing trip {trip_id}: status={trip.status}, eta={trip.eta}, grace_min={trip.grace_min}")

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
                    log.info(f"[Scheduler] Trip {trip_id} already has overdue event, checking grace period")
                    # Already marked as overdue, check if grace period expired
                    # Parse eta string to datetime (make naive for comparison)
                    if isinstance(trip.eta, str):
                        eta_dt = datetime.fromisoformat(trip.eta.replace(' ', 'T').replace('Z', '').replace('+00:00', ''))
                    else:
                        # Remove timezone info for comparison with naive datetime
                        eta_dt = trip.eta.replace(tzinfo=None) if trip.eta.tzinfo else trip.eta

                    grace_expired = eta_dt + timedelta(minutes=trip.grace_min)
                    log.info(f"[Scheduler] Trip {trip_id}: eta_dt={eta_dt}, grace_expired={grace_expired}, now={now}, grace_expired_check={now > grace_expired}")

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
                            log.info(f"[Scheduler] Trip {trip_id}: Grace period expired, no notify event yet - sending notifications")
                            # Get contacts to notify (via trip's contact1/2/3 foreign keys)
                            contacts = conn.execute(
                                sqlalchemy.text("""
                                    SELECT c.name, c.email
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

                            log.info(f"[Scheduler] Trip {trip_id}: Found {len(contacts)} contacts with email")

                            # Fetch user name for notification
                            user = conn.execute(
                                sqlalchemy.text("SELECT first_name, last_name FROM users WHERE id = :user_id"),
                                {"user_id": trip.user_id}
                            ).fetchone()
                            user_name = f"{user.first_name} {user.last_name}".strip() if user else "Someone"
                            if not user_name:
                                user_name = "A Homebound user"

                            if contacts:
                                log.info(f"[Scheduler] Sending overdue notifications for trip {trip_id} to {len(contacts)} contacts")
                                # Send notifications with user's timezone
                                user_timezone = trip.timezone if hasattr(trip, 'timezone') else None
                                await send_overdue_notifications(trip, list(contacts), user_name, user_timezone)
                                log.info(f"[Scheduler] Overdue notifications sent for trip {trip_id}")

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
                            else:
                                log.warning(f"[Scheduler] Trip {trip_id}: No contacts with email found, skipping notification")

                            # Update trip status
                            conn.execute(
                                sqlalchemy.text("""
                                    UPDATE trips SET status = 'overdue_notified'
                                    WHERE id = :trip_id
                                """),
                                {"trip_id": trip_id}
                            )
                            log.info(f"[Scheduler] Trip {trip_id}: Status updated to overdue_notified")
                        else:
                            log.info(f"[Scheduler] Trip {trip_id}: Already has notify event, skipping")
                    else:
                        log.info(f"[Scheduler] Trip {trip_id}: Grace period not yet expired")
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
