"""
Router Analytics Tracking

Phase 3: RouterGPT Integration

This module provides analytics tracking for RouterGPT operations.
Tracks: location searches, delegations, and booking completions.

Usage:
    from .router_analytics import track_search, track_delegation
    
    await track_search(
        session=db_session,
        session_id=router_session_id,
        latitude=33.4255,
        longitude=-111.94,
        radius_miles=5,
        results_count=3
    )
"""

import logging
from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import Column, Integer, String, Boolean, Numeric, DateTime, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Request

from .models import Base

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────
# Analytics Model
# ────────────────────────────────────────────────────────────────

class RouterAnalytics(Base):
    """SQLAlchemy model for router_analytics table."""
    
    __tablename__ = "router_analytics"
    
    id = Column(PGUUID(as_uuid=True), primary_key=True, server_default="gen_random_uuid()")
    
    # Event identification
    event_type = Column(String(50), nullable=False, index=True)
    session_id = Column(PGUUID(as_uuid=True), index=True)
    
    # Location search data
    search_latitude = Column(Numeric(10, 7))
    search_longitude = Column(Numeric(10, 7))
    search_radius_miles = Column(Numeric(5, 2))
    search_category = Column(String(50))
    search_results_count = Column(Integer)
    
    # Delegation data
    shop_id = Column(Integer)
    shop_slug = Column(String(100))
    delegation_intent = Column(String(200))
    
    # Booking completion data
    booking_id = Column(Integer)
    customer_email = Column(String(255))
    service_id = Column(Integer)
    
    # Distance tracking
    customer_to_shop_miles = Column(Numeric(6, 2))
    
    # Metadata
    ip_address = Column(String(45))
    user_agent = Column(Text)
    referrer = Column(Text)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default="NOW()")
    
    # Success tracking
    success = Column(Boolean, default=True)


# ────────────────────────────────────────────────────────────────
# Tracking Functions
# ────────────────────────────────────────────────────────────────

async def track_search(
    session: AsyncSession,
    session_id: UUID,
    latitude: float,
    longitude: float,
    radius_miles: float,
    results_count: int,
    category: Optional[str] = None,
    request: Optional[Request] = None,
    success: bool = True
):
    """
    Track a location search event.
    
    Args:
        session: Database session
        session_id: Router session ID
        latitude: Search latitude
        longitude: Search longitude
        radius_miles: Search radius
        results_count: Number of results returned
        category: Optional category filter
        request: Optional FastAPI request for IP/user agent
        success: Whether search succeeded
    """
    try:
        analytics = RouterAnalytics(
            event_type="search",
            session_id=session_id,
            search_latitude=latitude,
            search_longitude=longitude,
            search_radius_miles=radius_miles,
            search_category=category,
            search_results_count=results_count,
            success=success,
        )
        
        if request:
            analytics.ip_address = _get_client_ip(request)
            analytics.user_agent = request.headers.get("User-Agent")
            analytics.referrer = request.headers.get("Referer")
        
        session.add(analytics)
        await session.commit()
        
        logger.debug(f"[ANALYTICS] Tracked search: session={session_id}, results={results_count}")
        
    except Exception as e:
        logger.error(f"[ANALYTICS] Failed to track search: {e}")
        await session.rollback()


async def track_delegation(
    session: AsyncSession,
    session_id: UUID,
    shop_id: int,
    shop_slug: str,
    intent: Optional[str] = None,
    customer_latitude: Optional[float] = None,
    customer_longitude: Optional[float] = None,
    shop_latitude: Optional[float] = None,
    shop_longitude: Optional[float] = None,
    request: Optional[Request] = None,
    success: bool = True
):
    """
    Track a delegation event.
    
    Args:
        session: Database session
        session_id: Router session ID
        shop_id: Shop ID being delegated to
        shop_slug: Shop slug
        intent: Customer's stated intent
        customer_latitude: Customer's latitude (if available)
        customer_longitude: Customer's longitude (if available)
        shop_latitude: Shop's latitude (if available)
        shop_longitude: Shop's longitude (if available)
        request: Optional FastAPI request for IP/user agent
        success: Whether delegation succeeded
    """
    try:
        # Calculate distance if both locations available
        distance = None
        if all([customer_latitude, customer_longitude, shop_latitude, shop_longitude]):
            from .geocoding import calculate_distance
            distance = calculate_distance(
                customer_latitude, customer_longitude,
                shop_latitude, shop_longitude
            )
        
        analytics = RouterAnalytics(
            event_type="delegate",
            session_id=session_id,
            shop_id=shop_id,
            shop_slug=shop_slug,
            delegation_intent=intent,
            customer_to_shop_miles=distance,
            success=success,
        )
        
        if request:
            analytics.ip_address = _get_client_ip(request)
            analytics.user_agent = request.headers.get("User-Agent")
            analytics.referrer = request.headers.get("Referer")
        
        session.add(analytics)
        await session.commit()
        
        logger.debug(
            f"[ANALYTICS] Tracked delegation: session={session_id}, "
            f"shop={shop_slug}, distance={distance}mi"
        )
        
    except Exception as e:
        logger.error(f"[ANALYTICS] Failed to track delegation: {e}")
        await session.rollback()


