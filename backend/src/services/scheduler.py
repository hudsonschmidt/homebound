from __future__ import annotations

import logging
from datetime import datetime, timedelta

import sqlalchemy
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from .. import database as db
from ..config import get_settings
from .notifications import send_overdue_notifications, send_push_to_user

settings = get_settings()
log = logging.getLogger(__name__)

# Notification timing constants (in minutes)
STARTING_SOON_MINUTES = 15  # Notify 15 min before scheduled start
APPROACHING_ETA_MINUTES = 15  # Notify 15 min before ETA
CHECKIN_REMINDER_INTERVAL = 30  # Remind to check in every 30 min
GRACE_WARNING_INTERVAL = 5  # Warn every 5 min during grace period

# Global scheduler instance
scheduler: AsyncIOScheduler | None = None


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
                    SELECT t.id, t.user_id, t.title, t.eta, t.grace_min, t.location_text, t.status, t.timezone,
                           t.start, t.notes, a.name as activity_name
                    FROM trips t
                    JOIN activities a ON t.activity = a.id
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


async def check_push_notifications():
    """Check for and send push notifications to users."""
    try:
        now = datetime.utcnow()

        with db.engine.begin() as conn:
            # 1. Trip Starting Soon - notify 15 min before scheduled start
            starting_soon = conn.execute(
                sqlalchemy.text("""
                    SELECT id, user_id, title, start
                    FROM trips
                    WHERE status = 'planned'
                    AND notified_starting_soon = false
                    AND start > :now
                    AND start <= :soon
                """),
                {"now": now, "soon": now + timedelta(minutes=STARTING_SOON_MINUTES)}
            ).fetchall()

            for trip in starting_soon:
                await send_push_to_user(
                    trip.user_id,
                    "Trip Starting Soon",
                    f"Your trip '{trip.title}' is starting soon!",
                    notification_type="trip_reminder"
                )
                conn.execute(
                    sqlalchemy.text("UPDATE trips SET notified_starting_soon = true WHERE id = :id"),
                    {"id": trip.id}
                )
                log.info(f"[Push] Sent 'starting soon' notification for trip {trip.id}")

            # 2. Trip Started - when planned trip becomes active
            just_started = conn.execute(
                sqlalchemy.text("""
                    SELECT id, user_id, title
                    FROM trips
                    WHERE status = 'active'
                    AND notified_trip_started = false
                """)
            ).fetchall()

            for trip in just_started:
                await send_push_to_user(
                    trip.user_id,
                    "Trip Started",
                    f"Your trip '{trip.title}' has started. Stay safe!",
                    notification_type="trip_reminder"
                )
                conn.execute(
                    sqlalchemy.text("UPDATE trips SET notified_trip_started = true WHERE id = :id"),
                    {"id": trip.id}
                )
                log.info(f"[Push] Sent 'trip started' notification for trip {trip.id}")

            # 3. Approaching ETA - notify 15 min before ETA
            approaching_eta = conn.execute(
                sqlalchemy.text("""
                    SELECT id, user_id, title, eta
                    FROM trips
                    WHERE status = 'active'
                    AND notified_approaching_eta = false
                    AND eta > :now
                    AND eta <= :soon
                """),
                {"now": now, "soon": now + timedelta(minutes=APPROACHING_ETA_MINUTES)}
            ).fetchall()

            for trip in approaching_eta:
                await send_push_to_user(
                    trip.user_id,
                    "Almost Time",
                    f"You're expected back from '{trip.title}' in a couple minutes! Plan to check out soon, or extend your trip if you need more time!",
                    notification_type="trip_reminder"
                )
                conn.execute(
                    sqlalchemy.text("UPDATE trips SET notified_approaching_eta = true WHERE id = :id"),
                    {"id": trip.id}
                )
                log.info(f"[Push] Sent 'approaching ETA' notification for trip {trip.id}")

            # 4. ETA Reached - notify when ETA passes
            eta_reached = conn.execute(
                sqlalchemy.text("""
                    SELECT id, user_id, title, eta, grace_min
                    FROM trips
                    WHERE status IN ('active', 'overdue')
                    AND notified_eta_reached = false
                    AND eta <= :now
                """),
                {"now": now}
            ).fetchall()

            for trip in eta_reached:
                await send_push_to_user(
                    trip.user_id,
                    "Time to Check Out",
                    f"Your expected return time has passed. Check out or extend your trip '{trip.title}'.",
                    notification_type="checkin"
                )
                conn.execute(
                    sqlalchemy.text("UPDATE trips SET notified_eta_reached = true WHERE id = :id"),
                    {"id": trip.id}
                )
                log.info(f"[Push] Sent 'ETA reached' notification for trip {trip.id}")

            # 5. Check-in Reminders - during active trips (every 30 min)
            need_checkin_reminder = conn.execute(
                sqlalchemy.text("""
                    SELECT id, user_id, title, last_checkin_reminder
                    FROM trips
                    WHERE status = 'active'
                    AND (last_checkin_reminder IS NULL OR last_checkin_reminder <= :cutoff)
                """),
                {"cutoff": now - timedelta(minutes=CHECKIN_REMINDER_INTERVAL)}
            ).fetchall()

            for trip in need_checkin_reminder:
                # Skip if this is a brand new trip (don't spam immediately)
                if trip.last_checkin_reminder is None:
                    # Just mark the time, don't send notification on first pass
                    conn.execute(
                        sqlalchemy.text("UPDATE trips SET last_checkin_reminder = :now WHERE id = :id"),
                        {"now": now, "id": trip.id}
                    )
                else:
                    await send_push_to_user(
                        trip.user_id,
                        "Check-in Reminder",
                        f"Hope your trip is going well! Don't forget to check in!",
                        notification_type="checkin"
                    )
                    conn.execute(
                        sqlalchemy.text("UPDATE trips SET last_checkin_reminder = :now WHERE id = :id"),
                        {"now": now, "id": trip.id}
                    )
                    log.info(f"[Push] Sent check-in reminder for trip {trip.id}")

            # 6. Grace Period Warnings - every 5 min during grace period
            # Only send warnings for trips that are overdue (not yet notified)
            # Once contacts are notified (overdue_notified), stop sending warnings to user
            in_grace_period = conn.execute(
                sqlalchemy.text("""
                    SELECT id, user_id, title, eta, grace_min, last_grace_warning
                    FROM trips
                    WHERE status = 'overdue'
                    AND (last_grace_warning IS NULL OR last_grace_warning <= :cutoff)
                """),
                {"cutoff": now - timedelta(minutes=GRACE_WARNING_INTERVAL)}
            ).fetchall()

            for trip in in_grace_period:
                # Parse eta
                if isinstance(trip.eta, str):
                    eta_dt = datetime.fromisoformat(trip.eta.replace(' ', 'T').replace('Z', '').replace('+00:00', ''))
                else:
                    eta_dt = trip.eta.replace(tzinfo=None) if trip.eta.tzinfo else trip.eta

                grace_expires = eta_dt + timedelta(minutes=trip.grace_min)
                remaining = (grace_expires - now).total_seconds() / 60

                if remaining > 0:
                    await send_push_to_user(
                        trip.user_id,
                        "Urgent: Check In Now",
                        f"You're overdue! {int(remaining)} minutes left before contacts are notified.",
                        notification_type="emergency"
                    )
                    conn.execute(
                        sqlalchemy.text("UPDATE trips SET last_grace_warning = :now WHERE id = :id"),
                        {"now": now, "id": trip.id}
                    )
                    log.info(f"[Push] Sent grace warning for trip {trip.id}, {int(remaining)} min remaining")

    except Exception as e:
        log.error(f"Error checking push notifications: {e}", exc_info=True)


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
        IntervalTrigger(minutes=0.2),
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

    # Check for push notifications every minute
    scheduler.add_job(
        check_push_notifications,
        IntervalTrigger(minutes=0.2),
        id="check_push_notifications",
        name="Check for push notifications",
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
