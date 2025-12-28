import re
import uuid
from datetime import date, datetime, time, timedelta, timezone
from typing import List
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .core.config import get_settings
from .core.db import AsyncSessionLocal, Base, engine, get_session
from .chat import ChatRequest, ChatResponse, chat_with_ai
from .owner_chat import OwnerChatRequest, OwnerChatResponse, SUPPORTED_RULES, owner_chat_with_ai
from .models import Booking, BookingStatus, Service, ServiceRule, Shop, Stylist
from .seed import seed_initial_data


settings = get_settings()
app = FastAPI(title="Convo Booking Backend")


def get_local_now() -> datetime:
    """Get the current datetime in the configured timezone (Arizona)."""
    tz = ZoneInfo(settings.chat_timezone)
    return datetime.now(tz)

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


def overlap(start_a: datetime, end_a: datetime, start_b: datetime, end_b: datetime) -> bool:
    return start_a < end_b and start_b < end_a


def to_utc_from_local(local_date: date, local_time: time, tz_offset_minutes: int) -> datetime:
    tz = timezone(timedelta(minutes=tz_offset_minutes))
    local_dt = datetime.combine(local_date, local_time, tzinfo=tz)
    return local_dt.astimezone(timezone.utc)


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
) -> List[Booking]:
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
        if booking.status == BookingStatus.HOLD:
            if booking.hold_expires_at_utc and booking.hold_expires_at_utc > now:
                active.append(booking)
        else:
            active.append(booking)
    return active


def make_slots_for_stylist(
    stylist: Stylist,
    service_duration: int,
    local_date: date,
    tz_offset_minutes: int,
    working_start: time,
    working_end: time,
    blocked: List[Booking],
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
            digits = re.sub(r"[^\d]", "", raw)
            return int(digits) if digits else 0
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

    try:
        if action_type == "list_services":
            data = {"services": await list_services_with_rules(session, shop.id)}
            reply_override = "Here are your current services."

        elif action_type == "create_service":
            name = str(params.get("name") or "").strip()
            duration = parse_duration_minutes(params.get("duration_minutes"))
            price_cents = parse_price_cents(params.get("price_cents"))
            rule = str(params.get("availability_rule") or "none").strip().lower()

            if not name:
                return OwnerChatResponse(reply="What's the service name?", action=None)
            if duration < 5 or duration > 240:
                return OwnerChatResponse(reply="Duration should be between 5 and 240 minutes.", action=None)
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

        elif action_type == "update_service_price":
            service = await resolve_service()
            if not service:
                return OwnerChatResponse(reply="Which service should I update?", action=None)
            price_cents = parse_price_cents(params.get("price_cents"))
            if price_cents <= 0 or price_cents > 500000:
                return OwnerChatResponse(reply="Price should be between $1 and $5,000.", action=None)
            service.price_cents = price_cents
            await session.commit()
            data = {"services": await list_services_with_rules(session, shop.id)}
            reply_override = f"Updated {service.name} to ${price_cents/100:.2f}."

        elif action_type == "update_service_duration":
            service = await resolve_service()
            if not service:
                return OwnerChatResponse(reply="Which service should I update?", action=None)
            duration = parse_duration_minutes(params.get("duration_minutes"))
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

            result = await session.execute(select(Booking).where(Booking.service_id == service.id))
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
    return ConfirmResponse(ok=True, booking_id=booking.id, status=booking.status)


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
