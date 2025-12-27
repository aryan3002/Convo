import uuid
from datetime import date, datetime, time, timedelta, timezone
from typing import List

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .core.config import get_settings
from .core.db import AsyncSessionLocal, Base, engine, get_session
from .models import Booking, BookingStatus, Service, Stylist
from .seed import seed_initial_data
from .chat import ChatRequest, ChatResponse, chat_with_ai


settings = get_settings()
app = FastAPI(title="Convo Booking Backend")

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


@app.get("/health")
async def healthcheck():
    return {"ok": True}


@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest, session: AsyncSession = Depends(get_session)):
    """AI-powered chat endpoint for booking appointments."""
    return await chat_with_ai(request.messages, session, request.context)


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
    booking = Booking(
        shop_id=service.shop_id,
        service_id=service.id,
        stylist_id=stylist.id,
        customer_name=payload.customer_name,
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
