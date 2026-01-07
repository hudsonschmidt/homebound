from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime
from typing import Any

import pytz
import sqlalchemy

from .. import database as db
from ..config import get_settings
from ..messaging.resend_backend import html_to_text

settings = get_settings()
log = logging.getLogger(__name__)


# ==================== Friend Push Notifications ====================
# Friends receive push notifications instead of email

async def send_friend_trip_created_push(
    friend_user_id: int,
    user_name: str,
    trip_title: str
):
    """Send push notification to a friend when they're added as a safety contact."""
    log.info(f"[Notifications] send_friend_trip_created_push called: friend_user_id={friend_user_id}, user_name={user_name}, trip_title={trip_title}")
    title = "Safety Contact Added"
    body = f"{user_name} added you as a safety contact for their trip '{trip_title}'"

    await send_push_to_user(
        friend_user_id,
        title,
        body,
        notification_type="general"
    )
    log.info(f"[Notifications] Completed send_friend_trip_created_push to user {friend_user_id}")


async def send_friend_trip_starting_push(
    friend_user_id: int,
    user_name: str,
    trip_title: str
):
    """Send push notification to a friend when the trip they're monitoring starts."""
    title = "Trip Started"
    body = f"{user_name}'s trip '{trip_title}' has started. You'll be notified if they need help."

    await send_push_to_user(
        friend_user_id,
        title,
        body,
        notification_type="general"
    )
    log.info(f"Sent friend trip starting push to user {friend_user_id}")


async def send_friend_overdue_push(
    friend_user_id: int,
    user_name: str,
    trip_title: str,
    trip_id: int,
    last_location_name: str | None = None,
    last_location_coords: tuple[float, float] | None = None,
    destination_text: str | None = None,
    time_overdue_minutes: int = 0
):
    """Send URGENT push notification to a friend when a trip they're monitoring is overdue.

    This is a high-priority notification that should always be delivered.
    Enhanced: Now includes location information for better friend visibility.
    """
    title = f"🚨 URGENT: {user_name} is overdue!"

    # Build rich body with location details
    body_parts = [f"{user_name} hasn't checked in from '{trip_title}'"]
    if time_overdue_minutes > 0:
        body_parts.append(f"({time_overdue_minutes} min overdue)")
    if last_location_name:
        body_parts.append(f"Last seen: {last_location_name}")
    if destination_text:
        body_parts.append(f"Destination: {destination_text}")
    body_parts.append("They may need help!")

    body = ". ".join(body_parts)

    # Include coordinates in data for map deep linking
    data: dict = {"trip_id": trip_id, "is_overdue_alert": True}
    if last_location_coords:
        data["last_known_lat"] = last_location_coords[0]
        data["last_known_lon"] = last_location_coords[1]

    await send_push_to_user(
        friend_user_id,
        title,
        body,
        data=data,
        notification_type="emergency"  # Emergency notifications always send
    )
    log.info(f"Sent friend OVERDUE push to user {friend_user_id} for trip {trip_id}")


async def send_friend_trip_completed_push(
    friend_user_id: int,
    user_name: str,
    trip_title: str
):
    """Send push notification to a friend when the trip owner is safe."""
    title = f"✅ {user_name} is safe!"
    body = f"{user_name} completed their trip '{trip_title}' safely."

    await send_push_to_user(
        friend_user_id,
        title,
        body,
        notification_type="general"
    )
    log.info(f"Sent friend trip completed push to user {friend_user_id}")


async def send_friend_overdue_resolved_push(
    friend_user_id: int,
    user_name: str,
    trip_title: str
):
    """Send push notification to a friend when an overdue situation is resolved."""
    title = f"✅ {user_name} is safe!"
    body = f"Good news! {user_name} has checked in from '{trip_title}'."

    await send_push_to_user(
        friend_user_id,
        title,
        body,
        notification_type="emergency"  # Use emergency to ensure it's delivered
    )
    log.info(f"Sent friend overdue resolved push to user {friend_user_id}")


async def send_friend_checkin_push(
    friend_user_id: int,
    user_name: str,
    trip_title: str,
    location_name: str | None = None,
    coordinates: tuple[float, float] | None = None
):
    """Send push notification to a friend when the trip owner checks in.

    Enhanced: Now includes location information for better friend visibility.
    """
    title = "Check-in Update"

    # Include location in body if available
    if location_name:
        body = f"{user_name} checked in at {location_name} on '{trip_title}'"
    else:
        body = f"{user_name} checked in on their trip '{trip_title}'"

    # Include coordinates in data for map deep linking
    data: dict = {}
    if coordinates:
        data["checkin_lat"] = coordinates[0]
        data["checkin_lon"] = coordinates[1]

    await send_push_to_user(
        friend_user_id,
        title,
        body,
        data=data if data else None,
        notification_type="general"
    )
    log.info(f"Sent friend check-in push to user {friend_user_id}")


async def send_friend_trip_extended_push(
    friend_user_id: int,
    user_name: str,
    trip_title: str,
    extended_by_minutes: int
):
    """Send push notification to a friend when the trip they're monitoring is extended."""
    title = "Trip Extended"
    body = f"{user_name} extended their trip '{trip_title}' by {extended_by_minutes} minutes"

    await send_push_to_user(
        friend_user_id,
        title,
        body,
        notification_type="general"
    )
    log.info(f"Sent friend trip extended push to user {friend_user_id}")


async def send_update_request_push(
    owner_user_id: int,
    requester_name: str,
    trip_title: str,
    trip_id: int
):
    """Send push notification to trip owner when a friend requests an update.

    This is sent when a friend who is monitoring the trip wants to know if the owner is okay.
    """
    title = "Check-in Requested"
    body = f"{requester_name} is checking on you for '{trip_title}'. Tap to check in."

    await send_push_to_user(
        owner_user_id,
        title,
        body,
        data={"trip_id": trip_id, "action": "checkin_requested"},
        notification_type="checkin",
        category="CHECKIN_REMINDER"  # Actionable notification
    )
    log.info(f"Sent update request push to user {owner_user_id} from friend for trip {trip_id}")


