"""
Owner chat action execution logic.

Complete action handlers extracted from main.py for multi-tenant support.
All actions are shop-scoped to ensure proper tenant isolation.
"""

import re
import json
import logging
from datetime import date, datetime, time, timedelta, timezone as dt_timezone
from zoneinfo import ZoneInfo
from typing import Optional, Tuple

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .core.config import get_settings
from .models import (
    Service,
    ServiceRule,
    Stylist,
    StylistSpecialty,
    TimeOffBlock,
    Promo,
    PromoType,
    PromoDiscountType,
    PromoTriggerPoint,
    Booking,
    BookingStatus,
)
from .owner_chat import OwnerChatResponse

settings = get_settings()
logger = logging.getLogger(__name__)

SUPPORTED_RULES = ["weekends_only", "weekdays_only", "weekday_evenings", "none"]


# ────────────────────────────────────────────────────────────────
# Helper Functions
# ────────────────────────────────────────────────────────────────

async def fetch_service(session: AsyncSession, service_id: int, shop_id: int) -> Service:
    """Fetch a service by ID, scoped to shop."""
    result = await session.execute(
        select(Service).where(Service.id == service_id, Service.shop_id == shop_id)
    )
    service = result.scalar_one_or_none()
    if not service:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found")
    return service


async def fetch_service_by_name(session: AsyncSession, name: str, shop_id: int) -> Service | None:
    """Fetch a service by name (case-insensitive), scoped to shop."""
    result = await session.execute(
        select(Service).where(Service.shop_id == shop_id, Service.name.ilike(f"%{name}%"))
    )
    return result.scalar_one_or_none()


async def fetch_stylist(session: AsyncSession, stylist_id: int, shop_id: int) -> Stylist:
    """Fetch a stylist by ID, scoped to shop."""
    result = await session.execute(
        select(Stylist).where(Stylist.id == stylist_id, Stylist.shop_id == shop_id)
    )
    stylist = result.scalar_one_or_none()
    if not stylist:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stylist not found")
    return stylist


async def resolve_stylist_from_params(params: dict, session: AsyncSession, shop_id: int) -> Stylist | None:
    """Resolve stylist from params - by ID or name."""
    stylist_id = params.get("stylist_id")
    if stylist_id:
        try:
            return await fetch_stylist(session, int(stylist_id), shop_id)
        except HTTPException:
            return None
    stylist_name = str(params.get("stylist_name") or params.get("name") or "").strip()
    if stylist_name:
        result = await session.execute(
            select(Stylist).where(
                Stylist.shop_id == shop_id,
                Stylist.name.ilike(f"%{stylist_name}%"),
            )
        )
        return result.scalar_one_or_none()
    return None


async def resolve_service_from_params(params: dict, session: AsyncSession, shop_id: int) -> Service | None:
    """Resolve service from params - by ID or name."""
    service_id = params.get("service_id")
    if service_id:
        try:
            return await fetch_service(session, int(service_id), shop_id)
        except HTTPException:
            return None
    service_name = str(params.get("service_name") or params.get("name") or "").strip()
    if service_name:
        return await fetch_service_by_name(session, service_name, shop_id)
    return None


async def list_services_with_rules(session: AsyncSession, shop_id: int):
    """List all services with their availability rules."""
    result = await session.execute(
        select(Service).where(Service.shop_id == shop_id).order_by(Service.id)
    )
    services = result.scalars().all()
    
    rule_result = await session.execute(select(ServiceRule).where(ServiceRule.service_id.in_([s.id for s in services])))
    rules = {r.service_id: r.rule for r in rule_result.scalars().all()}
    
    return [
        {
            "id": svc.id,
            "name": svc.name,
            "duration_minutes": svc.duration_minutes,
            "price_cents": svc.price_cents,
            "availability_rule": rules.get(svc.id, "none"),
        }
        for svc in services
    ]


