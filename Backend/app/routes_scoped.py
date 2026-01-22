"""
Slug-scoped routes for multi-tenant API.

Phase 4: These routes use URL path slugs for shop resolution.
Phase 7: Added authentication and RBAC for protected routes.

Pattern: /s/{slug}/endpoint

These are the PREFERRED routes for multi-tenant access. The old root routes
(/chat, /owner/chat) are deprecated and will be removed in Phase 5.

Usage:
    POST /s/bishops-tempe/chat       -> Chat with shop "bishops-tempe"
    POST /s/bishops-tempe/owner/chat -> Owner chat for shop "bishops-tempe" (requires auth)
    GET  /s/bishops-tempe/services   -> List services for shop
    GET  /s/bishops-tempe/stylists   -> List stylists for shop
"""

import logging
import re
from datetime import datetime, time, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Path, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .core.config import get_settings
from .core.db import get_session
from .chat import ChatRequest, ChatResponse, chat_with_ai
from .owner_chat import OwnerChatRequest, OwnerChatResponse, owner_chat_with_ai
from .tenancy import (
    ShopContext,
    resolve_shop_from_slug,
    list_services,
    list_active_stylists,
)
from .models import Service, Stylist, ShopMemberRole, Booking, BookingStatus, TimeOffBlock, StylistSpecialty
from .auth import (
    get_current_user_id,
    require_owner_or_manager,
    log_audit,
    AUDIT_OWNER_CHAT,
)

settings = get_settings()
logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────
# Router Definition
# ────────────────────────────────────────────────────────────────

router = APIRouter(prefix="/s/{slug}", tags=["scoped-api"])


# ────────────────────────────────────────────────────────────────
# Dependency: Strict Shop Context from URL Slug
# ────────────────────────────────────────────────────────────────

async def get_shop_context_from_slug(
    slug: str = Path(..., description="Shop URL slug (e.g., 'bishops-tempe')"),
    session: AsyncSession = Depends(get_session),
) -> ShopContext:
    """
    Resolve shop context strictly from URL slug.
    
    Raises 404 if slug is invalid or shop not found.
    This is the Phase 4 replacement for get_default_shop().
    """
    ctx = await resolve_shop_from_slug(session, slug)
    if not ctx:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Shop not found: {slug}. Check the URL and try again."
        )
    logger.debug(f"Resolved shop from slug '{slug}': shop_id={ctx.shop_id}")
    return ctx


# ────────────────────────────────────────────────────────────────
# Response Models (include shop_slug for frontend routing)
# ────────────────────────────────────────────────────────────────

class ScopedChatResponse(ChatResponse):
    """Chat response with shop context for frontend routing."""
    shop_slug: Optional[str] = None
    shop_name: Optional[str] = None


class ScopedOwnerChatResponse(OwnerChatResponse):
    """Owner chat response with shop context."""
    shop_slug: Optional[str] = None
    shop_name: Optional[str] = None


class ServiceListItem(BaseModel):
    """Service info for list endpoint."""
    id: int
    name: str
    duration_minutes: int
    price_cents: int
    price_display: str


class StylistListItem(BaseModel):
    """Stylist info for list endpoint."""
    id: int
    name: str
    active: bool = True


class ServicesResponse(BaseModel):
    """Response for /s/{slug}/services endpoint."""
    shop_slug: str
    shop_name: Optional[str]
    services: list[ServiceListItem]


class StylistsResponse(BaseModel):
    """Response for /s/{slug}/stylists endpoint."""
    shop_slug: str
    shop_name: Optional[str]
    stylists: list[StylistListItem]


# ────────────────────────────────────────────────────────────────
# Endpoints
# ────────────────────────────────────────────────────────────────

@router.post("/chat", response_model=ScopedChatResponse)
async def scoped_chat_endpoint(
    request: ChatRequest,
    ctx: ShopContext = Depends(get_shop_context_from_slug),
    session: AsyncSession = Depends(get_session),
):
    """
    AI-powered chat endpoint for booking appointments.
    
    This is the Phase 4 multi-tenant chat endpoint. Shop is resolved from URL slug.
    
    Example: POST /s/bishops-tempe/chat
    """
    logger.info(f"Scoped chat request for shop_id={ctx.shop_id} ({ctx.shop_slug})")
    
    # Call the existing chat_with_ai with shop context
    ai_response = await chat_with_ai(
        request.messages,
        session,
        request.context,
        shop_id=ctx.shop_id,
    )
    
    # Process actions (same as main.py chat endpoint but scoped)
    action = ai_response.action or {}
    data = ai_response.data
    
    action_type = action.get("type")
    params = action.get("params") or {}
    
    # Handle show_services action with scoped query
    if action_type == "show_services":
        services = await list_services(session, ctx.shop_id)
        data = {
            "services": [
                {
                    "id": svc.id,
                    "name": svc.name,
                    "duration_minutes": svc.duration_minutes,
                    "price_cents": svc.price_cents,
                }
                for svc in services
            ]
        }
    
    return ScopedChatResponse(
        reply=ai_response.reply,
        action=ai_response.action,
        data=data,
        chips=ai_response.chips,
        shop_slug=ctx.shop_slug,
        shop_name=ctx.shop_name,
    )