async def send_friend_request_accepted_push(
    inviter_user_id: int,
    accepter_name: str
):
    """Send push notification to the inviter when someone accepts their friend request."""
    title = "Friend Request Accepted"
    body = f"{accepter_name} is now your friend on Homebound!"

    await send_push_to_user(
        inviter_user_id,
        title,
        body,
        notification_type="general"
    )
    log.info(f"Sent friend request accepted push to user {inviter_user_id}")


# ==================== Group Trip Invitation Push Notifications ====================

async def send_trip_invitation_push(
    invited_user_id: int,
    inviter_name: str,
    trip_title: str,
    trip_id: int
):
    """Send push notification when a user is invited to a group trip."""
    title = "Trip Invitation"
    body = f"{inviter_name} invited you to join '{trip_title}'"

    await send_push_to_user(
        invited_user_id,
        title,
        body,
        data={"trip_id": trip_id, "action": "trip_invitation"},
        notification_type="general"
    )
    log.info(f"Sent trip invitation push to user {invited_user_id} for trip {trip_id}")


async def send_trip_invitation_accepted_push(
    owner_user_id: int,
    accepter_name: str,
    trip_title: str,
    trip_id: int
):
    """Send push notification to trip owner when someone accepts their invitation."""
    title = "Invitation Accepted"
    body = f"{accepter_name} joined your trip '{trip_title}'"

    await send_push_to_user(
        owner_user_id,
        title,
        body,
        data={"trip_id": trip_id},
        notification_type="general"
    )
    log.info(f"Sent invitation accepted push to trip owner {owner_user_id} for trip {trip_id}")


async def send_trip_invitation_declined_push(
    owner_user_id: int,
    decliner_name: str,
    trip_title: str,
    trip_id: int
):
    """Send push notification to trip owner when someone declines their invitation."""
    title = "Invitation Declined"
    body = f"{decliner_name} declined to join '{trip_title}'"

    await send_push_to_user(
        owner_user_id,
        title,
        body,
        data={"trip_id": trip_id},
        notification_type="general"
    )
    log.info(f"Sent invitation declined push to trip owner {owner_user_id} for trip {trip_id}")


async def send_participant_left_push(
    owner_user_id: int,
    leaver_name: str,
    trip_title: str,
    trip_id: int
):
    """Send push notification to trip owner when a participant leaves the trip."""
    title = "Participant Left"
    body = f"{leaver_name} left '{trip_title}'"

    await send_push_to_user(
        owner_user_id,
        title,
        body,
        data={"trip_id": trip_id},
        notification_type="general"
    )
    log.info(f"Sent participant left push to trip owner {owner_user_id} for trip {trip_id}")


async def send_checkout_vote_push(
    participant_user_id: int,
    voter_name: str,
    trip_title: str,
    trip_id: int,
    votes_count: int,
    votes_needed: int
):
    """Send push notification to participants when someone votes to checkout."""
    title = "Checkout Vote"
    body = f"{voter_name} voted to end '{trip_title}' ({votes_count}/{votes_needed} votes)"

    await send_push_to_user(
        participant_user_id,
        title,
        body,
        data={"trip_id": trip_id, "action": "checkout_vote"},
        notification_type="general"
    )
    log.info(f"Sent checkout vote push to participant {participant_user_id} for trip {trip_id}")


async def send_trip_completed_by_vote_push(
    participant_user_id: int,
    trip_title: str,
    trip_id: int
):
    """Send push notification to participants when trip is completed by vote."""
    title = "Trip Completed"
    body = f"'{trip_title}' has ended - everyone voted to complete!"

    await send_push_to_user(
        participant_user_id,
        title,
        body,
        data={"trip_id": trip_id},
        notification_type="general"
    )
    log.info(f"Sent trip completed by vote push to participant {participant_user_id} for trip {trip_id}")


async def send_participant_checkin_push(
    participant_user_id: int,
    checker_name: str,
    trip_title: str,
    trip_id: int,
    location_name: str | None = None,
    coordinates: tuple[float, float] | None = None
):
    """Send push notification to other participants when someone checks in.

    This notifies other group trip participants when a fellow participant checks in,
    improving group situational awareness.
    """
    title = "Teammate Checked In"

    # Include location in body if available
    if location_name:
        body = f"{checker_name} checked in at {location_name}"
    else:
        body = f"{checker_name} checked in on '{trip_title}'"

    # Include coordinates in data for map deep linking
    data: dict = {"trip_id": trip_id, "action": "participant_checkin"}
    if coordinates:
        data["checkin_lat"] = coordinates[0]
        data["checkin_lon"] = coordinates[1]

    await send_push_to_user(
        participant_user_id,
        title,
        body,
        data=data,
        notification_type="general"
    )
    log.info(f"Sent participant check-in push to user {participant_user_id} for trip {trip_id}")


async def send_trip_completed_push(
    participant_user_id: int,
    completer_name: str,
    trip_title: str,
    trip_id: int
):
    """Send push notification to participants when trip is completed manually.

    This notifies group trip participants when the trip owner or another participant
    completes the trip (not via vote).
    """
    title = "Trip Completed"
    body = f"{completer_name} completed '{trip_title}'"

    await send_push_to_user(
        participant_user_id,
        title,
        body,
        data={"trip_id": trip_id},
        notification_type="general"
    )
    log.info(f"Sent trip completed push to participant {participant_user_id} for trip {trip_id}")


async def send_trip_cancelled_push(
    participant_user_id: int,
    owner_name: str,
    trip_title: str,
    trip_id: int
):
    """Send push notification to participants when a group trip is cancelled by the owner.

    This notifies group trip participants that the trip has been cancelled
    and they no longer need to check in.
    """
    title = "Trip Cancelled"
    body = f"'{trip_title}' has been cancelled by {owner_name}"

    await send_push_to_user(
        participant_user_id,
        title,
        body,
        data={"trip_id": trip_id, "action": "trip_cancelled"},
        notification_type="general"
    )
    log.info(f"Sent trip cancelled push to participant {participant_user_id} for trip {trip_id}")


async def send_friend_trip_update_silent_push(
    friend_user_id: int,
    trip_id: int
):
    """Send silent push to trigger friend data refresh.

    Used when live location updates or minor trip changes occur
    that don't warrant a visible notification. The app will wake
    in the background and refresh friend trip data.
    """
    await send_background_push_to_user(
        friend_user_id,
        data={"sync": "friend_trip_update", "trip_id": str(trip_id)}
    )
    log.info(f"Sent friend trip update silent push to user {friend_user_id} for trip {trip_id}")


