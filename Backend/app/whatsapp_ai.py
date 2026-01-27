"""
OpenAI-powered natural language processing for WhatsApp cab bookings.

Uses GPT function calling to extract booking details from conversational messages.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Optional
import openai

from .core.config import get_settings

logger = logging.getLogger(__name__)

# Get settings (which loads from .env)
settings = get_settings()

# OpenAI configuration from settings
openai.api_key = settings.openai_api_key


async def parse_booking_with_ai(message: str) -> Optional[Dict[str, str]]:
    """
    Use OpenAI GPT to extract booking details from natural language.
    
    Examples:
        "I need a ride from downtown Phoenix to the airport tomorrow at 3pm"
        "Book me a cab from 123 Main St to Sky Harbor for 2 people"
        "Can you get me an SUV from my hotel to the conference center at 5pm?"
    
    Args:
        message: Customer's WhatsApp message
        
    Returns:
        Dictionary with extracted fields or None if parsing fails
    """
    if not openai.api_key:
        logger.warning("OpenAI API key not configured. Falling back to regex parsing.")
        return None
    
    try:
        client = openai.OpenAI(api_key=openai.api_key)
        
        # Get current date/time for context
        now = datetime.now()
        current_date_str = now.strftime("%A, %B %d, %Y")
        current_time_str = now.strftime("%I:%M %p")
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": f"""You are a cab booking assistant. Extract booking details from customer messages.

IMPORTANT - Current date/time context:
- Today is: {current_date_str}
- Current time: {current_time_str}

Rules:
- Extract pickup location (pickup_text) - include full address with city/state
- Extract dropoff location (drop_text) - include full address with city/state
- Extract pickup time (pickup_time) - IMPORTANT: Return in YYYY-MM-DDTHH:MM:SS format in LOCAL TIME (not UTC)
- For "tomorrow", use {(now + timedelta(days=1)).strftime("%Y-%m-%d")}
- For "today", use {now.strftime("%Y-%m-%d")}
- If only time given (like "10 am" or "12 pm"), use tomorrow's date at that time
- If customer says "12 pm", interpret as 12:00 (noon), NOT 00:00
- Extract number of passengers (passengers) - default to 1 if not mentioned
- Extract vehicle type (vehicle_type): SEDAN_4, SUV, or VAN - default to SEDAN_4
- If time not specified, use 1 hour from current time
- TIMEZONE: Assume customer is in Arizona/Phoenix timezone (MST/Arizona - no DST)

Return ONLY a JSON object with these exact keys:
{{
  "pickup_text": "full pickup address",
  "drop_text": "full dropoff address",
  "pickup_time": "ISO datetime string in LOCAL Arizona time (YYYY-MM-DDTHH:MM:SS)",
  "passengers": number,
  "vehicle_type": "SEDAN_4|SUV|VAN"
}}"""
                },
                {
                    "role": "user",
                    "content": f"Extract booking details from: {message}"
                }
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
        )
        
        import json
        result = json.loads(response.choices[0].message.content)
        
        # Validate required fields
        if not result.get('pickup_text') or not result.get('drop_text'):
            logger.warning(f"AI parsing incomplete: {result}")
            return None
        
        # Set defaults
        if not result.get('pickup_time'):
            result['pickup_time'] = (datetime.now() + timedelta(hours=1)).isoformat()
        
        if not result.get('passengers'):
            result['passengers'] = 1
        
        if not result.get('vehicle_type'):
            result['vehicle_type'] = 'SEDAN_4'
        
        # Ensure vehicle_type is valid
        if result['vehicle_type'] not in ['SEDAN_4', 'SUV', 'VAN']:
            result['vehicle_type'] = 'SEDAN_4'
        
        # Validate and convert pickup_time from Arizona local time to UTC
        try:
            from zoneinfo import ZoneInfo
            
            # Parse the time (should be in Arizona local time)
            time_str = result['pickup_time'].replace('Z', '')
            parsed_time = datetime.fromisoformat(time_str)
            
            # If time is naive (no timezone), assume it's Arizona time
            if parsed_time.tzinfo is None:
                arizona_tz = ZoneInfo("America/Phoenix")  # Arizona doesn't observe DST
                # Create aware datetime in Arizona timezone
                local_time = parsed_time.replace(tzinfo=arizona_tz)
                # Convert to UTC
                utc_time = local_time.astimezone(ZoneInfo("UTC"))
                result['pickup_time'] = utc_time.isoformat()
                logger.info(f"Converted pickup time: {parsed_time} (AZ) -> {utc_time} (UTC)")
            else:
                # Already has timezone info, just convert to UTC
                utc_time = parsed_time.astimezone(ZoneInfo("UTC"))
                result['pickup_time'] = utc_time.isoformat()
            
            # Validate it's not in the past
            current_utc = datetime.now(ZoneInfo("UTC"))
            if utc_time < current_utc - timedelta(hours=1):  # Allow 1 hour grace period
                logger.warning(f"AI returned past time {utc_time}, fixing to 1 hour from now")
                result['pickup_time'] = (current_utc + timedelta(hours=1)).isoformat()
        except Exception as e:
            logger.error(f"Error validating pickup_time: {e}")
            # Default to 1 hour from now in UTC
            from zoneinfo import ZoneInfo
            result['pickup_time'] = (datetime.now(ZoneInfo("UTC")) + timedelta(hours=1)).isoformat()
        
        logger.info(f"✅ AI parsed booking: {result}")
        return result
        
    except Exception as e:
        logger.error(f"AI parsing failed: {e}")
        return None

async def detect_cancel_intent(message: str) -> bool:
    """
    Detect if customer wants to cancel a ride.
    
    Args:
        message: Customer's WhatsApp message
        
    Returns:
        True if cancel intent detected, False otherwise
    """
    if not openai.api_key:
        # Fallback to keyword matching
        cancel_keywords = ['cancel', 'cancellation', 'delete', 'remove', 'stop', 'abort']
        message_lower = message.lower()
        return any(keyword in message_lower for keyword in cancel_keywords)
    
    try:
        client = openai.OpenAI(api_key=openai.api_key)
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": """You are a cab booking assistant analyzing customer intent.

Determine if the customer wants to CANCEL an existing ride/booking.

Examples of cancel intent:
- "I want to cancel my ride"
- "Cancel booking"
- "Delete my trip"
- "I don't need the cab anymore"
- "Please remove my booking"

Return ONLY a JSON object:
{
  "is_cancel": true or false
}"""
                },
                {
                    "role": "user",
                    "content": f"Does this message indicate cancel intent? Message: {message}"
                }
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
        )
        
        import json
        result = json.loads(response.choices[0].message.content)
        return result.get('is_cancel', False)
        
    except Exception as e:
        logger.error(f"Cancel intent detection failed: {e}")
        # Fallback to keyword matching
        cancel_keywords = ['cancel', 'cancellation', 'delete', 'remove', 'stop', 'abort']
        message_lower = message.lower()
        return any(keyword in message_lower for keyword in cancel_keywords)