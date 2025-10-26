from __future__ import annotations

import logging
from typing import List, Optional

from ..core.config import settings
from ..models import Plan, Contact

log = logging.getLogger(__name__)


async def send_overdue_notifications(plan: Plan, contacts: List[Contact]):
    """Send overdue notifications to contacts via SMS, email, and push."""

    message = f"URGENT: {plan.title} was expected by {plan.eta_at.strftime('%I:%M %p')} but hasn't checked in."

    if plan.location_text:
        message += f" Last known location: {plan.location_text}"

    # Send SMS notifications
    for contact in contacts:
        if contact.phone:
            await send_sms(contact.phone, message)

    # Send Email notifications
    for contact in contacts:
        if contact.email:
            await send_email(
                contact.email,
                f"Overdue Alert: {plan.title}",
                message
            )

    # Send push notification to plan owner's devices
    await send_push_to_user(plan.user_id, "Check-in Overdue", message)


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


async def send_plan_created_notification(plan: Plan):
    """Send notification when a plan is created."""
    message = f"New trip plan created: {plan.title}"

    if plan.start_at and plan.eta_at:
        message += f" from {plan.start_at.strftime('%I:%M %p')} to {plan.eta_at.strftime('%I:%M %p')}"

    await send_push_to_user(plan.user_id, "Plan Created", message)