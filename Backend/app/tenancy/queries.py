"""
Tenant-scoped query helpers.

These functions provide safe, tenant-isolated database queries.
ALL queries for tenant data MUST use these helpers or include explicit shop_id filtering.

PHASE 3: This module is THE central place for tenant-scoped queries.
Any query for Service, Stylist, Booking, Promo, CustomerShopProfile, etc.
MUST either use these helpers OR include explicit shop_id == ctx.shop_id filter.

Usage:
    from app.tenancy.queries import get_service_by_id, list_services, scoped_select
    
    service = await get_service_by_id(session, ctx.shop_id, service_id)
    services = await list_services(session, ctx.shop_id)
    
    # Or using composable helpers:
    stmt = scoped_select(Service, shop_id).where(Service.name.ilike("%haircut%"))
"""

from typing import Optional, Sequence, TypeVar, Type
from datetime import datetime

from sqlalchemy import select, and_, Select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase

from ..models import (
    Service,
    Stylist,
    Promo,
    Booking,
    BookingStatus,
    Shop,
    CallSummary,
    CustomerShopProfile,
    CustomerStylistPreference,
    CustomerServicePreference,
)

# Type variable for generic model functions
T = TypeVar("T", bound=DeclarativeBase)


# ────────────────────────────────────────────────────────────────
# Composable Query Helpers (Phase 3)
# ────────────────────────────────────────────────────────────────

def scoped_select(model: Type[T], shop_id: int) -> Select:
    """
    Create a SELECT statement pre-filtered by shop_id.
    
    Usage:
        stmt = scoped_select(Service, ctx.shop_id).where(Service.active == True)
        result = await session.execute(stmt)
    """
    return select(model).where(model.shop_id == shop_id)


def tenant_filter(model: Type[T], shop_id: int):
    """
    Return a SQLAlchemy filter clause for shop_id.
    
    Usage:
        stmt = select(Service).where(tenant_filter(Service, ctx.shop_id), Service.active == True)
    """
    return model.shop_id == shop_id


async def require_owned(
    session: AsyncSession,
    model: Type[T],
    entity_id: int,
    shop_id: int,
) -> Optional[T]:
    """
    Fetch an entity by ID, validating shop ownership.
    Returns None if not found or wrong shop.
    
    Usage:
        service = await require_owned(session, Service, service_id, ctx.shop_id)
        if not service:
            raise HTTPException(404, "Service not found")
    """
    result = await session.execute(
        select(model).where(
            model.id == entity_id,
            model.shop_id == shop_id
        )
    )
    return result.scalar_one_or_none()


async def get_services_by_ids(
    session: AsyncSession,
    shop_id: int,
    service_ids: Sequence[int],
) -> Sequence[Service]:
    """Get multiple services by IDs, scoped to shop."""
    if not service_ids:
        return []
    result = await session.execute(
        select(Service).where(
            Service.shop_id == shop_id,
            Service.id.in_(service_ids)
        )
    )
    return result.scalars().all()


async def get_stylists_by_ids(
    session: AsyncSession,
    shop_id: int,
    stylist_ids: Sequence[int],
) -> Sequence[Stylist]:
    """Get multiple stylists by IDs, scoped to shop."""
    if not stylist_ids:
        return []
    result = await session.execute(
        select(Stylist).where(
            Stylist.shop_id == shop_id,
            Stylist.id.in_(stylist_ids)
        )
    )
    return result.scalars().all()


async def list_stylists_with_pin(
    session: AsyncSession,
    shop_id: int,
) -> Sequence[Stylist]:
    """List stylists who have set a PIN, scoped to shop."""
    result = await session.execute(
        select(Stylist).where(
            Stylist.shop_id == shop_id,
            Stylist.pin_hash.isnot(None)
        ).order_by(Stylist.name)
    )
    return result.scalars().all()


# ────────────────────────────────────────────────────────────────
# Shop Queries
# ────────────────────────────────────────────────────────────────

async def get_shop_by_id(session: AsyncSession, shop_id: int) -> Optional[Shop]:
    """Get a shop by ID."""
    result = await session.execute(select(Shop).where(Shop.id == shop_id))
    return result.scalar_one_or_none()


async def get_shop_by_slug(session: AsyncSession, slug: str) -> Optional[Shop]:
    """Get a shop by URL slug."""
    result = await session.execute(select(Shop).where(Shop.slug == slug))
    return result.scalar_one_or_none()


