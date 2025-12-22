from __future__ import annotations

import logging
from datetime import datetime, timedelta

import pytz
import sqlalchemy
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from .. import database as db
from ..config import get_settings
from .notifications import (
    send_overdue_notifications,
    send_push_to_user,
    send_friend_overdue_push,
    send_live_activity_update,
)

settings = get_settings()
log = logging.getLogger(__name__)

# Notification timing constants (in minutes)
STARTING_SOON_MINUTES = 15  # Notify 15 min before scheduled start
APPROACHING_ETA_MINUTES = 15  # Notify 15 min before ETA
DEFAULT_CHECKIN_REMINDER_INTERVAL = 30  # Default reminder interval (used if trip doesn't specify)
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
                           t.start, t.notes, t.start_location_text, t.has_separate_locations, t.checkout_token,
                           a.name as activity_name
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
                                # Get start location if trip has separate start/destination
                                start_location = trip.start_location_text if trip.has_separate_locations else None
                                await send_overdue_notifications(trip, list(contacts), user_name, user_timezone, start_location)
                                log.info(f"[Scheduler] Overdue notifications sent for trip {trip_id}")

                            # Fetch friend safety contacts from junction table
                            friend_contacts = conn.execute(
                                sqlalchemy.text("""
                                    SELECT tsc.friend_user_id
                                    FROM trip_safety_contacts tsc
                                    WHERE tsc.trip_id = :trip_id
                                    AND tsc.friend_user_id IS NOT NULL
                                """),
                                {"trip_id": trip_id}
                            ).fetchall()

                            if friend_contacts:
                                log.info(f"[Scheduler] Sending overdue push notifications to {len(friend_contacts)} friend contacts for trip {trip_id}")
                                for friend in friend_contacts:
                                    await send_friend_overdue_push(
                                        friend_user_id=friend.friend_user_id,
                                        user_name=user_name,
                                        trip_title=trip.title,
                                        trip_id=trip_id
                                    )
                                log.info(f"[Scheduler] Friend overdue notifications sent for trip {trip_id}")

                            # Only warn if no contacts of any kind were found
                            if not contacts and not friend_contacts:
                                log.warning(f"[Scheduler] Trip {trip_id}: No contacts (email or friend) found, skipping notification")
                            else:
                                # Mark as notified (only if we actually sent notifications)
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

                    # Parse eta for Live Activity update
                    if isinstance(trip.eta, str):
                        eta_dt = datetime.fromisoformat(trip.eta.replace(' ', 'T').replace('Z', '').replace('+00:00', ''))
                    else:
                        eta_dt = trip.eta.replace(tzinfo=None) if trip.eta.tzinfo else trip.eta

                    # Send direct Live Activity update (more reliable than silent push)
                    await send_live_activity_update(
                        trip_id=trip_id,
                        status="overdue",
                        eta=eta_dt,
                        last_checkin_time=None,  # Will be updated if available
                        is_overdue=False,  # Not past grace period yet, just past ETA
                        checkin_count=0
                    )
                    log.info(f"[Scheduler] Sent Live Activity update for overdue trip {trip_id}")

                    # Also send silent push as fallback
                    await send_push_to_user(
                        trip.user_id,
                        "",  # Empty title for silent/background push
                        "",  # Empty body
                        data={"sync": "trip_state_update", "trip_id": trip_id},
                        notification_type="emergency"  # Always send, bypass preferences
                    )
                    log.info(f"[Scheduler] Sent silent push for Live Activity update, trip {trip_id}")

    except Exception as e:
        log.error(f"Error checking overdue trips: {e}", exc_info=True)


