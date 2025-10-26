from __future__ import annotations

import logging
from typing import Optional

from twilio.rest import Client
from twilio.base.exceptions import TwilioException

from ..core.config import settings

log = logging.getLogger(__name__)

# Initialize Twilio client
twilio_client: Optional[Client] = None


def get_twilio_client() -> Optional[Client]:
    """Get or create Twilio client."""
    global twilio_client

    if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN:
        log.warning("Twilio credentials not configured")
        return None

    if twilio_client is None:
        twilio_client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)

    return twilio_client


async def send_twilio_sms(to_number: str, message: str) -> bool:
    """
    Send SMS via Twilio.

    Args:
        to_number: Phone number to send to (E.164 format preferred)
        message: SMS message content

    Returns:
        True if sent successfully, False otherwise
    """
    client = get_twilio_client()
    if not client:
        log.error("Twilio client not initialized")
        return False

    # Ensure phone number is in E.164 format
    if not to_number.startswith('+'):
        # Assume US number if no country code
        to_number = f"+1{to_number.replace('-', '').replace(' ', '').replace('(', '').replace(')', '')}"

    try:
        # Determine from parameter
        if settings.TWILIO_MESSAGING_SERVICE_SID:
            # Use messaging service (better for production)
            message_params = {
                'messaging_service_sid': settings.TWILIO_MESSAGING_SERVICE_SID,
                'to': to_number,
                'body': message
            }
        elif settings.TWILIO_FROM_NUMBER:
            # Use from number
            message_params = {
                'from_': settings.TWILIO_FROM_NUMBER,
                'to': to_number,
                'body': message
            }
        else:
            log.error("Neither TWILIO_MESSAGING_SERVICE_SID nor TWILIO_FROM_NUMBER configured")
            return False

        # Send message
        message_instance = client.messages.create(**message_params)

        log.info(f"SMS sent successfully to {to_number}, SID: {message_instance.sid}")
        return True

    except TwilioException as e:
        log.error(f"Twilio error sending SMS to {to_number}: {e}")
        return False
    except Exception as e:
        log.error(f"Unexpected error sending SMS to {to_number}: {e}")
        return False


def format_phone_for_twilio(phone: str) -> str:
    """
    Format a phone number for Twilio (E.164 format).

    Args:
        phone: Phone number in various formats

    Returns:
        Phone number in E.164 format
    """
    # Remove all non-numeric characters
    phone = ''.join(filter(str.isdigit, phone))

    # Add country code if missing (assume US)
    if len(phone) == 10:
        phone = '1' + phone

    # Add + prefix
    if not phone.startswith('+'):
        phone = '+' + phone

    return phone