async def get_shop_by_phone(session: AsyncSession, phone_number: str) -> Optional[Shop]:
    """
    Get a shop by phone number.
    Checks both shops.phone_number and shop_phone_numbers table.
    """
    from ..models import ShopPhoneNumber
    
    # Normalize phone number
    normalized = normalize_phone_for_lookup(phone_number)
    
    # First check shop_phone_numbers table (preferred)
    result = await session.execute(
        select(Shop)
        .join(ShopPhoneNumber, ShopPhoneNumber.shop_id == Shop.id)
        .where(ShopPhoneNumber.phone_number == normalized)
    )
    shop = result.scalar_one_or_none()
    if shop:
        return shop
    
    # Fallback: check shops.phone_number directly
    result = await session.execute(
        select(Shop).where(Shop.phone_number == normalized)
    )
    return result.scalar_one_or_none()


def normalize_phone_for_lookup(phone: str) -> str:
    """Normalize phone number for database lookup."""
    import re
    if not phone:
        return ""
    # Remove all non-digit chars except leading +
    if phone.startswith("+"):
        digits = re.sub(r"\D", "", phone[1:])
        return f"+{digits}"
    digits = re.sub(r"\D", "", phone)
    if len(digits) == 10:
        return f"+1{digits}"
    if len(digits) >= 11:
        return f"+{digits}"
    return phone


# ────────────────────────────────────────────────────────────────
# Service Queries (Tenant-Scoped)
# ────────────────────────────────────────────────────────────────

async def get_service_by_id(
    session: AsyncSession, 
    shop_id: int, 
    service_id: int
) -> Optional[Service]:
    """Get a service by ID, scoped to shop."""
    result = await session.execute(
        select(Service).where(
            Service.id == service_id,
            Service.shop_id == shop_id
        )
    )
    return result.scalar_one_or_none()


async def list_services(
    session: AsyncSession, 
    shop_id: int
) -> Sequence[Service]:
    """List all services for a shop."""
    result = await session.execute(
        select(Service)
        .where(Service.shop_id == shop_id)
        .order_by(Service.id)
    )
    return result.scalars().all()


async def find_service_by_name(
    session: AsyncSession,
    shop_id: int,
    name: str,
) -> Optional[Service]:
    """Find a service by name (case-insensitive partial match), scoped to shop."""
    result = await session.execute(
        select(Service)
        .where(
            Service.shop_id == shop_id,
            Service.name.ilike(f"%{name.strip()}%")
        )
        .order_by(Service.id)
        .limit(1)
    )
    return result.scalar_one_or_none()


# ────────────────────────────────────────────────────────────────
# Stylist Queries (Tenant-Scoped)
# ────────────────────────────────────────────────────────────────

async def get_stylist_by_id(
    session: AsyncSession, 
    shop_id: int, 
    stylist_id: int
) -> Optional[Stylist]:
    """Get a stylist by ID, scoped to shop."""
    result = await session.execute(
        select(Stylist).where(
            Stylist.id == stylist_id,
            Stylist.shop_id == shop_id
        )
    )
    return result.scalar_one_or_none()


async def list_stylists(
    session: AsyncSession, 
    shop_id: int,
    active_only: bool = False
) -> Sequence[Stylist]:
    """List all stylists for a shop."""
    query = select(Stylist).where(Stylist.shop_id == shop_id)
    if active_only:
        query = query.where(Stylist.active.is_(True))
    query = query.order_by(Stylist.id)
    result = await session.execute(query)
    return result.scalars().all()


async def list_active_stylists(
    session: AsyncSession, 
    shop_id: int
) -> Sequence[Stylist]:
    """List all active stylists for a shop."""
    return await list_stylists(session, shop_id, active_only=True)


async def find_stylist_by_name(
    session: AsyncSession,
    shop_id: int,
    name: str,
) -> Optional[Stylist]:
    """Find a stylist by name (case-insensitive partial match), scoped to shop."""
    result = await session.execute(
        select(Stylist)
        .where(
            Stylist.shop_id == shop_id,
            Stylist.name.ilike(f"%{name.strip()}%")
        )
        .order_by(Stylist.id)
        .limit(1)
    )
    return result.scalar_one_or_none()


# ────────────────────────────────────────────────────────────────
# Promo Queries (Tenant-Scoped)
# ────────────────────────────────────────────────────────────────

async def get_promo_by_id(
    session: AsyncSession, 
    shop_id: int, 
    promo_id: int
) -> Optional[Promo]:
    """Get a promo by ID, scoped to shop."""
    result = await session.execute(
        select(Promo).where(
            Promo.id == promo_id,
            Promo.shop_id == shop_id
        )
    )
    return result.scalar_one_or_none()