async def check_push_notifications():
    """Check for and send push notifications to users.

    Uses isolated transactions per trip to avoid lock contention with other scheduler jobs.
    """
    try:
        now = datetime.utcnow()

        # Fetch all data first in read-only queries
        with db.engine.connect() as conn:
            # 1. Trip Starting Soon
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

            # 2. Trip Started
            just_started = conn.execute(
                sqlalchemy.text("""
                    SELECT id, user_id, title
                    FROM trips
                    WHERE status = 'active'
                    AND notified_trip_started = false
                """)
            ).fetchall()

            # 3. Approaching ETA
            approaching_eta = conn.execute(
                sqlalchemy.text("""
                    SELECT id, user_id, title, eta, checkout_token
                    FROM trips
                    WHERE status = 'active'
                    AND notified_approaching_eta = false
                    AND eta > :now
                    AND eta <= :soon
                """),
                {"now": now, "soon": now + timedelta(minutes=APPROACHING_ETA_MINUTES)}
            ).fetchall()

            # 4. ETA Reached
            eta_reached = conn.execute(
                sqlalchemy.text("""
                    SELECT id, user_id, title, eta, grace_min, checkout_token
                    FROM trips
                    WHERE status IN ('active', 'overdue')
                    AND notified_eta_reached = false
                    AND eta <= :now
                """),
                {"now": now}
            ).fetchall()

            # 5. Check-in Reminders
            need_checkin_reminder = conn.execute(
                sqlalchemy.text("""
                    SELECT id, user_id, title, last_checkin_reminder,
                           COALESCE(checkin_interval_min, :default_interval) as interval_min,
                           notify_start_hour, notify_end_hour, timezone,
                           checkin_token, checkout_token
                    FROM trips
                    WHERE status = 'active'
                """),
                {"default_interval": DEFAULT_CHECKIN_REMINDER_INTERVAL}
            ).fetchall()

            # 6. Grace Period Warnings
            in_grace_period = conn.execute(
                sqlalchemy.text("""
                    SELECT id, user_id, title, eta, grace_min, last_grace_warning, checkout_token, status
                    FROM trips
                    WHERE status IN ('overdue', 'overdue_notified')
                    AND (last_grace_warning IS NULL OR last_grace_warning <= :cutoff)
                """),
                {"cutoff": now - timedelta(minutes=GRACE_WARNING_INTERVAL)}
            ).fetchall()

        # Process each notification type with isolated transactions

        # 1. Trip Starting Soon
        for trip in starting_soon:
            try:
                await send_push_to_user(
                    trip.user_id,
                    "Trip Starting Soon",
                    f"Your trip '{trip.title}' is starting soon!",
                    notification_type="trip_reminder"
                )
                with db.engine.begin() as conn:
                    conn.execute(
                        sqlalchemy.text("UPDATE trips SET notified_starting_soon = true WHERE id = :id"),
                        {"id": trip.id}
                    )
                log.info(f"[Push] Sent 'starting soon' notification for trip {trip.id}")
            except Exception as e:
                log.error(f"[Push] Error sending 'starting soon' for trip {trip.id}: {e}")

        # 2. Trip Started
        for trip in just_started:
            try:
                await send_push_to_user(
                    trip.user_id,
                    "Trip Started",
                    f"Your trip '{trip.title}' has started. Stay safe!",
                    data={"sync": "start_live_activity", "trip_id": trip.id},
                    notification_type="trip_reminder"
                )
                await send_push_to_user(
                    trip.user_id,
                    "", "",
                    data={"sync": "start_live_activity", "trip_id": trip.id},
                    notification_type="emergency"
                )
                with db.engine.begin() as conn:
                    conn.execute(
                        sqlalchemy.text("UPDATE trips SET notified_trip_started = true WHERE id = :id"),
                        {"id": trip.id}
                    )
                log.info(f"[Push] Sent 'trip started' notification for trip {trip.id}")
            except Exception as e:
                log.error(f"[Push] Error sending 'trip started' for trip {trip.id}: {e}")

        # 3. Approaching ETA
        for trip in approaching_eta:
            try:
                await send_push_to_user(
                    trip.user_id,
                    "Almost Time",
                    f"You're expected back from '{trip.title}' in a couple minutes!",
                    data={"trip_id": trip.id, "checkout_token": trip.checkout_token},
                    notification_type="emergency",
                    category="CHECKOUT_ONLY"
                )
                with db.engine.begin() as conn:
                    conn.execute(
                        sqlalchemy.text("UPDATE trips SET notified_approaching_eta = true WHERE id = :id"),
                        {"id": trip.id}
                    )
                log.info(f"[Push] Sent 'approaching ETA' notification for trip {trip.id}")
            except Exception as e:
                log.error(f"[Push] Error sending 'approaching ETA' for trip {trip.id}: {e}")

        # 4. ETA Reached
        for trip in eta_reached:
            try:
                await send_push_to_user(
                    trip.user_id,
                    "Time to Check Out",
                    f"Your expected return time has passed. Check out or extend your trip '{trip.title}'.",
                    data={"trip_id": trip.id, "checkout_token": trip.checkout_token},
                    notification_type="emergency",
                    category="CHECKOUT_ONLY"
                )
                with db.engine.begin() as conn:
                    conn.execute(
                        sqlalchemy.text("UPDATE trips SET notified_eta_reached = true WHERE id = :id"),
                        {"id": trip.id}
                    )
                log.info(f"[Push] Sent 'ETA reached' notification for trip {trip.id}")
            except Exception as e:
                log.error(f"[Push] Error sending 'ETA reached' for trip {trip.id}: {e}")

        # 5. Check-in Reminders
        for trip in need_checkin_reminder:
            try:
                interval_min = trip.interval_min
                cutoff = now - timedelta(minutes=interval_min)

                if trip.last_checkin_reminder is not None and trip.last_checkin_reminder > cutoff:
                    continue

                # Check quiet hours
                if trip.notify_start_hour is not None and trip.notify_end_hour is not None:
                    user_tz = pytz.timezone(trip.timezone) if trip.timezone else pytz.UTC
                    user_now = datetime.now(user_tz)
                    current_hour = user_now.hour

                    if trip.notify_start_hour <= trip.notify_end_hour:
                        in_active_hours = trip.notify_start_hour <= current_hour < trip.notify_end_hour
                    else:
                        in_active_hours = current_hour >= trip.notify_start_hour or current_hour < trip.notify_end_hour

                    if not in_active_hours:
                        continue

                if trip.last_checkin_reminder is None:
                    with db.engine.begin() as conn:
                        conn.execute(
                            sqlalchemy.text("UPDATE trips SET last_checkin_reminder = :now WHERE id = :id"),
                            {"now": now, "id": trip.id}
                        )
                else:
                    await send_push_to_user(
                        trip.user_id,
                        "Check-in Reminder",
                        "Hope your trip is going well! Don't forget to check in!",
                        data={"trip_id": trip.id, "checkin_token": trip.checkin_token, "checkout_token": trip.checkout_token},
                        notification_type="checkin",
                        category="CHECKIN_REMINDER"
                    )
                    with db.engine.begin() as conn:
                        conn.execute(
                            sqlalchemy.text("UPDATE trips SET last_checkin_reminder = :now WHERE id = :id"),
                            {"now": now, "id": trip.id}
                        )
                    log.info(f"[Push] Sent check-in reminder for trip {trip.id}")
            except Exception as e:
                log.error(f"[Push] Error sending check-in reminder for trip {trip.id}: {e}")

        # 6. Grace Period Warnings
        for trip in in_grace_period:
            try:
                if isinstance(trip.eta, str):
                    eta_dt = datetime.fromisoformat(trip.eta.replace(' ', 'T').replace('Z', '').replace('+00:00', ''))
                else:
                    eta_dt = trip.eta.replace(tzinfo=None) if trip.eta.tzinfo else trip.eta

                grace_expires = eta_dt + timedelta(minutes=trip.grace_min)
                remaining = (grace_expires - now).total_seconds() / 60

                if remaining > 0:
                    message = f"You're overdue! {int(remaining)} minutes left before contacts are notified."
                else:
                    message = "Your contacts have been notified. Check out now to let them know you're safe!"

                await send_push_to_user(
                    trip.user_id,
                    "Urgent: Check In Now",
                    message,
                    data={"trip_id": trip.id, "checkout_token": trip.checkout_token},
                    notification_type="emergency",
                    category="CHECKOUT_ONLY"
                )
                with db.engine.begin() as conn:
                    conn.execute(
                        sqlalchemy.text("UPDATE trips SET last_grace_warning = :now WHERE id = :id"),
                        {"now": now, "id": trip.id}
                    )
                log.info(f"[Push] Sent grace warning for trip {trip.id}")
            except Exception as e:
                log.error(f"[Push] Error sending grace warning for trip {trip.id}: {e}")

    except Exception as e:
        log.error(f"Error checking push notifications: {e}", exc_info=True)