@router.post("/owner/chat", response_model=ScopedOwnerChatResponse)
async def scoped_owner_chat_endpoint(
    request: OwnerChatRequest,
    ctx: ShopContext = Depends(get_shop_context_from_slug),
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    """
    Owner GPT chat endpoint for managing shop services and schedule.
    
    This is the Phase 4 multi-tenant owner chat endpoint.
    Phase 7: Requires authentication and OWNER or MANAGER role.
    
    Headers Required:
        X-User-Id: User identifier from auth provider
    
    Example: 
        curl -X POST /s/bishops-tempe/owner/chat \\
             -H "X-User-Id: user_abc123" \\
             -H "Content-Type: application/json" \\
             -d '{"messages": [{"role": "user", "content": "Show services"}]}'
    
    Returns:
        401: Missing X-User-Id header
        403: User is not a member or doesn't have OWNER/MANAGER role
        404: Shop not found
        200: Success with AI response
    """
    # Phase 7: Verify user has OWNER or MANAGER role
    await require_owner_or_manager(ctx, user_id, session)
    
    logger.info(f"Scoped owner chat request for shop_id={ctx.shop_id} ({ctx.shop_slug}) by user={user_id}")
    
    # Log audit trail for owner chat invocation
    # Extract intent from first user message for audit (no PII)
    # Note: request.messages are Pydantic models, not dicts
    user_messages = [m for m in request.messages if m.role == "user"]
    intent_preview = None
    if user_messages:
        # Truncate to first 100 chars for audit, avoid any potential PII
        raw_content = user_messages[-1].content[:100] if user_messages[-1].content else ""
        intent_preview = raw_content if raw_content else None
    
    await log_audit(
        session,
        actor_user_id=user_id,
        action=AUDIT_OWNER_CHAT,
        shop_id=ctx.shop_id,
        target_type="shop",
        target_id=str(ctx.shop_id),
        metadata={
            "slug": ctx.shop_slug,
            "intent_preview": intent_preview,
            "message_count": len(request.messages),
        }
    )
    
    # Call existing owner_chat_with_ai with shop context
    ai_response = await owner_chat_with_ai(
        request.messages,
        session,
        shop_id=ctx.shop_id,
    )
    
    return ScopedOwnerChatResponse(
        reply=ai_response.reply,
        action=ai_response.action,
        data=ai_response.data,
        shop_slug=ctx.shop_slug,
        shop_name=ctx.shop_name,
    )



@router.get("/services", response_model=ServicesResponse)
async def scoped_list_services(
    ctx: ShopContext = Depends(get_shop_context_from_slug),
    session: AsyncSession = Depends(get_session),
):
    """
    List all services for a shop.
    
    Example: GET /s/bishops-tempe/services
    """
    services = await list_services(session, ctx.shop_id)
    
    def format_price(cents: int) -> str:
        return f"${cents / 100:.2f}"
    
    return ServicesResponse(
        shop_slug=ctx.shop_slug or "",
        shop_name=ctx.shop_name,
        services=[
            ServiceListItem(
                id=svc.id,
                name=svc.name,
                duration_minutes=svc.duration_minutes,
                price_cents=svc.price_cents,
                price_display=format_price(svc.price_cents),
            )
            for svc in services
        ],
    )


@router.get("/stylists", response_model=StylistsResponse)
async def scoped_list_stylists(
    ctx: ShopContext = Depends(get_shop_context_from_slug),
    session: AsyncSession = Depends(get_session),
):
    """
    List all active stylists for a shop.
    
    Example: GET /s/bishops-tempe/stylists
    """
    stylists = await list_active_stylists(session, ctx.shop_id)
    
    return StylistsResponse(
        shop_slug=ctx.shop_slug or "",
        shop_name=ctx.shop_name,
        stylists=[
            StylistListItem(
                id=s.id,
                name=s.name,
                active=s.active,
            )
            for s in stylists
        ],
    )


@router.get("/info")
async def scoped_shop_info(
    ctx: ShopContext = Depends(get_shop_context_from_slug),
):
    """
    Get basic shop information.
    
    Useful for frontend to display shop name and build URLs.
    
    Example: GET /s/bishops-tempe/info
    """
    return {
        "shop_id": ctx.shop_id,
        "shop_slug": ctx.shop_slug,
        "shop_name": ctx.shop_name,
        "timezone": ctx.timezone,
        "working_hours_start": settings.working_hours_start,
        "working_hours_end": settings.working_hours_end,
    }


# ────────────────────────────────────────────────────────────────
# Owner Schedule Endpoint
# ────────────────────────────────────────────────────────────────

class OwnerScheduleBooking(BaseModel):
    """Booking info for schedule grid."""
    id: str  # UUID as string
    stylist_id: int
    stylist_name: str
    service_name: str
    secondary_service_name: str | None = None
    customer_name: str | None
    status: str  # BookingStatus enum value
    preferred_style_text: str | None = None
    preferred_style_image_url: str | None = None
    start_time: str  # HH:MM format
    end_time: str  # HH:MM format


class OwnerScheduleTimeOff(BaseModel):
    """Time off block for schedule grid."""
    id: int
    stylist_id: int
    stylist_name: str
    start_time: str  # HH:MM format
    end_time: str  # HH:MM format
    reason: str | None = None


class OwnerScheduleResponse(BaseModel):
    """Schedule data for a specific date."""
    date: str  # YYYY-MM-DD
    stylists: list[dict]  # Stylist details with specialties and time_off_count
    bookings: list[OwnerScheduleBooking]
    time_off: list[OwnerScheduleTimeOff]


def to_local_time_str(utc_dt: datetime, tz_offset_minutes: int) -> str:
    """Convert UTC datetime to local HH:MM string."""
    local_dt = utc_dt - timedelta(minutes=tz_offset_minutes)
    return local_dt.strftime("%H:%M")


def to_utc_from_local(date: datetime.date, local_time: time, tz_offset_minutes: int) -> datetime:
    """Convert local date/time to UTC datetime."""
    local_dt = datetime.combine(date, local_time)
    return local_dt + timedelta(minutes=tz_offset_minutes)


async def list_stylists_with_details(session: AsyncSession, shop_id: int):
    """Get stylists with specialties and time off count."""
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

        now = datetime.now(timezone.utc)
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
            "work_start": s.work_start,
            "work_end": s.work_end,
            "specialties": specialties_map.get(s.id, []),
            "time_off_count": len(time_off_days.get(s.id, set())),
            "active": s.active,
        }
        for s in stylists
    ]


