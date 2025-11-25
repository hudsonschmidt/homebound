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
    activity_name: str
):
    """Send notification emails to contacts when they're added to a trip.

    Args:
        trip: Dictionary or Row object with trip data
        contacts: List of contact dictionaries or Row objects
        user_name: Name of the user creating the trip
        activity_name: Name of the activity (e.g., "Hiking", "Skiing")
    """
    from datetime import datetime
    from ..messaging.resend_backend import create_trip_created_email_html

    # Handle both dict and Row objects
    trip_title = trip.get('title') if hasattr(trip, 'get') else trip.title
    trip_start = trip.get('start') if hasattr(trip, 'get') else trip.start
    trip_eta = trip.get('eta') if hasattr(trip, 'get') else trip.eta
    trip_location_text = trip.get('location_text') if hasattr(trip, 'get') else trip.location_text

    # Format times
    if isinstance(trip_start, str):
        start_dt = datetime.fromisoformat(trip_start.replace(' ', 'T'))
    else:
        start_dt = trip_start
    start_formatted = start_dt.strftime('%B %d, %Y at %I:%M %p')

    if isinstance(trip_eta, str):
        eta_dt = datetime.fromisoformat(trip_eta.replace(' ', 'T'))
    else:
        eta_dt = trip_eta
    eta_formatted = eta_dt.strftime('%B %d, %Y at %I:%M %p')

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
            subject = f"Good news! {user_name} is safe"

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
                from_email=settings.RESEND_HELLO_EMAIL  # hello@
            )

            log.info(f"Sent trip completed notification to {contact_email} for trip '{trip_title}'")


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
