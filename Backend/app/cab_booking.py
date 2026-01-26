"""
Cab Booking API - Core Logic

This module contains the core booking logic (helpers, calculations, Pydantic models).
The actual endpoints are defined in routes_scoped.py for proper shop context injection.

Functions:
    get_pricing_rule_for_shop - Get or create pricing rule for a shop
    calculate_route_and_price - Calculate route metrics and price
    create_cab_booking_record - Create a booking record in the database
"""

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .cab_models import (
    CabBooking,
    CabBookingChannel,
    CabBookingStatus,
    CabPricingRule,
    CabVehicleType,
)
from .cab_distance import get_route_metrics, RouteError, get_route_metrics_mock
from .cab_pricing import calculate_cab_price
from .core.config import get_settings

logger = logging.getLogger(__name__)

# Get settings for API key checks
settings = get_settings()


# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================

class CabBookingCreateRequest(BaseModel):
    """Request body for creating a cab booking."""
    
    pickup_text: str = Field(
        ..., 
        min_length=3, 
        max_length=500,
        description="Pickup location address or place name"
    )
    drop_text: str = Field(
        ..., 
        min_length=3, 
        max_length=500,
        description="Drop-off location address or place name"
    )
    pickup_time: datetime = Field(
        ...,
        description="Pickup date and time (ISO 8601 format)"
    )
    vehicle_type: CabVehicleType = Field(
        default=CabVehicleType.SEDAN_4,
        description="Vehicle type: SEDAN_4, SUV, or VAN"
    )
    
    # Optional fields
    flight_number: Optional[str] = Field(
        default=None, 
        max_length=20,
        description="Flight number for airport pickups"
    )
    passengers: Optional[int] = Field(
        default=None, 
        ge=1, 
        le=15,
        description="Number of passengers"
    )
    luggage: Optional[int] = Field(
        default=None, 
        ge=0, 
        le=20,
        description="Number of luggage pieces"
    )
    
    # Customer info
    customer_name: Optional[str] = Field(
        default=None, 
        max_length=255,
        description="Customer name"
    )
    customer_email: Optional[str] = Field(
        default=None, 
        max_length=255,
        description="Customer email for confirmation"
    )
    customer_phone: Optional[str] = Field(
        default=None, 
        max_length=32,
        description="Customer phone number"
    )
    
    # Booking channel
    channel: CabBookingChannel = Field(
        default=CabBookingChannel.WEB,
        description="Booking channel: web, whatsapp, phone, chatgpt"
    )
    
    @field_validator("pickup_time")
    @classmethod
    def validate_pickup_time(cls, v: datetime) -> datetime:
        """Ensure pickup time has timezone info."""
        if v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        return v


class CabBookingResponse(BaseModel):
    """Response after creating a cab booking."""
    
    booking_id: UUID
    status: CabBookingStatus
    
    # Trip details
    pickup_text: str
    drop_text: str
    pickup_time: datetime
    vehicle_type: CabVehicleType
    
    # Route info
    distance_miles: float
    duration_minutes: int
    
    # Pricing
    raw_price: float
    final_price: float
    currency: str = "USD"
    
    # Pricing breakdown (for transparency)
    pricing_breakdown: dict
    
    # Message
    message: str


class CabBookingDetailResponse(BaseModel):
    """Detailed booking information."""
    
    booking_id: UUID
    status: CabBookingStatus
    channel: CabBookingChannel
    
    # Trip details
    pickup_text: str
    drop_text: str
    pickup_time: datetime
    vehicle_type: CabVehicleType
    flight_number: Optional[str]
    passengers: Optional[int]
    luggage: Optional[int]
    
    # Customer info
    customer_name: Optional[str]
    customer_email: Optional[str]
    customer_phone: Optional[str]
    
    # Route info
    distance_miles: Optional[float]
    duration_minutes: Optional[int]
    
    # Pricing
    raw_price: Optional[float]
    final_price: Optional[float]
    pricing_locked: bool
    
    # Pricing snapshot
    per_mile_rate_snapshot: float
    rounding_step_snapshot: float
    minimum_fare_snapshot: float
    vehicle_multiplier_snapshot: float
    
    # Notes and timestamps
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime
    confirmed_at: Optional[datetime]
    rejected_at: Optional[datetime]


