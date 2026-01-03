from __future__ import annotations

import logging
from collections import namedtuple
from datetime import datetime, timedelta
from typing import Any

import pytz
import sqlalchemy
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from dateutil import parser as dateutil_parser

from .. import database as db
from ..config import get_settings
from .notifications import (
    send_overdue_notifications,
    send_push_to_user,
    send_background_push_to_user,
    send_friend_overdue_push,
    send_live_activity_update,
)


def parse_datetime_robust(dt_value: Any) -> datetime | None:
    """Parse datetime from various formats robustly.

    Handles:
    - datetime objects (returned as-is, timezone stripped)
    - ISO8601 strings with various formats (microseconds, timezone offsets, Z suffix)
    - Space-separated datetime strings

    Returns naive datetime (no timezone) or None if parsing fails.
    """
    if dt_value is None:
        return None

    if isinstance(dt_value, datetime):
        return dt_value.replace(tzinfo=None) if dt_value.tzinfo else dt_value

    if isinstance(dt_value, str):
        try:
            parsed = dateutil_parser.parse(dt_value)
            return parsed.replace(tzinfo=None) if parsed.tzinfo else parsed
        except (ValueError, TypeError) as e:
            logging.getLogger(__name__).warning(f"Failed to parse datetime '{dt_value}': {e}")
            return None

    return None

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
    """Check for overdue trips and send notifications.

    Uses isolated transactions per trip to avoid lock contention with other scheduler jobs.
    """
    try:
        now = datetime.utcnow()
        log.info(f"[Scheduler] Checking for overdue trips at {now}")

        # Phase 1: Activate planned trips (isolated transaction)
        activated_ids = []
        with db.engine.begin() as conn:
            activated = conn.execute(
                sqlalchemy.text("""
                    UPDATE trips
                    SET status = 'active'
                    WHERE status = 'planned' AND start < :now
                    RETURNING id
                """),
                {"now": now}
            ).fetchall()
            activated_ids = [t.id for t in activated]

        if activated_ids:
            log.info(f"[Scheduler] Activated {len(activated_ids)} planned trips: {activated_ids}")

        # Phase 2: Fetch all candidate trips (read-only)
        with db.engine.connect() as conn:
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

        # Phase 3: Process each trip in its own isolated transaction
        for trip in overdue_trips:
            try:
                await _process_overdue_trip(trip, now)
            except Exception as e:
                log.error(f"[Scheduler] Error processing trip {trip.id}: {e}", exc_info=True)

    except Exception as e:
        log.error(f"Error checking overdue trips: {e}", exc_info=True)


