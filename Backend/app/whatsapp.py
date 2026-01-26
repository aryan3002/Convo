"""
WhatsApp integration for cab bookings via Twilio.

This module handles:
- Incoming WhatsApp messages from customers
- Booking request parsing
- Price calculations and quotes
- Confirmation handling
- Status notifications
"""

import logging
import re
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
from twilio.rest import Client
from twilio.twiml.messaging_response import MessagingResponse

from .core.config import get_settings

logger = logging.getLogger(__name__)

# Get settings (which loads from .env)
settings = get_settings()

# Twilio configuration from settings
TWILIO_ACCOUNT_SID = settings.twilio_account_sid
TWILIO_AUTH_TOKEN = settings.twilio_auth_token
TWILIO_WHATSAPP_NUMBER = settings.twilio_whatsapp_number or "whatsapp:+14155238886"

# Initialize Twilio client
twilio_client = None
if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN:
    try:
        twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        logger.info("✅ Twilio client initialized successfully")
    except Exception as e:
        logger.error(f"❌ Failed to initialize Twilio client: {e}")
else:
    logger.warning("⚠️ Twilio credentials not configured. WhatsApp features disabled.")


class BookingParseError(Exception):
    """Raised when unable to parse booking request from message."""
    pass


def parse_booking_request(message: str) -> Dict[str, str]:
    """
    Parse a WhatsApp message to extract booking details.
    
    Supports two formats:
    1. Structured format:
       Book cab
       From: 123 Main St Phoenix
       To: Airport
       Time: Tomorrow 3pm
       Passengers: 2
       Type: Sedan
    
    2. Natural language (basic):
       "I need a cab from downtown Phoenix to airport tomorrow at 3pm for 2 people"
    
    Args:
        message: Raw message text from customer
        
    Returns:
        Dictionary with keys: pickup_text, drop_text, pickup_time, passengers, vehicle_type
        
    Raises:
        BookingParseError: If required fields cannot be extracted
    """
    message = message.strip()
    parsed = {}
    
    # Try structured format first
    pickup_match = re.search(r'From:\s*(.+?)(?=\n|To:|$)', message, re.IGNORECASE)
    dropoff_match = re.search(r'To:\s*(.+?)(?=\n|Time:|$)', message, re.IGNORECASE)
    time_match = re.search(r'Time:\s*(.+?)(?=\n|Passengers:|$)', message, re.IGNORECASE)
    passengers_match = re.search(r'Passengers:\s*(\d+)', message, re.IGNORECASE)
    type_match = re.search(r'Type:\s*(sedan|suv|van)', message, re.IGNORECASE)
    
    if pickup_match and dropoff_match:
        # Structured format detected
        parsed['pickup_text'] = pickup_match.group(1).strip()
        parsed['drop_text'] = dropoff_match.group(1).strip()
        
        if time_match:
            parsed['pickup_time'] = parse_time_string(time_match.group(1).strip())
        
        if passengers_match:
            parsed['passengers'] = int(passengers_match.group(1))
        else:
            parsed['passengers'] = 1  # Default
        
        if type_match:
            vehicle_map = {'sedan': 'SEDAN_4', 'suv': 'SUV', 'van': 'VAN'}
            parsed['vehicle_type'] = vehicle_map[type_match.group(1).lower()]
        else:
            parsed['vehicle_type'] = 'SEDAN_4'  # Default
            
    else:
        # Try natural language parsing (basic regex patterns)
        # Pattern: "from X to Y"
        from_to = re.search(r'from\s+(.+?)\s+to\s+(.+?)(?:\s+(?:at|on|tomorrow|today)|$)', message, re.IGNORECASE)
        if from_to:
            parsed['pickup_text'] = from_to.group(1).strip()
            parsed['drop_text'] = from_to.group(2).strip()
        
        # Extract time: "at 3pm", "tomorrow 3pm", "today at 5pm"
        time_patterns = [
            r'(?:at|@)\s*(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)',
            r'(tomorrow|today)\s+(?:at\s*)?(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)',
        ]
        for pattern in time_patterns:
            time_match = re.search(pattern, message, re.IGNORECASE)
            if time_match:
                time_str = time_match.group(0)
                parsed['pickup_time'] = parse_time_string(time_str)
                break
        
        # Extract passengers: "2 people", "for 3", "3 passengers"
        pax_match = re.search(r'(?:for\s+)?(\d+)\s*(?:people|passengers|pax)', message, re.IGNORECASE)
        if pax_match:
            parsed['passengers'] = int(pax_match.group(1))
        else:
            parsed['passengers'] = 1
        
        # Vehicle type
        if re.search(r'\bsuv\b', message, re.IGNORECASE):
            parsed['vehicle_type'] = 'SUV'
        elif re.search(r'\bvan\b', message, re.IGNORECASE):
            parsed['vehicle_type'] = 'VAN'
        else:
            parsed['vehicle_type'] = 'SEDAN_4'
    
    # Validate required fields
    if 'pickup_text' not in parsed or 'drop_text' not in parsed:
        raise BookingParseError(
            "I couldn't find pickup and dropoff locations. Please use this format:\n\n"
            "From: Your pickup address\n"
            "To: Your destination\n"
            "Time: When you need the ride\n"
            "Passengers: Number of passengers"
        )
    
    # Set default pickup_time if not provided (1 hour from now)
    if 'pickup_time' not in parsed:
        parsed['pickup_time'] = (datetime.utcnow() + timedelta(hours=1)).isoformat()
    
    return parsed


