from __future__ import annotations

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


async def send_push_to_user(user_id: int, title: str, body: str, data: dict | None = None):
    """Send push notification to all user's devices with retry logic."""
    import asyncio
    from ..messaging.apns import get_push_sender

    MAX_RETRIES = 3
    RETRY_DELAYS = [1, 2, 4]  # Exponential backoff: 1s, 2s, 4s

    if settings.PUSH_BACKEND == "dummy":
        log.info(f"[DUMMY PUSH] User: {user_id} - {title}: {body}")
        log_notification(user_id, "push", title, body, "sent", error_message="dummy backend")
        return

    if settings.PUSH_BACKEND != "apns":
        log.warning(f"Unknown push backend: {settings.PUSH_BACKEND}")
        return

    # Query user's iOS devices
    with db.engine.begin() as conn:
        devices = conn.execute(
            sqlalchemy.text(
                "SELECT token, env FROM devices WHERE user_id = :uid AND platform = 'ios'"
            ),
            {"uid": user_id}
        ).fetchall()

    if not devices:
        log.debug(f"No iOS devices registered for user {user_id}")
        return

    # Send to each device with retry logic
    sender = get_push_sender()
    tokens_to_remove: list[str] = []

    for device in devices:
        success = False
        last_error = None

        for attempt in range(MAX_RETRIES):
            try:
                result = await sender.send(device.token, title, body, data)
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
async def send_overdue_notifications(trip: Any, contacts: list[Any], user_name: str = "Someone", user_timezone: str | None = None):
    """Send overdue notifications to contacts via email and push."""
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

    for contact in contacts:
        contact_email = get_attr(contact, 'email')

        if contact_email:
            subject = f"URGENT: {user_name} is overdue on their {trip_title}"

            html_body = create_overdue_notification_email_html(
                user_name=user_name,
                plan_title=trip_title,
                activity=trip_activity,
                start_time=start_formatted,
                expected_time=eta_formatted,
                location=display_location,
                notes=trip_notes
            )
            plain_body = html_to_text(html_body)

            await send_email(
                contact_email,
                subject,
                plain_body,
                html_body,
                from_email=settings.RESEND_ALERTS_EMAIL,
                high_priority=True
            )

            log.info(f"Sent overdue notification to {contact_email} for trip '{trip_title}'")

    message = f"URGENT: {trip_title} was expected by {eta_formatted} but hasn't checked in."
    await send_push_to_user(trip_user_id, "Check-in Overdue", message)

# Trip created --------------------------------------------------------------------------------
async def send_trip_created_emails(
    trip: Any,
    contacts: list[Any],
    user_name: str,
    activity_name: str,
    user_timezone: str | None = None
):
    """Send notification emails to contacts when they're added to a trip."""
    from ..messaging.resend_backend import create_trip_created_email_html

    # Extract trip data
    trip_title = get_attr(trip, 'title')
    trip_location_text = get_attr(trip, 'location_text') or "Not specified"

    # Format times
    start_formatted, _ = format_datetime_with_tz(parse_datetime(get_attr(trip, 'start')), user_timezone)
    eta_formatted, _ = format_datetime_with_tz(parse_datetime(get_attr(trip, 'eta')), user_timezone)

    for contact in contacts:
        contact_email = get_attr(contact, 'email')

        if contact_email:
            subject = f"{user_name} added you as an emergency contact to their trip"

            html_body = create_trip_created_email_html(
                user_name=user_name,
                plan_title=trip_title,
                activity=activity_name,
                start_time=start_formatted,
                expected_time=eta_formatted,
                location=trip_location_text
            )
            plain_body = html_to_text(html_body)

            await send_email(
                contact_email,
                subject,
                plain_body,
                html_body,
                from_email=settings.RESEND_HELLO_EMAIL
            )

            log.info(f"Sent trip created notification to {contact_email} for trip '{trip_title}'")

# Trip starting --------------------------------------------------------------------------------
async def send_trip_starting_now_emails(
    trip: Any,
    contacts: list[Any],
    user_name: str,
    activity_name: str,
    user_timezone: str | None = None
):
    """Send notification emails to contacts when a trip starts immediately."""
    from ..messaging.resend_backend import create_trip_starting_now_email_html

    # Extract trip data
    trip_title = get_attr(trip, 'title')
    trip_location_text = get_attr(trip, 'location_text') or "Not specified"

    # Format times
    eta_formatted, _ = format_datetime_with_tz(parse_datetime(get_attr(trip, 'eta')), user_timezone)

    for contact in contacts:
        contact_email = get_attr(contact, 'email')

        if contact_email:
            subject = f"{user_name}'s trip just started!"

            html_body = create_trip_starting_now_email_html(
                user_name=user_name,
                plan_title=trip_title,
                activity=activity_name,
                expected_time=eta_formatted,
                location=trip_location_text
            )
            plain_body = html_to_text(html_body)

            await send_email(
                contact_email,
                subject,
                plain_body,
                html_body,
                from_email=settings.RESEND_HELLO_EMAIL
            )

            log.info(f"Sent trip starting now notification to {contact_email} for trip '{trip_title}'")