async def send_data_refresh_push(
    user_id: int,
    sync_type: str,
    trip_id: int | None = None
):
    """Send silent push to trigger app data refresh.

    Used when data changes that the user needs to see, such as:
    - Friend request accepted
    - Trip invitation accepted/declined
    - Participant left trip
    - Checkout vote cast
    - Trip completed by vote

    Args:
        user_id: The user to refresh data for
        sync_type: Type of sync needed (e.g., "friends", "trip", "trip_invitations")
        trip_id: Optional trip ID if related to a specific trip
    """
    data = {"sync": sync_type}
    if trip_id:
        data["trip_id"] = str(trip_id)

    await send_background_push_to_user(user_id, data=data)
    log.info(f"Sent data refresh push to user {user_id}: sync={sync_type}, trip_id={trip_id}")


def log_notification(
    user_id: int,
    notification_type: str,
    title: str,
    body: str | None,
    status: str,
    device_token: str | None = None,
    error_message: str | None = None
):
    """Log a notification attempt to the database for delivery tracking.

    Args:
        user_id: The user ID the notification is for
        notification_type: 'push' or 'email'
        title: Notification title or email subject
        body: Notification body
        status: 'sent', 'failed', or 'pending'
        device_token: Device token for push notifications (optional)
        error_message: Error details if status is 'failed' (optional)
    """
    try:
        with db.engine.begin() as conn:
            conn.execute(
                sqlalchemy.text("""
                    INSERT INTO notification_logs
                    (user_id, notification_type, title, body, status, device_token, error_message, created_at)
                    VALUES (:user_id, :notification_type, :title, :body, :status, :device_token, :error_message, :created_at)
                """),
                {
                    "user_id": user_id,
                    "notification_type": notification_type,
                    "title": title,
                    "body": body,
                    "status": status,
                    "device_token": device_token,
                    "error_message": error_message,
                    "created_at": datetime.utcnow()
                }
            )
    except Exception as e:
        # Don't let logging failures break the notification flow
        log.error(f"Failed to log notification: {e}")

def parse_datetime(dt_value: Any) -> datetime | None:
    """Parse datetime from string or return as-is."""
    if dt_value is None:
        return None
    if isinstance(dt_value, str):
        return datetime.fromisoformat(dt_value.replace(' ', 'T').replace('Z', '+00:00'))
    return dt_value


def format_datetime_with_tz(dt: datetime | None, user_timezone: str | None) -> tuple[str, str]:
    """Convert datetime to user's timezone and format it.

    Returns: (formatted_string, timezone_display)
    """
    if dt is None:
        return "Not specified", ""

    timezone_display = ""
    if user_timezone:
        try:
            tz = pytz.timezone(user_timezone)
            if dt.tzinfo is None:
                dt = pytz.utc.localize(dt)
            dt = dt.astimezone(tz)
            timezone_display = f" {dt.strftime('%Z')}"
        except Exception as e:
            log.warning(f"Failed to convert to timezone {user_timezone}: {e}")

    return dt.strftime('%B %d, %Y at %I:%M %p') + timezone_display, timezone_display


def get_current_time_formatted(user_timezone: str | None) -> tuple[str, str]:
    """Get current time formatted in user's timezone.

    Returns: (formatted_string, timezone_display)
    """
    now = datetime.utcnow()
    return format_datetime_with_tz(now, user_timezone)


def get_attr(obj: Any, key: str, default: Any = None) -> Any:
    """Get attribute from dict or Row object."""
    if hasattr(obj, 'get'):
        return obj.get(key, default)
    return getattr(obj, key, default)


def should_display_location(location_text: str | None) -> bool:
    """Check if location should be displayed in emails.

    Returns False for:
    - None or empty string
    - "Current Location"
    - Coordinate strings (e.g., "37.7749°N, 122.4194°W")
    """
    if not location_text:
        return False

    location_text = location_text.strip()

    # Skip "Current Location"
    if location_text.lower() == "current location":
        return False

    # Skip coordinate patterns (e.g., "37.7749°N, 122.4194°W" or "37.7749, -122.4194")
    coord_pattern = r'^-?\d+\.?\d*°?[NSEW]?,?\s*-?\d+\.?\d*°?[NSEW]?$'
    if re.match(coord_pattern, location_text, re.IGNORECASE):
        return False

    return True


async def send_email(
    email: str,
    subject: str,
    body: str,
    html_body: str | None = None,
    from_email: str | None = None,
    high_priority: bool = False
):
    """Send email notification.

    Args:
        email: Recipient email address
        subject: Email subject
        body: Plain text body
        html_body: Optional HTML body
        from_email: Optional from address (defaults to RESEND_FROM_EMAIL)
        high_priority: If True, mark email as high priority/urgent
    """
    if settings.EMAIL_BACKEND == "resend":
        from ..messaging.resend_backend import send_resend_email
        success = await send_resend_email(
            to_email=email,
            subject=subject,
            text_body=body,
            html_body=html_body,
            from_email=from_email,
            high_priority=high_priority
        )
        if not success:
            log.error(f"Failed to send email to {email}")
    elif settings.EMAIL_BACKEND == "console":
        priority_note = " [HIGH PRIORITY]" if high_priority else ""
        log.info(f"[CONSOLE EMAIL]{priority_note} To: {email}\nFrom: {from_email or 'default'}\nSubject: {subject}\n{body}")
    else:
        log.warning(f"Unknown email backend: {settings.EMAIL_BACKEND}")


