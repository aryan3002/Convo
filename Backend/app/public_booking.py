"""
Public Booking API for ChatGPT Custom GPT Integration.

This module provides tool-safe, public-facing endpoints for customers to book services
via ChatGPT Actions (Custom GPT). The quote → confirm flow is enforced to prevent
hallucinated bookings and ensure data integrity.

All endpoints are designed to be:
- Idempotent where possible
- Timezone-aware (UTC storage, local display)
- Multi-tenant ready (currently single shop)
- OwnerGPT compatible (uses same DB tables)
"""

import uuid
import secrets
import hashlib
from datetime import date, datetime, time, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Header, status, Request
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from .core.config import get_settings
from .core.db import get_session
from .models import (
    Booking,
    BookingStatus,
    Service,
    Shop,
    Stylist,
    TimeOffBlock,
)
from .customer_memory import (
    get_or_create_customer_by_identity,
    normalize_email,
    normalize_phone,
)

settings = get_settings()
router = APIRouter(prefix="/public", tags=["public-booking"])

# ────────────────────────────────────────────────────────────────
# In-Memory Quote Store (Production: Use Redis with TTL)
# ────────────────────────────────────────────────────────────────

# Quote storage: {quote_token: QuoteData}
# In production, use Redis with auto-expiry
_quote_store: dict[str, "QuoteData"] = {}

# Idempotency store: {quote_token: booking_id} - tracks confirmed bookings
# In production, use Redis with 1-hour TTL
_confirmed_quotes: dict[str, str] = {}

# Rate limiting store for /bookings/lookup: {ip: [(timestamp, timestamp, ...)]}
# In production, use Redis with sliding window
_lookup_rate_limit: dict[str, list[datetime]] = defaultdict(list)

QUOTE_TTL_MINUTES = 10
IDEMPOTENCY_TTL_MINUTES = 60  # How long to remember confirmed bookings
LOOKUP_RATE_LIMIT = 20  # Max requests per IP
LOOKUP_RATE_WINDOW_MINUTES = 10  # Time window for rate limiting


class QuoteData:
    """
    Internal quote data structure.
    
    Redis migration note: Serialize with json.dumps() using to_dict() method.
    """
    def __init__(
        self,
        shop_id: int,
        service_id: int,
        stylist_id: int,
        start_at_utc: datetime,
        end_at_utc: datetime,
        customer_name: str,
        customer_email: Optional[str],
        customer_phone: Optional[str],
        service_name: str,
        stylist_name: str,
        price_cents: int,
        duration_minutes: int,
        created_at: datetime,
        slot_id: Optional[str] = None,  # Deterministic slot identifier
    ):
        self.shop_id = shop_id
        self.service_id = service_id
        self.stylist_id = stylist_id
        self.start_at_utc = start_at_utc
        self.end_at_utc = end_at_utc
        self.customer_name = customer_name
        self.customer_email = customer_email
        self.customer_phone = customer_phone
        self.service_name = service_name
        self.stylist_name = stylist_name
        self.price_cents = price_cents
        self.duration_minutes = duration_minutes
        self.created_at = created_at
        self.slot_id = slot_id

    def is_expired(self, now: datetime) -> bool:
        return now > self.created_at + timedelta(minutes=QUOTE_TTL_MINUTES)
    
    def to_dict(self) -> dict:
        """For Redis serialization."""
        return {
            "shop_id": self.shop_id,
            "service_id": self.service_id,
            "stylist_id": self.stylist_id,
            "start_at_utc": self.start_at_utc.isoformat(),
            "end_at_utc": self.end_at_utc.isoformat(),
            "customer_name": self.customer_name,
            "customer_email": self.customer_email,
            "customer_phone": self.customer_phone,
            "service_name": self.service_name,
            "stylist_name": self.stylist_name,
            "price_cents": self.price_cents,
            "duration_minutes": self.duration_minutes,
            "created_at": self.created_at.isoformat(),
            "slot_id": self.slot_id,
        }


def generate_quote_token() -> str:
    """Generate a unique quote token."""
    return secrets.token_urlsafe(24)


def generate_slot_id(stylist_id: int, start_time_utc: datetime) -> str:
    """
    Generate a deterministic slot ID from stylist_id + start_time.
    This allows ChatGPT to reference slots directly.
    Format: slot_{stylist_id}_{YYYYMMDDTHHMMM}
    """
    time_str = start_time_utc.strftime("%Y%m%dT%H%M")
    return f"slot_{stylist_id}_{time_str}"


