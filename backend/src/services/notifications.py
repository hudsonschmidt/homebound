from __future__ import annotations

import logging
from typing import List, Optional, Any

from ..config import get_settings

settings = get_settings()
log = logging.getLogger(__name__)


async def send_overdue_notifications(plan: Any, contacts: List[Any]):
    """Send overdue notifications to contacts via SMS, email, and push.

    Args:
        plan: Dictionary or Row object with keys: title, eta_at, location_text, user_id
        contacts: List of dictionaries or Row objects with keys: phone, email
    """
    from datetime import datetime

    # Handle both dict and Row objects
    plan_title = plan.get('title') if hasattr(plan, 'get') else plan.title
    plan_eta_at = plan.get('eta_at') if hasattr(plan, 'get') else plan.eta_at
    plan_location_text = plan.get('location_text') if hasattr(plan, 'get') else plan.location_text
    plan_user_id = plan.get('user_id') if hasattr(plan, 'get') else plan.user_id

    # Format eta_at if it's a string
    if isinstance(plan_eta_at, str):
        eta_dt = datetime.fromisoformat(plan_eta_at.replace(' ', 'T'))
        eta_formatted = eta_dt.strftime('%I:%M %p')
    else:
        eta_formatted = plan_eta_at.strftime('%I:%M %p')

    message = f"URGENT: {plan_title} was expected by {eta_formatted} but hasn't checked in."

    if plan_location_text:
        message += f" Last known location: {plan_location_text}"

    # Send SMS notifications
    for contact in contacts:
        contact_phone = contact.get('phone') if hasattr(contact, 'get') else contact.phone
        if contact_phone:
            await send_sms(contact_phone, message)

    # Send Email notifications
    for contact in contacts:
        contact_email = contact.get('email') if hasattr(contact, 'get') else contact.email
        if contact_email:
            await send_email(
                contact_email,
                f"Overdue Alert: {plan_title}",
                message
            )

    # Send push notification to plan owner's devices
    await send_push_to_user(plan_user_id, "Check-in Overdue", message)


async def send_sms(phone: str, message: str):
    """Send SMS notification."""
    if settings.SMS_BACKEND == "twilio":
        from ..messaging.twilio_backend import send_twilio_sms
        success = await send_twilio_sms(phone, message)
        if not success:
            log.error(f"Failed to send SMS to {phone}")
    elif settings.SMS_BACKEND == "dummy":
        log.info(f"[DUMMY SMS] To: {phone} - {message}")
    else:
        log.warning(f"Unknown SMS backend: {settings.SMS_BACKEND}")


async def send_email(email: str, subject: str, body: str, html_body: Optional[str] = None):
    """Send email notification."""
    if settings.EMAIL_BACKEND == "resend":
        from ..messaging.resend_backend import send_resend_email
        success = await send_resend_email(
            to_email=email,
            subject=subject,
            text_body=body,
            html_body=html_body
        )
        if not success:
            log.error(f"Failed to send email to {email}")
    elif settings.EMAIL_BACKEND == "console":
        log.info(f"[CONSOLE EMAIL] To: {email}\nSubject: {subject}\n{body}")
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
    await send_email(email, subject, body, html_body)


async def send_plan_created_notification(plan: Any):
    """Send notification when a plan is created.

    Args:
        plan: Dictionary or Row object with keys: title, start_at, eta_at, user_id
    """
    from datetime import datetime

    # Handle both dict and Row objects
    plan_title = plan.get('title') if hasattr(plan, 'get') else plan.title
    plan_start_at = plan.get('start_at') if hasattr(plan, 'get') else plan.start_at
    plan_eta_at = plan.get('eta_at') if hasattr(plan, 'get') else plan.eta_at
    plan_user_id = plan.get('user_id') if hasattr(plan, 'get') else plan.user_id

    message = f"New trip plan created: {plan_title}"

    if plan_start_at and plan_eta_at:
        # Format times if they're strings
        if isinstance(plan_start_at, str):
            start_dt = datetime.fromisoformat(plan_start_at.replace(' ', 'T'))
            start_formatted = start_dt.strftime('%I:%M %p')
        else:
            start_formatted = plan_start_at.strftime('%I:%M %p')

        if isinstance(plan_eta_at, str):
            eta_dt = datetime.fromisoformat(plan_eta_at.replace(' ', 'T'))
            eta_formatted = eta_dt.strftime('%I:%M %p')
        else:
            eta_formatted = plan_eta_at.strftime('%I:%M %p')

        message += f" from {start_formatted} to {eta_formatted}"

    await send_push_to_user(plan_user_id, "Plan Created", message)