async def send_push_to_user(
    user_id: int,
    title: str,
    body: str,
    data: dict | None = None,
    notification_type: str = "general",
    category: str | None = None
):
    """Send push notification to all user's devices with retry logic.

    Args:
        user_id: The user to send the notification to
        title: Notification title
        body: Notification body
        data: Optional data payload
        notification_type: Type of notification - "trip_reminder", "checkin", "emergency", or "general"
                          Emergency notifications always send; others respect user preferences.
        category: APNs category for actionable notifications (e.g., "CHECKIN_REMINDER")
    """
    import asyncio
    from ..messaging.apns import get_push_sender

    MAX_RETRIES = 3
    RETRY_DELAYS = [1, 2, 4]  # Exponential backoff: 1s, 2s, 4s

    # Check user preferences (emergency notifications always sent for safety)
    if notification_type != "emergency":
        with db.engine.begin() as conn:
            prefs = conn.execute(
                sqlalchemy.text(
                    "SELECT notify_trip_reminders, notify_checkin_alerts FROM users WHERE id = :uid"
                ),
                {"uid": user_id}
            ).fetchone()

            if prefs:
                if notification_type == "trip_reminder" and not prefs.notify_trip_reminders:
                    log.info(f"[APNS] Skipping trip reminder for user {user_id} - disabled by preference")
                    return
                if notification_type == "checkin" and not prefs.notify_checkin_alerts:
                    log.info(f"[APNS] Skipping check-in alert for user {user_id} - disabled by preference")
                    return

    if settings.PUSH_BACKEND == "dummy":
        log.info(f"[DUMMY PUSH] User: {user_id} - {title}: {body}")
        log_notification(user_id, "push", title, body, "sent", error_message="dummy backend")
        return

    if settings.PUSH_BACKEND != "apns":
        log.warning(f"Unknown push backend: {settings.PUSH_BACKEND}")
        return

    # Query user's iOS devices matching current environment (sandbox vs production)
    current_env = "sandbox" if settings.APNS_USE_SANDBOX else "production"
    with db.engine.begin() as conn:
        devices = conn.execute(
            sqlalchemy.text(
                "SELECT token, env FROM devices WHERE user_id = :uid AND platform = 'ios' AND env = :env"
            ),
            {"uid": user_id, "env": current_env}
        ).fetchall()

    if not devices:
        log.warning(f"[APNS] No iOS devices registered for user {user_id} in {current_env} environment - notification not sent: {title}")
        return

    # Send to each device with retry logic
    sender = get_push_sender()
    tokens_to_remove: list[str] = []

    for device in devices:
        success = False
        last_error = None

        for attempt in range(MAX_RETRIES):
            try:
                result = await sender.send(device.token, title, body, data, category)
                if result.ok:
                    log.info(f"[APNS] Sent to user {user_id}: {title}")
                    log_notification(user_id, "push", title, body, "sent", device_token=device.token)
                    success = True
                    break
                elif result.status == 410:
                    # 410 Gone = device unregistered, mark for removal (don't retry)
                    log.info(f"[APNS] Device unregistered for user {user_id}, will remove token")
                    tokens_to_remove.append(device.token)
                    log_notification(user_id, "push", title, body, "failed", device_token=device.token,
                                   error_message="Device unregistered (410)")
                    success = True  # Not a retry-able error
                    break
                elif result.status == 400 and result.detail in ("BadDeviceToken", "DeviceTokenNotForTopic", "Unregistered"):
                    # 400 BadDeviceToken/DeviceTokenNotForTopic/Unregistered = invalid token, mark for removal
                    log.info(f"[APNS] Bad device token for user {user_id} ({result.detail}), will remove")
                    tokens_to_remove.append(device.token)
                    log_notification(user_id, "push", title, body, "failed", device_token=device.token,
                                   error_message=f"{result.detail} (400)")
                    success = True  # Not a retry-able error
                    break
                else:
                    last_error = f"status={result.status} detail={result.detail}"
                    log.warning(f"[APNS] Failed for user {user_id} (attempt {attempt + 1}/{MAX_RETRIES}): {last_error}")

            except Exception as e:
                last_error = str(e)
                log.error(f"[APNS] Error sending to user {user_id} (attempt {attempt + 1}/{MAX_RETRIES}): {e}")

            # Retry with exponential backoff if not the last attempt
            if attempt < MAX_RETRIES - 1:
                delay = RETRY_DELAYS[attempt]
                log.info(f"[APNS] Retrying in {delay} seconds...")
                await asyncio.sleep(delay)

        # Log failure if all retries exhausted
        if not success and last_error:
            log_notification(user_id, "push", title, body, "failed", device_token=device.token,
                           error_message=f"All retries failed: {last_error}")

    # Remove unregistered device tokens
    if tokens_to_remove:
        with db.engine.begin() as conn:
            for token in tokens_to_remove:
                conn.execute(
                    sqlalchemy.text("DELETE FROM devices WHERE token = :token"),
                    {"token": token}
                )
            log.info(f"[APNS] Removed {len(tokens_to_remove)} unregistered device(s) for user {user_id}")


async def send_background_push_to_user(user_id: int, data: dict):
    """Send a background push notification that wakes the app.

    Uses content-available: 1 to wake the app in the background so it can
    perform tasks like starting a Live Activity.

    Args:
        user_id: The user to send the notification to
        data: Custom data payload to include (e.g., {"sync": "start_live_activity", "trip_id": 123})
    """
    import asyncio
    from ..messaging.apns import get_push_sender

    if settings.PUSH_BACKEND == "dummy":
        log.info(f"[DUMMY BACKGROUND PUSH] User: {user_id} - data={data}")
        return

    if settings.PUSH_BACKEND != "apns":
        log.warning(f"Unknown push backend: {settings.PUSH_BACKEND}")
        return

    # Query user's iOS devices matching current environment
    current_env = "sandbox" if settings.APNS_USE_SANDBOX else "production"
    with db.engine.begin() as conn:
        devices = conn.execute(
            sqlalchemy.text(
                "SELECT token, env FROM devices WHERE user_id = :uid AND platform = 'ios' AND env = :env"
            ),
            {"uid": user_id, "env": current_env}
        ).fetchall()

    if not devices:
        log.warning(f"[APNS] No iOS devices for user {user_id} - background push not sent")
        return

    sender = get_push_sender()

    for device in devices:
        try:
            if hasattr(sender, 'send_background'):
                result = await sender.send_background(device.token, data)
                if result.ok:
                    log.info(f"[APNS] Background push sent to user {user_id}: {data}")
                else:
                    log.warning(f"[APNS] Background push failed for user {user_id}: {result.detail}")
            else:
                log.warning(f"[APNS] Sender does not support background push")
        except Exception as e:
            log.error(f"[APNS] Error sending background push to user {user_id}: {e}")


