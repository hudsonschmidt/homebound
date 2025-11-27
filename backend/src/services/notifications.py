from __future__ import annotations

import logging
from typing import List, Optional, Any

from ..config import get_settings

settings = get_settings()
log = logging.getLogger(__name__)


async def send_email(
    email: str,
    subject: str,
    body: str,
    html_body: Optional[str] = None,
    from_email: Optional[str] = None
):
    """Send email notification.

    Args:
        email: Recipient email address
        subject: Email subject
        body: Plain text body
        html_body: Optional HTML body
        from_email: Optional from address (defaults to RESEND_FROM_EMAIL)
    """
    if settings.EMAIL_BACKEND == "resend":
        from ..messaging.resend_backend import send_resend_email
        success = await send_resend_email(
            to_email=email,
            subject=subject,
            text_body=body,
            html_body=html_body,
            from_email=from_email
        )
        if not success:
            log.error(f"Failed to send email to {email}")
    elif settings.EMAIL_BACKEND == "console":
        log.info(f"[CONSOLE EMAIL] To: {email}\nFrom: {from_email or 'default'}\nSubject: {subject}\n{body}")
    else:
        log.warning(f"Unknown email backend: {settings.EMAIL_BACKEND}")


async def send_push_to_user(user_id: int, title: str, body: str):
    """Send push notification to all user's devices."""
    if settings.PUSH_BACKEND == "apns":
        # TODO: Implement APNs push
        log.info(f"[APNS PUSH] User: {user_id} - {title}: {body}")
    elif settings.PUSH_BACKEND == "dummy":
        log.info(f"[DUMMY PUSH] User: {user_id} - {title}: {body}")
    else:
        log.warning(f"Unknown push backend: {settings.PUSH_BACKEND}")


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


async def send_overdue_notifications(trip: Any, contacts: List[Any], user_name: str = "Someone"):
    """Send overdue notifications to contacts via email and push.

    Args:
        trip: Dictionary or Row object with trip data
        contacts: List of contact dictionaries or Row objects
        user_name: Name of the user who is overdue
    """
    from datetime import datetime
    from ..messaging.resend_backend import create_overdue_notification_email_html

    # Handle both dict and Row objects
    trip_title = trip.get('title') if hasattr(trip, 'get') else trip.title
    trip_eta = trip.get('eta') if hasattr(trip, 'get') else trip.eta
    trip_location_text = trip.get('location_text') if hasattr(trip, 'get') else trip.location_text
    trip_user_id = trip.get('user_id') if hasattr(trip, 'get') else trip.user_id

    # Format eta if it's a string
    if isinstance(trip_eta, str):
        eta_dt = datetime.fromisoformat(trip_eta.replace(' ', 'T'))
        eta_formatted = eta_dt.strftime('%B %d, %Y at %I:%M %p')
    else:
        eta_formatted = trip_eta.strftime('%B %d, %Y at %I:%M %p')

    # Send Email notifications to all contacts
    for contact in contacts:
        contact_email = contact.get('email') if hasattr(contact, 'get') else contact.email
        contact_name = contact.get('name') if hasattr(contact, 'get') else contact.name

        if contact_email:
            subject = f"⚠️ URGENT: {user_name} is overdue - {trip_title}"

            # Plain text fallback
            plain_body = f"""URGENT: Check-in Overdue

Dear {contact_name},

You're receiving this message because you were listed as an emergency contact for a Homebound safety plan that is now overdue.

Trip: {trip_title}
Expected by: {eta_formatted}
"""
            if trip_location_text:
                plain_body += f"Last known location: {trip_location_text}\n"

            plain_body += """
Action Needed:
- Try to contact the person directly
- If unable to reach them, consider checking their planned location
- If you have concerns about their safety, contact local authorities

This notification was sent automatically because the person did not check in by their expected time plus the grace period they set.
"""

            # HTML body
            html_body = create_overdue_notification_email_html(
                contact_name=contact_name,
                plan_title=trip_title,
                expected_time=eta_formatted,
                location=trip_location_text
            )

            await send_email(
                contact_email,
                subject,
                plain_body,
                html_body,
                from_email=settings.RESEND_ALERTS_EMAIL  # alerts@
            )

            log.info(f"Sent overdue notification to {contact_email} for trip '{trip_title}'")

    # Send push notification to trip owner's devices
    message = f"URGENT: {trip_title} was expected by {eta_formatted} but hasn't checked in."
    await send_push_to_user(trip_user_id, "Check-in Overdue", message)


