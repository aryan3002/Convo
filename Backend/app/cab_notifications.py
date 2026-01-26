"""
Cab Notifications Module

Handles notifications to cab owners when new bookings are created.
Uses the existing email infrastructure (Resend).

This module is called asynchronously from the booking creation flow.
Failures are logged but do not block booking creation.
"""

import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .cab_models import CabBooking
from .models import Shop
from .core.config import get_settings
from .emailer import send_booking_email_with_ics

logger = logging.getLogger(__name__)
settings = get_settings()


async def notify_owner_new_booking(
    session: AsyncSession,
    booking: CabBooking,
) -> bool:
    """
    Send notification to the shop owner about a new cab booking.
    
    Args:
        session: Database session
        booking: The newly created CabBooking
    
    Returns:
        True if notification was sent, False otherwise
    """
    try:
        # Get shop info
        result = await session.execute(
            select(Shop).where(Shop.id == booking.shop_id)
        )
        shop = result.scalar_one_or_none()
        
        if not shop:
            logger.warning(f"Shop not found for booking {booking.id}")
            return False
        
        # For now, log the notification - full email implementation in STEP 7
        logger.info(
            f"[CAB NOTIFICATION] New booking {booking.id} for shop '{shop.name}':\n"
            f"  Pickup: {booking.pickup_text}\n"
            f"  Drop: {booking.drop_text}\n"
            f"  Time: {booking.pickup_time}\n"
            f"  Vehicle: {booking.vehicle_type.value}\n"
            f"  Distance: {booking.distance_miles} miles\n"
            f"  Price: ${booking.final_price}"
        )
        
        # Check if email is configured
        if not settings.resend_api_key or not settings.resend_from:
            logger.warning("Email not configured (Resend). Skipping notification.")
            return False
        
        # Build email content
        subject = f"🚗 New Cab Booking Request - {booking.pickup_text} to {booking.drop_text}"
        
        html_content = f"""
        <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <h2 style="color: #1a73e8;">New Cab Booking Request</h2>
            
            <div style="background: #f8f9fa; padding: 20px; border-radius: 8px; margin: 20px 0;">
                <h3 style="margin-top: 0;">Trip Details</h3>
                <p><strong>From:</strong> {booking.pickup_text}</p>
                <p><strong>To:</strong> {booking.drop_text}</p>
                <p><strong>Pickup Time:</strong> {booking.pickup_time.strftime('%B %d, %Y at %I:%M %p')}</p>
                <p><strong>Vehicle:</strong> {booking.vehicle_type.value}</p>
                {f'<p><strong>Flight:</strong> {booking.flight_number}</p>' if booking.flight_number else ''}
                {f'<p><strong>Passengers:</strong> {booking.passengers}</p>' if booking.passengers else ''}
            </div>
            
            <div style="background: #e8f5e9; padding: 20px; border-radius: 8px; margin: 20px 0;">
                <h3 style="margin-top: 0;">Pricing</h3>
                <p><strong>Distance:</strong> {booking.distance_miles} miles</p>
                <p><strong>Duration:</strong> ~{booking.duration_minutes} minutes</p>
                <p><strong>Estimated Fare:</strong> <span style="font-size: 1.5em; color: #2e7d32;">${booking.final_price}</span></p>
            </div>
            
            {f'''
            <div style="background: #fff3e0; padding: 20px; border-radius: 8px; margin: 20px 0;">
                <h3 style="margin-top: 0;">Customer Info</h3>
                {f'<p><strong>Name:</strong> {booking.customer_name}</p>' if booking.customer_name else ''}
                {f'<p><strong>Email:</strong> {booking.customer_email}</p>' if booking.customer_email else ''}
                {f'<p><strong>Phone:</strong> {booking.customer_phone}</p>' if booking.customer_phone else ''}
            </div>
            ''' if booking.customer_name or booking.customer_email or booking.customer_phone else ''}
            
            <div style="margin: 30px 0;">
                <p>Please review this booking request in your owner dashboard.</p>
                <a href="{settings.public_api_base}/s/{shop.slug}/owner/cab/requests/{booking.id}" 
                   style="display: inline-block; background: #1a73e8; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px;">
                    View Booking Request
                </a>
            </div>
            
            <p style="color: #666; font-size: 12px; margin-top: 40px;">
                This is an automated notification from Convo AI Cab Services.
            </p>
        </body>
        </html>
        """
        
        # For now, we'll use a placeholder - in production, you'd get the owner's email
        # from shop_members table or a dedicated cab_owner field
        owner_email = settings.resend_from  # Placeholder: send to configured from address
        
        # Don't create ICS for cab bookings (not an appointment)
        # Just send a simple notification email
        import httpx
        import base64
        
        payload = {
            "from": settings.resend_from,
            "to": owner_email,
            "subject": subject,
            "html": html_content,
        }
        
        headers = {
            "Authorization": f"Bearer {settings.resend_api_key}",
            "Content-Type": "application/json",
        }
        
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                "https://api.resend.com/emails",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
        
        logger.info(f"Sent cab booking notification email for booking {booking.id}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to send cab booking notification: {e}")
        return False