def parse_time_string(time_str: str) -> str:
    """
    Parse time string to ISO datetime.
    
    Examples:
        "3pm" -> Today at 3pm
        "tomorrow 3pm" -> Tomorrow at 3pm
        "today at 5:30pm" -> Today at 5:30pm
        "14:00" -> Today at 2pm
    
    Args:
        time_str: Time string from message
        
    Returns:
        ISO format datetime string
    """
    time_str = time_str.lower().strip()
    now = datetime.now()
    
    # Check for "tomorrow" or "today"
    is_tomorrow = 'tomorrow' in time_str
    
    # Extract time portion
    time_match = re.search(r'(\d{1,2})(?::(\d{2}))?\s*(am|pm)?', time_str)
    if not time_match:
        # Default to 1 hour from now
        return (now + timedelta(hours=1)).isoformat()
    
    hour = int(time_match.group(1))
    minute = int(time_match.group(2)) if time_match.group(2) else 0
    period = time_match.group(3)
    
    # Convert to 24-hour format
    if period == 'pm' and hour < 12:
        hour += 12
    elif period == 'am' and hour == 12:
        hour = 0
    
    # Create datetime
    target_date = now.date()
    if is_tomorrow:
        target_date = (now + timedelta(days=1)).date()
    
    target_time = datetime.combine(target_date, datetime.min.time()).replace(hour=hour, minute=minute)
    
    # If time is in the past, assume tomorrow
    if target_time < now and not is_tomorrow:
        target_time += timedelta(days=1)
    
    return target_time.isoformat()


def send_whatsapp_message(to: str, body: str) -> bool:
    """
    Send a WhatsApp message via Twilio.
    
    Args:
        to: Recipient phone number (format: whatsapp:+1234567890)
        body: Message text
        
    Returns:
        True if message sent successfully, False otherwise
    """
    if not twilio_client:
        logger.error("Twilio client not initialized. Cannot send WhatsApp message.")
        return False
    
    try:
        # Ensure phone number has whatsapp: prefix
        if not to.startswith('whatsapp:'):
            to = f'whatsapp:{to}'
        
        message = twilio_client.messages.create(
            from_=TWILIO_WHATSAPP_NUMBER,
            to=to,
            body=body
        )
        
        logger.info(f"✅ WhatsApp message sent: {message.sid} to {to}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Failed to send WhatsApp message to {to}: {e}")
        return False