class CabBookingListItem(BaseModel):
    """Summary item for booking lists."""
    
    booking_id: UUID
    status: CabBookingStatus
    channel: CabBookingChannel
    pickup_text: str
    drop_text: str
    pickup_time: datetime
    vehicle_type: CabVehicleType
    distance_miles: Optional[float]
    final_price: Optional[float]
    customer_name: Optional[str]
    customer_phone: Optional[str]
    created_at: datetime


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

async def get_pricing_rule_for_shop(
    session: AsyncSession,
    shop_id: int,
) -> CabPricingRule:
    """
    Get the active pricing rule for a shop.
    
    Creates a default rule if none exists.
    """
    result = await session.execute(
        select(CabPricingRule).where(
            CabPricingRule.shop_id == shop_id,
            CabPricingRule.active == True,
        )
    )
    rule = result.scalar_one_or_none()
    
    if not rule:
        # Create default pricing rule
        logger.info(f"Creating default cab pricing rule for shop_id={shop_id}")
        rule = CabPricingRule(
            shop_id=shop_id,
            per_mile_rate=Decimal("4.00"),
            rounding_step=Decimal("5.00"),
            minimum_fare=Decimal("0.00"),
            currency="USD",
            vehicle_multipliers={"SEDAN_4": 1.0, "SUV": 1.3, "VAN": 1.5},
            active=True,
        )
        session.add(rule)
        await session.commit()
        await session.refresh(rule)
    
    return rule


# Alias for clarity in test endpoints
get_or_create_default_pricing_rule = get_pricing_rule_for_shop


async def calculate_route_and_price(
    pickup_text: str,
    drop_text: str,
    pricing_rule: CabPricingRule,
    vehicle_type: CabVehicleType,
    use_mock: bool = False,
) -> dict:
    """
    Calculate route metrics and price for a cab booking.
    
    Args:
        pickup_text: Pickup location
        drop_text: Drop-off location
        pricing_rule: Active pricing rule
        vehicle_type: Selected vehicle type
        use_mock: Use mock distance API (for testing)
    
    Returns:
        Dict with route metrics and pricing
    """
    # Get route metrics
    if use_mock or not settings.google_maps_api_key:
        logger.warning("Using mock distance service (GOOGLE_MAPS_API_KEY not set)")
        route = await get_route_metrics_mock(pickup_text, drop_text)
    else:
        logger.info(f"Using Google Maps API for distance calculation")
        route = await get_route_metrics(pickup_text, drop_text)
    
    # Get vehicle multiplier
    vehicle_multiplier = pricing_rule.get_vehicle_multiplier(vehicle_type)
    
    # Calculate price
    price_calc = calculate_cab_price(
        distance_miles=route.distance_miles,
        per_mile_rate=pricing_rule.per_mile_rate,
        rounding_step=pricing_rule.rounding_step,
        minimum_fare=pricing_rule.minimum_fare,
        vehicle_multiplier=vehicle_multiplier,
    )
    
    return {
        "distance_miles": route.distance_miles,
        "duration_minutes": route.duration_minutes,
        "raw_price": price_calc.raw_price,
        "final_price": price_calc.final_price,
        "per_mile_rate": pricing_rule.per_mile_rate,
        "rounding_step": pricing_rule.rounding_step,
        "minimum_fare": pricing_rule.minimum_fare,
        "vehicle_multiplier": vehicle_multiplier,
        "pricing_breakdown": price_calc.to_dict(),
    }