async def track_booking_complete(
    session: AsyncSession,
    session_id: UUID,
    shop_id: int,
    shop_slug: str,
    booking_id: Optional[int] = None,
    customer_email: Optional[str] = None,
    service_id: Optional[int] = None,
    customer_latitude: Optional[float] = None,
    customer_longitude: Optional[float] = None,
    shop_latitude: Optional[float] = None,
    shop_longitude: Optional[float] = None,
    request: Optional[Request] = None
):
    """
    Track a booking completion event.
    
    Args:
        session: Database session
        session_id: Router session ID
        shop_id: Shop ID
        shop_slug: Shop slug
        booking_id: Booking ID (if available)
        customer_email: Customer email
        service_id: Service ID booked
        customer_latitude: Customer's latitude (if available)
        customer_longitude: Customer's longitude (if available)
        shop_latitude: Shop's latitude (if available)
        shop_longitude: Shop's longitude (if available)
        request: Optional FastAPI request for IP/user agent
    """
    try:
        # Calculate distance if both locations available
        distance = None
        if all([customer_latitude, customer_longitude, shop_latitude, shop_longitude]):
            from .geocoding import calculate_distance
            distance = calculate_distance(
                customer_latitude, customer_longitude,
                shop_latitude, shop_longitude
            )
        
        analytics = RouterAnalytics(
            event_type="booking_complete",
            session_id=session_id,
            shop_id=shop_id,
            shop_slug=shop_slug,
            booking_id=booking_id,
            customer_email=customer_email,
            service_id=service_id,
            customer_to_shop_miles=distance,
            success=True,
        )
        
        if request:
            analytics.ip_address = _get_client_ip(request)
            analytics.user_agent = request.headers.get("User-Agent")
            analytics.referrer = request.headers.get("Referer")
        
        session.add(analytics)
        await session.commit()
        
        logger.info(
            f"[BOOKING] Complete: shop={shop_slug}, session={session_id}, "
            f"customer={customer_email}, distance={distance}mi"
        )
        
    except Exception as e:
        logger.error(f"[ANALYTICS] Failed to track booking completion: {e}")
        await session.rollback()


# ────────────────────────────────────────────────────────────────
# Analytics Queries
# ────────────────────────────────────────────────────────────────

async def get_usage_stats(session: AsyncSession, days: int = 30) -> dict:
    """
    Get RouterGPT usage statistics.
    
    Args:
        session: Database session
        days: Number of days to look back
    
    Returns:
        Dictionary with usage stats
    """
    try:
        from sqlalchemy import text
        
        query = text("""
            SELECT
                COUNT(DISTINCT CASE WHEN event_type = 'search' THEN session_id END) as total_searches,
                COUNT(DISTINCT CASE WHEN event_type = 'delegate' THEN session_id END) as total_delegations,
                COUNT(DISTINCT CASE WHEN event_type = 'booking_complete' THEN session_id END) as total_bookings,
                AVG(CASE WHEN event_type = 'search' THEN search_results_count END) as avg_search_results,
                AVG(customer_to_shop_miles) as avg_distance,
                COUNT(DISTINCT shop_id) as unique_shops_discovered
            FROM router_analytics
            WHERE created_at >= NOW() - INTERVAL ':days days'
        """)
        
        result = await session.execute(query, {"days": days})
        row = result.fetchone()
        
        if row:
            return {
                "period_days": days,
                "total_searches": row[0] or 0,
                "total_delegations": row[1] or 0,
                "total_bookings": row[2] or 0,
                "avg_search_results": float(row[3]) if row[3] else 0,
                "avg_distance_miles": float(row[4]) if row[4] else 0,
                "unique_shops": row[5] or 0,
            }
        
        return {}
        
    except Exception as e:
        logger.error(f"[ANALYTICS] Failed to get usage stats: {e}")
        return {}


async def get_conversion_rate(session: AsyncSession, days: int = 30) -> dict:
    """
    Calculate conversion rates through the RouterGPT funnel.
    
    Args:
        session: Database session
        days: Number of days to look back
    
    Returns:
        Dictionary with conversion rates
    """
    try:
        from sqlalchemy import text
        
        query = text("""
            SELECT
                COUNT(DISTINCT CASE WHEN event_type = 'search' THEN session_id END) as searches,
                COUNT(DISTINCT CASE WHEN event_type = 'delegate' THEN session_id END) as delegations,
                COUNT(DISTINCT CASE WHEN event_type = 'booking_complete' THEN session_id END) as bookings
            FROM router_analytics
            WHERE created_at >= NOW() - INTERVAL ':days days'
        """)
        
        result = await session.execute(query, {"days": days})
        row = result.fetchone()
        
        if row:
            searches, delegations, bookings = row
            
            search_to_delegate = (delegations / searches * 100) if searches else 0
            delegate_to_booking = (bookings / delegations * 100) if delegations else 0
            search_to_booking = (bookings / searches * 100) if searches else 0
            
            return {
                "period_days": days,
                "searches": searches or 0,
                "delegations": delegations or 0,
                "bookings": bookings or 0,
                "search_to_delegate_pct": round(search_to_delegate, 2),
                "delegate_to_booking_pct": round(delegate_to_booking, 2),
                "search_to_booking_pct": round(search_to_booking, 2),
            }
        
        return {}
        
    except Exception as e:
        logger.error(f"[ANALYTICS] Failed to get conversion rate: {e}")
        return {}


# ────────────────────────────────────────────────────────────────
# Utility Functions
# ────────────────────────────────────────────────────────────────

def _get_client_ip(request: Request) -> str:
    """Extract client IP from request."""
    # Check X-Forwarded-For header (common with reverse proxies)
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    
    # Fallback to direct client IP
    if request.client:
        return request.client.host
    
    return "unknown"