async def notify_customer_booking_confirmed(
    session: AsyncSession,
    booking: CabBooking,
) -> bool:
    """
    Send confirmation notification to customer when booking is confirmed.
    
    Args:
        session: Database session
        booking: The confirmed CabBooking
    
    Returns:
        True if notification was sent, False otherwise
    """
    try:
        if not booking.customer_email:
            logger.warning(f"No customer email for booking {booking.id}, skipping notification")
            return False
        
        # Get shop info
        result = await session.execute(
            select(Shop).where(Shop.id == booking.shop_id)
        )
        shop = result.scalar_one_or_none()
        
        if not shop:
            logger.warning(f"Shop not found for booking {booking.id}")
            return False
        
        # Check if email is configured
        if not settings.resend_api_key or not settings.resend_from:
            logger.warning("Email not configured (Resend). Skipping notification.")
            return False
        
        subject = f"✅ Cab Booking Confirmed - {shop.name}"
        
        html_content = f"""
        <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <h2 style="color: #2e7d32;">Your Cab Booking is Confirmed!</h2>
            
            <p>Hello{f' {booking.customer_name}' if booking.customer_name else ''},</p>
            
            <p>Great news! Your cab booking with <strong>{shop.name}</strong> has been confirmed.</p>
            
            <div style="background: #e8f5e9; padding: 20px; border-radius: 8px; margin: 20px 0;">
                <h3 style="margin-top: 0; color: #2e7d32;">Trip Details</h3>
                <p><strong>From:</strong> {booking.pickup_text}</p>
                <p><strong>To:</strong> {booking.drop_text}</p>
                <p><strong>Pickup Time:</strong> {booking.pickup_time.strftime('%B %d, %Y at %I:%M %p')}</p>
                <p><strong>Vehicle:</strong> {booking.vehicle_type.value}</p>
                {f'<p><strong>Flight:</strong> {booking.flight_number}</p>' if booking.flight_number else ''}
            </div>
            
            <div style="background: #f8f9fa; padding: 20px; border-radius: 8px; margin: 20px 0;">
                <h3 style="margin-top: 0;">Fare</h3>
                <p style="font-size: 1.5em; color: #2e7d32; margin: 0;"><strong>${booking.final_price}</strong></p>
            </div>
            
            <p style="color: #666;">
                Your driver will contact you before pickup. Please be ready at the pickup location on time.
            </p>
            
            <p style="color: #666; font-size: 12px; margin-top: 40px;">
                Booking ID: {booking.id}
            </p>
        </body>
        </html>
        """
        
        import httpx
        
        payload = {
            "from": settings.resend_from,
            "to": booking.customer_email,
            "subject": subject,
            "html": html_content,
        }
        
        headers = {
            "Authorization": f"Bearer {settings.resend_api_key}",
            "Content-Type": "application/json",
        }
        
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                "https://api.resend.com/emails",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
        
        logger.info(f"Sent booking confirmation email to {booking.customer_email}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to send booking confirmation email: {e}")
        return False


async def notify_customer_booking_rejected(
    session: AsyncSession,
    booking: CabBooking,
) -> bool:
    """
    Send rejection notification to customer when booking is rejected.
    
    Args:
        session: Database session
        booking: The rejected CabBooking
    
    Returns:
        True if notification was sent, False otherwise
    """
    try:
        if not booking.customer_email:
            logger.warning(f"No customer email for booking {booking.id}, skipping notification")
            return False
        
        # Get shop info
        result = await session.execute(
            select(Shop).where(Shop.id == booking.shop_id)
        )
        shop = result.scalar_one_or_none()
        
        if not shop:
            logger.warning(f"Shop not found for booking {booking.id}")
            return False
        
        # Check if email is configured
        if not settings.resend_api_key or not settings.resend_from:
            logger.warning("Email not configured (Resend). Skipping notification.")
            return False
        
        subject = f"Cab Booking Update - {shop.name}"
        
        reason_text = ""
        if booking.rejection_reason:
            reason_text = f"<p><strong>Reason:</strong> {booking.rejection_reason}</p>"
        
        html_content = f"""
        <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <h2 style="color: #d32f2f;">Booking Could Not Be Confirmed</h2>
            
            <p>Hello{f' {booking.customer_name}' if booking.customer_name else ''},</p>
            
            <p>Unfortunately, we were unable to confirm your cab booking request with <strong>{shop.name}</strong>.</p>
            
            {reason_text}
            
            <div style="background: #ffebee; padding: 20px; border-radius: 8px; margin: 20px 0;">
                <h3 style="margin-top: 0;">Original Request</h3>
                <p><strong>From:</strong> {booking.pickup_text}</p>
                <p><strong>To:</strong> {booking.drop_text}</p>
                <p><strong>Pickup Time:</strong> {booking.pickup_time.strftime('%B %d, %Y at %I:%M %p')}</p>
            </div>
            
            <p>
                We apologize for any inconvenience. Please feel free to submit a new booking request 
                for a different date/time, or contact us directly for assistance.
            </p>
            
            <p style="color: #666; font-size: 12px; margin-top: 40px;">
                Booking ID: {booking.id}
            </p>
        </body>
        </html>
        """
        
        import httpx
        
        payload = {
            "from": settings.resend_from,
            "to": booking.customer_email,
            "subject": subject,
            "html": html_content,
        }
        
        headers = {
            "Authorization": f"Bearer {settings.resend_api_key}",
            "Content-Type": "application/json",
        }
        
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                "https://api.resend.com/emails",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
        
        logger.info(f"Sent booking rejection email to {booking.customer_email}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to send booking rejection email: {e}")
        return False