def parse_slot_id(slot_id: str) -> tuple[int, datetime]:
    """
    Parse slot_id back into stylist_id and start_time_utc.
    Format: slot_{stylist_id}_{YYYYMMDDTHHMMM}
    
    Returns (stylist_id, start_time_utc)
    Raises ValueError if format is invalid.
    """
    if not slot_id.startswith("slot_"):
        raise ValueError("Invalid slot_id format")
    
    parts = slot_id[5:].rsplit("_", 1)  # Remove "slot_" prefix, split on last underscore
    if len(parts) != 2:
        raise ValueError("Invalid slot_id format")
    
    try:
        stylist_id = int(parts[0])
        time_str = parts[1]  # YYYYMMDDTHHMM format
        start_time_utc = datetime.strptime(time_str, "%Y%m%dT%H%M").replace(tzinfo=timezone.utc)
        return stylist_id, start_time_utc
    except (ValueError, IndexError) as e:
        raise ValueError(f"Invalid slot_id format: {e}")


def cleanup_expired_quotes():
    """Remove expired quotes from memory."""
    now = datetime.now(timezone.utc)
    expired = [token for token, quote in _quote_store.items() if quote.is_expired(now)]
    for token in expired:
        del _quote_store[token]


# ────────────────────────────────────────────────────────────────
# API Key Authentication (Simple for ChatGPT Actions)
# ────────────────────────────────────────────────────────────────

# API key for public booking (set in environment or use default for dev)
PUBLIC_BOOKING_API_KEY = getattr(settings, 'public_booking_api_key', None) or "convo-public-booking-key-2024"


async def verify_api_key(x_api_key: str = Header(..., alias="X-API-Key")):
    """Verify API key for public endpoints."""
    if x_api_key != PUBLIC_BOOKING_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
    return True


# ────────────────────────────────────────────────────────────────
# Pydantic Models for Public API
# ────────────────────────────────────────────────────────────────

class BusinessInfoResponse(BaseModel):
    """Business information for ChatGPT context."""
    business_name: str
    timezone: str
    working_hours_start: str
    working_hours_end: str
    working_days: list[str]  # ["Monday", "Tuesday", ...]
    address: Optional[str] = None
    phone: Optional[str] = None


class ServiceResponse(BaseModel):
    """Service information."""
    id: int
    name: str
    duration_minutes: int
    price_cents: int
    price_display: str  # "$35.00"


class StylistResponse(BaseModel):
    """Stylist information."""
    id: int
    name: str
    available: bool = True


class AvailabilitySlotResponse(BaseModel):
    """Available time slot with deterministic slot_id."""
    slot_id: str  # Deterministic identifier: slot_{stylist_id}_{YYYYMMDDTHHMMM}
    stylist_id: int
    stylist_name: str
    start_time: str  # ISO format (UTC)
    end_time: str  # ISO format (UTC)
    start_time_local: str  # "2:00 PM"
    date_local: str  # "January 22, 2026"


class AvailabilityRequest(BaseModel):
    """Request for availability check."""
    service_id: int
    date: str = Field(..., description="Date in YYYY-MM-DD format")
    stylist_id: Optional[int] = Field(None, description="Optional: specific stylist")

    @field_validator('date')
    @classmethod
    def validate_date(cls, v: str) -> str:
        try:
            parsed = datetime.strptime(v, "%Y-%m-%d").date()
            if parsed < date.today():
                raise ValueError("Date cannot be in the past")
        except ValueError as e:
            if "Date cannot be in the past" in str(e):
                raise
            raise ValueError("Date must be in YYYY-MM-DD format")
        return v


class AvailabilityResponse(BaseModel):
    """Response with available slots."""
    date: str
    service_name: str
    slots: list[AvailabilitySlotResponse]
    message: str