async def list_promos(
    session: AsyncSession, 
    shop_id: int,
    active_only: bool = False
) -> Sequence[Promo]:
    """List all promos for a shop."""
    query = select(Promo).where(Promo.shop_id == shop_id)
    if active_only:
        query = query.where(Promo.active.is_(True))
    query = query.order_by(Promo.id)
    result = await session.execute(query)
    return result.scalars().all()


# ────────────────────────────────────────────────────────────────
# Booking Queries (Tenant-Scoped)
# ────────────────────────────────────────────────────────────────

async def get_booking_by_id(
    session: AsyncSession, 
    shop_id: int, 
    booking_id
) -> Optional[Booking]:
    """Get a booking by ID, scoped to shop."""
    result = await session.execute(
        select(Booking).where(
            Booking.id == booking_id,
            Booking.shop_id == shop_id
        )
    )
    return result.scalar_one_or_none()


async def list_bookings_in_range(
    session: AsyncSession,
    shop_id: int,
    start_utc: datetime,
    end_utc: datetime,
    status: Optional[BookingStatus] = None,
) -> Sequence[Booking]:
    """List bookings within a time range, scoped to shop."""
    query = select(Booking).where(
        Booking.shop_id == shop_id,
        Booking.start_at_utc >= start_utc,
        Booking.end_at_utc <= end_utc,
    )
    if status:
        query = query.where(Booking.status == status)
    query = query.order_by(Booking.start_at_utc)
    result = await session.execute(query)
    return result.scalars().all()


# ────────────────────────────────────────────────────────────────
# Call Summary Queries (Tenant-Scoped)
# ────────────────────────────────────────────────────────────────

async def list_call_summaries(
    session: AsyncSession,
    shop_id: int,
    limit: int = 50,
) -> Sequence[CallSummary]:
    """List recent call summaries for a shop."""
    result = await session.execute(
        select(CallSummary)
        .where(CallSummary.shop_id == shop_id)
        .order_by(CallSummary.created_at.desc())
        .limit(limit)
    )
    return result.scalars().all()


# ────────────────────────────────────────────────────────────────
# Customer Shop Profile Queries (Tenant-Scoped)
# ────────────────────────────────────────────────────────────────

async def get_or_create_customer_shop_profile(
    session: AsyncSession,
    customer_id: int,
    shop_id: int,
) -> CustomerShopProfile:
    """Get or create a customer's shop-specific profile."""
    result = await session.execute(
        select(CustomerShopProfile).where(
            CustomerShopProfile.customer_id == customer_id,
            CustomerShopProfile.shop_id == shop_id,
        )
    )
    profile = result.scalar_one_or_none()
    
    if not profile:
        profile = CustomerShopProfile(
            customer_id=customer_id,
            shop_id=shop_id,
            total_bookings=0,
            total_spend_cents=0,
            no_show_count=0,
        )
        session.add(profile)
        await session.flush()
    
    return profile


async def update_customer_shop_profile_on_booking(
    session: AsyncSession,
    customer_id: int,
    shop_id: int,
    stylist_id: int,
    spend_cents: int,
    booking_time: datetime,
) -> CustomerShopProfile:
    """Update customer shop profile after a booking."""
    profile = await get_or_create_customer_shop_profile(session, customer_id, shop_id)
    
    profile.total_bookings += 1
    profile.total_spend_cents += spend_cents
    profile.last_booking_at = booking_time
    profile.preferred_stylist_id = stylist_id  # Update to most recent stylist
    
    return profile


# ────────────────────────────────────────────────────────────────
# Customer Preference Queries (Tenant-Scoped)
# ────────────────────────────────────────────────────────────────

async def get_customer_stylist_preference(
    session: AsyncSession,
    customer_id: int,
    shop_id: int,
    stylist_id: int,
) -> Optional[CustomerStylistPreference]:
    """Get a specific customer-stylist preference, scoped to shop."""
    result = await session.execute(
        select(CustomerStylistPreference).where(
            CustomerStylistPreference.customer_id == customer_id,
            CustomerStylistPreference.shop_id == shop_id,
            CustomerStylistPreference.stylist_id == stylist_id,
        )
    )
    return result.scalar_one_or_none()


async def get_customer_service_preference(
    session: AsyncSession,
    customer_id: int,
    shop_id: int,
    service_id: int,
) -> Optional[CustomerServicePreference]:
    """Get a specific customer-service preference, scoped to shop."""
    result = await session.execute(
        select(CustomerServicePreference).where(
            CustomerServicePreference.customer_id == customer_id,
            CustomerServicePreference.shop_id == shop_id,
            CustomerServicePreference.service_id == service_id,
        )
    )
    return result.scalar_one_or_none()
