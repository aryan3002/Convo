"""
SMS sender utility using Twilio Programmable SMS.
"""

import logging
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException

from .core.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


def _ensure_e164_format(phone: str) -> str:
    """Ensure phone number is in E.164 format (+1...)."""
    if not phone:
        return phone
    
    # Remove spaces, dashes, parentheses
    cleaned = phone.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    
    # If it doesn't start with +, assume US and add +1
    if not cleaned.startswith("+"):
        if cleaned.startswith("1") and len(cleaned) == 11:
            cleaned = f"+{cleaned}"
        else:
            cleaned = f"+1{cleaned}"
    
    return cleaned


async def send_sms(to_phone: str, body: str) -> bool:
    """
    Send an SMS using Twilio.
    
    Args:
        to_phone: Phone number in E.164 format (+1...)
        body: SMS message body
        
    Returns:
        True if SMS was sent successfully, False otherwise
        
    Note:
        If Twilio configuration is missing, this function logs and returns False.
        If Twilio API fails, this function logs the error and returns False.
        This function should never raise exceptions to avoid breaking booking confirmation.
    """
    try:
        # Check if Twilio is configured
        if not settings.twilio_account_sid or not settings.twilio_auth_token or not settings.twilio_from_number:
            logger.warning("Twilio SMS not configured. Skipping SMS send.")
            return False
        
        # Ensure phone numbers are in E.164 format
        to_phone_formatted = _ensure_e164_format(to_phone)
        from_number_formatted = _ensure_e164_format(settings.twilio_from_number)
        
        if not to_phone_formatted:
            logger.error(f"Invalid phone number format: {to_phone}")
            return False
        
        # Initialize Twilio client
        client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
        
        # Send SMS
        message = client.messages.create(
            body=body,
            from_=from_number_formatted,
            to=to_phone_formatted
        )
        
        logger.info(f"SMS sent successfully to {to_phone_formatted[:6]}***. SID: {message.sid}")
        return True
        
    except TwilioRestException as e:
        logger.error(f"Twilio API error sending SMS to {to_phone}: {e.code} - {e.msg}")
        return False
    except Exception as e:
        logger.exception(f"Unexpected error sending SMS to {to_phone}: {e}")
        return False
