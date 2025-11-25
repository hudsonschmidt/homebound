import resend
import logging
from ..config import settings
from __future__ import annotations
from typing import Optional, List, Dict, Any

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

        response = resend.Emails.send(params)

        log.info(f"Email sent successfully to {', '.join(to_email)}, ID: {response.get('id')}")
        return True

    except Exception as e:
        log.error(f"Resend error sending email to {', '.join(to_email)}: {e}")
        return False


def create_magic_link_email_html(email: str, code: str) -> str:
    """Create HTML email template for magic link."""
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
                line-height: 1.6;
                color: #333;
                max-width: 600px;
                margin: 0 auto;
                padding: 20px;
            }}
            .container {{
                background: #fff;
                border: 1px solid #ddd;
                border-radius: 8px;
                padding: 30px;
            }}
            .code-box {{
                background: #f5f5f5;
                border: 2px solid #333;
                border-radius: 6px;
                padding: 20px;
                text-align: center;
                margin: 30px 0;
            }}
            .code {{
                font-size: 32px;
                font-weight: bold;
                letter-spacing: 8px;
                color: #007bff;
            }}
            .footer {{
                margin-top: 30px;
                padding-top: 20px;
                border-top: 1px solid #eee;
                font-size: 14px;
                color: #666;
            }}
            h1 {{
                color: #333;
                font-size: 24px;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Your Homebound Login Code</h1>
            <p>Hi there!</p>
            <p>We recently received a request to verify the Homebound account that’s linked to this email address. Use the code below to complete your sign-in:</p>

            <div class="code-box">
                <div class="code">{code}</div>
            </div>

            <p>This code will expire in <strong>10 minutes</strong>. If you miss it, don't worry! Just request a new one in the app.</p>
            <p>If you didn't request this code, you can safely ignore this email.</p>

            <div class="footer">
                <p>Best regards,<br>The Homebound Team</p>
                <p style="font-size: 12px; color: #999;">
                    This email was sent to {email}.
                    If you have any questions, please contact support.
                </p>
            </div>
        </div>
    </body>
    </html>
    """


def create_overdue_notification_email_html(
    contact_name: str,
    plan_title: str,
    expected_time: str,
    location: Optional[str] = None
) -> str:
    """Create HTML email template for overdue notifications."""
    location_html = ""
    if location:
        location_html = f"<p><strong>Last known location:</strong> {location}</p>"

    return f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 600px;
            margin: 0 auto;
            padding: 20px;
        }}
        .alert-container {{
            background: #fff;
            border: 3px solid #dc3545;
            border-radius: 8px;
            padding: 30px;
        }}
        .alert-header {{
            background: #dc3545;
            color: white;
            padding: 15px;
            margin: -30px -30px 20px -30px;
            border-radius: 5px 5px 0 0;
            text-align: center;
        }}
        h1 {{
            margin: 0;
            font-size: 24px;
        }}
        .plan-info {{
            background: #f8f9fa;
            border-left: 4px solid #dc3545;
            padding: 15px;
            margin: 20px 0;
        }}
        .action-needed {{
            background: #fff3cd;
            border: 1px solid #ffc107;
            border-radius: 4px;
            padding: 15px;
            margin: 20px 0;
        }}
        .footer {{
            margin-top: 30px;
            padding-top: 20px;
            border-top: 1px solid #eee;
            font-size: 14px;
            color: #666;
        }}
    </style>
</head>
<body>
    <div class="alert-container">
        <div class="alert-header">
            <h1>⚠️ URGENT: Check-in Overdue</h1>
        </div>

        <p>Dear {contact_name},</p>

        <p>You're receiving this message because you were listed as an emergency contact for a Homebound safety plan that is now overdue.</p>

        <div class="plan-info">
            <p><strong>Trip:</strong> {plan_title}</p>
            <p><strong>Expected by:</strong> {expected_time}</p>
            {location_html}
        </div>

        <div class="action-needed">
            <p><strong>Action Needed:</strong></p>
            <ul>
                <li>Try to contact the person directly</li>
                <li>If unable to reach them, consider checking their planned location</li>
                <li>If you have concerns about their safety, contact local authorities</li>
            </ul>
        </div>

        <p>This notification was sent automatically because the person did not check in by their expected time plus the grace period they set.</p>

        <div class="footer">
            <p>This is an automated message from Homebound, a personal safety application.</p>
            <p style="font-size: 12px; color: #999;">
                You received this email because you were designated as an emergency contact.
            </p>
        </div>
    </div>
</body>
</html>
"""