async def list_stylists_with_details(session: AsyncSession, shop_id: int):
    """List stylists with specialties and time off count."""
    result = await session.execute(
        select(Stylist).where(Stylist.shop_id == shop_id).order_by(Stylist.id)
    )
    stylists = result.scalars().all()
    stylist_ids = [stylist.id for stylist in stylists]
    specialties_map: dict[int, list[str]] = {stylist_id: [] for stylist_id in stylist_ids}
    time_off_days: dict[int, set[str]] = {stylist_id: set() for stylist_id in stylist_ids}

    if stylist_ids:
        spec_result = await session.execute(
            select(StylistSpecialty).where(StylistSpecialty.stylist_id.in_(stylist_ids))
        )
        for spec in spec_result.scalars().all():
            specialties_map.setdefault(spec.stylist_id, []).append(spec.tag)

        now = datetime.now(dt_timezone.utc)
        tz = ZoneInfo(settings.chat_timezone)
        time_off_result = await session.execute(
            select(TimeOffBlock).where(
                TimeOffBlock.stylist_id.in_(stylist_ids),
                TimeOffBlock.end_at_utc > now,
            )
        )
        for block in time_off_result.scalars().all():
            local_start = block.start_at_utc.astimezone(tz)
            local_end = block.end_at_utc.astimezone(tz)
            start_date = local_start.date()
            end_date = local_end.date()
            if local_end.time() == time(0, 0) and end_date > start_date:
                end_date = end_date - timedelta(days=1)
            cursor = start_date
            while cursor <= end_date:
                time_off_days[block.stylist_id].add(cursor.isoformat())
                cursor += timedelta(days=1)

    return [
        {
            "id": s.id,
            "name": s.name,
            "work_start": s.work_start.strftime("%H:%M") if s.work_start else "09:00",
            "work_end": s.work_end.strftime("%H:%M") if s.work_end else "17:00",
            "specialties": specialties_map.get(s.id, []),
            "time_off_count": len(time_off_days.get(s.id, set())),
            "active": s.active,
        }
        for s in stylists
    ]


async def list_promos_data(session: AsyncSession, shop_id: int):
    """List all promos for a shop."""
    result = await session.execute(
        select(Promo).where(Promo.shop_id == shop_id).order_by(Promo.id)
    )
    promos = result.scalars().all()
    return [
        {
            "id": p.id,
            "promo_type": p.type.value if p.type else "DAILY_PROMO",
            "discount_type": p.discount_type.value if p.discount_type else "PERCENT",
            "discount_value": p.discount_value,
            "trigger_point": p.trigger_point.value if p.trigger_point else "AT_CHAT_START",
            "active": p.active,
            "custom_copy": p.custom_copy,
            "service_id": p.service_id,
            "starts_at": p.start_at_utc.isoformat() if p.start_at_utc else None,
            "ends_at": p.end_at_utc.isoformat() if p.end_at_utc else None,
        }
        for p in promos
    ]


def parse_working_hours() -> tuple[time, time]:
    """Parse default working hours from settings."""
    try:
        start_time = datetime.strptime(settings.working_hours_start, "%H:%M").time()
        end_time = datetime.strptime(settings.working_hours_end, "%H:%M").time()
        return start_time, end_time
    except ValueError:
        return time(9, 0), time(17, 0)