async def create_cab_booking_record(
    session: AsyncSession,
    shop_id: int,
    request: CabBookingCreateRequest,
    calc_result: dict,
) -> CabBooking:
    """
    Create a new cab booking record in the database.
    
    Args:
        session: Database session
        shop_id: Shop ID for tenant scoping
        request: Booking request data
        calc_result: Result from calculate_route_and_price
    
    Returns:
        Created CabBooking object
    """
    booking = CabBooking(
        shop_id=shop_id,
        channel=request.channel if isinstance(request.channel, CabBookingChannel) else CabBookingChannel(request.channel),
        pickup_text=request.pickup_text,
        drop_text=request.drop_text,
        pickup_time=request.pickup_time,
        vehicle_type=request.vehicle_type if isinstance(request.vehicle_type, CabVehicleType) else CabVehicleType(request.vehicle_type),
        flight_number=request.flight_number,
        passengers=request.passengers,
        luggage=request.luggage,
        customer_name=request.customer_name,
        customer_email=request.customer_email,
        customer_phone=request.customer_phone,
        distance_miles=calc_result["distance_miles"],
        duration_minutes=calc_result["duration_minutes"],
        per_mile_rate_snapshot=calc_result["per_mile_rate"],
        rounding_step_snapshot=calc_result["rounding_step"],
        minimum_fare_snapshot=calc_result["minimum_fare"],
        vehicle_multiplier_snapshot=calc_result["vehicle_multiplier"],
        raw_price=calc_result["raw_price"],
        final_price=calc_result["final_price"],
        pricing_locked=False,
        status=CabBookingStatus.PENDING,
    )
    
    session.add(booking)
    await session.commit()
    await session.refresh(booking)
    
    logger.info(f"Created cab booking: {booking.id}")
    return booking


def booking_to_response(booking: CabBooking, pricing_breakdown: dict) -> CabBookingResponse:
    """Convert a CabBooking to CabBookingResponse."""
    return CabBookingResponse(
        booking_id=booking.id,
        status=booking.status,
        pickup_text=booking.pickup_text,
        drop_text=booking.drop_text,
        pickup_time=booking.pickup_time,
        vehicle_type=booking.vehicle_type,
        distance_miles=float(booking.distance_miles),
        duration_minutes=booking.duration_minutes,
        raw_price=float(booking.raw_price),
        final_price=float(booking.final_price),
        currency="USD",
        pricing_breakdown=pricing_breakdown,
        message=f"Booking request created. Estimated fare: ${float(booking.final_price):.2f}",
    )


def booking_to_detail_response(booking: CabBooking) -> CabBookingDetailResponse:
    """Convert a CabBooking to CabBookingDetailResponse."""
    return CabBookingDetailResponse(
        booking_id=booking.id,
        status=booking.status,
        channel=booking.channel,
        pickup_text=booking.pickup_text,
        drop_text=booking.drop_text,
        pickup_time=booking.pickup_time,
        vehicle_type=booking.vehicle_type,
        flight_number=booking.flight_number,
        passengers=booking.passengers,
        luggage=booking.luggage,
        customer_name=booking.customer_name,
        customer_email=booking.customer_email,
        customer_phone=booking.customer_phone,
        distance_miles=float(booking.distance_miles) if booking.distance_miles else None,
        duration_minutes=booking.duration_minutes,
        raw_price=float(booking.raw_price) if booking.raw_price else None,
        final_price=float(booking.final_price) if booking.final_price else None,
        pricing_locked=booking.pricing_locked,
        per_mile_rate_snapshot=float(booking.per_mile_rate_snapshot),
        rounding_step_snapshot=float(booking.rounding_step_snapshot),
        minimum_fare_snapshot=float(booking.minimum_fare_snapshot),
        vehicle_multiplier_snapshot=float(booking.vehicle_multiplier_snapshot),
        notes=booking.notes,
        created_at=booking.created_at,
        updated_at=booking.updated_at,
        confirmed_at=booking.confirmed_at,
        rejected_at=booking.rejected_at,
    )


def booking_to_list_item(booking: CabBooking) -> CabBookingListItem:
    """Convert a CabBooking to CabBookingListItem."""
    return CabBookingListItem(
        booking_id=booking.id,
        status=booking.status,
        channel=booking.channel,
        pickup_text=booking.pickup_text,
        drop_text=booking.drop_text,
        pickup_time=booking.pickup_time,
        vehicle_type=booking.vehicle_type,
        distance_miles=float(booking.distance_miles) if booking.distance_miles else None,
        final_price=float(booking.final_price) if booking.final_price else None,
        customer_name=booking.customer_name,
        customer_phone=booking.customer_phone,
        created_at=booking.created_at,
    )
