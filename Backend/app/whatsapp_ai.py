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
- Extract pickup time (pickup_time) - convert to ISO datetime format
- For "tomorrow", use {(now + timedelta(days=1)).strftime("%Y-%m-%d")}
- For "today", use {now.strftime("%Y-%m-%d")}
- If only time given (like "10 am"), assume tomorrow if that makes sense
- Extract number of passengers (passengers) - default to 1 if not mentioned
- Extract vehicle type (vehicle_type): SEDAN_4, SUV, or VAN - default to SEDAN_4
- If time not specified, use 1 hour from current time

Return ONLY a JSON object with these exact keys:
{{
  "pickup_text": "full pickup address",
  "drop_text": "full dropoff address",
  "pickup_time": "ISO datetime string (YYYY-MM-DDTHH:MM:SS)",
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
        
        # Validate and fix pickup_time - ensure it's not in October when we're in January
        try:
            parsed_time = datetime.fromisoformat(result['pickup_time'].replace('Z', '+00:00'))
            current_time = datetime.now()
            
            # If the parsed date is way in the past (like October when it's January), fix it
            if parsed_time < current_time - timedelta(days=30):
                logger.warning(f"AI returned past date {parsed_time}, fixing to tomorrow")
                # Use tomorrow at the same time
                tomorrow = current_time + timedelta(days=1)
                fixed_time = tomorrow.replace(hour=parsed_time.hour, minute=parsed_time.minute, second=0, microsecond=0)
                result['pickup_time'] = fixed_time.isoformat()
        except Exception as e:
            logger.error(f"Error validating pickup_time: {e}")
            # Default to 1 hour from now
            result['pickup_time'] = (datetime.now() + timedelta(hours=1)).isoformat()
        
        logger.info(f"✅ AI parsed booking: {result}")
        return result
        
    except Exception as e:
        logger.error(f"AI parsing failed: {e}")
        return None