@router.get("/owner/schedule", response_model=OwnerScheduleResponse)
async def scoped_owner_schedule(
    date: str,
    tz_offset_minutes: int = 0,
    ctx: ShopContext = Depends(get_shop_context_from_slug),
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    """
    Get schedule for a specific date with bookings and time off blocks.
    
    Requires authentication and OWNER or MANAGER role.
    
    Headers Required:
        X-User-Id: User identifier from auth provider
    
    Example: 
        GET /s/bishops-tempe/owner/schedule?date=2026-01-22&tz_offset_minutes=-420
    
    Returns:
        401: Missing X-User-Id header
        403: User is not a member or doesn't have OWNER/MANAGER role
        404: Shop not found
        200: Schedule data
    """
    # Verify user has OWNER or MANAGER role
    await require_owner_or_manager(ctx, user_id, session)
    
    logger.info(f"Scoped owner schedule request for shop_id={ctx.shop_id} ({ctx.shop_slug}) by user={user_id}, date={date}")
    
    try:
        local_date = datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid date format")

    stylists = await list_stylists_with_details(session, ctx.shop_id)

    day_start = to_utc_from_local(local_date, time(0, 0), tz_offset_minutes)
    day_end = to_utc_from_local(local_date + timedelta(days=1), time(0, 0), tz_offset_minutes)

    # Fetch bookings for the day
    from .models import Service  # Already imported at top
    booking_result = await session.execute(
        select(Booking, Service, Stylist)
        .join(Service, Service.id == Booking.service_id)
        .join(Stylist, Stylist.id == Booking.stylist_id)
        .where(
            Booking.shop_id == ctx.shop_id,
            Booking.start_at_utc < day_end,
            Booking.end_at_utc > day_start,
            Booking.status.in_([BookingStatus.HOLD, BookingStatus.CONFIRMED]),
        )
        .order_by(Booking.start_at_utc)
    )
    bookings = []
    for booking, service, stylist in booking_result.all():
        secondary_service_name = None
        if booking.secondary_service_id:
            secondary_result = await session.execute(
                select(Service).where(
                    Service.id == booking.secondary_service_id,
                    Service.shop_id == ctx.shop_id
                )
            )
            secondary_service = secondary_result.scalar_one_or_none()
            if secondary_service:
                secondary_service_name = secondary_service.name
        bookings.append(
            OwnerScheduleBooking(
                id=str(booking.id),
                stylist_id=stylist.id,
                stylist_name=stylist.name,
                service_name=service.name,
                secondary_service_name=secondary_service_name,
                customer_name=booking.customer_name,
                status=booking.status.value,
                preferred_style_text=booking.preferred_style_text,
                preferred_style_image_url=booking.preferred_style_image_url,
                start_time=to_local_time_str(booking.start_at_utc, tz_offset_minutes),
                end_time=to_local_time_str(booking.end_at_utc, tz_offset_minutes),
            )
        )

    # Fetch time off blocks for the day
    time_off_result = await session.execute(
        select(TimeOffBlock, Stylist)
        .join(Stylist, Stylist.id == TimeOffBlock.stylist_id)
        .where(
            Stylist.shop_id == ctx.shop_id,
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