class QuoteRequest(BaseModel):
    """
    Request to create a booking quote (does NOT create booking).
    
    Either customer_email OR customer_phone must be provided.
    Optionally use slot_id instead of (date + start_time + stylist_id).
    """
    service_id: int
    stylist_id: Optional[int] = Field(None, description="Stylist ID (required if slot_id not provided)")
    date: Optional[str] = Field(None, description="Date in YYYY-MM-DD format (required if slot_id not provided)")
    start_time: Optional[str] = Field(None, description="Time in HH:MM format 24-hour (required if slot_id not provided)")
    slot_id: Optional[str] = Field(None, description="Slot ID from availability response (alternative to date+time+stylist)")
    customer_name: str = Field(..., min_length=1, max_length=100)
    customer_email: Optional[str] = Field(None, max_length=255)
    customer_phone: Optional[str] = Field(None, max_length=32)

    @field_validator('date')
    @classmethod
    def validate_date(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError:
            raise ValueError("Date must be in YYYY-MM-DD format")
        return v

    @field_validator('start_time')
    @classmethod
    def validate_time(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        try:
            parts = v.split(':')
            if len(parts) != 2:
                raise ValueError()
            hour, minute = int(parts[0]), int(parts[1])
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise ValueError()
        except (ValueError, IndexError):
            raise ValueError("Time must be in HH:MM format (24-hour)")
        return v

    @field_validator('customer_name')
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Customer name is required")
        return v

    @model_validator(mode='after')
    def validate_contact_and_slot(self):
        """Validate that email OR phone is provided, and slot info is complete."""
        # Validate contact info
        if not self.customer_email and not self.customer_phone:
            raise ValueError("Customer email or phone is required.")
        
        # Validate slot specification
        if self.slot_id:
            # slot_id provided - date/time/stylist can be derived
            pass
        else:
            # Must have date, start_time, and stylist_id
            if not self.date or not self.start_time or not self.stylist_id:
                raise ValueError("Either slot_id OR (date + start_time + stylist_id) is required.")
        
        return self


class QuoteResponse(BaseModel):
    """Response with booking quote (must be confirmed to create booking)."""
    quote_token: str = Field(..., description="Token to confirm this quote")
    expires_at: str  # ISO format
    service_name: str
    stylist_name: str
    date_local: str  # "Wednesday, January 22, 2026"
    start_time_local: str  # "2:00 PM"
    end_time_local: str  # "2:30 PM"
    duration_minutes: int
    price_cents: int
    price_display: str
    customer_name: str
    customer_contact: str  # email or phone (masked)
    message: str


class ConfirmRequest(BaseModel):
    """Request to confirm a booking quote."""
    quote_token: str = Field(..., description="Token from quote response")


class ConfirmResponse(BaseModel):
    """Response after confirming booking."""
    booking_id: str  # UUID
    status: str
    service_name: str
    stylist_name: str
    date_local: str
    start_time_local: str
    end_time_local: str
    customer_name: str
    message: str


class BookingDetailsResponse(BaseModel):
    """Response with booking details."""
    booking_id: str
    status: str
    service_name: str
    stylist_name: str
    date_local: str
    start_time_local: str
    end_time_local: str
    customer_name: str
    price_display: str
    created_at: str


class ErrorResponse(BaseModel):
    """Standard error response (matches FastAPI HTTPException format)."""
    detail: str


class BookingLookupItem(BaseModel):
    """Minimal booking info for lookup results (no extra PII)."""
    booking_id: str
    status: str
    service_name: str
    stylist_name: str
    date_local: str  # "Wednesday, January 22, 2026"
    start_time_local: str  # "2:00 PM"
    end_time_local: str  # "2:30 PM"
    created_at: str  # ISO format


class BookingLookupResponse(BaseModel):
    """Response for booking lookup by contact info."""
    matches: list[BookingLookupItem]
    message: str


# ────────────────────────────────────────────────────────────────
# Helper Functions
# ────────────────────────────────────────────────────────────────

def check_rate_limit(ip: str) -> bool:
    """
    Check if IP is within rate limit for lookup endpoint.
    Returns True if allowed, False if rate limit exceeded.
    
    Simple in-memory implementation - resets on restart.
    Production should use Redis with sliding window.
    """
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=LOOKUP_RATE_WINDOW_MINUTES)
    
    # Clean old entries
    _lookup_rate_limit[ip] = [ts for ts in _lookup_rate_limit[ip] if ts > cutoff]
    
    # Check limit
    if len(_lookup_rate_limit[ip]) >= LOOKUP_RATE_LIMIT:
        return False
    
    # Record this request
    _lookup_rate_limit[ip].append(now)
    return True

def get_local_tz() -> ZoneInfo:
    """Get the configured timezone."""
    return ZoneInfo(settings.chat_timezone)


def format_time_local(dt: datetime) -> str:
    """Format datetime to local time string like '2:00 PM'."""
    tz = get_local_tz()
    local = dt.astimezone(tz)
    return local.strftime("%-I:%M %p")


def format_date_local(dt: datetime) -> str:
    """Format datetime to local date string like 'Wednesday, January 22, 2026'."""
    tz = get_local_tz()
    local = dt.astimezone(tz)
    return local.strftime("%A, %B %-d, %Y")


def format_date_short(dt: datetime) -> str:
    """Format datetime to short date like 'January 22, 2026'."""
    tz = get_local_tz()
    local = dt.astimezone(tz)
    return local.strftime("%B %-d, %Y")


def format_price(cents: int) -> str:
    """Format price in cents to display string."""
    return f"${cents / 100:.2f}"


def mask_contact(email: Optional[str], phone: Optional[str]) -> str:
    """Mask contact info for display."""
    if email:
        parts = email.split('@')
        if len(parts) == 2:
            local = parts[0]
            domain = parts[1]
            if len(local) > 2:
                return f"{local[:2]}***@{domain}"
            return f"{local}***@{domain}"
        return email[:3] + "***"
    if phone:
        if len(phone) >= 4:
            return f"***-***-{phone[-4:]}"
        return "***"
    return "No contact"


def to_utc_from_local(local_date: date, local_time: time) -> datetime:
    """Convert local date/time to UTC."""
    tz = get_local_tz()
    local_dt = datetime.combine(local_date, local_time).replace(tzinfo=tz)
    return local_dt.astimezone(timezone.utc)


def is_working_day(local_date: date) -> bool:
    """Check if the given date is a working day."""
    return local_date.weekday() in settings.working_days_list


def parse_working_hours() -> tuple[time, time]:
    """Parse working hours from settings."""
    start_hour, start_minute = map(int, settings.working_hours_start.split(":"))
    end_hour, end_minute = map(int, settings.working_hours_end.split(":"))
    return time(start_hour, start_minute), time(end_hour, end_minute)


def get_stylist_hours(stylist: Stylist) -> tuple[time, time]:
    """Get working hours for a stylist."""
    if stylist.work_start and stylist.work_end:
        return stylist.work_start, stylist.work_end
    return parse_working_hours()


def overlap(start_a: datetime, end_a: datetime, start_b: datetime, end_b: datetime) -> bool:
    """Check if two time ranges overlap."""
    return start_a < end_b and start_b < end_a


async def get_default_shop(session: AsyncSession) -> Shop:
    """Get or create the default shop."""
    result = await session.execute(select(Shop).where(Shop.name == settings.default_shop_name))
    shop = result.scalar_one_or_none()
    if not shop:
        shop = Shop(name=settings.default_shop_name)
        session.add(shop)
        await session.flush()
    return shop


# ────────────────────────────────────────────────────────────────
# Public API Endpoints
# ────────────────────────────────────────────────────────────────

@router.get("/business", response_model=BusinessInfoResponse,
            responses={401: {"model": ErrorResponse}})
async def get_business_info(
    _: bool = Depends(verify_api_key),
    session: AsyncSession = Depends(get_session),
):
    """
    Get business information for ChatGPT context.
    
    Returns business name, hours, timezone, and working days.
    """
    shop = await get_default_shop(session)
    
    day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    working_days = [day_names[i] for i in sorted(settings.working_days_list)]
    
    return BusinessInfoResponse(
        business_name=shop.name,
        timezone=settings.chat_timezone,
        working_hours_start=settings.working_hours_start,
        working_hours_end=settings.working_hours_end,
        working_days=working_days,
        address="Tempe, Arizona",  # Could be stored in Shop model
        phone=None,
    )


@router.get("/services", response_model=list[ServiceResponse],
            responses={401: {"model": ErrorResponse}})
async def list_public_services(
    _: bool = Depends(verify_api_key),
    session: AsyncSession = Depends(get_session),
):
    """
    List all available services.
    
    Returns service ID, name, duration, and price.
    ChatGPT should use service_id when creating quotes.
    """
    shop = await get_default_shop(session)
    result = await session.execute(
        select(Service).where(Service.shop_id == shop.id).order_by(Service.id)
    )
    services = result.scalars().all()
    
    return [
        ServiceResponse(
            id=svc.id,
            name=svc.name,
            duration_minutes=svc.duration_minutes,
            price_cents=svc.price_cents,
            price_display=format_price(svc.price_cents),
        )
        for svc in services
    ]


@router.get("/stylists", response_model=list[StylistResponse],
            responses={401: {"model": ErrorResponse}})
async def list_public_stylists(
    _: bool = Depends(verify_api_key),
    session: AsyncSession = Depends(get_session),
):
    """
    List all available stylists.
    
    Returns stylist ID and name. Use stylist_id when creating quotes.
    """
    shop = await get_default_shop(session)
    result = await session.execute(
        select(Stylist).where(
            Stylist.shop_id == shop.id,
            Stylist.active.is_(True)
        ).order_by(Stylist.id)
    )
    stylists = result.scalars().all()
    
    return [
        StylistResponse(id=s.id, name=s.name, available=True)
        for s in stylists
    ]


@router.get("/availability", response_model=AvailabilityResponse,
            responses={
                400: {"model": ErrorResponse},
                401: {"model": ErrorResponse},
                404: {"model": ErrorResponse},
            })
async def check_availability(
    service_id: int,
    date: str,
    stylist_id: Optional[int] = None,
    _: bool = Depends(verify_api_key),
    session: AsyncSession = Depends(get_session),
):
    """
    Check available time slots for a service on a specific date.
    
    - service_id: Required service ID
    - date: Date in YYYY-MM-DD format
    - stylist_id: Optional - filter to specific stylist
    
    Returns list of available slots with stylist and time info.
    """
    # Validate date format
    try:
        local_date = datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid date format. Use YYYY-MM-DD.",
        )
    
    # Check if date is in the past
    tz = get_local_tz()
    now_local = datetime.now(tz)
    if local_date < now_local.date():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot check availability for past dates.",
        )
    
    # Check if working day
    if not is_working_day(local_date):
        day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        working_days = [day_names[i] for i in sorted(settings.working_days_list)]
        return AvailabilityResponse(
            date=date,
            service_name="",
            slots=[],
            message=f"We are closed on {day_names[local_date.weekday()]}. We're open {', '.join(working_days)}.",
        )
    
    shop = await get_default_shop(session)
    
    # Fetch service
    result = await session.execute(
        select(Service).where(Service.id == service_id, Service.shop_id == shop.id)
    )
    service = result.scalar_one_or_none()
    if not service:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service not found. Please check the service ID.",
        )
    
    # Fetch stylists
    query = select(Stylist).where(
        Stylist.shop_id == shop.id,
        Stylist.active.is_(True)
    )
    if stylist_id:
        query = query.where(Stylist.id == stylist_id)
    query = query.order_by(Stylist.id)
    
    result = await session.execute(query)
    stylists = result.scalars().all()
    
    if not stylists:
        if stylist_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Stylist not found or unavailable.",
            )
        return AvailabilityResponse(
            date=date,
            service_name=service.name,
            slots=[],
            message="No stylists available at this time.",
        )
    
    now_utc = datetime.now(timezone.utc)
    slots: list[AvailabilitySlotResponse] = []
    
    for stylist in stylists:
        working_start, working_end = get_stylist_hours(stylist)
        day_start_utc = to_utc_from_local(local_date, working_start)
        day_end_utc = to_utc_from_local(local_date, working_end)
        
        # Get existing bookings
        booking_result = await session.execute(
            select(Booking).where(
                Booking.stylist_id == stylist.id,
                Booking.end_at_utc > day_start_utc,
                Booking.start_at_utc < day_end_utc,
                Booking.status.in_([BookingStatus.HOLD, BookingStatus.CONFIRMED]),
            )
        )
        bookings = booking_result.scalars().all()
        
        # Get time off blocks
        time_off_result = await session.execute(
            select(TimeOffBlock).where(
                TimeOffBlock.stylist_id == stylist.id,
                TimeOffBlock.end_at_utc > day_start_utc,
                TimeOffBlock.start_at_utc < day_end_utc,
            )
        )
        time_off_blocks = time_off_result.scalars().all()
        
        # Build blocked times
        blocked_times: list[tuple[datetime, datetime]] = []
        for booking in bookings:
            if booking.status == BookingStatus.HOLD:
                if booking.hold_expires_at_utc and booking.hold_expires_at_utc > now_utc:
                    blocked_times.append((booking.start_at_utc, booking.end_at_utc))
            else:
                blocked_times.append((booking.start_at_utc, booking.end_at_utc))
        
        for block in time_off_blocks:
            blocked_times.append((block.start_at_utc, block.end_at_utc))
        
        # Generate slots
        cursor = day_start_utc
        step = timedelta(minutes=30)
        duration = timedelta(minutes=service.duration_minutes)
        
        while cursor + duration <= day_end_utc:
            slot_start = cursor
            slot_end = cursor + duration
            
            # Skip past slots
            if slot_start <= now_utc:
                cursor += step
                continue
            
            # Check for conflicts
            has_conflict = any(
                overlap(slot_start, slot_end, b_start, b_end)
                for b_start, b_end in blocked_times
            )
            
            if not has_conflict:
                slot_id = generate_slot_id(stylist.id, slot_start)
                slots.append(
                    AvailabilitySlotResponse(
                        slot_id=slot_id,
                        stylist_id=stylist.id,
                        stylist_name=stylist.name,
                        start_time=slot_start.isoformat(),
                        end_time=slot_end.isoformat(),
                        start_time_local=format_time_local(slot_start),
                        date_local=format_date_short(slot_start),
                    )
                )
            
            cursor += step
    
    # Sort by time
    slots.sort(key=lambda s: s.start_time)
    
    if not slots:
        return AvailabilityResponse(
            date=date,
            service_name=service.name,
            slots=[],
            message=f"No available slots for {service.name} on {format_date_short(datetime.combine(local_date, time(12, 0), tzinfo=tz))}. Try another date.",
        )
    
    return AvailabilityResponse(
        date=date,
        service_name=service.name,
        slots=slots,
        message=f"Found {len(slots)} available slot(s) for {service.name}.",
    )


