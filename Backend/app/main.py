import logging
import re
import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import List
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, HTTPException, Response, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .core.config import get_settings
from .core.db import AsyncSessionLocal, Base, engine, get_session
from .chat import ChatRequest, ChatResponse, chat_with_ai
from .owner_chat import OwnerChatRequest, OwnerChatResponse, SUPPORTED_RULES, owner_chat_with_ai
from .emailer import send_booking_email_with_ics
from .models import (
    Booking,
    BookingStatus,
    Service,
    ServiceRule,
    Shop,
    Stylist,
    StylistSpecialty,
    TimeOffBlock,
)
from .seed import seed_initial_data


settings = get_settings()
app = FastAPI(title="Convo Booking Backend")
logger = logging.getLogger(__name__)


def get_local_now() -> datetime:
    """Get the current datetime in the configured timezone (Arizona)."""
    tz = ZoneInfo(settings.chat_timezone)
    return datetime.now(tz)


def get_local_tz_offset_minutes() -> int:
    local_now = get_local_now()
    offset = local_now.utcoffset()
    if not offset:
        return 0
    return int(offset.total_seconds() / 60)


def format_utc_timestamp(value: datetime) -> str:
    """Format datetime as UTC timestamp for iCalendar (RFC 5545)."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.strftime("%Y%m%dT%H%M%SZ")


def escape_ical_text(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def build_ics_event(
    uid: str,
    start_at: datetime,
    end_at: datetime,
    summary: str,
    description: str,
    location: str,
) -> str:
    dtstamp = format_utc_timestamp(datetime.now(timezone.utc))
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Convo Salon//Booking//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{dtstamp}",
        f"DTSTART:{format_utc_timestamp(start_at)}",
        f"DTEND:{format_utc_timestamp(end_at)}",
        f"SUMMARY:{escape_ical_text(summary)}",
        f"DESCRIPTION:{escape_ical_text(description)}",
        f"LOCATION:{escape_ical_text(location)}",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    return "\r\n".join(lines) + "\r\n"
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AvailabilitySlot(BaseModel):
    stylist_id: int
    stylist_name: str
    start_time: datetime
    end_time: datetime


class HoldRequest(BaseModel):
    service_id: int
    date: str  # YYYY-MM-DD in local time
    start_time: str  # HH:MM in local time
    stylist_id: int
    customer_name: str | None = None
    customer_email: str | None = None
    tz_offset_minutes: int = Field(default=0, description="Minutes ahead of UTC. Browser offset is negative for Phoenix.")


class HoldResponse(BaseModel):
    booking_id: uuid.UUID
    status: BookingStatus
    hold_expires_at: datetime


class ConfirmRequest(BaseModel):
    booking_id: uuid.UUID


class ConfirmResponse(BaseModel):
    ok: bool
    booking_id: uuid.UUID
    status: BookingStatus


class OwnerScheduleBooking(BaseModel):
    id: uuid.UUID
    stylist_id: int
    stylist_name: str
    service_name: str
    customer_name: str | None
    status: BookingStatus
    start_time: str
    end_time: str


class OwnerScheduleTimeOff(BaseModel):
    id: int
    stylist_id: int
    stylist_name: str
    start_time: str
    end_time: str
    reason: str | None = None


class OwnerScheduleResponse(BaseModel):
    date: str
    stylists: list[dict]
    bookings: list[OwnerScheduleBooking]
    time_off: list[OwnerScheduleTimeOff]


class OwnerTimeOffEntry(BaseModel):
    start_time: str
    end_time: str
    date: str
    reason: str | None = None


class OwnerRescheduleRequest(BaseModel):
    booking_id: uuid.UUID
    stylist_id: int
    date: str
    start_time: str
    tz_offset_minutes: int = 0


class OwnerCancelRequest(BaseModel):
    booking_id: uuid.UUID


def parse_working_hours() -> tuple[time, time]:
    start_hour, start_minute = map(int, settings.working_hours_start.split(":"))
    end_hour, end_minute = map(int, settings.working_hours_end.split(":"))
    return time(start_hour, start_minute), time(end_hour, end_minute)


def is_working_day(local_date: date) -> bool:
    return local_date.weekday() in settings.working_days_list


def get_stylist_hours(stylist: Stylist) -> tuple[time, time]:
    if stylist.work_start and stylist.work_end:
        return stylist.work_start, stylist.work_end
    return parse_working_hours()


@dataclass
class BlockedTime:
    start_at_utc: datetime
    end_at_utc: datetime


def overlap(start_a: datetime, end_a: datetime, start_b: datetime, end_b: datetime) -> bool:
    return start_a < end_b and start_b < end_a


def to_utc_from_local(local_date: date, local_time: time, tz_offset_minutes: int) -> datetime:
    tz = timezone(timedelta(minutes=tz_offset_minutes))
    local_dt = datetime.combine(local_date, local_time, tzinfo=tz)
    return local_dt.astimezone(timezone.utc)


def to_utc_from_local_zone(local_date: date, local_time: time) -> datetime:
    tz = ZoneInfo(settings.chat_timezone)
    local_dt = datetime.combine(local_date, local_time).replace(tzinfo=tz)
    return local_dt.astimezone(timezone.utc)


def to_local_time_str(dt: datetime, tz_offset_minutes: int) -> str:
    tz = timezone(timedelta(minutes=tz_offset_minutes))
    return dt.astimezone(tz).strftime("%H:%M")


def to_local_date_str(dt: datetime, tz_offset_minutes: int) -> str:
    tz = timezone(timedelta(minutes=tz_offset_minutes))
    return dt.astimezone(tz).strftime("%Y-%m-%d")


async def fetch_service(session: AsyncSession, service_id: int) -> Service:
    result = await session.execute(select(Service).where(Service.id == service_id))
    service = result.scalar_one_or_none()
    if not service:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found")
    return service


async def fetch_service_by_name(session: AsyncSession, name: str, shop_id: int) -> Service | None:
    if not name:
        return None
    result = await session.execute(
        select(Service).where(Service.shop_id == shop_id, Service.name.ilike(f"%{name}%"))
    )
    return result.scalar_one_or_none()


async def get_default_shop(session: AsyncSession) -> Shop:
    result = await session.execute(select(Shop).where(Shop.name == settings.default_shop_name))
    shop = result.scalar_one_or_none()
    if not shop:
        shop = Shop(name=settings.default_shop_name)
        session.add(shop)
        await session.flush()
    return shop


async def fetch_stylist(session: AsyncSession, stylist_id: int) -> Stylist:
    result = await session.execute(select(Stylist).where(Stylist.id == stylist_id, Stylist.active.is_(True)))
    stylist = result.scalar_one_or_none()
    if not stylist:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stylist not found or inactive")
    return stylist


async def get_active_bookings_for_stylist(
    session: AsyncSession,
    stylist_id: int,
    window_start: datetime,
    window_end: datetime,
    now: datetime,
    exclude_booking_id: uuid.UUID | None = None,
) -> List[BlockedTime]:
    result = await session.execute(
        select(Booking)
        .where(
            Booking.stylist_id == stylist_id,
            Booking.end_at_utc > window_start,
            Booking.start_at_utc < window_end,
            Booking.status.in_([BookingStatus.HOLD, BookingStatus.CONFIRMED]),
        )
        .order_by(Booking.start_at_utc)
    )
    bookings = result.scalars().all()

    # Filter out expired holds; keep others
    active: list[Booking] = []
    for booking in bookings:
        if exclude_booking_id and booking.id == exclude_booking_id:
            continue
        if booking.status == BookingStatus.HOLD:
            if booking.hold_expires_at_utc and booking.hold_expires_at_utc > now:
                active.append(booking)
        else:
            active.append(booking)

    blocked: list[BlockedTime] = [
        BlockedTime(start_at_utc=b.start_at_utc, end_at_utc=b.end_at_utc) for b in active
    ]

    time_off_result = await session.execute(
        select(TimeOffBlock).where(
            TimeOffBlock.stylist_id == stylist_id,
            TimeOffBlock.end_at_utc > window_start,
            TimeOffBlock.start_at_utc < window_end,
        )
    )
    time_off_blocks = time_off_result.scalars().all()
    blocked.extend(
        BlockedTime(start_at_utc=block.start_at_utc, end_at_utc=block.end_at_utc)
        for block in time_off_blocks
    )

    return blocked


def make_slots_for_stylist(
    stylist: Stylist,
    service_duration: int,
    local_date: date,
    tz_offset_minutes: int,
    working_start: time,
    working_end: time,
    blocked: List[BlockedTime],
    now_utc: datetime,
) -> List[AvailabilitySlot]:
    day_start_utc = to_utc_from_local(local_date, working_start, tz_offset_minutes)
    day_end_utc = to_utc_from_local(local_date, working_end, tz_offset_minutes)

    slots: list[AvailabilitySlot] = []
    cursor = day_start_utc
    step = timedelta(minutes=30)
    duration = timedelta(minutes=service_duration)

    while cursor + duration <= day_end_utc:
        slot_start = cursor
        slot_end = cursor + duration

        # Skip slots that have already started (are in the past)
        if slot_start <= now_utc:
            cursor += step
            continue

        conflict = any(overlap(slot_start, slot_end, b.start_at_utc, b.end_at_utc) for b in blocked)
        if not conflict:
            slots.append(
                AvailabilitySlot(
                    stylist_id=stylist.id,
                    stylist_name=stylist.name,
                    start_time=slot_start,
                    end_time=slot_end,
                )
            )

        cursor += step

    return slots


@app.on_event("startup")
async def on_startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with AsyncSessionLocal() as session:
        await seed_initial_data(session)


@app.get("/services")
async def list_services(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Service).order_by(Service.id))
    services = result.scalars().all()
    return [
        {
            "id": svc.id,
            "name": svc.name,
            "duration_minutes": svc.duration_minutes,
            "price_cents": svc.price_cents,
        }
        for svc in services
    ]


async def list_services_with_rules(session: AsyncSession, shop_id: int):
    result = await session.execute(
        select(Service).where(Service.shop_id == shop_id).order_by(Service.id)
    )
    services = result.scalars().all()
    rules_result = await session.execute(select(ServiceRule))
    rules = {rule.service_id: rule.rule for rule in rules_result.scalars().all()}
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
    result = await session.execute(
        select(Stylist).where(Stylist.shop_id == shop_id).order_by(Stylist.id)
    )
    stylists = result.scalars().all()
    stylist_ids = [stylist.id for stylist in stylists]
    specialties_map: dict[int, list[str]] = {stylist_id: [] for stylist_id in stylist_ids}
    time_off_counts: dict[int, int] = {stylist_id: 0 for stylist_id in stylist_ids}

    if stylist_ids:
        spec_result = await session.execute(
            select(StylistSpecialty).where(StylistSpecialty.stylist_id.in_(stylist_ids))
        )
        for spec in spec_result.scalars().all():
            specialties_map.setdefault(spec.stylist_id, []).append(spec.tag)

        now = datetime.now(timezone.utc)
        time_off_result = await session.execute(
            select(TimeOffBlock).where(
                TimeOffBlock.stylist_id.in_(stylist_ids),
                TimeOffBlock.end_at_utc > now,
            )
        )
        for block in time_off_result.scalars().all():
            time_off_counts[block.stylist_id] = time_off_counts.get(block.stylist_id, 0) + 1

    return [
        {
            "id": stylist.id,
            "name": stylist.name,
            "work_start": stylist.work_start.strftime("%H:%M"),
            "work_end": stylist.work_end.strftime("%H:%M"),
            "active": stylist.active,
            "specialties": specialties_map.get(stylist.id, []),
            "time_off_count": time_off_counts.get(stylist.id, 0),
        }
        for stylist in stylists
    ]


@app.get("/health")
async def healthcheck():
    return {"ok": True}


@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest, session: AsyncSession = Depends(get_session)):
    """AI-powered chat endpoint for booking appointments."""
    ai_response = await chat_with_ai(request.messages, session, request.context)
    action = ai_response.action or {}
    data: dict | None = None
    reply_override: str | None = None

    action_type = action.get("type")
    params = action.get("params") or {}

    try:
        if action_type == "show_services":
            services = await list_services(session)
            data = {"services": services}
        elif action_type == "select_service":
            service_id = int(params.get("service_id") or 0)
            if not service_id and params.get("service_name"):
                svc_name = str(params.get("service_name")).strip().lower()
                result = await session.execute(select(Service).where(Service.name.ilike(f"%{svc_name}%")))
                svc = result.scalar_one_or_none()
            else:
                svc = await fetch_service(session, service_id) if service_id else None
            if svc:
                data = {
                    "selected_service_id": svc.id,
                    "selected_service_name": svc.name,
                }
        elif action_type == "fetch_availability":
            service_id = int(params.get("service_id") or 0)
            if not service_id:
                service_id = int((request.context or {}).get("selected_service_id") or 0)
            date_str = params.get("date") or (request.context or {}).get("selected_date")
            tz_offset = params.get("tz_offset_minutes")
            if tz_offset is None:
                tz_offset = (request.context or {}).get("tz_offset_minutes", 0)
            if service_id and date_str:
                slots = await get_availability(
                    service_id=service_id,
                    date=date_str,
                    tz_offset_minutes=int(tz_offset),
                    session=session,
                )
                data = {
                    "slots": slots,
                    "selected_service_id": service_id,
                    "selected_date": date_str,
                }
                if not slots:
                    reply_override = f"No openings on {date_str}. Try another date?"
                else:
                    reply_override = "Here are a few good options. Tap one to continue."
        elif action_type == "hold_slot":
            service_id = int(params.get("service_id") or 0)
            stylist_id = int(params.get("stylist_id") or 0)
            date_str = params.get("date") or ""
            start_time = params.get("start_time") or ""
            tz_offset = params.get("tz_offset_minutes")
            if tz_offset is None:
                tz_offset = (request.context or {}).get("tz_offset_minutes", 0)
            customer_name = params.get("customer_name") or (request.context or {}).get("customer_name")
            customer_email = params.get("customer_email") or (request.context or {}).get("customer_email")
            payload = HoldRequest(
                service_id=service_id,
                date=date_str,
                start_time=start_time,
                stylist_id=stylist_id,
                customer_name=customer_name,
                customer_email=customer_email,
                tz_offset_minutes=int(tz_offset),
            )
            hold_result = await create_hold(payload, session)

            svc = await fetch_service(session, service_id)
            stylist = await fetch_stylist(session, stylist_id)
            local_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            hour, minute = map(int, start_time.split(":"))
            local_time = time(hour=hour, minute=minute)
            start_at_utc = to_utc_from_local(local_date, local_time, int(tz_offset))
            end_at_utc = start_at_utc + timedelta(minutes=svc.duration_minutes)

            slot = AvailabilitySlot(
                stylist_id=stylist.id,
                stylist_name=stylist.name,
                start_time=start_at_utc,
                end_time=end_at_utc,
            )

            data = {
                "hold": hold_result.model_dump(),
                "selected_service_id": service_id,
                "selected_date": date_str,
                "selected_slot": slot.model_dump(),
            }
            reply_override = "Slot reserved. Tap Confirm booking to finalize."
        elif action_type == "confirm_booking":
            booking_id = params.get("booking_id")
            if not booking_id:
                booking_id = (request.context or {}).get("held_slot", {}).get("booking_id")
            if booking_id:
                confirm_result = await confirm_booking(
                    ConfirmRequest(booking_id=uuid.UUID(str(booking_id))),
                    session,
                )
                data = {"confirmed": confirm_result.model_dump()}
                reply_override = "You're all set. Your booking is confirmed."
    except HTTPException as exc:
        return ChatResponse(reply=str(exc.detail), action=None, data=None)
    except Exception:
        return ChatResponse(reply="I had trouble completing that step. Please try again.", action=None, data=None)

    return ChatResponse(reply=reply_override or ai_response.reply, action=ai_response.action, data=data)


@app.post("/owner/chat", response_model=OwnerChatResponse)
async def owner_chat_endpoint(request: OwnerChatRequest, session: AsyncSession = Depends(get_session)):
    ai_response = await owner_chat_with_ai(request.messages, session)
    action = ai_response.action or {}
    data: dict | None = None
    reply_override: str | None = None

    action_type = action.get("type")
    params = action.get("params") or {}

    shop = await get_default_shop(session)
    result = await session.execute(select(Service).where(Service.shop_id == shop.id).order_by(Service.id))
    service_list = result.scalars().all()
    stylist_result = await session.execute(
        select(Stylist).where(Stylist.shop_id == shop.id).order_by(Stylist.id)
    )
    stylist_list = stylist_result.scalars().all()

    def normalize_text(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()

    def match_service_in_text(text: str) -> Service | None:
        normalized = normalize_text(text)
        for svc in service_list:
            svc_name = normalize_text(svc.name)
            if svc_name and svc_name in normalized:
                return svc
        return None

    def match_stylist_in_text(text: str) -> Stylist | None:
        normalized = normalize_text(text)
        for stylist in stylist_list:
            stylist_name = normalize_text(stylist.name)
            if stylist_name and stylist_name in normalized:
                return stylist
        return None

    def latest_service_from_messages() -> Service | None:
        for msg in reversed(request.messages):
            if msg.role != "user":
                continue
            found = match_service_in_text(msg.content)
            if found:
                return found
        return None

    def latest_stylist_from_messages() -> Stylist | None:
        for msg in reversed(request.messages):
            if msg.role != "user":
                continue
            found = match_stylist_in_text(msg.content)
            if found:
                return found
        return None

    def parse_price_cents(raw: object) -> int:
        if raw is None:
            return 0
        if isinstance(raw, (int, float)):
            return int(float(raw) * 100) if float(raw) < 1000 else int(raw)
        if isinstance(raw, str):
            digits = re.sub(r"[^\d.]", "", raw)
            if not digits:
                return 0
            value = float(digits)
            return int(value * 100) if value < 1000 else int(value)
        return 0

    def parse_duration_minutes(raw: object) -> int:
        if raw is None:
            return 0
        if isinstance(raw, (int, float)):
            return int(raw)
        if isinstance(raw, str):
            match = re.search(r"(\d+(?:\.\d+)?)", raw)
            if not match:
                return 0
            value = float(match.group(1))
            if re.search(r"(hour|hr)", raw, re.IGNORECASE):
                return int(round(value * 60))
            return int(round(value))
        return 0

    async def resolve_service() -> Service | None:
        service_id = params.get("service_id")
        if service_id:
            try:
                return await fetch_service(session, int(service_id))
            except HTTPException:
                return None
        service_name = str(params.get("service_name") or params.get("name") or "").strip()
        if service_name:
            return await fetch_service_by_name(session, service_name, shop.id)
        return None

    async def resolve_stylist() -> Stylist | None:
        stylist_id = params.get("stylist_id")
        if stylist_id:
            try:
                return await fetch_stylist(session, int(stylist_id))
            except HTTPException:
                return None
        stylist_name = str(params.get("stylist_name") or params.get("name") or "").strip()
        if stylist_name:
            result = await session.execute(
                select(Stylist).where(
                    Stylist.shop_id == shop.id,
                    Stylist.name.ilike(f"%{stylist_name}%"),
                )
            )
            return result.scalar_one_or_none()
        return None

    def contains_add_intent(text: str) -> bool:
        normalized = normalize_text(text)
        if not normalized:
            return False
        if re.search(r"\b(add|create|introduce)\b", normalized) or "new service" in normalized:
            if "price" in normalized and "service" not in normalized and "treatment" not in normalized:
                return False
            return True
        return False

    def contains_remove_intent(text: str) -> bool:
        normalized = normalize_text(text)
        return any(word in normalized for word in ["remove", "delete", "drop", "retire"])

    def contains_list_intent(text: str) -> bool:
        normalized = normalize_text(text)
        return "list" in normalized or "show" in normalized

    def contains_price_intent(text: str) -> bool:
        normalized = normalize_text(text)
        return any(word in normalized for word in ["price", "cost", "increase", "decrease", "change", "set", "update"])

    def extract_rule(text: str) -> str:
        normalized = normalize_text(text)
        if "weekend" in normalized:
            return "weekends_only"
        if "evening" in normalized:
            return "weekday_evenings"
        if "weekday" in normalized:
            return "weekdays_only"
        return "none"

    def extract_price_from_text(text: str) -> int:
        if not text:
            return 0
        price_match = re.search(r"\$\s*(\d+(?:\.\d{1,2})?)", text)
        if price_match:
            return parse_price_cents(price_match.group(1))
        if re.search(r"\b(price|cost|usd|dollars?)\b", text, re.IGNORECASE):
            number_match = re.search(r"(\d+(?:\.\d{1,2})?)", text)
            if number_match:
                return parse_price_cents(number_match.group(1))
        return 0

    def extract_duration_from_text(text: str) -> int:
        if not text:
            return 0
        hour_match = re.search(r"(\d+(?:\.\d+)?)\s*(hours?|hrs?|hr)\b", text, re.IGNORECASE)
        if hour_match:
            return int(round(float(hour_match.group(1)) * 60))
        minute_match = re.search(r"(\d+(?:\.\d+)?)\s*(minutes?|mins?|min)\b", text, re.IGNORECASE)
        if minute_match:
            return int(round(float(minute_match.group(1))))
        return 0

    def extract_name_from_add(text: str) -> str:
        if not text:
            return ""
        match = re.search(
            r"\badd\b(?:\s+a|\s+an)?(?:\s+service)?(?:\s+named|\s+called|\s+name)?\s+(.+)",
            text,
            re.IGNORECASE,
        )
        if not match:
            return ""
        name = match.group(1).strip()
        name = name.split(":", 1)[0].strip()
        name = re.split(
            r"\b(for|at|cost|costing|costs|price|duration|taking|with)\b",
            name,
            1,
            flags=re.IGNORECASE,
        )[0].strip()
        name = name.strip(" ,.")
        if not name or re.fullmatch(r"\d+(?:\.\d+)?", name):
            return ""
        if re.search(r"\b(minutes?|mins?|hours?|hrs?|hr)\b", name, re.IGNORECASE):
            return ""
        return name

    def parse_time_of_day(value: str) -> time | None:
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

    def parse_date_str(value: str) -> date | None:
        if not value:
            return None
        try:
            return datetime.strptime(value.strip(), "%Y-%m-%d").date()
        except ValueError:
            return None

    def parse_weekday_date(text: str) -> date | None:
        if not text:
            return None
        match = re.search(
            r"\b(next|this)?\s*(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
            text,
            re.IGNORECASE,
        )
        if not match:
            return None
        modifier = (match.group(1) or "").lower()
        weekday_name = match.group(2).lower()
        weekday_map = {
            "monday": 0,
            "tuesday": 1,
            "wednesday": 2,
            "thursday": 3,
            "friday": 4,
            "saturday": 5,
            "sunday": 6,
        }
        target = weekday_map[weekday_name]
        today = get_local_now().date()
        delta = (target - today.weekday()) % 7
        if modifier == "next" and delta == 0:
            delta = 7
        if modifier == "next" and delta > 0:
            delta = delta
        if modifier == "this" and delta == 0:
            delta = 0
        if delta == 0 and modifier != "this":
            delta = 7
        return today + timedelta(days=delta)

    def parse_month_day(text: str) -> date | None:
        if not text:
            return None
        months = {
            "january": 1,
            "jan": 1,
            "february": 2,
            "feb": 2,
            "march": 3,
            "mar": 3,
            "april": 4,
            "apr": 4,
            "may": 5,
            "june": 6,
            "jun": 6,
            "july": 7,
            "jul": 7,
            "august": 8,
            "aug": 8,
            "september": 9,
            "sep": 9,
            "sept": 9,
            "october": 10,
            "oct": 10,
            "november": 11,
            "nov": 11,
            "december": 12,
            "dec": 12,
        }
        match = re.search(
            r"\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|"
            r"sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+(\d{1,2})(?:st|nd|rd|th)?"
            r"(?:,\s*(\d{4}))?\b",
            text,
            re.IGNORECASE,
        )
        if match:
            month = months.get(match.group(1).lower())
            day = int(match.group(2))
            year = int(match.group(3)) if match.group(3) else get_local_now().year
        else:
            match = re.search(
                r"\b(\d{1,2})(?:st|nd|rd|th)?\s+"
                r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|"
                r"sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
                r"(?:,\s*(\d{4}))?\b",
                text,
                re.IGNORECASE,
            )
            if not match:
                return None
            day = int(match.group(1))
            month = months.get(match.group(2).lower())
            year = int(match.group(3)) if match.group(3) else get_local_now().year
        try:
            return date(year, month, day)
        except ValueError:
            return None

    def infer_date_from_messages() -> date | None:
        for msg in reversed(request.messages):
            if msg.role != "user":
                continue
            text = msg.content or ""
            date_match = re.search(r"\d{4}-\d{2}-\d{2}", text)
            if date_match:
                parsed = parse_date_str(date_match.group(0))
                if parsed:
                    return parsed
            month_day = parse_month_day(text)
            if month_day:
                return month_day
            weekday = parse_weekday_date(text)
            if weekday:
                return weekday
        return None

    def parse_time_off_range(raw_params: dict) -> tuple[datetime | None, datetime | None, str | None]:
        tz_offset = raw_params.get("tz_offset_minutes")
        date_str = raw_params.get("date")
        start_time_str = raw_params.get("start_time")
        end_time_str = raw_params.get("end_time")
        if date_str and start_time_str and end_time_str:
            try:
                date = parse_date_str(date_str)
                start_time = parse_time_of_day(start_time_str)
                end_time = parse_time_of_day(end_time_str)
                if date and start_time and end_time:
                    if tz_offset is not None:
                        return (
                            to_utc_from_local(date, start_time, int(tz_offset)),
                            to_utc_from_local(date, end_time, int(tz_offset)),
                            None,
                        )
                    return (
                        to_utc_from_local_zone(date, start_time),
                        to_utc_from_local_zone(date, end_time),
                        None,
                    )
            except ValueError:
                return None, None, "Invalid date or time format."
        start_at = raw_params.get("start_at")
        end_at = raw_params.get("end_at")
        if isinstance(start_at, str) and isinstance(end_at, str):
            try:
                start_dt = datetime.fromisoformat(start_at)
                end_dt = datetime.fromisoformat(end_at)
                if start_dt.tzinfo and end_dt.tzinfo:
                    return start_dt.astimezone(timezone.utc), end_dt.astimezone(timezone.utc), None
            except ValueError:
                return None, None, "Start/end time format should be ISO datetime."

        start_local = raw_params.get("start_at_local")
        end_local = raw_params.get("end_at_local")
        if isinstance(start_local, str) and isinstance(end_local, str):
            try:
                start_date_str, start_time_str = re.split(r"[T\\s]+", start_local.strip(), maxsplit=1)
                end_date_str, end_time_str = re.split(r"[T\\s]+", end_local.strip(), maxsplit=1)
                start_date = parse_date_str(start_date_str)
                end_date = parse_date_str(end_date_str)
                start_time = parse_time_of_day(start_time_str)
                end_time = parse_time_of_day(end_time_str)
                if start_date and end_date and start_time and end_time:
                    if tz_offset is not None:
                        return (
                            to_utc_from_local(start_date, start_time, int(tz_offset)),
                            to_utc_from_local(end_date, end_time, int(tz_offset)),
                            None,
                        )
                    return (
                        to_utc_from_local_zone(start_date, start_time),
                        to_utc_from_local_zone(end_date, end_time),
                        None,
                    )
            except ValueError:
                return None, None, "Start/end time format should be YYYY-MM-DD HH:MM."

        date_str = raw_params.get("date") or raw_params.get("day")
        start_time_str = raw_params.get("start_time") or raw_params.get("start")
        end_time_str = raw_params.get("end_time") or raw_params.get("end")
        local_date = parse_date_str(str(date_str)) if date_str else None
        start_time = parse_time_of_day(str(start_time_str)) if start_time_str else None
        end_time = parse_time_of_day(str(end_time_str)) if end_time_str else None
        if local_date and start_time and end_time:
            if tz_offset is not None:
                return (
                    to_utc_from_local(local_date, start_time, int(tz_offset)),
                    to_utc_from_local(local_date, end_time, int(tz_offset)),
                    None,
                )
            return (
                to_utc_from_local_zone(local_date, start_time),
                to_utc_from_local_zone(local_date, end_time),
                None,
            )

        raw_text = str(raw_params.get("raw_text") or raw_params.get("text") or "")
        date_match = re.search(r"\d{4}-\d{2}-\d{2}", raw_text)
        inferred_date = (
            parse_date_str(date_match.group(0)) if date_match else None
        ) or parse_weekday_date(raw_text)
        inferred_start, inferred_end = extract_time_range_from_text(raw_text)
        if inferred_date and inferred_start and inferred_end:
            return (
                to_utc_from_local_zone(inferred_date, inferred_start),
                to_utc_from_local_zone(inferred_date, inferred_end),
                None,
            )

        return None, None, "Provide a date (YYYY-MM-DD) with start/end time."

    def normalize_tag(value: str) -> str:
        return re.sub(r"\s+", " ", value.strip().lower())

    def parse_tags(raw: object) -> list[str]:
        if raw is None:
            return []
        if isinstance(raw, list):
            tags = [normalize_tag(str(tag)) for tag in raw]
        else:
            cleaned = str(raw)
            cleaned = re.sub(
                r".*special(?:ty|ties|ize|izes|ized|izing)?\\s+in\\s+",
                "",
                cleaned,
                flags=re.IGNORECASE,
            )
            cleaned = re.sub(r"[+&]", ",", cleaned)
            cleaned = re.sub(r"\band\b", ",", cleaned, flags=re.IGNORECASE)
            tags = [normalize_tag(tag) for tag in cleaned.split(",")]
        return [tag for tag in tags if tag]

    def collect_create_fields_from_messages() -> dict:
        fields = {
            "name": "",
            "duration_minutes": 0,
            "price_cents": 0,
            "availability_rule": "none",
        }
        seen_add = False
        for msg in reversed(request.messages[-8:]):
            if msg.role != "user":
                continue
            text = msg.content or ""
            if contains_remove_intent(text) or contains_list_intent(text):
                if seen_add:
                    break
                if not contains_add_intent(text):
                    break
                continue
            if contains_price_intent(text) and not contains_add_intent(text) and not seen_add:
                break
            if contains_add_intent(text):
                seen_add = True

            extracted_name = extract_name_from_add(text)
            extracted_duration = extract_duration_from_text(text)
            extracted_price = extract_price_from_text(text)
            extracted_rule = extract_rule(text)

            if extracted_name and not fields["name"]:
                fields["name"] = extracted_name
            if extracted_duration and not fields["duration_minutes"]:
                fields["duration_minutes"] = extracted_duration
            if extracted_price and not fields["price_cents"]:
                fields["price_cents"] = extracted_price
            if fields["availability_rule"] == "none" and extracted_rule != "none":
                fields["availability_rule"] = extracted_rule

            if seen_add and fields["name"] and fields["duration_minutes"] and fields["price_cents"]:
                break

        if not seen_add:
            return {}
        return fields

    def find_service_for_update(text: str) -> Service | None:
        service = match_service_in_text(text)
        if service:
            return service
        for msg in reversed(request.messages[-6:]):
            if msg.role != "user":
                continue
            msg_text = msg.content or ""
            if contains_add_intent(msg_text) or contains_remove_intent(msg_text) or contains_list_intent(msg_text):
                break
            service = match_service_in_text(msg_text)
            if service:
                return service
        return None

    def find_service_for_remove(text: str) -> Service | None:
        service = match_service_in_text(text)
        if service:
            return service
        for msg in reversed(request.messages[-6:]):
            if msg.role != "user":
                continue
            msg_text = msg.content or ""
            if contains_add_intent(msg_text) or contains_price_intent(msg_text) or contains_list_intent(msg_text):
                break
            service = match_service_in_text(msg_text)
            if service:
                return service
        return None

    last_user = next((msg for msg in reversed(request.messages) if msg.role == "user"), None)
    last_text = last_user.content if last_user else ""
    normalized_last = normalize_text(last_text)
    create_fields = collect_create_fields_from_messages()
    add_intent = contains_add_intent(last_text)
    list_intent = contains_list_intent(last_text)
    remove_intent = contains_remove_intent(last_text)
    price_in_text = extract_price_from_text(last_text)
    price_keyword_intent = contains_price_intent(last_text)
    price_intent = price_keyword_intent or bool(price_in_text)
    stylist_list_intent = "stylist" in normalized_last and list_intent
    stylist_add_intent = "stylist" in normalized_last and any(
        word in normalized_last for word in ["add", "create", "new", "hire"]
    )
    stylist_remove_intent = "stylist" in normalized_last and remove_intent
    stylist_specialty_intent = any(
        word in normalized_last for word in ["specialty", "specialties", "specialize", "specializes"]
    )
    stylist_time_off_intent = any(
        phrase in normalized_last for phrase in ["time off", "off", "vacation", "pto"]
    )
    time_off_query_intent = any(
        phrase in normalized_last for phrase in ["time off", "vacation", "pto"]
    ) and any(
        word in normalized_last for word in ["who", "when", "any", "show", "list", "have"]
    )
    schedule_intent = any(word in normalized_last for word in ["schedule", "appointment", "appointments", "booking", "bookings"])
    reschedule_intent = any(word in normalized_last for word in ["reschedule", "move", "change", "shift"])
    create_signal = bool(
        add_intent
        or extract_name_from_add(last_text)
        or extract_duration_from_text(last_text)
        or (price_in_text and not price_keyword_intent)
    )

    try:
        inferred_date = infer_date_from_messages()
        stylist_for_schedule = match_stylist_in_text(last_text) or latest_stylist_from_messages()
        from_time, to_time = extract_time_range_from_text(last_text)
        tz_offset_default = get_local_tz_offset_minutes()
        if reschedule_intent and stylist_for_schedule and from_time and to_time:
            action_type = "reschedule_booking"
            action = {
                "type": action_type,
                "params": {
                    "stylist_name": stylist_for_schedule.name,
                    "from_time": from_time.strftime("%H:%M"),
                    "to_time": to_time.strftime("%H:%M"),
                    "date": inferred_date.isoformat() if inferred_date else None,
                    "tz_offset_minutes": tz_offset_default,
                },
            }
            params = action["params"]
        elif time_off_query_intent and action_type in {None, "list_services", "list_stylists"}:
            action_type = "list_schedule"
            action = {
                "type": action_type,
                "params": {
                    "date": inferred_date.isoformat() if inferred_date else None,
                    "stylist_name": stylist_for_schedule.name if stylist_for_schedule else None,
                    "time_off_only": True,
                    "tz_offset_minutes": tz_offset_default,
                },
            }
            params = action["params"]
        elif schedule_intent and action_type in {None, "list_services", "list_stylists"}:
            action_type = "list_schedule"
            action = {
                "type": action_type,
                "params": {
                    "date": inferred_date.isoformat() if inferred_date else None,
                    "stylist_name": stylist_for_schedule.name if stylist_for_schedule else None,
                    "tz_offset_minutes": tz_offset_default,
                },
            }
            params = action["params"]

        if stylist_add_intent and action_type in {
            "list_services",
            "list_stylists",
            "create_service",
            "update_service_price",
            "update_service_duration",
            "remove_service",
            "set_service_rule",
        }:
            action_type = "create_stylist"
            action = {"type": action_type, "params": {"name": last_text}}
            params = action["params"]

        if stylist_remove_intent and action_type in {
            "list_services",
            "list_stylists",
            "create_service",
            "update_service_price",
            "update_service_duration",
            "remove_service",
            "set_service_rule",
        }:
            stylist = match_stylist_in_text(last_text) or latest_stylist_from_messages()
            if stylist:
                action_type = "remove_stylist"
                action = {"type": action_type, "params": {"stylist_id": stylist.id}}
                params = action["params"]

        if "stylist" in normalized_last and action_type == "list_services":
            action_type = "list_stylists"
            action = {"type": action_type, "params": {}}
            params = action["params"]

        if create_fields and create_signal and action_type in {
            "update_service_price",
            "update_service_duration",
            "remove_service",
            "set_service_rule",
        }:
            action_type = None
            action = {}
            params = {}

        if action_type == "create_service" and create_fields:
            if not params.get("name") and create_fields.get("name"):
                params["name"] = create_fields["name"]
            if not params.get("duration_minutes") and create_fields.get("duration_minutes"):
                params["duration_minutes"] = create_fields["duration_minutes"]
            if not params.get("price_cents") and create_fields.get("price_cents"):
                params["price_cents"] = create_fields["price_cents"]
            if params.get("availability_rule") in [None, "", "none"] and create_fields.get("availability_rule"):
                params["availability_rule"] = create_fields["availability_rule"]

        if not action_type:
            if create_fields and create_signal:
                action_type = "create_service"
                action = {"type": action_type, "params": create_fields}
                params = action["params"]
            elif stylist_list_intent:
                action_type = "list_stylists"
                action = {"type": action_type, "params": {}}
                params = action["params"]
            elif stylist_add_intent:
                action_type = "create_stylist"
                action = {"type": action_type, "params": {"name": last_text}}
                params = action["params"]
            elif stylist_remove_intent:
                stylist = match_stylist_in_text(last_text) or latest_stylist_from_messages()
                if stylist:
                    action_type = "remove_stylist"
                    action = {"type": action_type, "params": {"stylist_id": stylist.id}}
                    params = action["params"]
            elif list_intent:
                action_type = "list_services"
                action = {"type": action_type, "params": {}}
            elif remove_intent:
                service = find_service_for_remove(last_text)
                if service:
                    action_type = "remove_service"
                    action = {"type": action_type, "params": {"service_id": service.id}}
                    params = action["params"]
            elif price_intent:
                price_cents = price_in_text
                service = find_service_for_update(last_text)
                if price_cents or service:
                    action_type = "update_service_price"
                    action = {
                        "type": action_type,
                        "params": {
                            "service_id": service.id if service else None,
                            "price_cents": price_cents,
                        },
                    }
                    params = action["params"]
            elif stylist_specialty_intent:
                stylist = match_stylist_in_text(last_text) or latest_stylist_from_messages()
                if stylist:
                    action_type = "update_stylist_specialties"
                    action = {
                        "type": action_type,
                        "params": {"stylist_id": stylist.id, "tags": last_text},
                    }
                    params = action["params"]
            elif stylist_time_off_intent:
                stylist = match_stylist_in_text(last_text) or latest_stylist_from_messages()
                if stylist and not time_off_query_intent:
                    if remove_intent:
                        action_type = "remove_time_off"
                    else:
                        action_type = "add_time_off"
                    action = {
                        "type": action_type,
                        "params": {"stylist_id": stylist.id, "raw_text": last_text},
                    }
                    params = action["params"]

        if action_type == "list_services":
            data = {"services": await list_services_with_rules(session, shop.id)}
            reply_override = "Here are your current services."

        elif action_type == "list_schedule":
            date_str = params.get("date") or datetime.now().date().isoformat()
            tz_offset = (
                int(params.get("tz_offset_minutes"))
                if params.get("tz_offset_minutes") is not None
                else get_local_tz_offset_minutes()
            )
            schedule = await owner_schedule(date=date_str, tz_offset_minutes=tz_offset, session=session)  # type: ignore[arg-type]
            data = {"schedule": schedule.model_dump()}
            stylist = await resolve_stylist()
            time_off_only = bool(params.get("time_off_only"))
            if stylist:
                stylist_time_off = [b for b in schedule.time_off if b.stylist_id == stylist.id]
                if time_off_only:
                    if stylist_time_off:
                        slots = [
                            f"{b.start_time}–{b.end_time}" + (f" ({b.reason})" if b.reason else "")
                            for b in stylist_time_off
                        ]
                        reply_override = (
                            f"{stylist.name} has time off on {date_str}: " + "; ".join(slots) + "."
                        )
                    else:
                        reply_override = f"{stylist.name} has no time off on {date_str}."
                else:
                    stylist_bookings = [
                        b for b in schedule.bookings if b.stylist_id == stylist.id
                    ]
                    if stylist_bookings:
                        def to_ampm(value: str) -> str:
                            try:
                                hh, mm = value.split(":")
                                hour = int(hh)
                                minute = int(mm)
                            except Exception:
                                return value
                            meridiem = "AM"
                            if hour >= 12:
                                meridiem = "PM"
                            hour = hour % 12 or 12
                            return f"{hour}:{minute:02d} {meridiem}"

                        slots = [
                            f"{to_ampm(b.start_time)}–{to_ampm(b.end_time)} ({b.service_name})"
                            for b in stylist_bookings
                        ]
                        reply_override = (
                            f"{stylist.name} has {len(stylist_bookings)} booking(s) on {date_str}: "
                            + "; ".join(slots)
                            + "."
                        )
                    else:
                        reply_override = f"{stylist.name} has no bookings on {date_str}."
            else:
                total_bookings = len(schedule.bookings)
                if total_bookings > 0:
                    stylist_counts = {}
                    for b in schedule.bookings:
                        stylist_name = next((s['name'] for s in schedule.stylists if s['id'] == b.stylist_id), 'Unknown')
                        stylist_counts[stylist_name] = stylist_counts.get(stylist_name, 0) + 1
                    summary = ", ".join(f"{name}: {count}" for name, count in stylist_counts.items())
                    reply_override = f"Schedule for {date_str}: {total_bookings} booking(s) total. Breakdown: {summary}."
                else:
                    reply_override = f"No bookings on {date_str}."
                # Add time off summary
                time_off_blocks = schedule.time_off
                if time_off_blocks:
                    time_off_list = []
                    for block in time_off_blocks:
                        stylist_name = next((s['name'] for s in schedule.stylists if s['id'] == block.stylist_id), 'Unknown')
                        time_off_list.append(f"{stylist_name}: {block.start_time}-{block.end_time}" + (f" ({block.reason})" if block.reason else ""))
                    time_off_summary = "; ".join(time_off_list)
                    reply_override += f" Time off: {time_off_summary}."
                else:
                    reply_override += " No time off."

        elif action_type == "reschedule_booking":
            date_str = params.get("date") or datetime.now().date().isoformat()
            tz_offset = (
                int(params.get("tz_offset_minutes"))
                if params.get("tz_offset_minutes") is not None
                else get_local_tz_offset_minutes()
            )
            from_stylist_name = params.get("from_stylist_name")
            to_stylist_name = params.get("to_stylist_name")
            from_time: time | None = parse_time_of_day(str(params.get("from_time") or ""))
            to_time: time | None = parse_time_of_day(str(params.get("to_time") or ""))
            if not from_stylist_name or not to_stylist_name or not from_time or not to_time:
                return OwnerChatResponse(reply="I need from stylist, to stylist, from time, and to time to move that booking.", action=None)
            from_stylist = await fetch_stylist_by_name(session, from_stylist_name)
            to_stylist = await fetch_stylist_by_name(session, to_stylist_name)
            if not from_stylist or not to_stylist:
                return OwnerChatResponse(reply="I couldn't find one of the stylists.", action=None)
            schedule = await owner_schedule(date=date_str, tz_offset_minutes=tz_offset, session=session)  # type: ignore[arg-type]
            target_booking = None
            for b in schedule.bookings:
                if b.stylist_id == from_stylist.id and b.start_time.startswith(from_time.strftime("%H:%M")):
                    target_booking = b
                    break
            if not target_booking:
                return OwnerChatResponse(
                    reply=f"I couldn't find a booking for {from_stylist.name} at {from_time.strftime('%-I:%M %p')} on {date_str}.",
                    action=None,
                )
            await owner_reschedule_booking(
                OwnerRescheduleRequest(
                    booking_id=target_booking.id,
                    stylist_id=to_stylist.id,
                    date=date_str,
                    start_time=to_time.strftime("%H:%M"),
                    tz_offset_minutes=tz_offset,
                ),
                session,
            )
            # Return updated schedule
            updated = await owner_schedule(date=date_str, tz_offset_minutes=tz_offset, session=session)  # type: ignore[arg-type]
            data = {"schedule": updated.model_dump()}
            reply_override = f"Moved {from_stylist.name}'s booking from {from_time.strftime('%-I:%M %p')} to {to_stylist.name} at {to_time.strftime('%-I:%M %p')}."

        elif action_type == "list_stylists":
            data = {"stylists": await list_stylists_with_details(session, shop.id)}
            reply_override = "Here are your current stylists."

        elif action_type == "create_service":
            name = str(params.get("name") or "").strip()
            duration = parse_duration_minutes(params.get("duration_minutes"))
            price_cents = parse_price_cents(params.get("price_cents"))
            rule = str(params.get("availability_rule") or "none").strip().lower()

            if not name:
                return OwnerChatResponse(reply="What's the service name?", action=None)
            if duration == 0:
                return OwnerChatResponse(reply="How many minutes is the service?", action=None)
            if duration < 5 or duration > 240:
                return OwnerChatResponse(reply="Duration should be between 5 and 240 minutes.", action=None)
            if price_cents == 0:
                return OwnerChatResponse(reply="What price should I set?", action=None)
            if price_cents <= 0 or price_cents > 500000:
                return OwnerChatResponse(reply="Price should be between $1 and $5,000.", action=None)
            if rule not in SUPPORTED_RULES:
                return OwnerChatResponse(
                    reply="Rule must be weekends_only, weekdays_only, weekday_evenings, or none.",
                    action=None,
                )

            existing = await fetch_service_by_name(session, name, shop.id)
            if existing:
                return OwnerChatResponse(reply="That service already exists.", action=None)

            service = Service(
                shop_id=shop.id,
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
                "services": await list_services_with_rules(session, shop.id),
            }
            reply_override = f"Done. {service.name} added."

        elif action_type == "create_stylist":
            raw_name = str(params.get("name") or "").strip()
            name = raw_name
            match = re.search(
                r"\\badd\\b\\s+(?:a\\s+)?(?:new\\s+)?stylist\\s+([a-z][a-z\\s'-]+)",
                raw_name,
                re.IGNORECASE,
            )
            if not match:
                match = re.search(
                    r"\\badd\\b\\s+([a-z][a-z\\s'-]+?)\\s+as\\s+(?:a\\s+)?stylist",
                    raw_name,
                    re.IGNORECASE,
                )
            if not match and "stylist" in normalize_text(raw_name):
                match = re.search(r"stylist\\s+([a-z][a-z\\s'-]+)", raw_name, re.IGNORECASE)
            if not match:
                match = re.search(r"\\badd\\b\\s+([a-z][a-z\\s'-]+)", raw_name, re.IGNORECASE)
            if match:
                name = match.group(1).strip()
                name = re.split(r"\\b(from|to|with|at|as)\\b", name, 1, flags=re.IGNORECASE)[0].strip()
            if not name:
                return OwnerChatResponse(reply="What's the stylist's name?", action=None)

            work_start = parse_time_of_day(str(params.get("work_start") or "")) if params.get("work_start") else None
            work_end = parse_time_of_day(str(params.get("work_end") or "")) if params.get("work_end") else None
            if not work_start or not work_end:
                work_start, work_end = extract_time_range_from_text(raw_name)
            if not work_start or not work_end:
                work_start, work_end = parse_working_hours()
            if work_end <= work_start:
                return OwnerChatResponse(reply="End time should be after start time.", action=None)

            existing_stylist = await session.execute(
                select(Stylist).where(Stylist.shop_id == shop.id, Stylist.name.ilike(f"%{name}%"))
            )
            if existing_stylist.scalar_one_or_none():
                return OwnerChatResponse(reply="That stylist already exists.", action=None)

            stylist = Stylist(
                shop_id=shop.id,
                name=name,
                work_start=work_start,
                work_end=work_end,
                active=True,
            )
            session.add(stylist)
            await session.commit()
            await session.refresh(stylist)
            data = {"stylists": await list_stylists_with_details(session, shop.id)}
            reply_override = f"Added stylist {stylist.name} ({work_start.strftime('%H:%M')}–{work_end.strftime('%H:%M')})."

        elif action_type == "update_service_price":
            service = await resolve_service()
            if not service:
                return OwnerChatResponse(reply="Which service should I update?", action=None)
            price_cents = parse_price_cents(params.get("price_cents"))
            if price_cents == 0:
                return OwnerChatResponse(reply="What price should I set?", action=None)
            if price_cents > 500000:
                return OwnerChatResponse(reply="Price should be between $1 and $5,000.", action=None)
            service.price_cents = price_cents
            await session.commit()
            data = {
                "services": await list_services_with_rules(session, shop.id),
                "updated_service": {
                    "id": service.id,
                    "name": service.name,
                    "price_cents": service.price_cents,
                },
            }
            reply_override = f"Updated {service.name} to ${price_cents/100:.2f}."

        elif action_type == "update_stylist_hours":
            stylist = await resolve_stylist()
            if not stylist:
                return OwnerChatResponse(reply="Which stylist should I update?", action=None)
            start_time = parse_time_of_day(str(params.get("work_start") or params.get("start_time") or ""))
            end_time = parse_time_of_day(str(params.get("work_end") or params.get("end_time") or ""))
            if not start_time or not end_time:
                start_time, end_time = extract_time_range_from_text(last_text)
            if not start_time or not end_time:
                return OwnerChatResponse(reply="What hours should I set? (e.g., 10:00 to 18:00)", action=None)
            if end_time <= start_time:
                return OwnerChatResponse(reply="End time should be after start time.", action=None)
            stylist.work_start = start_time
            stylist.work_end = end_time
            await session.commit()
            data = {"stylists": await list_stylists_with_details(session, shop.id)}
            reply_override = f"Updated {stylist.name}'s hours to {start_time.strftime('%H:%M')}–{end_time.strftime('%H:%M')}."

        elif action_type == "update_stylist_specialties":
            stylist = await resolve_stylist()
            if not stylist:
                return OwnerChatResponse(reply="Which stylist should I update?", action=None)
            tags = parse_tags(params.get("tags") or params.get("specialties") or params.get("specialties_list"))
            if not tags:
                return OwnerChatResponse(reply="What specialties should I set?", action=None)
            await session.execute(
                StylistSpecialty.__table__.delete().where(StylistSpecialty.stylist_id == stylist.id)
            )
            for tag in tags:
                session.add(StylistSpecialty(stylist_id=stylist.id, tag=tag))
            await session.commit()
            data = {"stylists": await list_stylists_with_details(session, shop.id)}
            reply_override = f"Updated {stylist.name}'s specialties."

        elif action_type == "add_time_off":
            stylist = await resolve_stylist()
            if not stylist:
                return OwnerChatResponse(reply="Which stylist is this for?", action=None)
            start_at_utc, end_at_utc, error = parse_time_off_range(params)
            if error:
                return OwnerChatResponse(reply=error, action=None)
            if not start_at_utc or not end_at_utc or end_at_utc <= start_at_utc:
                return OwnerChatResponse(reply="Please provide a valid start and end time.", action=None)
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
            date_str = params.get("date") or (infer_date_from_messages().isoformat() if infer_date_from_messages() else None)
            tz_offset = (
                int(params.get("tz_offset_minutes"))
                if params.get("tz_offset_minutes") is not None
                else get_local_tz_offset_minutes()
            )
            schedule = await owner_schedule(
                date=date_str or datetime.now().date().isoformat(),
                tz_offset_minutes=tz_offset,
                session=session,
            )  # type: ignore[arg-type]
            data = {
                "stylists": await list_stylists_with_details(session, shop.id),
                "schedule": schedule.model_dump(),
            }
            reply_override = f"Time off saved for {stylist.name}."

        elif action_type == "remove_time_off":
            stylist = await resolve_stylist()
            if not stylist:
                return OwnerChatResponse(reply="Which stylist is this for?", action=None)
            start_at_utc, end_at_utc, error = parse_time_off_range(params)
            if error:
                return OwnerChatResponse(reply=error, action=None)
            if not start_at_utc or not end_at_utc:
                return OwnerChatResponse(reply="Please provide a valid start and end time.", action=None)
            # Find and delete the time off block
            result = await session.execute(
                select(TimeOffBlock).where(
                    TimeOffBlock.stylist_id == stylist.id,
                    TimeOffBlock.start_at_utc == start_at_utc,
                    TimeOffBlock.end_at_utc == end_at_utc,
                )
            )
            block = result.scalar_one_or_none()
            if not block:
                return OwnerChatResponse(reply=f"No time off found for {stylist.name} at that time.", action=None)
            await session.delete(block)
            await session.commit()
            date_str = params.get("date") or (infer_date_from_messages().isoformat() if infer_date_from_messages() else None)
            tz_offset = (
                int(params.get("tz_offset_minutes"))
                if params.get("tz_offset_minutes") is not None
                else get_local_tz_offset_minutes()
            )
            schedule = await owner_schedule(
                date=date_str or datetime.now().date().isoformat(),
                tz_offset_minutes=tz_offset,
                session=session,
            )  # type: ignore[arg-type]
            data = {
                "stylists": await list_stylists_with_details(session, shop.id),
                "schedule": schedule.model_dump(),
            }
            reply_override = f"Time off removed for {stylist.name}."

        elif action_type == "update_service_duration":
            service = await resolve_service()
            if not service:
                return OwnerChatResponse(reply="Which service should I update?", action=None)
            duration = parse_duration_minutes(params.get("duration_minutes"))
            if duration == 0:
                return OwnerChatResponse(reply="What duration should I set?", action=None)
            if duration < 5 or duration > 240:
                return OwnerChatResponse(reply="Duration should be between 5 and 240 minutes.", action=None)
            service.duration_minutes = duration
            await session.commit()
            data = {"services": await list_services_with_rules(session, shop.id)}
            reply_override = f"Updated {service.name} to {duration} minutes."

        elif action_type == "remove_service":
            service = await resolve_service()
            if not service:
                return OwnerChatResponse(reply="Which service should I remove?", action=None)

            result = await session.execute(
                select(Booking.id).where(Booking.service_id == service.id).limit(1)
            )
            if result.scalar_one_or_none():
                return OwnerChatResponse(
                    reply="That service has bookings. Remove bookings first or keep it.",
                    action=None,
                )

            rule_result = await session.execute(select(ServiceRule).where(ServiceRule.service_id == service.id))
            rule = rule_result.scalar_one_or_none()
            if rule:
                await session.delete(rule)
            await session.delete(service)
            await session.commit()
            data = {"services": await list_services_with_rules(session, shop.id)}
            reply_override = "Service removed."

        elif action_type == "remove_stylist":
            stylist = await resolve_stylist()
            if not stylist:
                return OwnerChatResponse(reply="Which stylist should I remove?", action=None)

            result = await session.execute(
                select(Booking.id).where(Booking.stylist_id == stylist.id).limit(1)
            )
            if result.scalar_one_or_none():
                return OwnerChatResponse(
                    reply="That stylist has bookings. Remove bookings first or keep them.",
                    action=None,
                )

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
            data = {"stylists": await list_stylists_with_details(session, shop.id)}
            reply_override = f"Stylist {stylist.name} removed."

        elif action_type == "set_service_rule":
            service = await resolve_service()
            if not service:
                return OwnerChatResponse(reply="Which service should I update?", action=None)
            rule = str(params.get("availability_rule") or "").strip().lower()
            if rule not in SUPPORTED_RULES:
                return OwnerChatResponse(
                    reply="Rule must be weekends_only, weekdays_only, weekday_evenings, or none.",
                    action=None,
                )
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
            data = {"services": await list_services_with_rules(session, shop.id)}
            reply_override = f"Rule updated for {service.name}."

    except HTTPException as exc:
        return OwnerChatResponse(reply=str(exc.detail), action=None)
    except Exception:
        return OwnerChatResponse(reply="I couldn't complete that update. Please try again.", action=None)

    return OwnerChatResponse(reply=reply_override or ai_response.reply, action=ai_response.action, data=data)


@app.get("/owner/stylists/{stylist_id}/time_off")
async def get_stylist_time_off(stylist_id: int, session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(TimeOffBlock).where(TimeOffBlock.stylist_id == stylist_id).order_by(TimeOffBlock.start_at_utc)
    )
    blocks = result.scalars().all()
    tz_offset = 0  # or get from request, but for simplicity
    return [
        {
            "id": b.id,
            "start_time": to_local_time_str(b.start_at_utc, tz_offset),
            "end_time": to_local_time_str(b.end_at_utc, tz_offset),
            "reason": b.reason,
            "date": b.start_at_utc.date().isoformat(),
        }
        for b in blocks
    ]


@app.get("/owner/schedule")
async def owner_schedule(
    date: str,
    tz_offset_minutes: int = 0,
    session: AsyncSession = Depends(get_session),
):
    try:
        local_date = datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid date format")

    shop = await get_default_shop(session)
    stylists = await list_stylists_with_details(session, shop.id)

    day_start = to_utc_from_local(local_date, time(0, 0), tz_offset_minutes)
    day_end = to_utc_from_local(local_date + timedelta(days=1), time(0, 0), tz_offset_minutes)

    booking_result = await session.execute(
        select(Booking, Service, Stylist)
        .join(Service, Service.id == Booking.service_id)
        .join(Stylist, Stylist.id == Booking.stylist_id)
        .where(
            Booking.start_at_utc < day_end,
            Booking.end_at_utc > day_start,
            Booking.status.in_([BookingStatus.HOLD, BookingStatus.CONFIRMED]),
        )
        .order_by(Booking.start_at_utc)
    )
    bookings = []
    for booking, service, stylist in booking_result.all():
        bookings.append(
            OwnerScheduleBooking(
                id=booking.id,
                stylist_id=stylist.id,
                stylist_name=stylist.name,
                service_name=service.name,
                customer_name=booking.customer_name,
                status=booking.status,
                start_time=to_local_time_str(booking.start_at_utc, tz_offset_minutes),
                end_time=to_local_time_str(booking.end_at_utc, tz_offset_minutes),
            )
        )

    time_off_result = await session.execute(
        select(TimeOffBlock, Stylist)
        .join(Stylist, Stylist.id == TimeOffBlock.stylist_id)
        .where(
            TimeOffBlock.start_at_utc < day_end,
            TimeOffBlock.end_at_utc > day_start,
        )
        .order_by(TimeOffBlock.start_at_utc)
    )
    time_off = []
    for block, stylist in time_off_result.all():
        time_off.append(
            OwnerScheduleTimeOff(
                id=block.id,
                stylist_id=stylist.id,
                stylist_name=stylist.name,
                start_time=to_local_time_str(block.start_at_utc, tz_offset_minutes),
                end_time=to_local_time_str(block.end_at_utc, tz_offset_minutes),
                reason=block.reason,
            )
        )

    return OwnerScheduleResponse(
        date=local_date.strftime("%Y-%m-%d"),
        stylists=stylists,
        bookings=bookings,
        time_off=time_off,
    )


@app.get("/owner/stylists/{stylist_id}/time_off", response_model=list[OwnerTimeOffEntry])
async def owner_time_off_for_stylist(
    stylist_id: int,
    tz_offset_minutes: int = 0,
    session: AsyncSession = Depends(get_session),
):
    stylist = await fetch_stylist(session, stylist_id)
    result = await session.execute(
        select(TimeOffBlock)
        .where(TimeOffBlock.stylist_id == stylist.id)
        .order_by(TimeOffBlock.start_at_utc)
    )
    entries = []
    for block in result.scalars().all():
        local_start = to_local_time_str(block.start_at_utc, tz_offset_minutes)
        local_end = to_local_time_str(block.end_at_utc, tz_offset_minutes)
        local_date = to_local_date_str(block.start_at_utc, tz_offset_minutes)
        entries.append(
            OwnerTimeOffEntry(
                start_time=local_start,
                end_time=local_end,
                date=local_date,
                reason=block.reason,
            )
        )
    return entries


@app.post("/owner/bookings/reschedule")
async def owner_reschedule_booking(
    payload: OwnerRescheduleRequest, session: AsyncSession = Depends(get_session)
):
    result = await session.execute(select(Booking).where(Booking.id == payload.booking_id))
    booking = result.scalar_one_or_none()
    if not booking:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")

    service = await fetch_service(session, booking.service_id)
    stylist = await fetch_stylist(session, payload.stylist_id)

    try:
        local_date = datetime.strptime(payload.date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid date format")

    try:
        hour, minute = map(int, payload.start_time.split(":"))
        local_time = time(hour=hour, minute=minute)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid start_time")

    if not is_working_day(local_date):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Outside working days")

    working_start, working_end = get_stylist_hours(stylist)
    duration = timedelta(minutes=service.duration_minutes)
    local_end_time = (datetime.combine(local_date, local_time) + duration).time()
    if not (working_start <= local_time < working_end) or local_end_time > working_end:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Outside working hours")

    start_at_utc = to_utc_from_local(local_date, local_time, payload.tz_offset_minutes)
    end_at_utc = start_at_utc + duration
    now = datetime.now(timezone.utc)

    blocked = await get_active_bookings_for_stylist(
        session,
        stylist.id,
        start_at_utc,
        end_at_utc,
        now,
        exclude_booking_id=booking.id,
    )
    if any(overlap(start_at_utc, end_at_utc, b.start_at_utc, b.end_at_utc) for b in blocked):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Slot not available")

    booking.stylist_id = stylist.id
    booking.start_at_utc = start_at_utc
    booking.end_at_utc = end_at_utc
    await session.commit()
    return {"ok": True}


@app.post("/owner/bookings/cancel")
async def owner_cancel_booking(
    payload: OwnerCancelRequest, session: AsyncSession = Depends(get_session)
):
    result = await session.execute(select(Booking).where(Booking.id == payload.booking_id))
    booking = result.scalar_one_or_none()
    if not booking:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")
    await session.delete(booking)
    await session.commit()
    return {"ok": True}


@app.get("/availability")
async def get_availability(
    service_id: int,
    date: str,
    tz_offset_minutes: int,
    session: AsyncSession = Depends(get_session),
):
    try:
        local_date = datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid date format")

    if not is_working_day(local_date):
        return []

    service = await fetch_service(session, service_id)
    # Get stylists in same shop
    result = await session.execute(
        select(Stylist).where(Stylist.shop_id == service.shop_id, Stylist.active.is_(True)).order_by(Stylist.id)
    )
    stylists = result.scalars().all()
    if not stylists:
        return []

    now = datetime.now(timezone.utc)
    slots: list[AvailabilitySlot] = []

    for stylist in stylists:
        working_start, working_end = get_stylist_hours(stylist)
        day_start_utc = to_utc_from_local(local_date, working_start, tz_offset_minutes)
        day_end_utc = to_utc_from_local(local_date, working_end, tz_offset_minutes)
        blocked = await get_active_bookings_for_stylist(
            session,
            stylist.id,
            day_start_utc,
            day_end_utc,
            now,
        )
        slots.extend(
            make_slots_for_stylist(
                stylist,
                service.duration_minutes,
                local_date,
                tz_offset_minutes,
                working_start,
                working_end,
                blocked,
                now,
            )
        )

    # Sort chronologically
    slots.sort(key=lambda s: s.start_time)
    return [slot.model_dump() for slot in slots]


@app.post("/bookings/hold", response_model=HoldResponse)
async def create_hold(payload: HoldRequest, session: AsyncSession = Depends(get_session)):
    service = await fetch_service(session, payload.service_id)
    stylist = await fetch_stylist(session, payload.stylist_id)

    if stylist.shop_id != service.shop_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Stylist does not belong to this shop")

    if not payload.customer_email or not payload.customer_email.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Customer email is required to hold a slot")

    try:
        local_date = datetime.strptime(payload.date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid date format")

    try:
        hour, minute = map(int, payload.start_time.split(":"))
        local_time = time(hour=hour, minute=minute)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid start_time")

    if not is_working_day(local_date):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Outside working days")

    working_start, working_end = get_stylist_hours(stylist)
    duration = timedelta(minutes=service.duration_minutes)
    local_end_time = (datetime.combine(local_date, local_time) + duration).time()

    if not (working_start <= local_time < working_end) or local_end_time > working_end:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Outside working hours")

    start_at_utc = to_utc_from_local(local_date, local_time, payload.tz_offset_minutes)
    end_at_utc = start_at_utc + duration

    now = datetime.now(timezone.utc)

    # Check conflicts
    result = await session.execute(
        select(Booking).where(
            Booking.stylist_id == stylist.id,
            Booking.end_at_utc > start_at_utc,
            Booking.start_at_utc < end_at_utc,
            Booking.status.in_([BookingStatus.HOLD, BookingStatus.CONFIRMED]),
        )
    )
    conflicts = result.scalars().all()
    for existing in conflicts:
        if existing.status == BookingStatus.HOLD:
            if existing.hold_expires_at_utc and existing.hold_expires_at_utc > now:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Slot is held by another user",
                )
        elif overlap(start_at_utc, end_at_utc, existing.start_at_utc, existing.end_at_utc):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Slot already booked",
            )

    hold_expires_at = now + timedelta(minutes=settings.hold_ttl_minutes)
    customer_email = payload.customer_email.strip().lower()
    booking = Booking(
        shop_id=service.shop_id,
        service_id=service.id,
        stylist_id=stylist.id,
        customer_name=payload.customer_name,
        customer_email=customer_email,
        start_at_utc=start_at_utc,
        end_at_utc=end_at_utc,
        status=BookingStatus.HOLD,
        hold_expires_at_utc=hold_expires_at,
    )
    session.add(booking)
    await session.commit()
    await session.refresh(booking)

    return HoldResponse(
        booking_id=booking.id,
        status=booking.status,
        hold_expires_at=booking.hold_expires_at_utc,
    )


@app.post("/bookings/confirm", response_model=ConfirmResponse)
async def confirm_booking(payload: ConfirmRequest, session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Booking).where(Booking.id == payload.booking_id))
    booking = result.scalar_one_or_none()
    if not booking:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")

    if booking.status == BookingStatus.CONFIRMED:
        return ConfirmResponse(ok=True, booking_id=booking.id, status=booking.status)

    if booking.status != BookingStatus.HOLD:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Booking not on hold")

    now = datetime.now(timezone.utc)
    if not booking.hold_expires_at_utc or booking.hold_expires_at_utc <= now:
        booking.status = BookingStatus.EXPIRED
        await session.commit()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Hold expired")

    # Ensure no new conflicts appeared before confirming
    result = await session.execute(
        select(Booking).where(
            Booking.id != booking.id,
            Booking.stylist_id == booking.stylist_id,
            Booking.end_at_utc > booking.start_at_utc,
            Booking.start_at_utc < booking.end_at_utc,
            Booking.status.in_([BookingStatus.HOLD, BookingStatus.CONFIRMED]),
        )
    )
    conflicts = result.scalars().all()
    for existing in conflicts:
        if existing.status == BookingStatus.CONFIRMED:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Slot already booked")
        if existing.is_hold_active(now):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Slot held by another user")

    booking.status = BookingStatus.CONFIRMED
    await session.commit()
    await session.refresh(booking)

    if booking.customer_email:
        try:
            result = await session.execute(
                select(Service, Stylist).where(
                    Service.id == booking.service_id,
                    Stylist.id == booking.stylist_id,
                )
            )
            service, stylist = result.one()
            customer_name = booking.customer_name or "Guest"
            summary = f"{service.name} with {stylist.name}"
            description = f"Booking for {customer_name}"
            location = settings.default_shop_name
            ics_text = build_ics_event(
                uid=str(booking.id),
                start_at=booking.start_at_utc,
                end_at=booking.end_at_utc,
                summary=summary,
                description=description,
                location=location,
            )
            invite_url = f"{settings.public_api_base}/bookings/{booking.id}/invite"
            html = f"""
                <p>Hi {customer_name},</p>
                <p>Your booking is confirmed.</p>
                <ul>
                  <li><strong>Service:</strong> {service.name}</li>
                  <li><strong>Stylist:</strong> {stylist.name}</li>
                  <li><strong>Start:</strong> {booking.start_at_utc} UTC</li>
                  <li><strong>End:</strong> {booking.end_at_utc} UTC</li>
                  <li><strong>Location:</strong> {location}</li>
                </ul>
                <p><a href="{invite_url}">Download calendar invite</a></p>
            """
            await send_booking_email_with_ics(
                to_email=booking.customer_email,
                subject=f"Booking confirmed: {service.name}",
                html=html,
                ics_filename=f"convo-booking-{booking.id}.ics",
                ics_text=ics_text,
            )
        except Exception as exc:
            logger.exception("Failed to send booking confirmation email: %s", exc)

    return ConfirmResponse(ok=True, booking_id=booking.id, status=booking.status)


@app.get("/bookings/{booking_id}/invite")
async def booking_invite(
    booking_id: uuid.UUID, session: AsyncSession = Depends(get_session)
):
    """Return a .ics invite file compatible with Google, Apple, and Outlook."""
    result = await session.execute(
        select(Booking, Service, Stylist)
        .join(Service, Service.id == Booking.service_id)
        .join(Stylist, Stylist.id == Booking.stylist_id)
        .where(Booking.id == booking_id)
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")

    booking, service, stylist = row
    if not booking.is_confirmed():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Booking is not confirmed"
        )

    customer_name = booking.customer_name or "Guest"
    summary = f"{service.name} with {stylist.name}"
    description = f"Booking for {customer_name}"
    location = settings.default_shop_name

    ics = build_ics_event(
        uid=str(booking.id),
        start_at=booking.start_at_utc,
        end_at=booking.end_at_utc,
        summary=summary,
        description=description,
        location=location,
    )
    filename = f"convo-booking-{booking.id}.ics"
    return Response(
        content=ics,
        media_type="text/calendar",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


class BookingTrackResponse(BaseModel):
    booking_id: uuid.UUID
    service_name: str
    stylist_name: str
    customer_name: str | None
    customer_email: str | None
    start_time: datetime
    end_time: datetime
    status: str
    created_at: datetime


@app.get("/bookings/track")
async def track_bookings(email: str, session: AsyncSession = Depends(get_session)):
    """Track bookings by customer email."""
    if not email or not email.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email is required")

    normalized_email = email.strip().lower()

    # Get all bookings for this email
    result = await session.execute(
        select(Booking)
        .where(Booking.customer_email == normalized_email)
        .order_by(Booking.start_at_utc.desc())
    )
    bookings = result.scalars().all()
    
    # Fetch service and stylist names for each booking
    response = []
    for booking in bookings:
        # Get service name
        svc_result = await session.execute(select(Service).where(Service.id == booking.service_id))
        service = svc_result.scalar_one_or_none()
        
        # Get stylist name
        stylist_result = await session.execute(select(Stylist).where(Stylist.id == booking.stylist_id))
        stylist = stylist_result.scalar_one_or_none()
        
        response.append(BookingTrackResponse(
            booking_id=booking.id,
            service_name=service.name if service else "Unknown Service",
            stylist_name=stylist.name if stylist else "Unknown Stylist",
            customer_name=booking.customer_name,
            customer_email=booking.customer_email,
            start_time=booking.start_at_utc,
            end_time=booking.end_at_utc,
            status=booking.status.value,
            created_at=booking.created_at,
        ))
    
    return response