async def _process_overdue_trip(trip, now: datetime):
    """Process a single overdue trip in its own transaction."""
    trip_id = trip.id
    log.info(f"[Scheduler] Processing trip {trip_id}: status={trip.status}, eta={trip.eta}, grace_min={trip.grace_min}")

    # Parse ETA first - needed for all paths
    eta_dt = parse_datetime_robust(trip.eta)
    if eta_dt is None:
        log.error(f"[Scheduler] Failed to parse ETA for trip {trip_id}: {trip.eta}")
        return

    # Check if we've already marked this trip as overdue
    with db.engine.connect() as conn:
        existing_overdue = conn.execute(
            sqlalchemy.text("""
                SELECT id FROM events
                WHERE trip_id = :trip_id AND what = 'overdue'
                LIMIT 1
            """),
            {"trip_id": trip_id}
        ).fetchone()

    # Step 1: Mark as overdue if not already marked
    if not existing_overdue:
        log.info(f"Marking trip {trip_id} as overdue")

        # Insert event and update status in isolated transaction
        with db.engine.begin() as conn:
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

        # Send Live Activity update (outside transaction)
        await send_live_activity_update(
            trip_id=trip_id,
            status="overdue",
            eta=eta_dt,
            last_checkin_time=None,
            is_overdue=False,  # Not past grace period yet, just past ETA
            checkin_count=0,
            grace_min=trip.grace_min or 15
        )
        log.info(f"[Scheduler] Sent Live Activity update for overdue trip {trip_id}")

        # Also send background push as fallback to wake app for state sync
        await send_background_push_to_user(
            trip.user_id,
            data={"sync": "trip_state_update", "trip_id": trip_id}
        )
        log.info(f"[Scheduler] Sent background push for Live Activity update, trip {trip_id}")
    else:
        log.info(f"[Scheduler] Trip {trip_id} already has overdue event")

    # Step 2: Check if grace period has expired (regardless of whether we just marked it)
    grace_expired_time = eta_dt + timedelta(minutes=trip.grace_min)
    log.info(f"[Scheduler] Trip {trip_id}: eta_dt={eta_dt}, grace_expired_time={grace_expired_time}, now={now}, grace_expired_check={now > grace_expired_time}")

    if now > grace_expired_time:
        # Check if we've already notified
        with db.engine.connect() as conn:
            existing_notify = conn.execute(
                sqlalchemy.text("""
                    SELECT id FROM events
                    WHERE trip_id = :trip_id AND what = 'notify'
                    LIMIT 1
                """),
                {"trip_id": trip_id}
            ).fetchone()

        if existing_notify:
            log.info(f"[Scheduler] Trip {trip_id}: Already has notify event, skipping")
            return

        log.info(f"[Scheduler] Trip {trip_id}: Grace period expired, no notify event yet - sending notifications")

        # Fetch contacts and user info in read-only query
        with db.engine.connect() as conn:
            # Check if this is a group trip
            is_group_trip_row = conn.execute(
                sqlalchemy.text("SELECT is_group_trip FROM trips WHERE id = :trip_id"),
                {"trip_id": trip_id}
            ).fetchone()
            is_group_trip = is_group_trip_row and is_group_trip_row.is_group_trip

            # Get trip owner's designated safety contacts (email contacts)
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
            contacts = list(contacts)

            # For group trips, also fetch contacts for all accepted participants
            participant_user_ids = []
            if is_group_trip:
                # Get all accepted participants (excluding owner, already handled above)
                participants = conn.execute(
                    sqlalchemy.text("""
                        SELECT user_id FROM trip_participants
                        WHERE trip_id = :trip_id AND status = 'accepted' AND role = 'participant'
                    """),
                    {"trip_id": trip_id}
                ).fetchall()

                participant_user_ids = [p.user_id for p in participants]
                log.info(f"[Scheduler] Trip {trip_id}: Group trip with {len(participant_user_ids)} participants")

                # Get each participant's contacts
                if participant_user_ids:
                    # Build dynamic IN clause for cross-database compatibility
                    placeholders = ", ".join([f":uid{i}" for i in range(len(participant_user_ids))])
                    params = {f"uid{i}": uid for i, uid in enumerate(participant_user_ids)}
                    participant_contacts = conn.execute(
                        sqlalchemy.text(f"""
                            SELECT DISTINCT c.name, c.email
                            FROM contacts c
                            WHERE c.owner_id IN ({placeholders}) AND c.email IS NOT NULL
                        """),
                        params
                    ).fetchall()

                    # Deduplicate by email (keep unique emails)
                    existing_emails = {c.email.lower() for c in contacts}
                    for pc in participant_contacts:
                        if pc.email.lower() not in existing_emails:
                            contacts.append(pc)
                            existing_emails.add(pc.email.lower())

                    log.info(f"[Scheduler] Trip {trip_id}: Added {len(participant_contacts)} contacts from participants (total unique: {len(contacts)})")

            user = conn.execute(
                sqlalchemy.text("SELECT first_name, last_name FROM users WHERE id = :user_id"),
                {"user_id": trip.user_id}
            ).fetchone()

            # Get friend safety contacts for the trip
            friend_contacts = conn.execute(
                sqlalchemy.text("""
                    SELECT tsc.friend_user_id
                    FROM trip_safety_contacts tsc
                    WHERE tsc.trip_id = :trip_id
                    AND tsc.friend_user_id IS NOT NULL
                """),
                {"trip_id": trip_id}
            ).fetchall()
            friend_contacts = list(friend_contacts)

            # For group trips, also notify all participants as friend contacts
            # (they should know the group is overdue)
            if is_group_trip and participant_user_ids:
                existing_friend_ids = {f.friend_user_id for f in friend_contacts}
                ParticipantAsFriend = namedtuple('ParticipantAsFriend', ['friend_user_id'])
                for participant_id in participant_user_ids:
                    if participant_id not in existing_friend_ids:
                        friend_contacts.append(ParticipantAsFriend(participant_id))
                        existing_friend_ids.add(participant_id)

                log.info(f"[Scheduler] Trip {trip_id}: Total friend contacts (including participants): {len(friend_contacts)}")

        log.info(f"[Scheduler] Trip {trip_id}: Found {len(contacts)} contacts with email")

        user_name = f"{user.first_name} {user.last_name}".strip() if user else "Someone"
        if not user_name:
            user_name = "A Homebound user"

        # Send notifications (async, outside transaction)
        if contacts:
            log.info(f"[Scheduler] Sending overdue notifications for trip {trip_id} to {len(contacts)} contacts")
            user_timezone = trip.timezone if hasattr(trip, 'timezone') else None
            start_location = trip.start_location_text if trip.has_separate_locations else None
            await send_overdue_notifications(trip, list(contacts), user_name, user_timezone, start_location)
            log.info(f"[Scheduler] Overdue notifications sent for trip {trip_id}")

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

        # Update database in isolated transaction
        if not contacts and not friend_contacts:
            log.warning(f"[Scheduler] Trip {trip_id}: No contacts (email or friend) found, skipping notification")
        else:
            with db.engine.begin() as conn:
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

        # Update trip status in separate transaction
        with db.engine.begin() as conn:
            conn.execute(
                sqlalchemy.text("""
                    UPDATE trips SET status = 'overdue_notified'
                    WHERE id = :trip_id
                """),
                {"trip_id": trip_id}
            )
        log.info(f"[Scheduler] Trip {trip_id}: Status updated to overdue_notified")
    else:
        log.info(f"[Scheduler] Trip {trip_id}: Grace period not yet expired")