async def check_live_activity_transitions():
    """Check for Live Activity countdown transitions and send update pushes.

    Sends direct Live Activity push updates at:
    1. ~15 seconds before ETA -> "Check In Now" warning state (isOverdue: false)
    2. ~15 seconds before grace period ends -> "Overdue" state (isOverdue: true)
    """
    try:
        now = datetime.utcnow()

        # First, fetch all trips that need processing (read-only transaction)
        with db.engine.connect() as conn:
            # Find active trips approaching ETA (within 15 seconds)
            approaching_eta = conn.execute(
                sqlalchemy.text("""
                    SELECT id, user_id, eta, grace_min, status, last_checkin
                    FROM trips
                    WHERE status = 'active'
                    AND notified_eta_transition = false
                    AND eta <= :soon
                    AND eta > :now
                """),
                {
                    "now": now,
                    "soon": now + timedelta(seconds=15)
                }
            ).fetchall()

            # Find overdue trips approaching grace period end
            overdue_trips = conn.execute(
                sqlalchemy.text("""
                    SELECT id, user_id, eta, grace_min, status, last_checkin
                    FROM trips
                    WHERE status = 'overdue'
                    AND notified_grace_transition = false
                """)
            ).fetchall()

        # Process each ETA transition trip in its own transaction
        for trip in approaching_eta:
            try:
                # Parse eta for content-state
                if isinstance(trip.eta, str):
                    eta_dt = datetime.fromisoformat(trip.eta.replace(' ', 'T').replace('Z', '').replace('+00:00', ''))
                else:
                    eta_dt = trip.eta.replace(tzinfo=None) if trip.eta.tzinfo else trip.eta

                # Parse last_checkin if present
                last_checkin_dt = None
                if trip.last_checkin:
                    try:
                        last_checkin_dt = datetime.fromisoformat(str(trip.last_checkin).replace(' ', 'T').replace('Z', '').replace('+00:00', ''))
                    except Exception:
                        pass

                # Get check-in count from events (optional, default to 0)
                checkin_count = 0
                try:
                    with db.engine.connect() as conn:
                        count_row = conn.execute(
                            sqlalchemy.text("SELECT COUNT(*) FROM timeline_events WHERE trip_id = :trip_id AND event_type = 'checkin'"),
                            {"trip_id": trip.id}
                        ).fetchone()
                        if count_row:
                            checkin_count = count_row[0]
                except Exception:
                    pass  # timeline_events table may not exist, use default 0

                # Send direct Live Activity update (new approach)
                await send_live_activity_update(
                    trip_id=trip.id,
                    status="active",
                    eta=eta_dt,
                    last_checkin_time=last_checkin_dt,
                    is_overdue=False,  # ETA warning, not yet overdue
                    checkin_count=checkin_count
                )

                # Also send silent push as fallback for older devices
                await send_push_to_user(
                    trip.user_id,
                    "",  # Empty for silent push
                    "",
                    data={
                        "sync": "live_activity_eta_warning",
                        "trip_id": trip.id,
                        "transition": "eta_warning"
                    },
                    notification_type="emergency"
                )

                # Mark as notified in its own transaction
                with db.engine.begin() as conn:
                    conn.execute(
                        sqlalchemy.text("UPDATE trips SET notified_eta_transition = true WHERE id = :id"),
                        {"id": trip.id}
                    )
                log.info(f"[LiveActivity] Sent ETA warning transition for trip {trip.id}")

            except Exception as e:
                log.error(f"[LiveActivity] Error processing ETA transition for trip {trip.id}: {e}", exc_info=True)

        # Process each grace period transition trip in its own transaction
        for trip in overdue_trips:
            try:
                # Parse eta
                if isinstance(trip.eta, str):
                    eta_dt = datetime.fromisoformat(trip.eta.replace(' ', 'T').replace('Z', '').replace('+00:00', ''))
                else:
                    eta_dt = trip.eta.replace(tzinfo=None) if trip.eta.tzinfo else trip.eta

                grace_end = eta_dt + timedelta(minutes=trip.grace_min)
                seconds_until_grace_end = (grace_end - now).total_seconds()

                # Send push if within 15 seconds of grace ending
                if 0 < seconds_until_grace_end <= 15:
                    # Parse last_checkin if present
                    last_checkin_dt = None
                    if trip.last_checkin:
                        try:
                            last_checkin_dt = datetime.fromisoformat(str(trip.last_checkin).replace(' ', 'T').replace('Z', '').replace('+00:00', ''))
                        except Exception:
                            pass

                    # Get check-in count
                    checkin_count = 0
                    try:
                        with db.engine.connect() as conn:
                            count_row = conn.execute(
                                sqlalchemy.text("SELECT COUNT(*) FROM timeline_events WHERE trip_id = :trip_id AND event_type = 'checkin'"),
                                {"trip_id": trip.id}
                            ).fetchone()
                            if count_row:
                                checkin_count = count_row[0]
                    except Exception:
                        pass  # timeline_events table may not exist, use default 0

                    # Send direct Live Activity update
                    await send_live_activity_update(
                        trip_id=trip.id,
                        status="overdue",
                        eta=eta_dt,
                        last_checkin_time=last_checkin_dt,
                        is_overdue=True,  # Past grace period
                        checkin_count=checkin_count
                    )

                    # Also send silent push as fallback
                    await send_push_to_user(
                        trip.user_id,
                        "",
                        "",
                        data={
                            "sync": "live_activity_overdue",
                            "trip_id": trip.id,
                            "transition": "overdue"
                        },
                        notification_type="emergency"
                    )

                    # Mark as notified in its own transaction
                    with db.engine.begin() as conn:
                        conn.execute(
                            sqlalchemy.text("UPDATE trips SET notified_grace_transition = true WHERE id = :id"),
                            {"id": trip.id}
                        )
                    log.info(f"[LiveActivity] Sent overdue transition for trip {trip.id}")

            except Exception as e:
                log.error(f"[LiveActivity] Error processing grace transition for trip {trip.id}: {e}", exc_info=True)

    except Exception as e:
        log.error(f"Error checking Live Activity transitions: {e}", exc_info=True)


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

    # Check for Live Activity countdown transitions every 12 seconds
    scheduler.add_job(
        check_live_activity_transitions,
        IntervalTrigger(minutes=0.2),
        id="check_live_activity_transitions",
        name="Check Live Activity countdown transitions",
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