def normalize_text(value: str) -> str:
    """Normalize text for fuzzy matching."""
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def parse_time_of_day(value: str) -> time | None:
    """Parse time from string like '10am', '2:30pm', '14:00'."""
    if not value:
        return None
    raw = value.strip().lower()
    match = re.match(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", raw)
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    meridiem = match.group(3)
    if meridiem:
        if hour == 12:
            hour = 0
        if meridiem == "pm":
            hour += 12
    if hour > 23 or minute > 59:
        return None
    return time(hour, minute)


def extract_time_range_from_text(text: str) -> tuple[time | None, time | None]:
    """Extract time range from text like 'from 9am to 5pm' or '9:00-17:00'."""
    if not text:
        return None, None
    normalized = text.replace("–", "-").replace("—", "-")
    match = re.search(
        r"\bfrom\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\s*(?:to|-)\s*(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)",
        normalized,
        re.IGNORECASE,
    )
    if not match:
        match = re.search(
            r"(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\s*-\s*(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)",
            normalized,
            re.IGNORECASE,
        )
    if not match:
        return None, None
    start_time = parse_time_of_day(match.group(1))
    end_time = parse_time_of_day(match.group(2))
    return start_time, end_time


def parse_price_cents(value) -> int:
    """Parse price to cents from string like '$25', '25.50', etc."""
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        return int(value * 100) if isinstance(value, float) and value < 1000 else int(value)
    
    raw = str(value).strip().replace("$", "").replace(",", "")
    try:
        num = float(raw)
        if num < 1000:  # Assume dollars if small number
            return int(num * 100)
        return int(num)
    except ValueError:
        return 0


def parse_duration_minutes(value) -> int:
    """Parse duration in minutes from various formats."""
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    
    raw = str(value).strip().lower()
    
    # Handle hour format
    hour_match = re.search(r"(\d+(?:\.\d+)?)\s*(hours?|hrs?|hr)\b", raw)
    if hour_match:
        return int(round(float(hour_match.group(1)) * 60))
    
    # Handle minute format
    minute_match = re.search(r"(\d+(?:\.\d+)?)\s*(minutes?|mins?|min)\b", raw)
    if minute_match:
        return int(round(float(minute_match.group(1))))
    
    # Plain number
    try:
        return int(float(raw))
    except ValueError:
        return 0


def parse_date_str(value: str) -> date | None:
    """Parse date string in YYYY-MM-DD format."""
    if not value:
        return None
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def get_local_tz_offset_minutes() -> int:
    """Get local timezone offset in minutes from UTC."""
    try:
        tz = ZoneInfo(settings.chat_timezone)
        now = datetime.now(tz)
        offset = now.utcoffset()
        if offset:
            return int(offset.total_seconds() / 60)
    except Exception:
        pass
    return 0


def to_utc_from_local(local_date: date, local_time: time, tz_offset_minutes: int) -> datetime:
    """Convert local date/time to UTC datetime."""
    local_dt = datetime.combine(local_date, local_time)
    return local_dt + timedelta(minutes=tz_offset_minutes)


def normalize_tag(tag: str) -> str:
    """Normalize a tag string."""
    return re.sub(r"[^a-z0-9]+", "-", tag.lower()).strip("-")


def parse_tags(value) -> list[str]:
    """Parse tags from string or list."""
    if not value:
        return []
    if isinstance(value, list):
        return [normalize_tag(str(t)) for t in value if t]
    
    raw = str(value)
    # Split on commas or 'and'
    parts = re.split(r",|\band\b", raw)
    return [normalize_tag(p.strip()) for p in parts if p.strip()]


def extract_rule_from_text(text: str) -> str:
    """Extract availability rule from text."""
    normalized = normalize_text(text)
    if "weekend" in normalized:
        return "weekends_only"
    if "evening" in normalized:
        return "weekday_evenings"
    if "weekday" in normalized:
        return "weekdays_only"
    return "none"


# ────────────────────────────────────────────────────────────────
# Time Off Parsing
# ────────────────────────────────────────────────────────────────

def parse_time_off_range(params: dict) -> tuple[datetime | None, datetime | None, str | None]:
    """
    Parse time off range from params.
    Returns (start_utc, end_utc, error_message).
    """
    tz_offset = (
        int(params.get("tz_offset_minutes"))
        if params.get("tz_offset_minutes") is not None
        else get_local_tz_offset_minutes()
    )
    
    date_str = params.get("date")
    start_time_str = params.get("start_time")
    end_time_str = params.get("end_time")
    
    if not date_str:
        return None, None, "Which date should I use?"
    
    target_date = parse_date_str(date_str)
    if not target_date:
        return None, None, "I couldn't understand that date format. Please use YYYY-MM-DD."
    
    start_time = parse_time_of_day(start_time_str) if start_time_str else time(0, 0)
    end_time = parse_time_of_day(end_time_str) if end_time_str else time(23, 59)
    
    start_utc = to_utc_from_local(target_date, start_time, tz_offset)
    end_utc = to_utc_from_local(target_date, end_time, tz_offset)
    
    return start_utc, end_utc, None


# ────────────────────────────────────────────────────────────────
# Action Handlers
# ────────────────────────────────────────────────────────────────

async def execute_create_stylist(
    params: dict,
    session: AsyncSession,
    shop_id: int,
) -> tuple[dict | None, str]:
    """Execute create_stylist action."""
    raw_name = str(params.get("name") or "").strip()
    name = raw_name
    
    # Extract name from variations
    match = re.search(
        r"\badd\b\s+(?:a\s+)?(?:new\s+)?stylist\s+([a-z][a-z\s'-]+)",
        raw_name,
        re.IGNORECASE,
    )
    if not match:
        match = re.search(
            r"\badd\b\s+([a-z][a-z\s'-]+?)\s+as\s+(?:a\s+)?stylist",
            raw_name,
            re.IGNORECASE,
        )
    if not match and "stylist" in normalize_text(raw_name):
        match = re.search(r"stylist\s+([a-z][a-z\s'-]+)", raw_name, re.IGNORECASE)
    if not match:
        match = re.search(r"\badd\b\s+([a-z][a-z\s'-]+)", raw_name, re.IGNORECASE)
    if match:
        name = match.group(1).strip()
        name = re.split(r"\b(from|to|with|at|as)\b", name, 1, flags=re.IGNORECASE)[0].strip()
    
    if not name:
        raise ValueError("What's the stylist's name?")

    work_start = parse_time_of_day(str(params.get("work_start") or "")) if params.get("work_start") else None
    work_end = parse_time_of_day(str(params.get("work_end") or "")) if params.get("work_end") else None
    
    if not work_start or not work_end:
        work_start, work_end = extract_time_range_from_text(raw_name)
    
    if not work_start or not work_end:
        work_start, work_end = parse_working_hours()
    
    if work_end <= work_start:
        raise ValueError("End time should be after start time.")

    existing = await session.execute(
        select(Stylist).where(Stylist.shop_id == shop_id, Stylist.name.ilike(f"%{name}%"))
    )
    if existing.scalar_one_or_none():
        raise ValueError("That stylist already exists.")

    stylist = Stylist(
        shop_id=shop_id,
        name=name,
        work_start=work_start,
        work_end=work_end,
        active=True,
    )
    session.add(stylist)
    await session.commit()
    await session.refresh(stylist)
    
    data = {"stylists": await list_stylists_with_details(session, shop_id)}
    reply = f"Added stylist {stylist.name} ({work_start.strftime('%H:%M')}–{work_end.strftime('%H:%M')})."
    
    return data, reply


async def execute_remove_stylist(
    params: dict,
    session: AsyncSession,
    shop_id: int,
) -> tuple[dict | None, str]:
    """Execute remove_stylist action."""
    stylist = await resolve_stylist_from_params(params, session, shop_id)
    if not stylist:
        raise ValueError("Which stylist should I remove?")

    # Check for bookings
    result = await session.execute(
        select(Booking.id).where(Booking.stylist_id == stylist.id).limit(1)
    )
    if result.scalar_one_or_none():
        raise ValueError("That stylist has bookings. Remove bookings first or keep them.")

    # Remove specialties
    await session.execute(
        StylistSpecialty.__table__.delete().where(StylistSpecialty.stylist_id == stylist.id)
    )
    # Remove time off
    await session.execute(
        TimeOffBlock.__table__.delete().where(TimeOffBlock.stylist_id == stylist.id)
    )
    await session.delete(stylist)
    await session.commit()
    
    data = {"stylists": await list_stylists_with_details(session, shop_id)}
    return data, f"Stylist {stylist.name} removed."


async def execute_update_stylist_hours(
    params: dict,
    session: AsyncSession,
    shop_id: int,
    last_text: str = "",
) -> tuple[dict | None, str]:
    """Execute update_stylist_hours action."""
    stylist = await resolve_stylist_from_params(params, session, shop_id)
    if not stylist:
        raise ValueError("Which stylist should I update?")
    
    start_time = parse_time_of_day(str(params.get("work_start") or params.get("start_time") or ""))
    end_time = parse_time_of_day(str(params.get("work_end") or params.get("end_time") or ""))
    
    if not start_time or not end_time:
        start_time, end_time = extract_time_range_from_text(last_text)
    
    if not start_time or not end_time:
        raise ValueError("What hours should I set? (e.g., 10:00 to 18:00)")
    
    if end_time <= start_time:
        raise ValueError("End time should be after start time.")
    
    stylist.work_start = start_time
    stylist.work_end = end_time
    await session.commit()
    
    data = {"stylists": await list_stylists_with_details(session, shop_id)}
    return data, f"Updated {stylist.name}'s hours to {start_time.strftime('%H:%M')}–{end_time.strftime('%H:%M')}."


async def execute_update_stylist_specialties(
    params: dict,
    session: AsyncSession,
    shop_id: int,
) -> tuple[dict | None, str]:
    """Execute update_stylist_specialties action."""
    stylist = await resolve_stylist_from_params(params, session, shop_id)
    if not stylist:
        raise ValueError("Which stylist should I update?")
    
    tags = parse_tags(params.get("tags") or params.get("specialties") or params.get("specialties_list"))
    if not tags:
        raise ValueError("What specialties should I set?")
    
    await session.execute(
        StylistSpecialty.__table__.delete().where(StylistSpecialty.stylist_id == stylist.id)
    )
    for tag in tags:
        session.add(StylistSpecialty(stylist_id=stylist.id, tag=tag))
    await session.commit()
    
    data = {"stylists": await list_stylists_with_details(session, shop_id)}
    return data, f"Updated {stylist.name}'s specialties."


async def execute_create_service(
    params: dict,
    session: AsyncSession,
    shop_id: int,
) -> tuple[dict | None, str]:
    """Execute create_service action."""
    name = str(params.get("name") or "").strip()
    if not name:
        raise ValueError("What's the service name?")
    
    duration = parse_duration_minutes(params.get("duration_minutes"))
    if duration == 0:
        duration = 30  # Default
    if duration < 5 or duration > 240:
        raise ValueError("Duration should be between 5 and 240 minutes.")
    
    price_cents = parse_price_cents(params.get("price_cents"))
    if price_cents == 0:
        raise ValueError("What's the price?")
    if price_cents > 500000:
        raise ValueError("Price should be between $1 and $5,000.")
    
    rule = str(params.get("availability_rule") or "").strip().lower()
    if rule not in SUPPORTED_RULES:
        rule = "none"
    
    # Check if service already exists
    existing = await session.execute(
        select(Service).where(Service.shop_id == shop_id, Service.name.ilike(f"%{name}%"))
    )
    if existing.scalar_one_or_none():
        raise ValueError("A service with that name already exists.")
    
    service = Service(
        shop_id=shop_id,
        name=name,
        duration_minutes=duration,
        price_cents=price_cents,
    )
    session.add(service)
    await session.flush()
    
    if rule != "none":
        session.add(ServiceRule(service_id=service.id, rule=rule))
    
    await session.commit()
    await session.refresh(service)
    
    data = {
        "service": {
            "id": service.id,
            "name": service.name,
            "duration_minutes": service.duration_minutes,
            "price_cents": service.price_cents,
            "availability_rule": rule,
        },
        "services": await list_services_with_rules(session, shop_id),
    }
    return data, f"Done. {service.name} added."


async def execute_update_service_price(
    params: dict,
    session: AsyncSession,
    shop_id: int,
) -> tuple[dict | None, str]:
    """Execute update_service_price action."""
    service = await resolve_service_from_params(params, session, shop_id)
    if not service:
        raise ValueError("Which service should I update?")
    
    price_cents = parse_price_cents(params.get("price_cents"))
    if price_cents == 0:
        raise ValueError("What price should I set?")
    if price_cents > 500000:
        raise ValueError("Price should be between $1 and $5,000.")
    
    service.price_cents = price_cents
    await session.commit()
    
    data = {
        "services": await list_services_with_rules(session, shop_id),
        "updated_service": {
            "id": service.id,
            "name": service.name,
            "price_cents": service.price_cents,
        },
    }
    return data, f"Updated {service.name} to ${price_cents/100:.2f}."


async def execute_update_service_duration(
    params: dict,
    session: AsyncSession,
    shop_id: int,
) -> tuple[dict | None, str]:
    """Execute update_service_duration action."""
    service = await resolve_service_from_params(params, session, shop_id)
    if not service:
        raise ValueError("Which service should I update?")
    
    duration = parse_duration_minutes(params.get("duration_minutes"))
    if duration == 0:
        raise ValueError("What duration should I set?")
    if duration < 5 or duration > 240:
        raise ValueError("Duration should be between 5 and 240 minutes.")
    
    service.duration_minutes = duration
    await session.commit()
    
    data = {"services": await list_services_with_rules(session, shop_id)}
    return data, f"Updated {service.name} to {duration} minutes."


async def execute_remove_service(
    params: dict,
    session: AsyncSession,
    shop_id: int,
) -> tuple[dict | None, str]:
    """Execute remove_service action."""
    service = await resolve_service_from_params(params, session, shop_id)
    if not service:
        raise ValueError("Which service should I remove?")

    # Check for bookings
    result = await session.execute(
        select(Booking.id).where(Booking.service_id == service.id).limit(1)
    )
    if result.scalar_one_or_none():
        raise ValueError("That service has bookings. Remove bookings first or keep it.")

    # Remove rule if exists
    rule_result = await session.execute(select(ServiceRule).where(ServiceRule.service_id == service.id))
    rule = rule_result.scalar_one_or_none()
    if rule:
        await session.delete(rule)
    
    await session.delete(service)
    await session.commit()
    
    data = {"services": await list_services_with_rules(session, shop_id)}
    return data, "Service removed."


async def execute_set_service_rule(
    params: dict,
    session: AsyncSession,
    shop_id: int,
) -> tuple[dict | None, str]:
    """Execute set_service_rule action."""
    service = await resolve_service_from_params(params, session, shop_id)
    if not service:
        raise ValueError("Which service should I update?")
    
    rule = str(params.get("availability_rule") or "").strip().lower()
    if rule not in SUPPORTED_RULES:
        raise ValueError("Rule must be weekends_only, weekdays_only, weekday_evenings, or none.")
    
    result = await session.execute(select(ServiceRule).where(ServiceRule.service_id == service.id))
    existing = result.scalar_one_or_none()
    
    if rule == "none":
        if existing:
            await session.delete(existing)
    else:
        if existing:
            existing.rule = rule
        else:
            session.add(ServiceRule(service_id=service.id, rule=rule))
    
    await session.commit()
    
    data = {"services": await list_services_with_rules(session, shop_id)}
    return data, f"Rule updated for {service.name}."


async def execute_add_time_off(
    params: dict,
    session: AsyncSession,
    shop_id: int,
) -> tuple[dict | None, str]:
    """Execute add_time_off action."""
    stylist = await resolve_stylist_from_params(params, session, shop_id)
    if not stylist:
        raise ValueError("Which stylist is this for?")
    
    start_at_utc, end_at_utc, error = parse_time_off_range(params)
    if error:
        raise ValueError(error)
    if not start_at_utc or not end_at_utc or end_at_utc <= start_at_utc:
        raise ValueError("Please provide a valid start and end time.")
    
    reason = str(params.get("reason") or "").strip() or None
    session.add(
        TimeOffBlock(
            stylist_id=stylist.id,
            start_at_utc=start_at_utc,
            end_at_utc=end_at_utc,
            reason=reason,
        )
    )
    await session.commit()
    
    data = {"stylists": await list_stylists_with_details(session, shop_id)}
    return data, f"Time off saved for {stylist.name}."


async def execute_remove_time_off(
    params: dict,
    session: AsyncSession,
    shop_id: int,
) -> tuple[dict | None, str]:
    """Execute remove_time_off action."""
    stylist = await resolve_stylist_from_params(params, session, shop_id)
    if not stylist:
        raise ValueError("Which stylist is this for?")
    
    start_at_utc, end_at_utc, _ = parse_time_off_range(params)
    
    # If no specific time range, try to find all blocks for the date
    if not start_at_utc or not end_at_utc:
        date_str = params.get("date")
        if date_str:
            target_date = parse_date_str(date_str)
            if target_date:
                tz_offset = (
                    int(params.get("tz_offset_minutes"))
                    if params.get("tz_offset_minutes") is not None
                    else get_local_tz_offset_minutes()
                )
                day_start_utc = to_utc_from_local(target_date, time(0, 0), tz_offset)
                day_end_utc = to_utc_from_local(target_date, time(23, 59), tz_offset)
                
                result = await session.execute(
                    select(TimeOffBlock).where(
                        TimeOffBlock.stylist_id == stylist.id,
                        TimeOffBlock.start_at_utc >= day_start_utc,
                        TimeOffBlock.start_at_utc <= day_end_utc,
                    ).order_by(TimeOffBlock.start_at_utc)
                )
                blocks = list(result.scalars().all())
                
                if not blocks:
                    raise ValueError(f"No time off found for {stylist.name} on {date_str}.")
                
                for block in blocks:
                    await session.delete(block)
                await session.commit()
                
                data = {"stylists": await list_stylists_with_details(session, shop_id)}
                count = len(blocks)
                return data, f"Removed {count} time off block{'s' if count > 1 else ''} for {stylist.name} on {date_str}."
        
        raise ValueError("Which date should I remove time off from?")
    
    # If specific times were provided, remove that exact block
    result = await session.execute(
        select(TimeOffBlock).where(
            TimeOffBlock.stylist_id == stylist.id,
            TimeOffBlock.start_at_utc == start_at_utc,
            TimeOffBlock.end_at_utc == end_at_utc,
        )
    )
    block = result.scalar_one_or_none()
    if not block:
        raise ValueError(f"No time off found for {stylist.name} at that time.")
    
    await session.delete(block)
    await session.commit()
    
    data = {"stylists": await list_stylists_with_details(session, shop_id)}
    return data, f"Time off removed for {stylist.name}."


async def execute_create_promo(
    params: dict,
    session: AsyncSession,
    shop_id: int,
) -> tuple[dict | None, str]:
    """Execute create_promo action."""
    custom_copy = str(params.get("name") or params.get("custom_copy") or "").strip()
    
    discount_value = params.get("discount_value")
    if discount_value is None:
        raise ValueError("What's the discount value?")
    discount_value = int(float(discount_value))
    
    discount_type_str = str(params.get("discount_type") or "PERCENT").upper()
    try:
        discount_type = PromoDiscountType(discount_type_str)
    except ValueError:
        discount_type = PromoDiscountType.PERCENT
    
    promo_type_str = str(params.get("promo_type") or "DAILY_PROMO").upper()
    try:
        promo_type = PromoType(promo_type_str)
    except ValueError:
        promo_type = PromoType.DAILY_PROMO
    
    trigger_str = str(params.get("trigger_point") or "AT_CHAT_START").upper()
    try:
        trigger_point = PromoTriggerPoint(trigger_str)
    except ValueError:
        trigger_point = PromoTriggerPoint.AT_CHAT_START
    
    promo = Promo(
        shop_id=shop_id,
        type=promo_type,
        discount_type=discount_type,
        discount_value=discount_value,
        trigger_point=trigger_point,
        custom_copy=custom_copy or None,
        active=True,
    )
    session.add(promo)
    await session.commit()
    await session.refresh(promo)
    
    data = {"promos": await list_promos_data(session, shop_id)}
    return data, f"Created promo with {discount_value}% discount."


async def execute_update_promo(
    params: dict,
    session: AsyncSession,
    shop_id: int,
) -> tuple[dict | None, str]:
    """Execute update_promo action."""
    promo_id = params.get("promo_id")
    
    promo = None
    if promo_id:
        result = await session.execute(
            select(Promo).where(Promo.id == int(promo_id), Promo.shop_id == shop_id)
        )
        promo = result.scalar_one_or_none()
    
    if not promo:
        raise ValueError("Which promo should I update?")
    
    if "discount_value" in params:
        promo.discount_value = int(float(params["discount_value"]))
    if "active" in params:
        promo.active = bool(params["active"])
    if "discount_type" in params:
        try:
            promo.discount_type = PromoDiscountType(str(params["discount_type"]).upper())
        except ValueError:
            pass
    if "custom_copy" in params:
        promo.custom_copy = params["custom_copy"]
    
    await session.commit()
    
    data = {"promos": await list_promos_data(session, shop_id)}
    return data, f"Updated promo #{promo.id}."


async def execute_delete_promo(
    params: dict,
    session: AsyncSession,
    shop_id: int,
) -> tuple[dict | None, str]:
    """Execute delete_promo action."""
    promo_id = params.get("promo_id")
    
    promo = None
    if promo_id:
        result = await session.execute(
            select(Promo).where(Promo.id == int(promo_id), Promo.shop_id == shop_id)
        )
        promo = result.scalar_one_or_none()
    
    if not promo:
        raise ValueError("Which promo should I delete?")
    
    deleted_id = promo.id
    await session.delete(promo)
    await session.commit()
    
    data = {"promos": await list_promos_data(session, shop_id)}
    return data, f"Deleted promo #{deleted_id}."


async def execute_list_services(
    params: dict,
    session: AsyncSession,
    shop_id: int,
) -> tuple[dict | None, str]:
    """Execute list_services action."""
    services = await list_services_with_rules(session, shop_id)
    data = {"services": services}
    
    if not services:
        return data, "No services found."
    
    count = len(services)
    return data, f"Found {count} service{'s' if count != 1 else ''}."


async def execute_list_stylists(
    params: dict,
    session: AsyncSession,
    shop_id: int,
) -> tuple[dict | None, str]:
    """Execute list_stylists action."""
    stylists = await list_stylists_with_details(session, shop_id)
    data = {"stylists": stylists}
    
    if not stylists:
        return data, "No stylists found."
    
    count = len(stylists)
    return data, f"Found {count} stylist{'s' if count != 1 else ''}."


async def execute_list_promos(
    params: dict,
    session: AsyncSession,
    shop_id: int,
) -> tuple[dict | None, str]:
    """Execute list_promos action."""
    promos = await list_promos_data(session, shop_id)
    data = {"promos": promos}
    
    if not promos:
        return data, "No promos found."
    
    count = len(promos)
    return data, f"Found {count} promo{'s' if count != 1 else ''}."


async def execute_get_customer_profile(
    params: dict,
    session: AsyncSession,
    shop_id: int,
) -> tuple[dict | None, str]:
    """Execute get_customer_profile action."""
    phone = str(params.get("phone") or params.get("customer_phone") or "").strip()
    email = str(params.get("email") or params.get("customer_email") or "").strip().lower()
    
    if not phone and not email:
        raise ValueError("Please provide a phone number or email to look up.")
    
    # Find bookings for this customer
    query = select(Booking).where(Booking.shop_id == shop_id)
    if phone:
        query = query.where(Booking.customer_phone == phone)
    elif email:
        query = query.where(Booking.customer_email == email)
    
    query = query.order_by(Booking.start_at_utc.desc()).limit(20)
    result = await session.execute(query)
    bookings = result.scalars().all()
    
    if not bookings:
        raise ValueError("No customer found with that contact info.")
    
    # Build profile from bookings
    customer_name = bookings[0].customer_name if bookings else None
    customer_phone = bookings[0].customer_phone if bookings else phone
    customer_email = bookings[0].customer_email if bookings else email
    
    booking_history = []
    for b in bookings:
        booking_history.append({
            "id": str(b.id),
            "date": b.start_at_utc.strftime("%Y-%m-%d") if b.start_at_utc else None,
            "service_id": b.service_id,
            "stylist_id": b.stylist_id,
            "status": b.status.value if b.status else "unknown",
        })
    
    data = {
        "customer": {
            "name": customer_name,
            "phone": customer_phone,
            "email": customer_email,
            "total_bookings": len(bookings),
        },
        "bookings": booking_history,
    }
    return data, f"Found {len(bookings)} booking{'s' if len(bookings) != 1 else ''} for {customer_name or 'this customer'}."


# ────────────────────────────────────────────────────────────────
# Main Action Executor
# ────────────────────────────────────────────────────────────────

async def execute_owner_action(
    action: dict | None,
    session: AsyncSession,
    shop_id: int,
    last_user_text: str = "",
) -> OwnerChatResponse:
    """
    Execute an owner chat action and return updated response.
    
    Args:
        action: The action dict from AI response
        session: Database session
        shop_id: Shop ID for tenant isolation
        last_user_text: Last user message text for context
    
    Returns:
        OwnerChatResponse with data and reply_override if successful
    """
    if not action:
        logger.debug("[OWNER_ACTIONS] No action to execute")
        return OwnerChatResponse(reply="What would you like to do?", action=None)
    
    action_type = action.get("type")
    params = action.get("params") or {}
    
    logger.info(f"[OWNER_ACTIONS] >>> EXECUTING ACTION: type={action_type}, shop_id={shop_id}")
    logger.info(f"[OWNER_ACTIONS] Action params: {params}")
    
    try:
        data = None
        reply = None
        
        # Stylist actions
        if action_type == "create_stylist":
            data, reply = await execute_create_stylist(params, session, shop_id)
        elif action_type == "remove_stylist":
            data, reply = await execute_remove_stylist(params, session, shop_id)
        elif action_type == "update_stylist_hours":
            data, reply = await execute_update_stylist_hours(params, session, shop_id, last_user_text)
        elif action_type == "update_stylist_specialties":
            data, reply = await execute_update_stylist_specialties(params, session, shop_id)
        elif action_type == "list_stylists":
            data, reply = await execute_list_stylists(params, session, shop_id)
        
        # Service actions
        elif action_type == "create_service":
            data, reply = await execute_create_service(params, session, shop_id)
        elif action_type == "update_service_price":
            data, reply = await execute_update_service_price(params, session, shop_id)
        elif action_type == "update_service_duration":
            data, reply = await execute_update_service_duration(params, session, shop_id)
        elif action_type == "remove_service":
            data, reply = await execute_remove_service(params, session, shop_id)
        elif action_type == "set_service_rule":
            data, reply = await execute_set_service_rule(params, session, shop_id)
        elif action_type == "list_services":
            data, reply = await execute_list_services(params, session, shop_id)
        
        # Time off actions
        elif action_type == "add_time_off":
            data, reply = await execute_add_time_off(params, session, shop_id)
        elif action_type == "remove_time_off":
            data, reply = await execute_remove_time_off(params, session, shop_id)
        
        # Promo actions
        elif action_type == "create_promo":
            data, reply = await execute_create_promo(params, session, shop_id)
        elif action_type == "update_promo":
            data, reply = await execute_update_promo(params, session, shop_id)
        elif action_type == "delete_promo":
            data, reply = await execute_delete_promo(params, session, shop_id)
        elif action_type == "list_promos":
            data, reply = await execute_list_promos(params, session, shop_id)
        
        # Customer actions
        elif action_type == "get_customer_profile":
            data, reply = await execute_get_customer_profile(params, session, shop_id)
        
        # Unknown action
        else:
            logger.warning(f"[OWNER_ACTIONS] Unhandled action type: {action_type}")
            return OwnerChatResponse(
                reply="I understood what you want, but that action isn't implemented yet.",
                action=action,
            )
        
        logger.info(f"[OWNER_ACTIONS] <<< ACTION COMPLETED: type={action_type}, success=True")
        logger.info(f"[OWNER_ACTIONS] Action reply: {reply}")
        if data:
            logger.debug(f"[OWNER_ACTIONS] Action data keys: {list(data.keys()) if isinstance(data, dict) else 'N/A'}")
        
        return OwnerChatResponse(reply=reply, action=action, data=data)
    
    except ValueError as e:
        logger.warning(f"[OWNER_ACTIONS] <<< ACTION FAILED: type={action_type}, error=ValueError: {e}")
        return OwnerChatResponse(reply=str(e), action=None)
    except HTTPException as e:
        logger.warning(f"[OWNER_ACTIONS] <<< ACTION FAILED: type={action_type}, error=HTTPException: {e.detail}")
        return OwnerChatResponse(reply=str(e.detail), action=None)
    except Exception as e:
        logger.error(f"[OWNER_ACTIONS] <<< ACTION FAILED: type={action_type}, error={type(e).__name__}: {e}", exc_info=True)
        return OwnerChatResponse(
            reply="I had trouble completing that step. Please try again.",
            action=None,
        )