# Live Activity Updates ------------------------------------------------------------------------
async def send_live_activity_update(
    trip_id: int,
    status: str,
    eta: datetime,
    last_checkin_time: datetime | None,
    is_overdue: bool,
    checkin_count: int,
    event: str = "update",
    grace_min: int = 15
):
    """Send a Live Activity push update to the iOS lock screen widget.

    This sends a push notification that directly updates the Live Activity UI
    without needing to wake the app.

    Includes retry logic for token lookup since iOS may take a moment to register
    the Live Activity push token after the activity starts.

    Args:
        trip_id: The trip ID
        status: Trip status ("active", "overdue", "overdue_notified")
        eta: Expected arrival time
        last_checkin_time: Last check-in timestamp (optional)
        is_overdue: Whether trip is past ETA + grace period
        checkin_count: Number of check-ins performed
        event: "update" to update, "end" to dismiss the activity
        grace_min: Grace period in minutes (default 15)
    """
    import asyncio
    import time
    from ..messaging.apns import get_push_sender

    log.info(f"[LiveActivity] Sending update: trip_id={trip_id}, status={status}, eta={eta}, is_overdue={is_overdue}")

    # Retry logic for token lookup - iOS may take several seconds to start the Activity,
    # receive the push token from ActivityKit, and register it with the backend.
    # Increased from 3 retries (6s total) to 5 retries (15s total) for reliability.
    MAX_TOKEN_RETRIES = 5
    TOKEN_RETRY_DELAY = 3  # seconds

    token_row = None
    for attempt in range(MAX_TOKEN_RETRIES):
        with db.engine.connect() as conn:
            token_row = conn.execute(
                sqlalchemy.text("""
                    SELECT token, env FROM live_activity_tokens
                    WHERE trip_id = :trip_id
                """),
                {"trip_id": trip_id}
            ).fetchone()

            # On first attempt, log all tokens in database for debugging
            if attempt == 0:
                all_tokens = conn.execute(
                    sqlalchemy.text("SELECT trip_id, env FROM live_activity_tokens ORDER BY trip_id")
                ).fetchall()
                if all_tokens:
                    token_list = ", ".join([f"trip_{t.trip_id}({t.env})" for t in all_tokens])
                    log.info(f"[LiveActivity] Tokens in DB: [{token_list}]")
                else:
                    log.info("[LiveActivity] No tokens in database")

        if token_row:
            log.info(f"[LiveActivity] Found token for trip {trip_id}: env={token_row.env}, prefix={token_row.token[:20]}...")
            break

        if attempt < MAX_TOKEN_RETRIES - 1:
            log.info(f"[LiveActivity] No token for trip {trip_id} (attempt {attempt + 1}/{MAX_TOKEN_RETRIES}), retrying in {TOKEN_RETRY_DELAY}s...")
            await asyncio.sleep(TOKEN_RETRY_DELAY)

    if not token_row:
        log.warning(f"[LiveActivity] No token found for trip {trip_id} after {MAX_TOKEN_RETRIES} attempts, skipping push update")
        return

    # Check environment matches
    current_env = "development" if settings.APNS_USE_SANDBOX else "production"
    if token_row.env != current_env:
        log.warning(
            f"[LiveActivity] Environment mismatch for trip {trip_id}: "
            f"token was registered in '{token_row.env}' but server is in '{current_env}' mode. "
            "Cleaning up stale token - device will need to re-register."
        )
        # Auto-cleanup the mismatched token instead of leaving it stale
        with db.engine.begin() as conn:
            conn.execute(
                sqlalchemy.text("DELETE FROM live_activity_tokens WHERE trip_id = :trip_id"),
                {"trip_id": trip_id}
            )
        return

    # Build content-state matching iOS ContentState struct
    # CRITICAL: Keys must be camelCase to match Swift Codable
    # CRITICAL: Swift's default Codable Date strategy uses Apple's reference date
    # (Jan 1, 2001), NOT Unix epoch (Jan 1, 1970). Difference is 978307200 seconds.
    from datetime import timedelta
    APPLE_EPOCH_OFFSET = 978307200  # Seconds between 1970-01-01 and 2001-01-01

    # Calculate grace end time (ETA + grace minutes)
    grace_end = eta + timedelta(minutes=grace_min) if eta else None

    content_state = {
        "status": status,
        "eta": (eta.timestamp() - APPLE_EPOCH_OFFSET) if eta else None,
        "graceEnd": (grace_end.timestamp() - APPLE_EPOCH_OFFSET) if grace_end else None,
        "lastCheckinTime": (last_checkin_time.timestamp() - APPLE_EPOCH_OFFSET) if last_checkin_time else None,
        "isOverdue": is_overdue,
        "checkinCount": checkin_count
    }

    # Calculate stale date: ETA + grace period + 5 minute buffer
    # This tells iOS when the activity should be marked as stale if no updates received.
    # NOTE: stale-date uses Unix timestamp (seconds since 1970-01-01), NOT Apple epoch.
    # This is different from content-state dates which use Apple epoch for Swift Codable compatibility.
    # See: https://developer.apple.com/documentation/activitykit/updating-and-ending-your-live-activity-with-remote-push-notifications
    stale_date = None
    if eta:
        stale_dt = eta + timedelta(minutes=grace_min + 5)
        stale_date = int(stale_dt.timestamp())  # Unix timestamp (correct for stale-date)

    sender = get_push_sender()
    if hasattr(sender, 'send_live_activity_update'):
        # Retry logic for transient APNs errors
        MAX_PUSH_RETRIES = 3
        PUSH_RETRY_DELAYS = [1, 2, 4]  # Exponential backoff: 1s, 2s, 4s
        TERMINAL_ERRORS = ("ExpiredToken", "Unregistered", "BadDeviceToken", "DeviceTokenNotForTopic")

        result = None
        for attempt in range(MAX_PUSH_RETRIES):
            result = await sender.send_live_activity_update(
                live_activity_token=token_row.token,
                content_state=content_state,
                event=event,
                timestamp=int(time.time()),
                stale_date=stale_date,
                relevance_score=100  # Active trips are high priority
            )

            if result.ok:
                log.info(f"[LiveActivity] Update sent for trip {trip_id}: {status}")
                break

            # Terminal errors - don't retry, handle token invalidation
            if result.status == 410 or result.detail in TERMINAL_ERRORS:
                log.info(f"[LiveActivity] Removing invalid token for trip {trip_id} (error: {result.detail})")
                with db.engine.begin() as conn:
                    conn.execute(
                        sqlalchemy.text("DELETE FROM live_activity_tokens WHERE trip_id = :trip_id"),
                        {"trip_id": trip_id}
                    )
                break

            # Transient error - retry with backoff if not last attempt
            if attempt < MAX_PUSH_RETRIES - 1:
                delay = PUSH_RETRY_DELAYS[attempt]
                log.warning(f"[LiveActivity] Update failed for trip {trip_id} (attempt {attempt + 1}/{MAX_PUSH_RETRIES}): {result.detail}. Retrying in {delay}s...")
                await asyncio.sleep(delay)
            else:
                log.error(f"[LiveActivity] Update failed for trip {trip_id} after {MAX_PUSH_RETRIES} attempts: {result.detail}")
    else:
        log.info(f"[LiveActivity] Dummy push for trip {trip_id}: {content_state}")


