from __future__ import annotations

import resend
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any

from ..config import settings

# Template directory
TEMPLATES_DIR = Path(__file__).parent / "emails"


def load_template(name: str) -> str:
    """Load HTML template from emails directory."""
    template_path = TEMPLATES_DIR / f"{name}.html"
    return template_path.read_text()


def render_template(name: str, **kwargs) -> str:
    """Load and render HTML template with variables.

    Uses string replacement instead of .format() to avoid conflicts
    with CSS curly braces in the templates.
    """
    template = load_template(name)
    for key, value in kwargs.items():
        template = template.replace(f"{{{key}}}", str(value))
    return template

log = logging.getLogger(__name__)

# Initialize Resend
resend_configured = False


def init_resend():
    """Initialize Resend with API key."""
    global resend_configured

    if not settings.RESEND_API_KEY:
        log.warning("Resend API key not configured")
        return False

    if not resend_configured:
        resend.api_key = settings.RESEND_API_KEY
        resend_configured = True

    return True


async def send_resend_email(
    to_email: str | List[str],
    subject: str,
    html_body: Optional[str] = None,
    text_body: Optional[str] = None,
    from_email: Optional[str] = None,
    reply_to: Optional[str] = None,
    high_priority: bool = False,
) -> bool:
    """
    Send email via Resend.

    Args:
        to_email: Email address(es) to send to
        subject: Email subject
        html_body: HTML content of email
        text_body: Plain text content of email
        from_email: From email address (defaults to RESEND_FROM_EMAIL)
        reply_to: Reply-to email address
        high_priority: If True, mark email as high priority/urgent

    Returns:
        True if sent successfully, False otherwise
    """
    if not init_resend():
        log.error("Resend not initialized")
        return False

    if not html_body and not text_body:
        log.error("Either html_body or text_body must be provided")
        return False

    # Use default from email if not provided
    if not from_email:
        from_email = settings.RESEND_FROM_EMAIL

    # Ensure to_email is a list
    if isinstance(to_email, str):
        to_email = [to_email]

    try:
        params: Dict[str, Any] = {
            "from": from_email,
            "to": to_email,
            "subject": subject,
        }

        if html_body:
            params["html"] = html_body
        if text_body:
            params["text"] = text_body
        if reply_to:
            params["reply_to"] = reply_to

        # Add high priority headers for urgent emails
        if high_priority:
            params["headers"] = {
                "X-Priority": "1",
                "X-MSMail-Priority": "High",
                "Importance": "high",
            }

        response = resend.Emails.send(params)

        log.info(f"Email sent successfully to {', '.join(to_email)}, ID: {response.get('id')}")
        return True

    except Exception as e:
        log.error(f"Resend error sending email to {', '.join(to_email)}: {e}")
        return False


def create_magic_link_email_html(email: str, code: str) -> str:
    """Create HTML email template for magic link."""
    return render_template("magic_link", code=code, email=email)


def create_overdue_notification_email_html(
    user_name: str,
    plan_title: str,
    activity: str,
    start_time: str,
    expected_time: str,
    location: Optional[str] = None,
    notes: Optional[str] = None
) -> str:
    """Create HTML email template for overdue notifications."""
    location_html = location if location else "Not specified"
    notes_text = notes if notes else "None"

    return render_template(
        "overdue",
        user_name=user_name,
        plan_title=plan_title,
        activity=activity,
        start_time=start_time,
        expected_time=expected_time,
        location_html=location_html,
        notes=notes_text
    )


def create_trip_created_email_html(
    user_name: str,
    plan_title: str,
    activity: str,
    start_time: str,
    expected_time: str,
    location: Optional[str] = None
) -> str:
    """Create HTML email template for trip created notifications to contacts."""
    location_html = location if location else "Not specified"

    return render_template(
        "new_trip",
        user_name=user_name,
        plan_title=plan_title,
        activity=activity,
        start_time=start_time,
        expected_time=expected_time,
        location_html=location_html
    )


def create_trip_starting_now_email_html(
    user_name: str,
    plan_title: str,
    activity: str,
    expected_time: str,
    location: Optional[str] = None
) -> str:
    """Create HTML email template for trip starting immediately notifications."""
    location_html = location if location else "Not specified"

    return render_template(
        "new_trip_now",
        user_name=user_name,
        plan_title=plan_title,
        activity=activity,
        expected_time=expected_time,
        location_html=location_html
    )


def create_checkin_update_email_html(
    user_name: str,
    plan_title: str,
    activity: str,
    checkin_time: str,
    expected_time: str,
    coordinates: Optional[str] = None,
    location: Optional[str] = None
) -> str:
    """Create HTML email template for check-in update notifications."""
    location_html = location if location else "Not specified"
    coordinates_text = coordinates if coordinates else "Not available"

    return render_template(
        "checkin",
        user_name=user_name,
        checkin_time=checkin_time,
        coordinates=coordinates_text,
        plan_title=plan_title,
        activity=activity,
        expected_time=expected_time,
        location_html=location_html
    )


def create_trip_extended_email_html(
    user_name: str,
    plan_title: str,
    activity: str,
    extended_by: int,
    new_eta: str,
    location: Optional[str] = None
) -> str:
    """Create HTML email template for trip extended notifications."""
    location_html = location if location else "Not specified"

    return render_template(
        "extended",
        user_name=user_name,
        extended_by=extended_by,
        plan_title=plan_title,
        activity=activity,
        new_eta=new_eta,
        location_html=location_html
    )


def create_trip_completed_email_html(
    user_name: str,
    plan_title: str,
    activity: str,
    location: Optional[str] = None
) -> str:
    """Create HTML email template for trip completed notifications to contacts."""
    location_html = location if location else "Not specified"

    return render_template(
        "completed",
        user_name=user_name,
        plan_title=plan_title,
        activity=activity,
        location_html=location_html
    )


def create_overdue_resolved_email_html(
    user_name: str,
    plan_title: str,
    activity: str,
) -> str:
    """Create HTML email template for overdue resolved notifications to contacts.

    This is sent when a user who was overdue has now checked in safely.
    """
    return render_template(
        "overdue_finished",
        user_name=user_name,
        plan_title=plan_title,
        activity=activity
    )