def format_price_quote(
    pickup_text: str,
    drop_text: str,
    distance_miles: float,
    final_price: float,
    vehicle_type: str,
    duration_minutes: int
) -> str:
    """
    Format a price quote message for customer.
    
    Args:
        pickup_text: Pickup location
        drop_text: Dropoff location
        distance_miles: Trip distance
        final_price: Calculated fare
        vehicle_type: Vehicle type (SEDAN_4, SUV, VAN)
        duration_minutes: Estimated trip duration
        
    Returns:
        Formatted message string
    """
    vehicle_names = {
        'SEDAN_4': 'Sedan (4 passengers)',
        'SUV': 'SUV (6 passengers)',
        'VAN': 'Van (8+ passengers)'
    }
    
    vehicle_display = vehicle_names.get(vehicle_type, vehicle_type)
    
    message = f"""🚖 *Ride Quote*

📍 From: {pickup_text}
📍 To: {drop_text}

🚗 Vehicle: {vehicle_display}
📏 Distance: {distance_miles:.1f} miles
⏱️ Est. Time: {duration_minutes} minutes
💵 *Fare: ${final_price:.2f}*

Reply *YES* to confirm booking
Reply *NO* to cancel"""
    
    return message


def format_booking_confirmation(
    booking_id: str,
    pickup_text: str,
    drop_text: str,
    pickup_time: str,
    final_price: float
) -> str:
    """
    Format booking confirmation message.
    
    Args:
        booking_id: Booking reference ID
        pickup_text: Pickup location
        drop_text: Dropoff location  
        pickup_time: Scheduled pickup time
        final_price: Final fare
        
    Returns:
        Formatted confirmation message
    """
    # Parse ISO time to readable format
    try:
        dt = datetime.fromisoformat(pickup_time.replace('Z', '+00:00'))
        time_display = dt.strftime("%B %d at %I:%M %p")
    except:
        time_display = pickup_time
    
    message = f"""✅ *Booking Confirmed!*

🎫 Reference: #{booking_id[:8].upper()}

📍 Pickup: {pickup_text}
📍 Dropoff: {drop_text}
🕐 Time: {time_display}
💵 Fare: ${final_price:.2f}

We'll notify you when a driver is assigned. Thank you for choosing us! 🙏"""
    
    return message


def format_owner_confirmation_message(
    booking_id: str,
    pickup_text: str,
    drop_text: str,
    pickup_time: str,
    final_price: float
) -> str:
    """
    Format owner confirmation notification to customer.
    
    Args:
        booking_id: Booking reference ID
        pickup_text: Pickup location
        drop_text: Dropoff location
        pickup_time: Scheduled pickup time (ISO format)
        final_price: Final fare
        
    Returns:
        Formatted notification message
    """
    # Parse ISO time to readable format
    try:
        dt = datetime.fromisoformat(pickup_time.replace('Z', '+00:00'))
        time_display = dt.strftime("%B %d at %I:%M %p")
    except:
        time_display = pickup_time
    
    message = f"""✅ *Booking Confirmed by Owner!*

🎫 Reference: #{booking_id[:8].upper()}

📍 Pickup: {pickup_text}
📍 Dropoff: {drop_text}
🕐 Time: {time_display}
💵 Fare: ${final_price:.2f}

Your ride has been confirmed! We'll notify you when a driver is assigned. 🙏"""
    
    return message


def format_rejection_notification(
    booking_id: str,
    pickup_text: str,
    drop_text: str,
    reason: Optional[str] = None
) -> str:
    """
    Format booking rejection notification to customer.
    
    Args:
        booking_id: Booking reference ID
        pickup_text: Pickup location
        drop_text: Dropoff location
        reason: Optional rejection reason
        
    Returns:
        Formatted notification message
    """
    reason_text = f"\n\n📝 Reason: {reason}" if reason else ""
    
    message = f"""❌ *Booking Cancelled*

🎫 Reference: #{booking_id[:8].upper()}

📍 From: {pickup_text}
📍 To: {drop_text}{reason_text}

We apologize for the inconvenience. Please try booking again or contact us for assistance. 🙏"""
    
    return message


def format_driver_assigned_message(
    booking_id: str,
    driver_name: str,
    driver_phone: str,
    vehicle_info: str
) -> str:
    """
    Format driver assignment notification.
    
    Args:
        booking_id: Booking reference ID
        driver_name: Driver's name
        driver_phone: Driver's contact number
        vehicle_info: Vehicle description (e.g., "Toyota Camry - ABC123")
        
    Returns:
        Formatted notification message
    """
    message = f"""👨‍✈️ *Driver Assigned!*

🎫 Booking: #{booking_id[:8].upper()}

👤 Driver: {driver_name}
📞 Phone: {driver_phone}
🚗 Vehicle: {vehicle_info}

Your driver will arrive at the scheduled time. Have a great trip! 🎉"""
    
    return message