# Magic Link --------------------------------------------------------------------------------
async def send_magic_link_email(email: str, code: str):
    """Send magic link code via email."""
    from ..messaging.resend_backend import create_magic_link_email_html

    subject = "Your Homebound Login Code"
    body = f"""Your verification code is: {code}

        This code will expire in 10 minutes.

        If you didn't request this code, please ignore this email.
        """

    html_body = create_magic_link_email_html(email, code) if settings.EMAIL_BACKEND == "resend" else None
    await send_email(
        email,
        subject,
        body,
        html_body,
        from_email=settings.RESEND_FROM_EMAIL  # noreply@
    )

# Overdue --------------------------------------------------------------------------------
async def send_overdue_notifications(
    trip: Any,
    contacts: list[Any],
    user_name: str = "Someone",
    user_timezone: str | None = None,
    start_location: str | None = None,
    owner_email: str | None = None
):
    """Send overdue notifications to contacts via email and push.

    If owner_email is provided, also sends a copy to the trip owner.
    """
    from ..messaging.resend_backend import create_overdue_notification_email_html

    # Extract trip data
    trip_title = get_attr(trip, 'title')
    trip_location_text = get_attr(trip, 'location_text')
    trip_user_id = get_attr(trip, 'user_id')
    trip_activity = get_attr(trip, 'activity_name', 'Unknown')
    trip_notes = get_attr(trip, 'notes')

    # Format times
    eta_formatted, _ = format_datetime_with_tz(parse_datetime(get_attr(trip, 'eta')), user_timezone)
    start_formatted, _ = format_datetime_with_tz(parse_datetime(get_attr(trip, 'start')), user_timezone)

    display_location = trip_location_text if should_display_location(trip_location_text) else None
    display_start_location = start_location if should_display_location(start_location) else None

    # Build list of all recipients (contacts + owner if enabled)
    recipients = []
    for contact in contacts:
        contact_email = get_attr(contact, 'email')
        if contact_email:
            recipients.append(contact_email)

    # Add owner email if notify_self is enabled
    if owner_email and owner_email not in recipients:
        recipients.append(owner_email)

    for recipient_email in recipients:
        subject = f"URGENT: {user_name} is overdue on their {trip_title}"
        # Use different subject for owner
        if recipient_email == owner_email:
            subject = f"URGENT: Your trip '{trip_title}' is overdue"

        html_body = create_overdue_notification_email_html(
            user_name=user_name,
            plan_title=trip_title,
            activity=trip_activity,
            start_time=start_formatted,
            expected_time=eta_formatted,
            location=display_location,
            notes=trip_notes,
            start_location=display_start_location
        )
        plain_body = html_to_text(html_body)

        await send_email(
            recipient_email,
            subject,
            plain_body,
            html_body,
            from_email=settings.RESEND_ALERTS_EMAIL,
            high_priority=True
        )

        log.info(f"Sent overdue notification to {recipient_email} for trip '{trip_title}'")
        await asyncio.sleep(0.5)  # Rate limit: max 2 requests/second

    # Send push notification to user with checkout action
    trip_id = get_attr(trip, 'id')
    checkout_token = get_attr(trip, 'checkout_token')
    message = f"URGENT: {trip_title} was expected by {eta_formatted} but hasn't checked in."
    await send_push_to_user(
        trip_user_id,
        "Check-in Overdue",
        message,
        data={
            "trip_id": trip_id,
            "checkout_token": checkout_token
        },
        category="CHECKOUT_ONLY"
    )

# Trip created --------------------------------------------------------------------------------
async def send_trip_created_emails(
    trip: Any,
    contacts: list[Any],
    user_name: str,
    activity_name: str,
    user_timezone: str | None = None,
    start_location: str | None = None,
    owner_email: str | None = None
):
    """Send notification emails to contacts when they're added to a trip.

    If owner_email is provided, also sends a copy to the trip owner.
    """
    from ..messaging.resend_backend import create_trip_created_email_html

    # Extract trip data
    trip_title = get_attr(trip, 'title')
    trip_location_text = get_attr(trip, 'location_text') or "Not specified"

    # Format times
    start_formatted, _ = format_datetime_with_tz(parse_datetime(get_attr(trip, 'start')), user_timezone)
    eta_formatted, _ = format_datetime_with_tz(parse_datetime(get_attr(trip, 'eta')), user_timezone)

    display_start_location = start_location if should_display_location(start_location) else None

    # Build list of all recipients (contacts + owner if enabled)
    recipients = []
    for contact in contacts:
        contact_email = get_attr(contact, 'email')
        if contact_email:
            recipients.append(contact_email)

    # Add owner email if notify_self is enabled
    if owner_email and owner_email not in recipients:
        recipients.append(owner_email)

    for recipient_email in recipients:
        subject = f"{user_name} added you as an emergency contact to their trip"
        # Use different subject for owner
        if recipient_email == owner_email:
            subject = f"Your trip '{trip_title}' has been created"

        html_body = create_trip_created_email_html(
            user_name=user_name,
            plan_title=trip_title,
            activity=activity_name,
            start_time=start_formatted,
            expected_time=eta_formatted,
            location=trip_location_text,
            start_location=display_start_location
        )
        plain_body = html_to_text(html_body)

        await send_email(
            recipient_email,
            subject,
            plain_body,
            html_body,
            from_email=settings.RESEND_HELLO_EMAIL
        )

        log.info(f"Sent trip created notification to {recipient_email} for trip '{trip_title}'")
        await asyncio.sleep(0.5)  # Rate limit: max 2 requests/second