@router.post("/booking/quote", response_model=QuoteResponse,
             responses={
                 400: {"model": ErrorResponse},
                 401: {"model": ErrorResponse},
                 404: {"model": ErrorResponse},
                 409: {"model": ErrorResponse},
             })
async def create_booking_quote(
    request: QuoteRequest,
    _: bool = Depends(verify_api_key),
    session: AsyncSession = Depends(get_session),
):
    """
    Create a booking QUOTE (does NOT create actual booking).
    
    This returns a quote_token that must be used with /booking/confirm
    to actually create the booking. Quotes expire in 10 minutes.
    
    Required: service_id, customer_name
    Required: customer_email OR customer_phone (at least one)
    Required: Either slot_id OR (date + start_time + stylist_id)
    
    IMPORTANT: This endpoint does NOT create a booking. 
    Customer must confirm using the quote_token.
    """
    # Validate contact info (also validated by Pydantic model_validator)
    customer_email = normalize_email(request.customer_email) if request.customer_email else None
    customer_phone = normalize_phone(request.customer_phone) if request.customer_phone else None
    
    if not customer_email and not customer_phone:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Customer email or phone number is required for booking.",
        )
    
    shop = await get_default_shop(session)
    tz = get_local_tz()
    now_utc = datetime.now(timezone.utc)
    now_local = datetime.now(tz)
    
    # Resolve slot information - either from slot_id or from date/time/stylist
    if request.slot_id:
        # Parse slot_id to get stylist_id and start_time
        try:
            stylist_id, start_at_utc = parse_slot_id(request.slot_id)
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid slot_id: {e}",
            )
        
        # Get the local date/time from the parsed UTC time
        local_dt = start_at_utc.astimezone(tz)
        local_date = local_dt.date()
        local_time_obj = local_dt.time()
    else:
        # Use provided date/time/stylist
        stylist_id = request.stylist_id
        
        # Parse date
        try:
            local_date = datetime.strptime(request.date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid date format. Use YYYY-MM-DD.",
            )
        
        # Parse time
        try:
            hour, minute = map(int, request.start_time.split(':'))
            local_time_obj = time(hour=hour, minute=minute)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid time format. Use HH:MM (24-hour).",
            )
        
        # Convert to UTC
        start_at_utc = to_utc_from_local(local_date, local_time_obj)
    
    # Check if in the past
    if start_at_utc <= now_utc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot book appointments in the past.",
        )
    
    # Check working day
    if not is_working_day(local_date):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="We are closed on this day.",
        )
    
    shop = await get_default_shop(session)
    
    # Fetch service
    result = await session.execute(
        select(Service).where(Service.id == request.service_id, Service.shop_id == shop.id)
    )
    service = result.scalar_one_or_none()
    if not service:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service not found. Please check the service ID.",
        )
    
    # Fetch stylist
    result = await session.execute(
        select(Stylist).where(
            Stylist.id == stylist_id,
            Stylist.shop_id == shop.id,
            Stylist.active.is_(True)
        )
    )
    stylist = result.scalar_one_or_none()
    if not stylist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Stylist not found or unavailable.",
        )
    
    # Check working hours
    working_start, working_end = get_stylist_hours(stylist)
    duration = timedelta(minutes=service.duration_minutes)
    end_at_utc = start_at_utc + duration
    local_end_time = (datetime.combine(local_date, local_time_obj) + duration).time()
    
    if not (working_start <= local_time_obj < working_end) or local_end_time > working_end:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Time is outside working hours ({working_start.strftime('%I:%M %p')} - {working_end.strftime('%I:%M %p')}).",
        )
    
    # Check for conflicts (existing bookings)
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
            if existing.hold_expires_at_utc and existing.hold_expires_at_utc > now_utc:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="This time slot is currently being held by another customer. Please try a different time.",
                )
        elif overlap(start_at_utc, end_at_utc, existing.start_at_utc, existing.end_at_utc):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This time slot is already booked. Please choose a different time.",
            )
    
    # Check time off blocks
    time_off_result = await session.execute(
        select(TimeOffBlock).where(
            TimeOffBlock.stylist_id == stylist.id,
            TimeOffBlock.end_at_utc > start_at_utc,
            TimeOffBlock.start_at_utc < end_at_utc,
        )
    )
    if time_off_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{stylist.name} is not available at this time. Please try a different time or stylist.",
        )
    
    # Clean up expired quotes
    cleanup_expired_quotes()
    
    # Create quote (NOT a booking)
    quote_token = generate_quote_token()
    slot_id = generate_slot_id(stylist.id, start_at_utc)
    
    quote_data = QuoteData(
        shop_id=shop.id,
        service_id=service.id,
        stylist_id=stylist.id,
        start_at_utc=start_at_utc,
        end_at_utc=end_at_utc,
        customer_name=request.customer_name.strip(),
        customer_email=customer_email,
        customer_phone=customer_phone,
        service_name=service.name,
        stylist_name=stylist.name,
        price_cents=service.price_cents,
        duration_minutes=service.duration_minutes,
        created_at=now_utc,
        slot_id=slot_id,
    )
    _quote_store[quote_token] = quote_data
    
    expires_at = now_utc + timedelta(minutes=QUOTE_TTL_MINUTES)
    
    return QuoteResponse(
        quote_token=quote_token,
        expires_at=expires_at.isoformat(),
        service_name=service.name,
        stylist_name=stylist.name,
        date_local=format_date_local(start_at_utc),
        start_time_local=format_time_local(start_at_utc),
        end_time_local=format_time_local(end_at_utc),
        duration_minutes=service.duration_minutes,
        price_cents=service.price_cents,
        price_display=format_price(service.price_cents),
        customer_name=request.customer_name.strip(),
        customer_contact=mask_contact(customer_email, customer_phone),
        message=f"Quote created for {service.name} with {stylist.name} on {format_date_local(start_at_utc)} at {format_time_local(start_at_utc)}. Please confirm within {QUOTE_TTL_MINUTES} minutes to complete your booking.",
    )


