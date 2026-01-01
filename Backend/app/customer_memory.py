from __future__ import annotations

import re

from sqlalchemy import desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import (
    Booking,
    BookingStatus,
    Customer,
    CustomerBookingStats,
    CustomerStylistPreference,
    Service,
    Stylist,
)


def normalize_email(email: str | None) -> str:
    if not email:
        return ""
    trimmed = email.strip().lower()
    if "@" not in trimmed:
        return ""
    return trimmed


def normalize_phone(phone: str | None) -> str:
    if not phone:
        return ""
    text = phone.strip()
    if not text:
        return ""
    if text.startswith("+"):
        digits = re.sub(r"\D", "", text)
        return f"+{digits}" if digits else ""
    digits = re.sub(r"\D", "", text)
    if len(digits) == 10:
        return f"+1{digits}"
    if len(digits) >= 11:
        return f"+{digits}"
    return ""


async def get_customer_by_email(session: AsyncSession, email: str) -> Customer | None:
    normalized = normalize_email(email)
    if not normalized:
        return None
    result = await session.execute(select(Customer).where(Customer.email == normalized))
    return result.scalar_one_or_none()


async def get_customer_by_phone(session: AsyncSession, phone: str) -> Customer | None:
    normalized = normalize_phone(phone)
    if not normalized:
        return None
    result = await session.execute(select(Customer).where(Customer.phone == normalized))
    return result.scalar_one_or_none()


async def get_or_create_customer_by_identity(
    session: AsyncSession,
    email: str | None,
    phone: str | None,
    name: str | None,
) -> Customer | None:
    normalized_email = normalize_email(email)
    normalized_phone = normalize_phone(phone)

    customer = None
    if normalized_phone:
        customer = await get_customer_by_phone(session, normalized_phone)
        if customer:
            if normalized_email and not customer.email:
                existing = await get_customer_by_email(session, normalized_email)
                if not existing or existing.id == customer.id:
                    customer.email = normalized_email
            if name and (not customer.name or customer.name.strip().lower() in {"guest", "unknown"}):
                customer.name = name.strip()
            return customer

    if normalized_email:
        customer = await get_customer_by_email(session, normalized_email)
        if customer:
            if normalized_phone and not customer.phone:
                existing = await get_customer_by_phone(session, normalized_phone)
                if not existing or existing.id == customer.id:
                    customer.phone = normalized_phone
            if name and (not customer.name or customer.name.strip().lower() in {"guest", "unknown"}):
                customer.name = name.strip()
            return customer

    if not normalized_email and not normalized_phone:
        return None

    customer = Customer(
        email=normalized_email or None,
        phone=normalized_phone or None,
        name=name.strip() if name else None,
    )
    session.add(customer)
    await session.flush()
    return customer


async def get_or_create_customer(
    session: AsyncSession, email: str, name: str | None
) -> Customer | None:
    return await get_or_create_customer_by_identity(session, email, None, name)


async def update_customer_stats(
    session: AsyncSession,
    booking: Booking,
    service: Service,
    stylist: Stylist,
) -> Customer | None:
    if not (booking.customer_phone or booking.customer_email):
        return None

    customer = await get_or_create_customer_by_identity(
        session,
        booking.customer_email,
        booking.customer_phone,
        booking.customer_name,
    )
    if not customer:
        return None

    result = await session.execute(
        select(CustomerBookingStats).where(CustomerBookingStats.customer_id == customer.id)
    )
    stats = result.scalar_one_or_none()
    if not stats:
        stats = CustomerBookingStats(
            customer_id=customer.id,
            total_bookings=0,
            total_spend_cents=0,
            last_booking_at=None,
        )
        session.add(stats)

    stats.total_bookings += 1
    stats.total_spend_cents += service.price_cents
    stats.last_booking_at = booking.start_at_utc

    if stats.total_bookings > 0:
        customer.average_spend_cents = int(stats.total_spend_cents / stats.total_bookings)

    pref_result = await session.execute(
        select(CustomerStylistPreference).where(
            CustomerStylistPreference.customer_id == customer.id,
            CustomerStylistPreference.stylist_id == stylist.id,
        )
    )
    pref = pref_result.scalar_one_or_none()
    if not pref:
        pref = CustomerStylistPreference(
            customer_id=customer.id, stylist_id=stylist.id, booking_count=1
        )
        session.add(pref)
    else:
        pref.booking_count += 1

    top_result = await session.execute(
        select(CustomerStylistPreference)
        .where(CustomerStylistPreference.customer_id == customer.id)
        .order_by(
            CustomerStylistPreference.booking_count.desc(),
            CustomerStylistPreference.stylist_id.asc(),
        )
        .limit(1)
    )
    top_pref = top_result.scalar_one_or_none()
    if top_pref:
        customer.preferred_stylist_id = top_pref.stylist_id

    return customer


async def get_customer_context(session: AsyncSession, email: str | None = None, phone: str | None = None) -> dict:
    if email and "@" not in email and not phone:
        phone = email
        email = None

    normalized_email = normalize_email(email)
    normalized_phone = normalize_phone(phone)

    customer = None
    if normalized_phone:
        customer = await get_customer_by_phone(session, normalized_phone)
    if not customer and normalized_email:
        customer = await get_customer_by_email(session, normalized_email)
    if not customer:
        return {}

    stats_result = await session.execute(
        select(CustomerBookingStats).where(CustomerBookingStats.customer_id == customer.id)
    )
    stats = stats_result.scalar_one_or_none()

    booking_filters = []
    if customer.email:
        booking_filters.append(Booking.customer_email == customer.email)
    if customer.phone:
        booking_filters.append(Booking.customer_phone == customer.phone)

    booking_row = None
    if booking_filters:
        booking_result = await session.execute(
            select(Booking, Service, Stylist)
            .join(Service, Service.id == Booking.service_id)
            .join(Stylist, Stylist.id == Booking.stylist_id)
            .where(
                Booking.status == BookingStatus.CONFIRMED,
                or_(*booking_filters),
            )
            .order_by(Booking.start_at_utc.desc())
            .limit(1)
        )
        booking_row = booking_result.first()

    preferred_stylist_name = None
    if customer.preferred_stylist_id:
        stylist_result = await session.execute(
            select(Stylist).where(Stylist.id == customer.preferred_stylist_id)
        )
        stylist = stylist_result.scalar_one_or_none()
        preferred_stylist_name = stylist.name if stylist else None

    context = {
        "email": customer.email,
        "phone": customer.phone,
        "name": customer.name,
        "preferred_stylist": preferred_stylist_name,
        "average_spend_cents": customer.average_spend_cents,
        "total_bookings": stats.total_bookings if stats else 0,
        "total_spend_cents": stats.total_spend_cents if stats else 0,
        "last_booking_at": stats.last_booking_at if stats else None,
        "last_service": None,
        "last_stylist": None,
    }

    if booking_row:
        booking, service, stylist = booking_row
        context["last_service"] = service.name
        context["last_stylist"] = stylist.name
        context["last_booking_at"] = booking.start_at_utc

    return context


async def get_customers_by_preferred_stylist(
    session: AsyncSession, stylist_id: int
) -> list[Customer]:
    result = await session.execute(
        select(Customer)
        .where(Customer.preferred_stylist_id == stylist_id)
        .order_by(desc(Customer.average_spend_cents))
    )
    return result.scalars().all()