# Trip starting --------------------------------------------------------------------------------
async def send_trip_starting_now_emails(
    trip: Any,
    contacts: list[Any],
    user_name: str,
    activity_name: str,
    user_timezone: str | None = None,
    start_location: str | None = None,
    owner_email: str | None = None
):
    """Send notification emails to contacts when a trip starts immediately.

    If owner_email is provided, also sends a copy to the trip owner.
    """
    from ..messaging.resend_backend import create_trip_starting_now_email_html

    # Extract trip data
    trip_title = get_attr(trip, 'title')
    trip_location_text = get_attr(trip, 'location_text') or "Not specified"

    # Format times
    eta_formatted, _ = format_datetime_with_tz(parse_datetime(get_attr(trip, 'eta')), user_timezone)

    display_start_location = start_location if should_display_location(start_location) else None

    # Build list of all recipients (contacts + owner if enabled)
    recipients = []
    for contact in contacts:
        contact_email = get_attr(contact, 'email')
        if contact_email:
            recipients.append(contact_email)

    # Add owner email if notify_self is enabled
    if owner_email and owner_email not in recipients:
        recipients.append(owner_email)

    for recipient_email in recipients:
        subject = f"{user_name}'s trip just started!"
        # Use different subject for owner
        if recipient_email == owner_email:
            subject = f"Your trip '{trip_title}' has started"

        html_body = create_trip_starting_now_email_html(
            user_name=user_name,
            plan_title=trip_title,
            activity=activity_name,
            expected_time=eta_formatted,
            location=trip_location_text,
            start_location=display_start_location
        )
        plain_body = html_to_text(html_body)

        await send_email(
            recipient_email,
            subject,
            plain_body,
            html_body,
            from_email=settings.RESEND_HELLO_EMAIL
        )

        log.info(f"Sent trip starting now notification to {recipient_email} for trip '{trip_title}'")
        await asyncio.sleep(0.5)  # Rate limit: max 2 requests/second

# Check in --------------------------------------------------------------------------------
async def send_checkin_update_emails(
    trip: Any,
    contacts: list[Any],
    user_name: str,
    activity_name: str,
    user_timezone: str | None = None,
    coordinates: str | None = None,
    location_name: str | None = None,
    owner_email: str | None = None,
    actor_name: str | None = None
):
    """Send check-in update emails to contacts when user checks in.

    If owner_email is provided, also sends a copy to the trip owner.

    For group trips, each contact has a 'watched_user_name' indicating who they're watching.
    The subject line uses the watched user's name, while the body mentions the actor.
    If actor_name is not provided, user_name is used for both.
    """
    from ..messaging.resend_backend import create_checkin_update_email_html

    # Use user_name as actor_name if not specified (backward compatibility)
    if actor_name is None:
        actor_name = user_name

    # Extract trip data
    trip_title = get_attr(trip, 'title')
    trip_location_text = get_attr(trip, 'location_text')

    # Format times
    checkin_time, _ = get_current_time_formatted(user_timezone)
    expected_time, _ = format_datetime_with_tz(parse_datetime(get_attr(trip, 'eta')), user_timezone)

    display_location = trip_location_text if should_display_location(trip_location_text) else None

    # Process each contact individually for personalized notifications
    for contact in contacts:
        contact_email = get_attr(contact, 'email')
        if not contact_email:
            continue

        # Get the watched user's name for this contact (defaults to actor_name for solo trips)
        watched_user_name = get_attr(contact, 'watched_user_name') or actor_name

        # Subject uses watched user's name so the contact knows whose trip this is about
        subject = f"Update on {watched_user_name}'s trip: Check-in received"

        html_body = create_checkin_update_email_html(
            user_name=actor_name,  # Who checked in
            plan_title=trip_title,
            activity=activity_name,
            checkin_time=checkin_time,
            expected_time=expected_time,
            coordinates=coordinates,
            location=display_location,
            location_name=location_name,
            watched_user_name=watched_user_name
        )
        plain_body = html_to_text(html_body)

        await send_email(
            contact_email,
            subject,
            plain_body,
            html_body,
            from_email=settings.RESEND_UPDATE_EMAIL
        )

        log.info(f"Sent checkin update to {contact_email} for trip '{trip_title}' (watched: {watched_user_name})")
        await asyncio.sleep(0.5)  # Rate limit: max 2 requests/second

    # Also send to owner if enabled
    if owner_email:
        subject = f"Your check-in was recorded for '{trip_title}'"

        html_body = create_checkin_update_email_html(
            user_name=actor_name,
            plan_title=trip_title,
            activity=activity_name,
            checkin_time=checkin_time,
            expected_time=expected_time,
            coordinates=coordinates,
            location=display_location,
            location_name=location_name,
            watched_user_name=actor_name  # Owner is watching themselves
        )
        plain_body = html_to_text(html_body)

        await send_email(
            owner_email,
            subject,
            plain_body,
            html_body,
            from_email=settings.RESEND_UPDATE_EMAIL
        )

        log.info(f"Sent checkin update to owner {owner_email} for trip '{trip_title}'")
        await asyncio.sleep(0.5)