async def check_push_notifications():
    """Check for and send push notifications to users.

    Uses FOR UPDATE SKIP LOCKED to avoid lock contention with other scheduler jobs.
    Each notification type is processed in its own transaction.
    """
    try:
        now = datetime.utcnow()

        # 1. Trip Starting Soon - SELECT and UPDATE in same transaction with SKIP LOCKED
        with db.engine.begin() as conn:
            starting_soon = conn.execute(
                sqlalchemy.text("""
                    SELECT id, user_id, title, start
                    FROM trips
                    WHERE status = 'planned'
                    AND notified_starting_soon = false
                    AND start > :now
                    AND start <= :soon
                    FOR UPDATE SKIP LOCKED
                """),
                {"now": now, "soon": now + timedelta(minutes=STARTING_SOON_MINUTES)}
            ).fetchall()

            for trip in starting_soon:
                try:
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
                except Exception as e:
                    log.error(f"[Push] Error sending 'starting soon' for trip {trip.id}: {e}")

        # 2. Trip Started
        with db.engine.begin() as conn:
            just_started = conn.execute(
                sqlalchemy.text("""
                    SELECT id, user_id, title
                    FROM trips
                    WHERE status = 'active'
                    AND notified_trip_started = false
                    FOR UPDATE SKIP LOCKED
                """)
            ).fetchall()

            for trip in just_started:
                try:
                    # Send visible notification
                    await send_push_to_user(
                        trip.user_id,
                        "Trip Started",
                        f"Your trip '{trip.title}' has started. Stay safe!",
                        data={"sync": "start_live_activity", "trip_id": trip.id},
                        notification_type="trip_reminder"
                    )
                    # Send background push to wake app and start Live Activity
                    # Uses apns-push-type: background with content-available: 1
                    await send_background_push_to_user(
                        trip.user_id,
                        data={"sync": "start_live_activity", "trip_id": trip.id}
                    )
                    conn.execute(
                        sqlalchemy.text("UPDATE trips SET notified_trip_started = true WHERE id = :id"),
                        {"id": trip.id}
                    )
                    log.info(f"[Push] Sent 'trip started' notification for trip {trip.id}")
                except Exception as e:
                    log.error(f"[Push] Error sending 'trip started' for trip {trip.id}: {e}")

        # 3. Approaching ETA
        with db.engine.begin() as conn:
            approaching_eta = conn.execute(
                sqlalchemy.text("""
                    SELECT id, user_id, title, eta, checkout_token
                    FROM trips
                    WHERE status = 'active'
                    AND notified_approaching_eta = false
                    AND eta > :now
                    AND eta <= :soon
                    FOR UPDATE SKIP LOCKED
                """),
                {"now": now, "soon": now + timedelta(minutes=APPROACHING_ETA_MINUTES)}
            ).fetchall()

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
                    conn.execute(
                        sqlalchemy.text("UPDATE trips SET notified_approaching_eta = true WHERE id = :id"),
                        {"id": trip.id}
                    )
                    log.info(f"[Push] Sent 'approaching ETA' notification for trip {trip.id}")
                except Exception as e:
                    log.error(f"[Push] Error sending 'approaching ETA' for trip {trip.id}: {e}")

        # 4. ETA Reached
        with db.engine.begin() as conn:
            eta_reached = conn.execute(
                sqlalchemy.text("""
                    SELECT id, user_id, title, eta, grace_min, checkout_token
                    FROM trips
                    WHERE status IN ('active', 'overdue')
                    AND notified_eta_reached = false
                    AND eta <= :now
                    FOR UPDATE SKIP LOCKED
                """),
                {"now": now}
            ).fetchall()

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
                    conn.execute(
                        sqlalchemy.text("UPDATE trips SET notified_eta_reached = true WHERE id = :id"),
                        {"id": trip.id}
                    )
                    log.info(f"[Push] Sent 'ETA reached' notification for trip {trip.id}")
                except Exception as e:
                    log.error(f"[Push] Error sending 'ETA reached' for trip {trip.id}: {e}")

        # 5. Check-in Reminders
        with db.engine.begin() as conn:
            need_checkin_reminder = conn.execute(
                sqlalchemy.text("""
                    SELECT id, user_id, title, last_checkin_reminder,
                           COALESCE(checkin_interval_min, :default_interval) as interval_min,
                           notify_start_hour, notify_end_hour, timezone,
                           checkin_token, checkout_token
                    FROM trips
                    WHERE status = 'active'
                    FOR UPDATE SKIP LOCKED
                """),
                {"default_interval": DEFAULT_CHECKIN_REMINDER_INTERVAL}
            ).fetchall()

            for trip in need_checkin_reminder:
                try:
                    interval_min = trip.interval_min
                    cutoff = now - timedelta(minutes=interval_min)

                    # Parse last_checkin_reminder (may be string from DB)
                    last_reminder = parse_datetime_robust(trip.last_checkin_reminder)
                    if last_reminder is not None and last_reminder > cutoff:
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

                    if last_reminder is None:
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
                        conn.execute(
                            sqlalchemy.text("UPDATE trips SET last_checkin_reminder = :now WHERE id = :id"),
                            {"now": now, "id": trip.id}
                        )
                        log.info(f"[Push] Sent check-in reminder for trip {trip.id}")
                except Exception as e:
                    log.error(f"[Push] Error sending check-in reminder for trip {trip.id}: {e}")

        # 6. Grace Period Warnings (only for 'overdue' status - 'overdue_notified' means contacts were already alerted)
        with db.engine.begin() as conn:
            in_grace_period = conn.execute(
                sqlalchemy.text("""
                    SELECT id, user_id, title, eta, grace_min, last_grace_warning, checkout_token, status
                    FROM trips
                    WHERE status = 'overdue'
                    AND (last_grace_warning IS NULL OR last_grace_warning <= :cutoff)
                    FOR UPDATE SKIP LOCKED
                """),
                {"cutoff": now - timedelta(minutes=GRACE_WARNING_INTERVAL)}
            ).fetchall()

            for trip in in_grace_period:
                try:
                    eta_dt = parse_datetime_robust(trip.eta)
                    if eta_dt is None:
                        log.warning(f"[Push] Failed to parse ETA for trip {trip.id}, skipping grace warning")
                        continue

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
            # Find active trips at or past ETA that haven't been notified yet
            # This catches ANY trip past ETA regardless of when it passed
            # (previously used a 15-second window which caused 30s+ delays)
            approaching_eta = conn.execute(
                sqlalchemy.text("""
                    SELECT id, user_id, eta, grace_min, status, last_checkin
                    FROM trips
                    WHERE status = 'active'
                    AND notified_eta_transition = false
                    AND eta <= :now
                """),
                {"now": now}
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
                eta_dt = parse_datetime_robust(trip.eta)
                if eta_dt is None:
                    log.warning(f"[LiveActivity] Failed to parse ETA for trip {trip.id}, skipping ETA transition")
                    continue

                # Parse last_checkin if present
                last_checkin_dt = parse_datetime_robust(trip.last_checkin)

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
                    status="overdue",  # Triggers grace countdown in iOS (isPastETA=true)
                    eta=eta_dt,
                    last_checkin_time=last_checkin_dt,
                    is_overdue=False,  # ETA warning, not yet past grace period
                    checkin_count=checkin_count,
                    grace_min=trip.grace_min or 15
                )

                # Also send background push as fallback for older devices
                await send_background_push_to_user(
                    trip.user_id,
                    data={
                        "sync": "live_activity_eta_warning",
                        "trip_id": trip.id,
                        "transition": "eta_warning"
                    }
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
                eta_dt = parse_datetime_robust(trip.eta)
                if eta_dt is None:
                    log.warning(f"[LiveActivity] Failed to parse ETA for trip {trip.id}, skipping grace transition")
                    continue

                grace_end = eta_dt + timedelta(minutes=trip.grace_min)
                seconds_until_grace_end = (grace_end - now).total_seconds()

                # Send push if grace period is ending soon or has ended
                # Removes lower bound to catch trips where grace ended more than 30s ago
                # (previously -30 < x <= 30 which missed trips past the window)
                if seconds_until_grace_end <= 30:
                    # Parse last_checkin if present
                    last_checkin_dt = parse_datetime_robust(trip.last_checkin)

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
                        checkin_count=checkin_count,
                        grace_min=trip.grace_min or 15
                    )

                    # Also send background push as fallback
                    await send_background_push_to_user(
                        trip.user_id,
                        data={
                            "sync": "live_activity_overdue",
                            "trip_id": trip.id,
                            "transition": "overdue"
                        }
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


async def clean_stale_live_activity_tokens():
    """Clean up stale Live Activity tokens that haven't been updated in 30 days.

    This prevents accumulation of orphaned tokens from:
    - Deleted/uninstalled apps
    - Abandoned trips
    - Failed unregistration attempts
    """
    try:
        cutoff = datetime.utcnow() - timedelta(days=30)

        with db.engine.begin() as conn:
            result = conn.execute(
                sqlalchemy.text("""
                    DELETE FROM live_activity_tokens
                    WHERE updated_at < :cutoff
                """),
                {"cutoff": cutoff}
            )
            deleted = result.rowcount

            if deleted > 0:
                log.info(f"[Scheduler] Cleaned {deleted} stale Live Activity tokens (older than 30 days)")

    except Exception as e:
        log.error(f"Error cleaning stale Live Activity tokens: {e}", exc_info=True)


async def clean_old_live_locations():
    """Clean up old live location records older than 7 days.

    The live_locations table can grow indefinitely from active trips sharing
    their location. This job prevents unbounded table growth by removing
    stale location data that's no longer useful for monitoring.
    """
    try:
        cutoff = datetime.utcnow() - timedelta(days=7)

        with db.engine.begin() as conn:
            result = conn.execute(
                sqlalchemy.text("""
                    DELETE FROM live_locations
                    WHERE timestamp < :cutoff
                """),
                {"cutoff": cutoff}
            )
            deleted = result.rowcount

            if deleted > 0:
                log.info(f"[Scheduler] Cleaned {deleted} old live location records (older than 7 days)")

    except Exception as e:
        log.error(f"Error cleaning old live locations: {e}", exc_info=True)


def init_scheduler() -> AsyncIOScheduler:
    """Initialize and configure the scheduler."""
    global scheduler

    if scheduler is not None:
        return scheduler

    scheduler = AsyncIOScheduler(timezone=settings.TIMEZONE)

    # Stagger job start times to reduce lock contention
    now = datetime.utcnow()

    # Check for overdue trips every 30 seconds - starts immediately
    scheduler.add_job(
        check_overdue_trips,
        IntervalTrigger(seconds=30),
        id="check_overdue",
        name="Check for overdue trips",
        replace_existing=True,
        max_instances=1,
        next_run_time=now,
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

    # Clean stale Live Activity tokens daily (tokens older than 30 days)
    scheduler.add_job(
        clean_stale_live_activity_tokens,
        IntervalTrigger(hours=24),
        id="clean_live_activity_tokens",
        name="Clean stale Live Activity tokens",
        replace_existing=True,
        max_instances=1,
    )

    # Clean old live location records daily (older than 7 days)
    scheduler.add_job(
        clean_old_live_locations,
        IntervalTrigger(hours=24),
        id="clean_live_locations",
        name="Clean old live location records",
        replace_existing=True,
        max_instances=1,
    )

    # Check for push notifications every 60 seconds - stagger by 15s
    scheduler.add_job(
        check_push_notifications,
        IntervalTrigger(seconds=60),
        id="check_push_notifications",
        name="Check for push notifications",
        replace_existing=True,
        max_instances=1,
        next_run_time=now + timedelta(seconds=15),
    )

    # Check for Live Activity countdown transitions every 15 seconds
    scheduler.add_job(
        check_live_activity_transitions,
        IntervalTrigger(seconds=15),
        id="check_live_activity_transitions",
        name="Check Live Activity countdown transitions",
        replace_existing=True,
        max_instances=1,
        next_run_time=now + timedelta(seconds=5),  # Start sooner
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