@router.post("/booking/confirm", response_model=ConfirmResponse,
             responses={
                 400: {"model": ErrorResponse},
                 401: {"model": ErrorResponse},
                 404: {"model": ErrorResponse},
                 409: {"model": ErrorResponse},
             })
async def confirm_booking_quote(
    request: ConfirmRequest,
    _: bool = Depends(verify_api_key),
    session: AsyncSession = Depends(get_session),
):
    """
    Confirm a booking quote and create the actual booking.
    
    Requires the quote_token from /booking/quote response.
    This is IDEMPOTENT - calling multiple times with the same token
    after successful booking will return the same booking details.
    
    Possible errors:
    - 400: Invalid quote_token format
    - 401: Invalid API key
    - 404: Quote not found or expired
    - 409: Slot no longer available (taken between quote and confirm)
    """
    quote_token = request.quote_token
    
    if not quote_token or len(quote_token) < 10:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid quote_token format.",
        )
    
    # Check idempotency - was this quote already confirmed?
    if quote_token in _confirmed_quotes:
        booking_id = _confirmed_quotes[quote_token]
        # Fetch existing booking
        try:
            booking_uuid = uuid.UUID(booking_id)
            result = await session.execute(
                select(Booking, Service, Stylist)
                .join(Service, Booking.service_id == Service.id)
                .join(Stylist, Booking.stylist_id == Stylist.id)
                .where(Booking.id == booking_uuid)
            )
            row = result.one_or_none()
            if row:
                booking, service, stylist = row
                return ConfirmResponse(
                    booking_id=str(booking.id),
                    status="CONFIRMED",
                    service_name=service.name,
                    stylist_name=stylist.name,
                    date_local=format_date_local(booking.start_at_utc),
                    start_time_local=format_time_local(booking.start_at_utc),
                    end_time_local=format_time_local(booking.end_at_utc),
                    customer_name=booking.customer_name or "Guest",
                    message=f"Your booking is already confirmed! {service.name} with {stylist.name} on {format_date_local(booking.start_at_utc)} at {format_time_local(booking.start_at_utc)}. Booking ID: {booking.id}",
                )
        except Exception:
            pass  # Fall through to normal flow if lookup fails
    
    # Clean up expired quotes
    cleanup_expired_quotes()
    
    # Find quote
    quote = _quote_store.get(quote_token)
    if not quote:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quote not found or expired. Please create a new quote.",
        )
    
    now_utc = datetime.now(timezone.utc)
    
    if quote.is_expired(now_utc):
        del _quote_store[quote_token]
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quote has expired. Please create a new quote.",
        )
    
    # Re-check for conflicts (slot may have been taken)
    result = await session.execute(
        select(Booking).where(
            Booking.stylist_id == quote.stylist_id,
            Booking.end_at_utc > quote.start_at_utc,
            Booking.start_at_utc < quote.end_at_utc,
            Booking.status.in_([BookingStatus.HOLD, BookingStatus.CONFIRMED]),
        )
    )
    conflicts = result.scalars().all()
    
    for existing in conflicts:
        if existing.status == BookingStatus.HOLD:
            if existing.hold_expires_at_utc and existing.hold_expires_at_utc > now_utc:
                del _quote_store[quote_token]
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Sorry, this slot was just taken by another customer. Please choose a different time.",
                )
        elif overlap(quote.start_at_utc, quote.end_at_utc, existing.start_at_utc, existing.end_at_utc):
            del _quote_store[quote_token]
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Sorry, this slot was just booked by another customer. Please choose a different time.",
            )
    
    # Create or get customer
    customer = None
    if quote.customer_email or quote.customer_phone:
        customer = await get_or_create_customer_by_identity(
            session,
            quote.customer_email,
            quote.customer_phone,
            quote.customer_name,
        )
    
    # Create booking (directly as CONFIRMED - no hold step for ChatGPT flow)
    booking = Booking(
        shop_id=quote.shop_id,
        service_id=quote.service_id,
        stylist_id=quote.stylist_id,
        customer_name=quote.customer_name,
        customer_email=quote.customer_email,
        customer_phone=quote.customer_phone,
        start_at_utc=quote.start_at_utc,
        end_at_utc=quote.end_at_utc,
        status=BookingStatus.CONFIRMED,
        hold_expires_at_utc=None,
    )
    session.add(booking)
    await session.commit()
    await session.refresh(booking)
    
    # Store idempotency record (tracks that this quote was confirmed)
    _confirmed_quotes[quote_token] = str(booking.id)
    
    # Remove quote (consumed)
    if quote_token in _quote_store:
        del _quote_store[quote_token]
    
    return ConfirmResponse(
        booking_id=str(booking.id),
        status="CONFIRMED",
        service_name=quote.service_name,
        stylist_name=quote.stylist_name,
        date_local=format_date_local(quote.start_at_utc),
        start_time_local=format_time_local(quote.start_at_utc),
        end_time_local=format_time_local(quote.end_at_utc),
        customer_name=quote.customer_name,
        message=f"Your booking is confirmed! {quote.service_name} with {quote.stylist_name} on {format_date_local(quote.start_at_utc)} at {format_time_local(quote.start_at_utc)}. Booking ID: {booking.id}",
    )