# Trip extended --------------------------------------------------------------------------------
async def send_trip_extended_emails(
    trip: Any,
    contacts: list[Any],
    user_name: str,
    activity_name: str,
    extended_by_minutes: int,
    user_timezone: str | None = None,
    owner_email: str | None = None,
    actor_name: str | None = None
):
    """Send notification emails to contacts when user extends their trip.

    If owner_email is provided, also sends a copy to the trip owner.

    For group trips, each contact has a 'watched_user_name' indicating who they're watching.
    The subject line uses the watched user's name, while the body mentions the actor.
    """
    from ..messaging.resend_backend import create_trip_extended_email_html

    # Use user_name as actor_name if not specified (backward compatibility)
    if actor_name is None:
        actor_name = user_name

    # Extract trip data
    trip_title = get_attr(trip, 'title')
    trip_location_text = get_attr(trip, 'location_text')

    # Format times
    new_eta_formatted, _ = format_datetime_with_tz(parse_datetime(get_attr(trip, 'eta')), user_timezone)

    display_location = trip_location_text if should_display_location(trip_location_text) else None

    # Process each contact individually for personalized notifications
    for contact in contacts:
        contact_email = get_attr(contact, 'email')
        if not contact_email:
            continue

        # Get the watched user's name for this contact
        watched_user_name = get_attr(contact, 'watched_user_name') or actor_name

        # Subject uses watched user's name
        subject = f"Update on {watched_user_name}'s trip: Extended by {extended_by_minutes} min"

        html_body = create_trip_extended_email_html(
            user_name=actor_name,  # Who extended
            plan_title=trip_title,
            activity=activity_name,
            extended_by=extended_by_minutes,
            new_eta=new_eta_formatted,
            location=display_location,
            watched_user_name=watched_user_name
        )
        plain_body = html_to_text(html_body)

        await send_email(
            contact_email,
            subject,
            plain_body,
            html_body,
            from_email=settings.RESEND_UPDATE_EMAIL
        )

        log.info(f"Sent trip extended notification to {contact_email} for trip '{trip_title}' (watched: {watched_user_name})")
        await asyncio.sleep(0.5)  # Rate limit: max 2 requests/second

    # Also send to owner if enabled
    if owner_email:
        subject = f"Your trip '{trip_title}' has been extended"

        html_body = create_trip_extended_email_html(
            user_name=actor_name,
            plan_title=trip_title,
            activity=activity_name,
            extended_by=extended_by_minutes,
            new_eta=new_eta_formatted,
            location=display_location,
            watched_user_name=actor_name
        )
        plain_body = html_to_text(html_body)

        await send_email(
            owner_email,
            subject,
            plain_body,
            html_body,
            from_email=settings.RESEND_UPDATE_EMAIL
        )

        log.info(f"Sent trip extended notification to owner {owner_email} for trip '{trip_title}'")
        await asyncio.sleep(0.5)

# Trip completed --------------------------------------------------------------------------------
async def send_trip_completed_emails(
    trip: Any,
    contacts: list[Any],
    user_name: str,
    activity_name: str,
    user_timezone: str | None = None,
    owner_email: str | None = None,
    actor_name: str | None = None
):
    """Send notification emails to contacts when a trip is completed safely.

    If owner_email is provided, also sends a copy to the trip owner.

    For group trips, each contact has a 'watched_user_name' indicating who they're watching.
    """
    from ..messaging.resend_backend import create_trip_completed_email_html

    # Use user_name as actor_name if not specified (backward compatibility)
    if actor_name is None:
        actor_name = user_name

    # Extract trip data
    trip_title = get_attr(trip, 'title')
    trip_location_text = get_attr(trip, 'location_text')

    display_location = trip_location_text if should_display_location(trip_location_text) else None

    # Process each contact individually for personalized notifications
    for contact in contacts:
        contact_email = get_attr(contact, 'email')
        if not contact_email:
            continue

        # Get the watched user's name for this contact
        watched_user_name = get_attr(contact, 'watched_user_name') or actor_name

        # Subject uses watched user's name
        subject = f"{watched_user_name} is Homebound!"

        html_body = create_trip_completed_email_html(
            user_name=actor_name,  # Who completed
            plan_title=trip_title,
            activity=activity_name,
            location=display_location,
            watched_user_name=watched_user_name
        )
        plain_body = html_to_text(html_body)

        await send_email(
            contact_email,
            subject,
            plain_body,
            html_body,
            from_email=settings.RESEND_UPDATE_EMAIL
        )

        log.info(f"Sent trip completed notification to {contact_email} for trip '{trip_title}' (watched: {watched_user_name})")
        await asyncio.sleep(0.5)  # Rate limit: max 2 requests/second

    # Also send to owner if enabled
    if owner_email:
        subject = f"Your trip '{trip_title}' is complete!"

        html_body = create_trip_completed_email_html(
            user_name=actor_name,
            plan_title=trip_title,
            activity=activity_name,
            location=display_location,
            watched_user_name=actor_name
        )
        plain_body = html_to_text(html_body)

        await send_email(
            owner_email,
            subject,
            plain_body,
            html_body,
            from_email=settings.RESEND_UPDATE_EMAIL
        )

        log.info(f"Sent trip completed notification to owner {owner_email} for trip '{trip_title}'")
        await asyncio.sleep(0.5)

# Overdue resolved --------------------------------------------------------------------------------
async def send_overdue_resolved_emails(
    trip: Any,
    contacts: list[Any],
    user_name: str,
    activity_name: str,
    user_timezone: str | None = None,
    owner_email: str | None = None
):
    """Send urgent "all clear" emails when an overdue trip is resolved.

    If owner_email is provided, also sends a copy to the trip owner.
    """
    from ..messaging.resend_backend import create_overdue_resolved_email_html

    # Extract trip data
    trip_title = get_attr(trip, 'title')

    # Build list of all recipients (contacts + owner if enabled)
    recipients = []
    for contact in contacts:
        contact_email = get_attr(contact, 'email')
        if contact_email:
            recipients.append(contact_email)

    # Add owner email if notify_self is enabled
    if owner_email and owner_email not in recipients:
        recipients.append(owner_email)

    for recipient_email in recipients:
        subject = f"{user_name} is safe!"
        # Use different subject for owner
        if recipient_email == owner_email:
            subject = f"Overdue resolved: Your trip '{trip_title}'"

        html_body = create_overdue_resolved_email_html(
            user_name=user_name,
            plan_title=trip_title,
            activity=activity_name
        )
        plain_body = html_to_text(html_body)

        await send_email(
            recipient_email,
            subject,
            plain_body,
            html_body,
            from_email=settings.RESEND_ALERTS_EMAIL,
            high_priority=True
        )

        log.info(f"Sent overdue resolved notification to {recipient_email} for trip '{trip_title}'")
        await asyncio.sleep(0.5)  # Rate limit: max 2 requests/second