async def send_trip_created_emails(
    trip: Any,
    contacts: List[Any],
    user_name: str,
    activity_name: str,
    user_timezone: Optional[str] = None
):
    """Send notification emails to contacts when they're added to a trip.

    Args:
        trip: Dictionary or Row object with trip data
        contacts: List of contact dictionaries or Row objects
        user_name: Name of the user creating the trip
        activity_name: Name of the activity (e.g., "Hiking", "Skiing")
        user_timezone: User's timezone (e.g., "America/New_York")
    """
    from datetime import datetime
    import pytz
    from ..messaging.resend_backend import create_trip_created_email_html

    # Handle both dict and Row objects
    trip_title = trip.get('title') if hasattr(trip, 'get') else trip.title
    trip_start = trip.get('start') if hasattr(trip, 'get') else trip.start
    trip_eta = trip.get('eta') if hasattr(trip, 'get') else trip.eta
    trip_location_text = trip.get('location_text') if hasattr(trip, 'get') else trip.location_text

    # Parse datetimes
    if isinstance(trip_start, str):
        start_dt = datetime.fromisoformat(trip_start.replace(' ', 'T').replace('Z', '+00:00'))
    else:
        start_dt = trip_start

    if isinstance(trip_eta, str):
        eta_dt = datetime.fromisoformat(trip_eta.replace(' ', 'T').replace('Z', '+00:00'))
    else:
        eta_dt = trip_eta

    # Convert to user's timezone if provided
    timezone_display = ""
    if user_timezone:
        try:
            tz = pytz.timezone(user_timezone)
            # Make datetimes timezone-aware if they aren't
            if start_dt.tzinfo is None:
                start_dt = pytz.utc.localize(start_dt)
            if eta_dt.tzinfo is None:
                eta_dt = pytz.utc.localize(eta_dt)
            # Convert to user's timezone
            start_dt = start_dt.astimezone(tz)
            eta_dt = eta_dt.astimezone(tz)
            # Get timezone abbreviation (e.g., "PST", "EST")
            timezone_display = f" {start_dt.strftime('%Z')}"
        except Exception as e:
            log.warning(f"Failed to convert to timezone {user_timezone}: {e}")

    start_formatted = start_dt.strftime('%B %d, %Y at %I:%M %p') + timezone_display
    eta_formatted = eta_dt.strftime('%B %d, %Y at %I:%M %p') + timezone_display

    # Send to each contact
    for contact in contacts:
        contact_email = contact.get('email') if hasattr(contact, 'get') else contact.email
        contact_name = contact.get('name') if hasattr(contact, 'get') else contact.name

        if contact_email:
            subject = f"{user_name} added you as an emergency contact"

            # Plain text fallback
            plain_body = f"""Hi {contact_name},

{user_name} has added you as an emergency contact for an upcoming trip on Homebound.

Trip: {trip_title}
Activity: {activity_name}
Starting: {start_formatted}
Expected back by: {eta_formatted}
"""
            if trip_location_text:
                plain_body += f"Location: {trip_location_text}\n"

            plain_body += f"""
What does this mean?
If {user_name} doesn't check in by their expected return time (plus a grace period), you'll receive an alert email asking you to check on them.

No action is needed right now. We just wanted you to know they're heading out and trust you to be there if needed.

Safe travels!
- The Homebound Team
"""

            # HTML body
            html_body = create_trip_created_email_html(
                contact_name=contact_name,
                user_name=user_name,
                plan_title=trip_title,
                activity=activity_name,
                start_time=start_formatted,
                expected_time=eta_formatted,
                location=trip_location_text
            )

            await send_email(
                contact_email,
                subject,
                plain_body,
                html_body,
                from_email=settings.RESEND_HELLO_EMAIL  # hello@
            )

            log.info(f"Sent trip created notification to {contact_email} for trip '{trip_title}'")