@router.get("/booking/{booking_id}", response_model=BookingDetailsResponse,
            responses={
                400: {"model": ErrorResponse},
                401: {"model": ErrorResponse},
                404: {"model": ErrorResponse},
            })
async def get_booking_details(
    booking_id: str,
    _: bool = Depends(verify_api_key),
    session: AsyncSession = Depends(get_session),
):
    """
    Get details of an existing booking by ID.
    
    Returns booking status, service, stylist, and time information.
    """
    try:
        booking_uuid = uuid.UUID(booking_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid booking ID format.",
        )
    
    result = await session.execute(
        select(Booking, Service, Stylist)
        .join(Service, Booking.service_id == Service.id)
        .join(Stylist, Booking.stylist_id == Stylist.id)
        .where(Booking.id == booking_uuid)
    )
    row = result.one_or_none()
    
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Booking not found.",
        )
    
    booking, service, stylist = row
    
    return BookingDetailsResponse(
        booking_id=str(booking.id),
        status=booking.status.value,
        service_name=service.name,
        stylist_name=stylist.name,
        date_local=format_date_local(booking.start_at_utc),
        start_time_local=format_time_local(booking.start_at_utc),
        end_time_local=format_time_local(booking.end_at_utc),
        customer_name=booking.customer_name or "Guest",
        price_display=format_price(service.price_cents),
        created_at=booking.created_at.isoformat(),
    )


