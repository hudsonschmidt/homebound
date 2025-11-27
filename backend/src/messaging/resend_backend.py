from __future__ import annotations

import resend
import logging
from typing import Optional, List, Dict, Any

from ..config import settings

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


def create_trip_created_email_html(
    contact_name: str,
    user_name: str,
    plan_title: str,
    activity: str,
    start_time: str,
    expected_time: str,
    location: Optional[str] = None
) -> str:
    """Create HTML email template for trip created notifications to contacts."""
    location_html = ""
    if location:
        location_html = f"<p><strong>📍 Location:</strong> {location}</p>"

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
            background: #f5f5f5;
        }}
        .container {{
            background: #fff;
            border: 1px solid #ddd;
            border-radius: 12px;
            padding: 30px;
        }}
        .header {{
            background: linear-gradient(135deg, #6C63FF, #4ECDC4);
            color: white;
            padding: 20px;
            margin: -30px -30px 25px -30px;
            border-radius: 12px 12px 0 0;
            text-align: center;
        }}
        h1 {{
            margin: 0;
            font-size: 22px;
            font-weight: 600;
        }}
        .trip-card {{
            background: #f8f9fa;
            border-radius: 8px;
            padding: 20px;
            margin: 20px 0;
        }}
        .trip-card p {{
            margin: 8px 0;
        }}
        .info-box {{
            background: #e8f4fd;
            border-left: 4px solid #6C63FF;
            padding: 15px;
            margin: 20px 0;
            border-radius: 0 8px 8px 0;
        }}
        .footer {{
            margin-top: 30px;
            padding-top: 20px;
            border-top: 1px solid #eee;
            font-size: 14px;
            color: #666;
            text-align: center;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🏔️ You're an Emergency Contact</h1>
        </div>

        <p>Hi {contact_name},</p>

        <p><strong>{user_name}</strong> has added you as an emergency contact for an upcoming trip on Homebound.</p>

        <div class="trip-card">
            <p><strong>🎯 Trip:</strong> {plan_title}</p>
            <p><strong>🎿 Activity:</strong> {activity}</p>
            <p><strong>🕐 Starting:</strong> {start_time}</p>
            <p><strong>⏰ Expected back by:</strong> {expected_time}</p>
            {location_html}
        </div>

        <div class="info-box">
            <p><strong>What does this mean?</strong></p>
            <p>If {user_name} doesn't check in by their expected return time (plus a grace period), you'll receive an alert email asking you to check on them.</p>
        </div>

        <p>No action is needed right now. We just wanted you to know they're heading out and trust you to be there if needed.</p>

        <div class="footer">
            <p>Safe travels! 🌟</p>
            <p style="font-size: 12px; color: #999;">
                Sent via Homebound - Personal Safety for Adventurers
            </p>
        </div>
    </div>
</body>
</html>
"""


def create_trip_starting_now_email_html(
    contact_name: str,
    user_name: str,
    plan_title: str,
    activity: str,
    expected_time: str,
    location: Optional[str] = None
) -> str:
    """Create HTML email template for trip starting immediately notifications."""
    location_html = ""
    if location:
        location_html = f"<p><strong>📍 Location:</strong> {location}</p>"

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
            background: #f5f5f5;
        }}
        .container {{
            background: #fff;
            border: 1px solid #ddd;
            border-radius: 12px;
            padding: 30px;
        }}
        .header {{
            background: linear-gradient(135deg, #FF6B6B, #FF8E53);
            color: white;
            padding: 20px;
            margin: -30px -30px 25px -30px;
            border-radius: 12px 12px 0 0;
            text-align: center;
        }}
        h1 {{
            margin: 0;
            font-size: 22px;
            font-weight: 600;
        }}
        .active-badge {{
            display: inline-block;
            background: #fff;
            color: #FF6B6B;
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 600;
            margin-top: 8px;
        }}
        .trip-card {{
            background: #fff8f0;
            border-radius: 8px;
            padding: 20px;
            margin: 20px 0;
            border-left: 4px solid #FF6B6B;
        }}
        .trip-card p {{
            margin: 8px 0;
        }}
        .info-box {{
            background: #fff3cd;
            border-left: 4px solid #ffc107;
            padding: 15px;
            margin: 20px 0;
            border-radius: 0 8px 8px 0;
        }}
        .footer {{
            margin-top: 30px;
            padding-top: 20px;
            border-top: 1px solid #eee;
            font-size: 14px;
            color: #666;
            text-align: center;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🚀 Trip Started!</h1>
            <div class="active-badge">ACTIVE NOW</div>
        </div>

        <p>Hi {contact_name},</p>

        <p><strong>{user_name}</strong> has just started a trip and added you as an emergency contact.</p>

        <div class="trip-card">
            <p><strong>🎯 Trip:</strong> {plan_title}</p>
            <p><strong>🎿 Activity:</strong> {activity}</p>
            <p><strong>⏰ Expected back by:</strong> {expected_time}</p>
            {location_html}
        </div>

        <div class="info-box">
            <p><strong>⚠️ What does this mean?</strong></p>
            <p>If {user_name} doesn't check in by their expected return time (plus a grace period), you'll receive an urgent alert email asking you to check on them.</p>
        </div>

        <p>No action is needed right now. We just wanted you to know they're currently out and trust you to be there if needed.</p>

        <div class="footer">
            <p>Stay safe out there! 🌟</p>
            <p style="font-size: 12px; color: #999;">
                Sent via Homebound - Personal Safety for Adventurers
            </p>
        </div>
    </div>
</body>
</html>
"""


def create_checkin_update_email_html(
    contact_name: str,
    user_name: str,
    plan_title: str,
    activity: str,
    checkin_time: str
) -> str:
    """Create HTML email template for check-in update notifications."""
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
            background: #f5f5f5;
        }}
        .container {{
            background: #fff;
            border: 1px solid #ddd;
            border-radius: 12px;
            padding: 30px;
        }}
        .header {{
            background: linear-gradient(135deg, #17a2b8, #20c997);
            color: white;
            padding: 20px;
            margin: -30px -30px 25px -30px;
            border-radius: 12px 12px 0 0;
            text-align: center;
        }}
        h1 {{
            margin: 0;
            font-size: 22px;
            font-weight: 600;
        }}
        .update-box {{
            background: #e8f8f5;
            border: 1px solid #bee5eb;
            border-radius: 8px;
            padding: 20px;
            margin: 20px 0;
            text-align: center;
        }}
        .update-box .icon {{
            font-size: 36px;
            margin-bottom: 10px;
        }}
        .trip-info {{
            background: #f8f9fa;
            border-radius: 8px;
            padding: 15px;
            margin: 20px 0;
        }}
        .footer {{
            margin-top: 30px;
            padding-top: 20px;
            border-top: 1px solid #eee;
            font-size: 14px;
            color: #666;
            text-align: center;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📍 Check-in Update</h1>
        </div>

        <p>Hi {contact_name},</p>

        <div class="update-box">
            <div class="icon">✓</div>
            <p><strong>{user_name}</strong> just checked in!</p>
            <p style="font-size: 14px; color: #666;">Check-in time: {checkin_time}</p>
        </div>

        <div class="trip-info">
            <p><strong>Trip:</strong> {plan_title}</p>
            <p><strong>Activity:</strong> {activity}</p>
        </div>

        <p>This is just an update to let you know they're doing well. Their trip is still active.</p>

        <div class="footer">
            <p style="font-size: 12px; color: #999;">
                Sent via Homebound - Personal Safety for Adventurers
            </p>
        </div>
    </div>
</body>
</html>
"""


def create_trip_extended_email_html(
    contact_name: str,
    user_name: str,
    plan_title: str,
    activity: str,
    extended_by: int,
    new_eta: str
) -> str:
    """Create HTML email template for trip extended notifications."""
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
            background: #f5f5f5;
        }}
        .container {{
            background: #fff;
            border: 1px solid #ddd;
            border-radius: 12px;
            padding: 30px;
        }}
        .header {{
            background: linear-gradient(135deg, #fd7e14, #ffc107);
            color: white;
            padding: 20px;
            margin: -30px -30px 25px -30px;
            border-radius: 12px 12px 0 0;
            text-align: center;
        }}
        h1 {{
            margin: 0;
            font-size: 22px;
            font-weight: 600;
        }}
        .update-box {{
            background: #fff8e1;
            border: 1px solid #ffecb3;
            border-radius: 8px;
            padding: 20px;
            margin: 20px 0;
            text-align: center;
        }}
        .update-box .icon {{
            font-size: 36px;
            margin-bottom: 10px;
        }}
        .time-change {{
            background: #f8f9fa;
            border-radius: 8px;
            padding: 15px;
            margin: 20px 0;
        }}
        .new-eta {{
            font-size: 18px;
            font-weight: 600;
            color: #fd7e14;
        }}
        .footer {{
            margin-top: 30px;
            padding-top: 20px;
            border-top: 1px solid #eee;
            font-size: 14px;
            color: #666;
            text-align: center;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>⏱️ Trip Extended</h1>
        </div>

        <p>Hi {contact_name},</p>

        <div class="update-box">
            <div class="icon">🕐</div>
            <p><strong>{user_name}</strong> extended their trip by {extended_by} minutes</p>
        </div>

        <div class="time-change">
            <p><strong>Trip:</strong> {plan_title}</p>
            <p><strong>Activity:</strong> {activity}</p>
            <p><strong>New expected return:</strong> <span class="new-eta">{new_eta}</span></p>
        </div>

        <p>This means they checked in and need a bit more time. The trip is still active and they're doing well.</p>

        <div class="footer">
            <p style="font-size: 12px; color: #999;">
                Sent via Homebound - Personal Safety for Adventurers
            </p>
        </div>
    </div>
</body>
</html>
"""


def create_trip_completed_email_html(
    contact_name: str,
    user_name: str,
    plan_title: str,
    activity: str,
) -> str:
    """Create HTML email template for trip completed notifications to contacts."""
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
            background: #f5f5f5;
        }}
        .container {{
            background: #fff;
            border: 1px solid #ddd;
            border-radius: 12px;
            padding: 30px;
        }}
        .header {{
            background: linear-gradient(135deg, #28a745, #20c997);
            color: white;
            padding: 20px;
            margin: -30px -30px 25px -30px;
            border-radius: 12px 12px 0 0;
            text-align: center;
        }}
        h1 {{
            margin: 0;
            font-size: 22px;
            font-weight: 600;
        }}
        .success-box {{
            background: #d4edda;
            border: 1px solid #c3e6cb;
            border-radius: 8px;
            padding: 20px;
            margin: 20px 0;
            text-align: center;
        }}
        .success-box .icon {{
            font-size: 48px;
            margin-bottom: 10px;
        }}
        .trip-info {{
            background: #f8f9fa;
            border-radius: 8px;
            padding: 15px;
            margin: 20px 0;
        }}
        .footer {{
            margin-top: 30px;
            padding-top: 20px;
            border-top: 1px solid #eee;
            font-size: 14px;
            color: #666;
            text-align: center;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>✅ Good News!</h1>
        </div>

        <p>Hi {contact_name},</p>

        <div class="success-box">
            <div class="icon">🎉</div>
            <p><strong>{user_name}</strong> has checked in safely!</p>
        </div>

        <div class="trip-info">
            <p><strong>Trip:</strong> {plan_title}</p>
            <p><strong>Activity:</strong> {activity}</p>
        </div>

        <p>Their adventure is complete and they've arrived safely. No action needed on your part.</p>

        <p>Thanks for being there as an emergency contact!</p>

        <div class="footer">
            <p>Until the next adventure! 🌄</p>
            <p style="font-size: 12px; color: #999;">
                Sent via Homebound - Personal Safety for Adventurers
            </p>
        </div>
    </div>
</body>
</html>
"""


def create_overdue_resolved_email_html(
    contact_name: str,
    user_name: str,
    plan_title: str,
    activity: str,
) -> str:
    """Create HTML email template for overdue resolved notifications to contacts.

    This is sent when a user who was overdue has now checked in safely.
    Uses a celebratory but urgent style to clearly communicate the good news.
    """
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
            background: #f5f5f5;
        }}
        .container {{
            background: #fff;
            border: 1px solid #ddd;
            border-radius: 12px;
            padding: 30px;
        }}
        .header {{
            background: linear-gradient(135deg, #28a745, #17a2b8);
            color: white;
            padding: 25px;
            margin: -30px -30px 25px -30px;
            border-radius: 12px 12px 0 0;
            text-align: center;
        }}
        h1 {{
            margin: 0;
            font-size: 26px;
            font-weight: 700;
        }}
        .all-clear-badge {{
            display: inline-block;
            background: rgba(255,255,255,0.2);
            padding: 5px 15px;
            border-radius: 20px;
            font-size: 14px;
            margin-top: 10px;
        }}
        .success-box {{
            background: linear-gradient(135deg, #d4edda, #c3e6cb);
            border: 2px solid #28a745;
            border-radius: 12px;
            padding: 25px;
            margin: 20px 0;
            text-align: center;
        }}
        .success-box .icon {{
            font-size: 64px;
            margin-bottom: 15px;
        }}
        .success-box .message {{
            font-size: 20px;
            font-weight: 600;
            color: #155724;
        }}
        .context-box {{
            background: #fff3cd;
            border: 1px solid #ffeeba;
            border-radius: 8px;
            padding: 15px;
            margin: 20px 0;
        }}
        .context-box p {{
            margin: 0;
            color: #856404;
        }}
        .trip-info {{
            background: #f8f9fa;
            border-radius: 8px;
            padding: 15px;
            margin: 20px 0;
        }}
        .footer {{
            margin-top: 30px;
            padding-top: 20px;
            border-top: 1px solid #eee;
            font-size: 14px;
            color: #666;
            text-align: center;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🎉 ALL CLEAR!</h1>
            <div class="all-clear-badge">Crisis Resolved</div>
        </div>

        <p>Hi {contact_name},</p>

        <div class="success-box">
            <div class="icon">✅</div>
            <p class="message">{user_name} is safe!</p>
        </div>

        <div class="context-box">
            <p>📋 <strong>Previous Alert Resolved:</strong> We previously notified you that {user_name} was overdue from their trip. They have now confirmed they are safe and sound.</p>
        </div>

        <div class="trip-info">
            <p><strong>Trip:</strong> {plan_title}</p>
            <p><strong>Activity:</strong> {activity}</p>
            <p><strong>Status:</strong> ✅ Completed safely</p>
        </div>

        <p><strong>No further action is needed.</strong> Thank you for being ready to help as an emergency contact!</p>

        <div class="footer">
            <p>Thank you for being there! 💚</p>
            <p style="font-size: 12px; color: #999;">
                Sent via Homebound - Personal Safety for Adventurers
            </p>
        </div>
    </div>
</body>
</html>
"""