async def send_trip_starting_now_emails(
    trip: Any,
    contacts: List[Any],
    user_name: str,
    activity_name: str,
    user_timezone: Optional[str] = None
):
    """Send notification emails to contacts when a trip starts immediately.

    Args:
        trip: Dictionary or Row object with trip data
        contacts: List of contact dictionaries or Row objects
        user_name: Name of the user creating the trip
        activity_name: Name of the activity (e.g., "Hiking", "Skiing")
        user_timezone: User's timezone (e.g., "America/New_York")
    """
    from datetime import datetime
    import pytz
    from ..messaging.resend_backend import create_trip_starting_now_email_html

    # Handle both dict and Row objects
    trip_title = trip.get('title') if hasattr(trip, 'get') else trip.title
    trip_eta = trip.get('eta') if hasattr(trip, 'get') else trip.eta
    trip_location_text = trip.get('location_text') if hasattr(trip, 'get') else trip.location_text

    # Parse eta datetime
    if isinstance(trip_eta, str):
        eta_dt = datetime.fromisoformat(trip_eta.replace(' ', 'T').replace('Z', '+00:00'))
    else:
        eta_dt = trip_eta

    # Convert to user's timezone if provided
    timezone_display = ""
    if user_timezone:
        try:
            tz = pytz.timezone(user_timezone)
            if eta_dt.tzinfo is None:
                eta_dt = pytz.utc.localize(eta_dt)
            eta_dt = eta_dt.astimezone(tz)
            timezone_display = f" {eta_dt.strftime('%Z')}"
        except Exception as e:
            log.warning(f"Failed to convert to timezone {user_timezone}: {e}")

    eta_formatted = eta_dt.strftime('%B %d, %Y at %I:%M %p') + timezone_display

    # Send to each contact
    for contact in contacts:
        contact_email = contact.get('email') if hasattr(contact, 'get') else contact.email
        contact_name = contact.get('name') if hasattr(contact, 'get') else contact.name

        if contact_email:
            subject = f"🚀 {user_name} just started a trip"

            # Plain text fallback
            plain_body = f"""Hi {contact_name},

{user_name} has just started a trip and added you as an emergency contact.

Trip: {trip_title}
Activity: {activity_name}
Expected back by: {eta_formatted}
"""
            if trip_location_text:
                plain_body += f"Location: {trip_location_text}\n"

            plain_body += f"""
What does this mean?
If {user_name} doesn't check in by their expected return time (plus a grace period), you'll receive an urgent alert email asking you to check on them.

No action is needed right now. We just wanted you to know they're currently out and trust you to be there if needed.

Stay safe out there!
- The Homebound Team
"""

            # HTML body
            html_body = create_trip_starting_now_email_html(
                contact_name=contact_name,
                user_name=user_name,
                plan_title=trip_title,
                activity=activity_name,
                expected_time=eta_formatted,
                location=trip_location_text
            )

            await send_email(
                contact_email,
                subject,
                plain_body,
                html_body,
                from_email=settings.RESEND_HELLO_EMAIL  # hello@
            )

            log.info(f"Sent trip starting now notification to {contact_email} for trip '{trip_title}'")


async def send_checkin_update_emails(
    trip: Any,
    contacts: List[Any],
    user_name: str,
    activity_name: str,
    user_timezone: Optional[str] = None
):
    """Send check-in update emails to contacts when user checks in.

    Args:
        trip: Dictionary or Row object with trip data
        contacts: List of contact dictionaries or Row objects
        user_name: Name of the user who checked in
        activity_name: Name of the activity (e.g., "Hiking", "Skiing")
        user_timezone: User's timezone (e.g., "America/New_York")
    """
    from datetime import datetime
    import pytz
    from ..messaging.resend_backend import create_checkin_update_email_html

    # Handle both dict and Row objects
    trip_title = trip.get('title') if hasattr(trip, 'get') else trip.title

    # Get current time in user's timezone
    now = datetime.utcnow()
    timezone_display = ""
    if user_timezone:
        try:
            tz = pytz.timezone(user_timezone)
            now = pytz.utc.localize(now).astimezone(tz)
            timezone_display = f" {now.strftime('%Z')}"
        except Exception as e:
            log.warning(f"Failed to convert to timezone {user_timezone}: {e}")

    checkin_time = now.strftime('%B %d, %Y at %I:%M %p') + timezone_display

    # Send to each contact
    for contact in contacts:
        contact_email = contact.get('email') if hasattr(contact, 'get') else contact.email
        contact_name = contact.get('name') if hasattr(contact, 'get') else contact.name

        if contact_email:
            subject = f"📍 {user_name} checked in"

            # Plain text fallback
            plain_body = f"""Hi {contact_name},

{user_name} just checked in!

Trip: {trip_title}
Activity: {activity_name}
Check-in time: {checkin_time}

This is just an update to let you know they're doing well. Their trip is still active.

- The Homebound Team
"""

            # HTML body
            html_body = create_checkin_update_email_html(
                contact_name=contact_name,
                user_name=user_name,
                plan_title=trip_title,
                activity=activity_name,
                checkin_time=checkin_time
            )

            await send_email(
                contact_email,
                subject,
                plain_body,
                html_body,
                from_email=settings.RESEND_UPDATE_EMAIL  # update@
            )

            log.info(f"Sent checkin update to {contact_email} for trip '{trip_title}'")


