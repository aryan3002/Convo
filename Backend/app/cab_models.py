"""
Cab Services Models

This module defines SQLAlchemy models for the cab booking vertical.
These models are ISOLATED from the existing salon/service booking models.

Tables:
    - CabOwner: Shop that has enabled cab services
    - CabDriver: Driver associated with a cab owner
    - CabPricingRule: Per-shop pricing configuration
    - CabBooking: Customer cab booking requests

Status Flow:
    PENDING -> CONFIRMED (owner accepts)
    PENDING -> REJECTED (owner declines)
    PENDING -> CANCELLED (customer cancels, future feature)
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
    Enum as PgEnum,
    JSON,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .core.db import Base


# ============================================================================
# ENUMS
# ============================================================================

class CabBookingStatus(str, Enum):
    """Status of a cab booking request."""
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    COMPLETED = "COMPLETED"  # Ride has been completed
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class CabVehicleType(str, Enum):
    """Vehicle type for cab booking."""
    SEDAN_4 = "SEDAN_4"  # Standard sedan, 4 passengers
    SUV = "SUV"          # SUV, 6 passengers
    VAN = "VAN"          # Van, 8+ passengers


class CabBookingChannel(str, Enum):
    """Channel through which booking was made."""
    WEB = "web"
    WHATSAPP = "whatsapp"
    PHONE = "phone"
    CHATGPT = "chatgpt"


class CabDriverStatus(str, Enum):
    """Status of a cab driver."""
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


# ============================================================================
# CAB OWNER MODEL
# ============================================================================

class CabOwner(Base):
    """
    Shop that has enabled cab services.
    
    One cab owner record per shop. If this record doesn't exist,
    the shop hasn't enabled cab services yet.
    """
    __tablename__ = "cab_owners"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    shop_id: Mapped[int] = mapped_column(
        ForeignKey("shops.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True
    )
    
    # Business info
    business_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    whatsapp_phone: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    
    # Status
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )
    
    # Relationships
    drivers: Mapped[list["CabDriver"]] = relationship("CabDriver", back_populates="owner")
    pricing_rule: Mapped[Optional["CabPricingRule"]] = relationship(
        "CabPricingRule", 
        back_populates="owner",
        uselist=False
    )


# ============================================================================
# CAB DRIVER MODEL
# ============================================================================

class CabDriver(Base):
    """
    Driver associated with a cab owner.
    
    Owners can add drivers and assign them to bookings.
    """
    __tablename__ = "cab_drivers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cab_owner_id: Mapped[int] = mapped_column(
        ForeignKey("cab_owners.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Driver info
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str] = mapped_column(String(32), nullable=False)
    whatsapp_phone: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    
    # Status
    status: Mapped[CabDriverStatus] = mapped_column(
        PgEnum(CabDriverStatus, name="cab_driver_status", create_type=False),
        nullable=False,
        default=CabDriverStatus.ACTIVE
    )
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )
    
    # Relationships
    owner: Mapped["CabOwner"] = relationship("CabOwner", back_populates="drivers")


# ============================================================================
# MODELS
# ============================================================================

class CabPricingRule(Base):
    """
    Cab service pricing configuration per shop.
    
    Each shop has ONE active pricing rule that defines:
    - Base per-mile rate
    - Rounding step (e.g., $5 increments)
    - Minimum fare
    - Vehicle type multipliers
    
    All prices are stored in the shop's currency (default USD).
    """
    __tablename__ = "cab_pricing_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    shop_id: Mapped[int] = mapped_column(
        ForeignKey("shops.id", ondelete="CASCADE"), 
        nullable=False, 
        unique=True,
        index=True
    )
    
    # Optional link to cab_owner (for new-style setup)
    cab_owner_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("cab_owners.id", ondelete="CASCADE"),
        nullable=True,
        index=True
    )
    
    # Pricing parameters
    per_mile_rate: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, default=Decimal("4.00")
    )
    rounding_step: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, default=Decimal("5.00")
    )
    minimum_fare: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, default=Decimal("0.00")
    )
    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, default="USD"
    )
    
    # Vehicle multipliers (JSON for flexibility)
    # Format: {"SEDAN_4": 1.0, "SUV": 1.3, "VAN": 1.5}
    vehicle_multipliers: Mapped[dict] = mapped_column(
        JSON, 
        nullable=False,
        default={"SEDAN_4": 1.0, "SUV": 1.3, "VAN": 1.5}
    )
    
    # Status
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        server_default=func.now(), 
        onupdate=func.now(),
        nullable=False
    )
    
    # Relationship to owner
    owner: Mapped[Optional["CabOwner"]] = relationship("CabOwner", back_populates="pricing_rule")

    def get_vehicle_multiplier(self, vehicle_type) -> Decimal:
        """Get the price multiplier for a vehicle type. Accepts enum or string."""
        multipliers = self.vehicle_multipliers or {}
        # Handle both enum and string inputs
        key = vehicle_type.value if hasattr(vehicle_type, 'value') else vehicle_type
        return Decimal(str(multipliers.get(key, 1.0)))


class CabBooking(Base):
    """
    Cab booking request with full pricing snapshot.
    
    Pricing Snapshot:
        All pricing parameters are captured at booking time to ensure
        the price shown to customer is honored even if rates change later.
    
    Status Flow:
        PENDING -> CONFIRMED: Owner accepts, pricing_locked=True
        PENDING -> REJECTED: Owner declines
        PENDING -> CANCELLED: Customer cancels (future)
    
    Pricing Override:
        Owner can override final_price while status=PENDING and pricing_locked=False.
        raw_price remains unchanged for audit purposes.
    """
    __tablename__ = "cab_bookings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    
    # Tenant relationship
    shop_id: Mapped[int] = mapped_column(
        ForeignKey("shops.id", ondelete="CASCADE"), 
        nullable=False, 
        index=True
    )
    
    # Booking channel
    channel: Mapped[CabBookingChannel] = mapped_column(
        PgEnum(CabBookingChannel, name="cab_booking_channel", create_type=False, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=CabBookingChannel.WEB
    )
    
    # Trip details
    pickup_text: Mapped[str] = mapped_column(Text, nullable=False)
    drop_text: Mapped[str] = mapped_column(Text, nullable=False)
    pickup_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    vehicle_type: Mapped[CabVehicleType] = mapped_column(
        PgEnum(CabVehicleType, name="cab_vehicle_type", create_type=False, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=CabVehicleType.SEDAN_4
    )
    
    # Optional trip info
    flight_number: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    passengers: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    luggage: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Customer info (for guest bookings)
    customer_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    customer_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    customer_phone: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, index=True)
    
    # Route metrics (from Google Maps)
    distance_miles: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    duration_minutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Pricing snapshot (captured at booking time)
    per_mile_rate_snapshot: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False
    )
    rounding_step_snapshot: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False
    )
    minimum_fare_snapshot: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False
    )
    vehicle_multiplier_snapshot: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, default=Decimal("1.0")
    )
    
    # Calculated prices
    raw_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    final_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    original_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    price_override: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    
    # Pricing lock
    pricing_locked: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    
    # Status
    status: Mapped[CabBookingStatus] = mapped_column(
        PgEnum(CabBookingStatus, name="cab_booking_status", create_type=False, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=CabBookingStatus.PENDING
    )
    
    # Notes (owner can add)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    confirmed_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    rejected_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    rejected_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Driver assignment
    assigned_driver_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("cab_drivers.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    assigned_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    
    # Relationship to assigned driver
    assigned_driver: Mapped[Optional["CabDriver"]] = relationship("CabDriver")

    def can_override_price(self) -> bool:
        """Check if price can be overridden."""
        return self.status == CabBookingStatus.PENDING and not self.pricing_locked

    def can_confirm(self) -> bool:
        """Check if booking can be confirmed."""
        return self.status == CabBookingStatus.PENDING and self.final_price is not None

    def can_reject(self) -> bool:
        """Check if booking can be rejected."""
        return self.status == CabBookingStatus.PENDING

    @staticmethod
    def now_utc() -> datetime:
        """Get current UTC datetime."""
        return datetime.now(timezone.utc)
