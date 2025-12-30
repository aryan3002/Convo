from __future__ import annotations

from sqlalchemy import desc, select
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


async def get_customer_by_email(session: AsyncSession, email: str) -> Customer | None:
    normalized = email.strip().lower()
    result = await session.execute(select(Customer).where(Customer.email == normalized))
    return result.scalar_one_or_none()


async def get_or_create_customer(
    session: AsyncSession, email: str, name: str | None
) -> Customer:
    normalized = email.strip().lower()
    customer = await get_customer_by_email(session, normalized)
    if customer:
        if name and (not customer.name or customer.name.strip().lower() in {"guest", "unknown"}):
            customer.name = name.strip()
        return customer

    customer = Customer(email=normalized, name=name.strip() if name else None)
    session.add(customer)
    await session.flush()
    return customer


async def update_customer_stats(
    session: AsyncSession,
    booking: Booking,
    service: Service,
    stylist: Stylist,
) -> Customer | None:
    if not booking.customer_email:
        return None

    customer = await get_or_create_customer(session, booking.customer_email, booking.customer_name)

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


async def get_customer_context(session: AsyncSession, email: str) -> dict:
    if not email:
        return {}
    normalized = email.strip().lower()
    customer = await get_customer_by_email(session, normalized)
    if not customer:
        return {}

    stats_result = await session.execute(
        select(CustomerBookingStats).where(CustomerBookingStats.customer_id == customer.id)
    )
    stats = stats_result.scalar_one_or_none()

    booking_result = await session.execute(
        select(Booking, Service, Stylist)
        .join(Service, Service.id == Booking.service_id)
        .join(Stylist, Stylist.id == Booking.stylist_id)
        .where(
            Booking.customer_email == normalized,
            Booking.status == BookingStatus.CONFIRMED,
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
        "email": normalized,
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