async def send_trip_extended_emails(
    trip: Any,
    contacts: List[Any],
    user_name: str,
    activity_name: str,
    extended_by_minutes: int,
    user_timezone: Optional[str] = None
):
    """Send notification emails to contacts when user extends their trip.

    Args:
        trip: Dictionary or Row object with trip data
        contacts: List of contact dictionaries or Row objects
        user_name: Name of the user who extended the trip
        activity_name: Name of the activity (e.g., "Hiking", "Skiing")
        extended_by_minutes: How many minutes the trip was extended by
        user_timezone: User's timezone (e.g., "America/New_York")
    """
    from datetime import datetime
    import pytz
    from ..messaging.resend_backend import create_trip_extended_email_html

    # Handle both dict and Row objects
    trip_title = trip.get('title') if hasattr(trip, 'get') else trip.title
    trip_eta = trip.get('eta') if hasattr(trip, 'get') else trip.eta

    # Parse eta datetime
    if isinstance(trip_eta, str):
        eta_dt = datetime.fromisoformat(trip_eta.replace(' ', 'T').replace('Z', '+00:00'))
    else:
        eta_dt = trip_eta

    # Convert to user's timezone if provided
    timezone_display = ""
    if user_timezone:
        try:
            tz = pytz.timezone(user_timezone)
            if eta_dt.tzinfo is None:
                eta_dt = pytz.utc.localize(eta_dt)
            eta_dt = eta_dt.astimezone(tz)
            timezone_display = f" {eta_dt.strftime('%Z')}"
        except Exception as e:
            log.warning(f"Failed to convert to timezone {user_timezone}: {e}")

    new_eta_formatted = eta_dt.strftime('%B %d, %Y at %I:%M %p') + timezone_display

    # Send to each contact
    for contact in contacts:
        contact_email = contact.get('email') if hasattr(contact, 'get') else contact.email
        contact_name = contact.get('name') if hasattr(contact, 'get') else contact.name

        if contact_email:
            subject = f"⏱️ {user_name} extended their trip"

            # Plain text fallback
            plain_body = f"""Hi {contact_name},

{user_name} extended their trip by {extended_by_minutes} minutes.

Trip: {trip_title}
Activity: {activity_name}
New expected return: {new_eta_formatted}

This means they checked in and need a bit more time. The trip is still active and they're doing well.

- The Homebound Team
"""

            # HTML body
            html_body = create_trip_extended_email_html(
                contact_name=contact_name,
                user_name=user_name,
                plan_title=trip_title,
                activity=activity_name,
                extended_by=extended_by_minutes,
                new_eta=new_eta_formatted
            )

            await send_email(
                contact_email,
                subject,
                plain_body,
                html_body,
                from_email=settings.RESEND_UPDATE_EMAIL  # update@
            )

            log.info(f"Sent trip extended notification to {contact_email} for trip '{trip_title}'")