def format_cancellation_confirmation(
    booking_id: str,
    pickup_text: str,
    drop_text: str
) -> str:
    """
    Format cancellation confirmation for customer.
    
    Args:
        booking_id: Booking reference ID
        pickup_text: Pickup location
        drop_text: Dropoff location
        
    Returns:
        Formatted confirmation message
    """
    message = f"""✅ *Ride Cancelled Successfully*

🎫 Reference: #{booking_id[:8].upper()}

📍 From: {pickup_text}
📍 To: {drop_text}

Your ride has been cancelled. No charges will be applied. Book again anytime! 🙏"""
    
    return message


def format_ride_selection_list(bookings: list) -> str:
    """
    Format list of rides for customer to select which one to cancel.
    
    Args:
        bookings: List of booking objects
        
    Returns:
        Formatted message with numbered list
    """
    message = "You have multiple upcoming rides. Reply with the number to cancel:\n\n"
    
    for idx, booking in enumerate(bookings, 1):
        # Parse pickup time
        try:
            if hasattr(booking.pickup_time, 'strftime'):
                time_display = booking.pickup_time.strftime("%b %d at %I:%M %p")
            else:
                dt = datetime.fromisoformat(str(booking.pickup_time).replace('Z', '+00:00'))
                time_display = dt.strftime("%b %d at %I:%M %p")
        except:
            time_display = str(booking.pickup_time)
        
        # Get status badge
        status_emoji = {
            'PENDING': '⏳',
            'CONFIRMED': '✅',
            'COMPLETED': '🏁',
            'REJECTED': '❌',
            'CANCELLED': '❌'
        }.get(booking.status.value if hasattr(booking.status, 'value') else booking.status, '📋')
        
        message += f"""*{idx}.* {status_emoji} #{str(booking.id)[:8].upper()}
   📍 {booking.pickup_text} → {booking.drop_text}
   🕐 {time_display}
   💵 ${booking.final_price:.2f}

"""
    
    message += "Reply with just the number (e.g., '1') or 'CANCEL' to abort."
    return message


def format_no_rides_to_cancel() -> str:
    """
    Format message when customer has no cancellable rides.
    
    Returns:
        Formatted message
    """
    return """ℹ️ *No Active Rides*

You don't have any upcoming rides to cancel.

To book a new ride, send me your pickup and dropoff locations! 🚖"""


def format_error_message(error_type: str) -> str:
    """
    Format user-friendly error messages.
    
    Args:
        error_type: Type of error (parse_error, calc_error, booking_error)
        
    Returns:
        Formatted error message
    """
    messages = {
        'parse_error': """❌ I couldn't understand your booking request.

Please use this format:

From: Your pickup address
To: Your destination  
Time: When you need the ride
Passengers: Number of passengers

Example:
From: 123 Main St Phoenix AZ
To: Sky Harbor Airport
Time: Tomorrow 3pm
Passengers: 2""",
        
        'calc_error': """❌ Unable to calculate route.

Please check that your addresses are valid and include city/state.

Example:
From: 123 Main St, Phoenix, AZ
To: Phoenix Sky Harbor Airport, Phoenix, AZ""",
        
        'booking_error': """❌ Unable to create booking.

Please try again or contact us directly for assistance.""",
        
        'shop_not_found': """❌ Service not available.

This number is not associated with an active cab service."""
    }
    
    return messages.get(error_type, "❌ An error occurred. Please try again.")


def get_help_message() -> str:
    """
    Get help/instructions message for customers.
    
    Returns:
        Help message text
    """
    return """🚖 *Welcome to our Cab Service!*

To book a ride, send a message with:

From: Your pickup address
To: Your destination
Time: When you need the ride
Passengers: Number of passengers
Type: Sedan, SUV, or Van (optional)

*Example:*
From: Downtown Phoenix
To: Sky Harbor Airport
Time: Tomorrow 3pm
Passengers: 2
Type: Sedan

We'll send you a price quote instantly!

Need help? Just send "HELP" anytime."""