# Check in --------------------------------------------------------------------------------
async def send_checkin_update_emails(
    trip: Any,
    contacts: list[Any],
    user_name: str,
    activity_name: str,
    user_timezone: str | None = None,
    coordinates: str | None = None
):
    """Send check-in update emails to contacts when user checks in."""
    from ..messaging.resend_backend import create_checkin_update_email_html

    # Extract trip data
    trip_title = get_attr(trip, 'title')
    trip_location_text = get_attr(trip, 'location_text')

    # Format times
    checkin_time, _ = get_current_time_formatted(user_timezone)
    expected_time, _ = format_datetime_with_tz(parse_datetime(get_attr(trip, 'eta')), user_timezone)

    display_location = trip_location_text if should_display_location(trip_location_text) else None

    for contact in contacts:
        contact_email = get_attr(contact, 'email')

        if contact_email:
            subject = f"{user_name} checked in"

            html_body = create_checkin_update_email_html(
                user_name=user_name,
                plan_title=trip_title,
                activity=activity_name,
                checkin_time=checkin_time,
                expected_time=expected_time,
                coordinates=coordinates,
                location=display_location
            )
            plain_body = html_to_text(html_body)

            await send_email(
                contact_email,
                subject,
                plain_body,
                html_body,
                from_email=settings.RESEND_UPDATE_EMAIL
            )

            log.info(f"Sent checkin update to {contact_email} for trip '{trip_title}'")

# Trip extended --------------------------------------------------------------------------------
async def send_trip_extended_emails(
    trip: Any,
    contacts: list[Any],
    user_name: str,
    activity_name: str,
    extended_by_minutes: int,
    user_timezone: str | None = None
):
    """Send notification emails to contacts when user extends their trip."""
    from ..messaging.resend_backend import create_trip_extended_email_html

    # Extract trip data
    trip_title = get_attr(trip, 'title')
    trip_location_text = get_attr(trip, 'location_text')

    # Format times
    new_eta_formatted, _ = format_datetime_with_tz(parse_datetime(get_attr(trip, 'eta')), user_timezone)

    display_location = trip_location_text if should_display_location(trip_location_text) else None

    for contact in contacts:
        contact_email = get_attr(contact, 'email')

        if contact_email:
            subject = f"{user_name} extended their trip"

            html_body = create_trip_extended_email_html(
                user_name=user_name,
                plan_title=trip_title,
                activity=activity_name,
                extended_by=extended_by_minutes,
                new_eta=new_eta_formatted,
                location=display_location
            )
            plain_body = html_to_text(html_body)

            await send_email(
                contact_email,
                subject,
                plain_body,
                html_body,
                from_email=settings.RESEND_UPDATE_EMAIL
            )

            log.info(f"Sent trip extended notification to {contact_email} for trip '{trip_title}'")

# Trip completed --------------------------------------------------------------------------------
async def send_trip_completed_emails(
    trip: Any,
    contacts: list[Any],
    user_name: str,
    activity_name: str,
    user_timezone: str | None = None
):
    """Send notification emails to contacts when a trip is completed safely."""
    from ..messaging.resend_backend import create_trip_completed_email_html

    # Extract trip data
    trip_title = get_attr(trip, 'title')
    trip_location_text = get_attr(trip, 'location_text')

    display_location = trip_location_text if should_display_location(trip_location_text) else None

    for contact in contacts:
        contact_email = get_attr(contact, 'email')

        if contact_email:
            subject = f"{user_name} is Homebound!"

            html_body = create_trip_completed_email_html(
                user_name=user_name,
                plan_title=trip_title,
                activity=activity_name,
                location=display_location
            )
            plain_body = html_to_text(html_body)

            await send_email(
                contact_email,
                subject,
                plain_body,
                html_body,
                from_email=settings.RESEND_UPDATE_EMAIL
            )

            log.info(f"Sent trip completed notification to {contact_email} for trip '{trip_title}'")

# Overdue resolved --------------------------------------------------------------------------------
async def send_overdue_resolved_emails(
    trip: Any,
    contacts: list[Any],
    user_name: str,
    activity_name: str,
    user_timezone: str | None = None
):
    """Send urgent "all clear" emails when an overdue trip is resolved."""
    from ..messaging.resend_backend import create_overdue_resolved_email_html

    # Extract trip data
    trip_title = get_attr(trip, 'title')

    for contact in contacts:
        contact_email = get_attr(contact, 'email')

        if contact_email:
            subject = f"{user_name} is safe!"

            html_body = create_overdue_resolved_email_html(
                user_name=user_name,
                plan_title=trip_title,
                activity=activity_name
            )
            plain_body = html_to_text(html_body)

            await send_email(
                contact_email,
                subject,
                plain_body,
                html_body,
                from_email=settings.RESEND_ALERTS_EMAIL,
                high_priority=True
            )

            log.info(f"Sent overdue resolved notification to {contact_email} for trip '{trip_title}'")