async def send_trip_completed_emails(
    trip: Any,
    contacts: List[Any],
    user_name: str,
    activity_name: str
):
    """Send notification emails to contacts when a trip is completed safely.

    Args:
        trip: Dictionary or Row object with trip data
        contacts: List of contact dictionaries or Row objects
        user_name: Name of the user who completed the trip
        activity_name: Name of the activity (e.g., "Hiking", "Skiing")
    """
    from ..messaging.resend_backend import create_trip_completed_email_html

    # Handle both dict and Row objects
    trip_title = trip.get('title') if hasattr(trip, 'get') else trip.title

    # Send to each contact
    for contact in contacts:
        contact_email = contact.get('email') if hasattr(contact, 'get') else contact.email
        contact_name = contact.get('name') if hasattr(contact, 'get') else contact.name

        if contact_email:
            subject = f"✅ Good news! {user_name} is safe"

            # Plain text fallback
            plain_body = f"""Hi {contact_name},

Good news! {user_name} has checked in safely.

Trip: {trip_title}
Activity: {activity_name}

Their adventure is complete and they've arrived safely. No action needed on your part.

Thanks for being there as an emergency contact!

Until the next adventure!
- The Homebound Team
"""

            # HTML body
            html_body = create_trip_completed_email_html(
                contact_name=contact_name,
                user_name=user_name,
                plan_title=trip_title,
                activity=activity_name
            )

            await send_email(
                contact_email,
                subject,
                plain_body,
                html_body,
                from_email=settings.RESEND_UPDATE_EMAIL  # update@ for completion
            )

            log.info(f"Sent trip completed notification to {contact_email} for trip '{trip_title}'")


async def send_overdue_resolved_emails(
    trip: Any,
    contacts: List[Any],
    user_name: str,
    activity_name: str
):
    """Send urgent "all clear" emails when an overdue trip is resolved.

    This is sent from alerts@ because the contacts already received an alert
    about the user being overdue. This follow-up confirms they are now safe.

    Args:
        trip: Dictionary or Row object with trip data
        contacts: List of contact dictionaries or Row objects
        user_name: Name of the user who is now safe
        activity_name: Name of the activity (e.g., "Hiking", "Skiing")
    """
    from ..messaging.resend_backend import create_overdue_resolved_email_html

    # Handle both dict and Row objects
    trip_title = trip.get('title') if hasattr(trip, 'get') else trip.title

    # Send to each contact
    for contact in contacts:
        contact_email = contact.get('email') if hasattr(contact, 'get') else contact.email
        contact_name = contact.get('name') if hasattr(contact, 'get') else contact.name

        if contact_email:
            subject = f"🎉 ALL CLEAR: {user_name} is safe!"

            # Plain text fallback
            plain_body = f"""Hi {contact_name},

GREAT NEWS! {user_name} has checked in and is safe!

Trip: {trip_title}
Activity: {activity_name}

We previously notified you that {user_name} was overdue from their trip.
They have now confirmed they are safe. No further action is needed.

Thank you for being there as an emergency contact!

- The Homebound Team
"""

            # HTML body
            html_body = create_overdue_resolved_email_html(
                contact_name=contact_name,
                user_name=user_name,
                plan_title=trip_title,
                activity=activity_name
            )

            await send_email(
                contact_email,
                subject,
                plain_body,
                html_body,
                from_email=settings.RESEND_ALERTS_EMAIL  # alerts@ since this follows up on an alert
            )

            log.info(f"Sent overdue resolved notification to {contact_email} for trip '{trip_title}'")


async def send_plan_created_notification(plan: Any):
    """Send push notification when a plan is created (to the user).

    Args:
        plan: Dictionary or Row object with plan data
    """
    from datetime import datetime

    # Handle both dict and Row objects
    plan_title = plan.get('title') if hasattr(plan, 'get') else plan.title
    plan_start = plan.get('start') if hasattr(plan, 'get') else plan.start
    plan_eta = plan.get('eta') if hasattr(plan, 'get') else plan.eta
    plan_user_id = plan.get('user_id') if hasattr(plan, 'get') else plan.user_id

    message = f"New trip plan created: {plan_title}"

    if plan_start and plan_eta:
        # Format times if they're strings
        if isinstance(plan_start, str):
            start_dt = datetime.fromisoformat(plan_start.replace(' ', 'T'))
            start_formatted = start_dt.strftime('%I:%M %p')
        else:
            start_formatted = plan_start.strftime('%I:%M %p')

        if isinstance(plan_eta, str):
            eta_dt = datetime.fromisoformat(plan_eta.replace(' ', 'T'))
            eta_formatted = eta_dt.strftime('%I:%M %p')
        else:
            eta_formatted = plan_eta.strftime('%I:%M %p')

        message += f" from {start_formatted} to {eta_formatted}"

    await send_push_to_user(plan_user_id, "Plan Created", message)