@router.get("/bookings/lookup", response_model=BookingLookupResponse,
            responses={
                400: {"model": ErrorResponse},
                401: {"model": ErrorResponse},
                429: {"model": ErrorResponse},
            })
async def lookup_bookings(
    request: Request,
    email: str | None = None,
    phone: str | None = None,
    _: bool = Depends(verify_api_key),
    session: AsyncSession = Depends(get_session),
):
    """
    Look up recent bookings by customer email or phone.
    
    Returns up to 5 most recent bookings matching the provided contact info.
    Requires at least one of: email or phone.
    Rate limited to 20 requests per 10 minutes per IP.
    """
    # Rate limit check (per IP)
    client_ip = request.client.host if request.client else "unknown"
    if not check_rate_limit(client_ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many lookup requests. Please try again later.",
        )
    
    # Validate: must provide email OR phone
    if not email and not phone:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Must provide either email or phone to lookup bookings.",
        )
    
    # Normalize inputs
    norm_email = normalize_email(email) if email else None
    norm_phone = normalize_phone(phone) if phone else None
    
    # Build query: WHERE (email = X OR phone = Y)
    conditions = []
    if norm_email:
        conditions.append(Booking.customer_email == norm_email)
    if norm_phone:
        conditions.append(Booking.customer_phone == norm_phone)
    
    result = await session.execute(
        select(Booking, Service, Stylist)
        .join(Service, Booking.service_id == Service.id)
        .join(Stylist, Booking.stylist_id == Stylist.id)
        .where(or_(*conditions))
        .order_by(Booking.created_at.desc())
        .limit(5)
    )
    rows = result.all()
    
    if not rows:
        return BookingLookupResponse(
            matches=[],
            message="No bookings found for the provided contact information.",
        )
    
    # Build minimal response items
    matches = [
        BookingLookupItem(
            booking_id=str(booking.id),
            status=booking.status.value,
            service_name=service.name,
            stylist_name=stylist.name,
            date_local=format_date_local(booking.start_at_utc),
            start_time_local=format_time_local(booking.start_at_utc),
            end_time_local=format_time_local(booking.end_at_utc),
            created_at=booking.created_at.isoformat(),
        )
        for booking, service, stylist in rows
    ]
    
    count = len(matches)
    message = f"Found {count} booking{'s' if count > 1 else ''} for the provided contact information."
    
    return BookingLookupResponse(
        matches=matches,
        message=message,
    )
