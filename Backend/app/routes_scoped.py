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
    
    Public booking endpoints (no auth required):
    GET  /s/bishops-tempe/public/business     -> Get business info
    GET  /s/bishops-tempe/public/services     -> List services
    GET  /s/bishops-tempe/public/stylists     -> List stylists
    GET  /s/bishops-tempe/public/availability -> Check availability
    POST /s/bishops-tempe/public/booking/quote   -> Create booking quote
    POST /s/bishops-tempe/public/booking/confirm -> Confirm booking
"""

import logging
import re
from datetime import datetime, time, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Path, status, Request, Form
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from .core.config import get_settings
from .core.db import get_session
from .chat import ChatRequest, ChatResponse, ChatMessage, chat_with_ai
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
    get_optional_user_id,
    require_owner_or_manager,
    log_audit,
    AUDIT_OWNER_CHAT,
)
from .owner_actions import execute_owner_action
from .public_booking import router as public_booking_router  # Phase 4: Include public booking routes

settings = get_settings()
logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────
# Router Definition
# ────────────────────────────────────────────────────────────────

router = APIRouter(prefix="/s/{slug}", tags=["scoped-api"])

# Include public booking endpoints under /s/{slug}/public/...
router.include_router(public_booking_router, tags=["public-booking"])


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


# ────────────────────────────────────────────────────────────────
# Phase 3: Enhanced Chat Request with Router Context
# ────────────────────────────────────────────────────────────────

class CustomerLocation(BaseModel):
    """Customer's geographic location from RouterGPT."""
    lat: float
    lon: float


class ScopedChatRequest(BaseModel):
    """
    Extended chat request that accepts RouterGPT context.
    
    Standard fields:
        messages: Conversation history
        context: Optional booking context (service_id, date, etc.)
    
    Router context fields (optional, passed from RouterGPT):
        router_session_id: UUID from /router/delegate for tracking
        customer_location: Lat/lon from location-based discovery
        router_intent: Customer's stated intent (e.g., "haircut", "color")
    """
    messages: list[ChatMessage]
    context: dict | None = None
    
    # Phase 3: Router context fields
    router_session_id: Optional[str] = None
    customer_location: Optional[CustomerLocation] = None
    router_intent: Optional[str] = None


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


class ShopInfoResponse(BaseModel):
    """
    Shop information response for frontend routing and display.
    
    This endpoint is the SERVER-AUTHORITATIVE source for:
    - Shop category (determines which dashboard to show)
    - Redirect hints (where to navigate the user)
    - Shop metadata for display
    """
    id: int
    slug: str
    name: str
    category: Optional[str] = None
    timezone: str
    address: Optional[str] = None
    phone: Optional[str] = None
    # Routing hints
    is_cab_service: bool = False
    owner_dashboard_path: str


# ────────────────────────────────────────────────────────────────
# Endpoints
# ────────────────────────────────────────────────────────────────

@router.get("/info", response_model=ShopInfoResponse)
async def get_shop_info(
    ctx: ShopContext = Depends(get_shop_context_from_slug),
    session: AsyncSession = Depends(get_session),
):
    """
    Get shop information including category and routing hints.
    
    This is the SERVER-AUTHORITATIVE endpoint for shop routing.
    Frontend should use this to determine which dashboard to display.
    
    Example: GET /s/bishops-tempe/info
    
    Response includes:
    - is_cab_service: True if this is a cab/transportation business
    - owner_dashboard_path: The correct path for the owner dashboard
    
    No authentication required - this is public shop info.
    """
    from .models import Shop
    
    result = await session.execute(
        select(Shop).where(Shop.id == ctx.shop_id)
    )
    shop = result.scalar_one_or_none()
    
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")
    
    is_cab = shop.category == "cab"
    
    return ShopInfoResponse(
        id=shop.id,
        slug=shop.slug,
        name=shop.name,
        category=shop.category,
        timezone=shop.timezone,
        address=shop.address,
        phone=shop.phone_number,
        is_cab_service=is_cab,
        owner_dashboard_path=f"/s/{shop.slug}/owner/cab" if is_cab else f"/s/{shop.slug}/owner",
    )


class AuthStatusResponse(BaseModel):
    """Response for auth status check."""
    # Request info
    user_id_from_header: Optional[str] = None
    is_authenticated: bool = False
    # Shop access
    has_shop_access: bool = False
    user_role: Optional[str] = None
    # Debug info (only in non-production)
    shop_owner_ids: list[str] = []
    error_hint: Optional[str] = None


@router.get("/owner/auth-status", response_model=AuthStatusResponse)
async def check_auth_status(
    ctx: ShopContext = Depends(get_shop_context_from_slug),
    session: AsyncSession = Depends(get_session),
    user_id: Optional[str] = Depends(get_optional_user_id),
):
    """
    Debug endpoint to check authentication and authorization status.
    
    Use this to diagnose 403 errors. Returns:
    - What user ID was received from frontend
    - Whether that user has access to the shop
    - What role they have (if any)
    - What user IDs DO have owner access (for debugging)
    
    Example: GET /s/my-cab-shop/owner/auth-status
    """
    from .models import ShopMember
    
    response = AuthStatusResponse(
        user_id_from_header=user_id,
        is_authenticated=bool(user_id),
    )
    
    # Get all owners/managers for this shop
    result = await session.execute(
        select(ShopMember).where(
            ShopMember.shop_id == ctx.shop_id,
            ShopMember.role.in_(["OWNER", "MANAGER"])
        )
    )
    members = result.scalars().all()
    
    # Collect owner IDs (for debugging)
    response.shop_owner_ids = [m.user_id for m in members]
    
    if not user_id:
        response.error_hint = "No X-User-Id header found in request. Check localStorage.getItem('owner_user_id') in browser."
        return response
    
    # Check if user has access
    user_member = next((m for m in members if m.user_id == user_id), None)
    
    if user_member:
        response.has_shop_access = True
        response.user_role = user_member.role
    else:
        # Check if user has ANY role in the shop
        result = await session.execute(
            select(ShopMember).where(
                ShopMember.shop_id == ctx.shop_id,
                ShopMember.user_id == user_id
            )
        )
        any_membership = result.scalar_one_or_none()
        
        if any_membership:
            response.has_shop_access = True
            response.user_role = any_membership.role
            response.error_hint = f"User has {any_membership.role} role, but OWNER or MANAGER is required for this operation."
        else:
            response.error_hint = (
                f"User '{user_id}' is not a member of shop '{ctx.shop_slug}'. "
                f"Expected one of: {response.shop_owner_ids}. "
                f"This usually means the localStorage owner_user_id doesn't match what was used during shop creation."
            )
    
    return response


@router.post("/chat", response_model=ScopedChatResponse)
async def scoped_chat_endpoint(
    request: ScopedChatRequest,
    ctx: ShopContext = Depends(get_shop_context_from_slug),
    session: AsyncSession = Depends(get_session),
):
    """
    AI-powered chat endpoint for booking appointments.
    
    This is the Phase 4 multi-tenant chat endpoint. Shop is resolved from URL slug.
    
    Phase 3 Enhancement: Accepts optional RouterGPT context fields:
        - router_session_id: UUID for tracking delegated sessions
        - customer_location: Lat/lon from location-based discovery
        - router_intent: Customer's stated intent (e.g., "haircut")
    
    Example: POST /s/bishops-tempe/chat
    
    With RouterGPT context:
        POST /s/bishops-tempe/chat
        {
            "messages": [...],
            "router_session_id": "abc-123",
            "router_intent": "haircut",
            "customer_location": {"lat": 33.4255, "lon": -111.94}
        }
    """
    # Log router context if present
    if request.router_session_id:
        logger.info(
            f"Scoped chat from RouterGPT: session={request.router_session_id}, "
            f"intent={request.router_intent}, shop={ctx.shop_slug}"
        )
    else:
        logger.info(f"Scoped chat request for shop_id={ctx.shop_id} ({ctx.shop_slug})")
    
    # Merge router context into the regular context
    merged_context = request.context.copy() if request.context else {}
    
    if request.router_session_id:
        merged_context["router_session_id"] = request.router_session_id
    if request.router_intent:
        merged_context["router_intent"] = request.router_intent
    if request.customer_location:
        merged_context["customer_location"] = {
            "lat": request.customer_location.lat,
            "lon": request.customer_location.lon,
        }
    
    # Call the existing chat_with_ai with shop context
    ai_response = await chat_with_ai(
        request.messages,
        session,
        merged_context if merged_context else None,
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
    logger.info(f"[OWNER_CHAT] Calling AI for shop {ctx.shop_slug} (id={ctx.shop_id})")
    ai_response = await owner_chat_with_ai(
        request.messages,
        session,
        shop_id=ctx.shop_id,
    )
    logger.info(f"[OWNER_CHAT] AI response: action={ai_response.action.get('type') if ai_response.action else 'None'}")
    
    # Execute the action if present
    if ai_response.action:
        logger.info(f"[OWNER_CHAT] Executing action: {ai_response.action.get('type')}")
        executed_response = await execute_owner_action(
            ai_response.action,
            session,
            ctx.shop_id,
        )
        logger.info(f"[OWNER_CHAT] Action executed, reply={executed_response.reply[:50] if executed_response.reply else 'None'}...")
        # Use executed response data and reply if available
        if executed_response.data:
            ai_response.data = executed_response.data
            logger.info(f"[OWNER_CHAT] Data updated with keys: {list(executed_response.data.keys()) if isinstance(executed_response.data, dict) else 'N/A'}")
        if executed_response.reply and executed_response.reply != ai_response.reply:
            ai_response.reply = executed_response.reply
    
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


# ────────────────────────────────────────────────────────────────
# Quick Add Endpoints (Setup Wizard)
# ────────────────────────────────────────────────────────────────

class QuickServiceRequest(BaseModel):
    """Request to quickly add a service."""
    name: str
    duration_minutes: int = 30
    price_cents: int


class QuickServiceResponse(BaseModel):
    """Response for quick service creation."""
    id: int
    name: str
    duration_minutes: int
    price_cents: int


class QuickStylistRequest(BaseModel):
    """Request to quickly add a stylist."""
    name: str
    work_start: str = "09:00"  # HH:MM format
    work_end: str = "17:00"    # HH:MM format


class QuickStylistResponse(BaseModel):
    """Response for quick stylist creation."""
    id: int
    name: str
    work_start: str
    work_end: str
    active: bool = True


@router.post("/owner/services/quick-add", response_model=QuickServiceResponse)
async def quick_add_service(
    request: QuickServiceRequest,
    ctx: ShopContext = Depends(get_shop_context_from_slug),
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    """
    Quick service creation for setup wizard.
    
    Requires OWNER or MANAGER role.
    
    Example:
        POST /s/bishops-tempe/owner/services/quick-add
        {"name": "Men's Haircut", "duration_minutes": 30, "price_cents": 2500}
    """
    await require_owner_or_manager(ctx, user_id, session)
    
    # Validate inputs
    if not request.name or len(request.name.strip()) == 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Service name is required."
        )
    
    if request.duration_minutes < 5 or request.duration_minutes > 480:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Duration must be between 5 and 480 minutes."
        )
    
    if request.price_cents < 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Price cannot be negative."
        )
    
    # Check if service already exists
    existing = await session.execute(
        select(Service).where(
            Service.shop_id == ctx.shop_id,
            Service.name == request.name.strip()
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Service '{request.name}' already exists."
        )
    
    # Create service
    service = Service(
        shop_id=ctx.shop_id,
        name=request.name.strip(),
        duration_minutes=request.duration_minutes,
        price_cents=request.price_cents,
    )
    session.add(service)
    await session.commit()
    await session.refresh(service)
    
    logger.info(f"Quick add service '{service.name}' (id={service.id}) for shop_id={ctx.shop_id}")
    
    return QuickServiceResponse(
        id=service.id,
        name=service.name,
        duration_minutes=service.duration_minutes,
        price_cents=service.price_cents,
    )


@router.post("/owner/stylists/quick-add", response_model=QuickStylistResponse)
async def quick_add_stylist(
    request: QuickStylistRequest,
    ctx: ShopContext = Depends(get_shop_context_from_slug),
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    """
    Quick stylist creation for setup wizard.
    
    Requires OWNER or MANAGER role.
    
    Example:
        POST /s/bishops-tempe/owner/stylists/quick-add
        {"name": "John Smith", "work_start": "09:00", "work_end": "17:00"}
    """
    await require_owner_or_manager(ctx, user_id, session)
    
    # Validate inputs
    if not request.name or len(request.name.strip()) == 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Stylist name is required."
        )
    
    # Parse work hours
    try:
        work_start_parts = request.work_start.split(":")
        work_start = time(int(work_start_parts[0]), int(work_start_parts[1]))
    except (ValueError, IndexError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid work_start time format. Use HH:MM."
        )
    
    try:
        work_end_parts = request.work_end.split(":")
        work_end = time(int(work_end_parts[0]), int(work_end_parts[1]))
    except (ValueError, IndexError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid work_end time format. Use HH:MM."
        )
    
    # Check if stylist already exists
    existing = await session.execute(
        select(Stylist).where(
            Stylist.shop_id == ctx.shop_id,
            Stylist.name == request.name.strip()
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Stylist '{request.name}' already exists."
        )
    
    # Create stylist
    stylist = Stylist(
        shop_id=ctx.shop_id,
        name=request.name.strip(),
        work_start=work_start,
        work_end=work_end,
        active=True,
    )
    session.add(stylist)
    await session.commit()
    await session.refresh(stylist)
    
    logger.info(f"Quick add stylist '{stylist.name}' (id={stylist.id}) for shop_id={ctx.shop_id}")
    
    return QuickStylistResponse(
        id=stylist.id,
        name=stylist.name,
        work_start=stylist.work_start.strftime("%H:%M"),
        work_end=stylist.work_end.strftime("%H:%M"),
        active=stylist.active,
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
# Owner Promos Endpoints
# ────────────────────────────────────────────────────────────────

class PromoResponse(BaseModel):
    """Promo info."""
    id: int
    promo_type: str
    discount_type: str
    discount_value: float | None
    trigger_point: str
    active: bool
    custom_copy: str | None = None
    service_id: int | None = None
    starts_at: str | None = None
    ends_at: str | None = None


class PromosListResponse(BaseModel):
    """Response for promos list."""
    shop_slug: str
    promos: list[PromoResponse]


class CreatePromoRequest(BaseModel):
    """Request to create a promo."""
    discount_value: float
    discount_type: str = "PERCENT"
    promo_type: str = "DAILY_PROMO"
    trigger_point: str = "AT_CHAT_START"
    custom_copy: str | None = None
    service_id: int | None = None


class UpdatePromoRequest(BaseModel):
    """Request to update a promo."""
    discount_value: float | None = None
    active: bool | None = None
    discount_type: str | None = None
    custom_copy: str | None = None


@router.get("/owner/promos", response_model=PromosListResponse)
async def scoped_list_promos(
    ctx: ShopContext = Depends(get_shop_context_from_slug),
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    """List all promos for a shop."""
    await require_owner_or_manager(ctx, user_id, session)
    
    from .models import Promo
    result = await session.execute(
        select(Promo).where(Promo.shop_id == ctx.shop_id).order_by(Promo.id)
    )
    promos = result.scalars().all()
    
    return PromosListResponse(
        shop_slug=ctx.shop_slug or "",
        promos=[
            PromoResponse(
                id=p.id,
                promo_type=p.type.value if p.type else "DAILY_PROMO",
                discount_type=p.discount_type.value if p.discount_type else "PERCENT",
                discount_value=p.discount_value,
                trigger_point=p.trigger_point.value if p.trigger_point else "AT_CHAT_START",
                active=p.active,
                custom_copy=p.custom_copy,
                service_id=p.service_id,
                starts_at=p.start_at_utc.isoformat() if p.start_at_utc else None,
                ends_at=p.end_at_utc.isoformat() if p.end_at_utc else None,
            )
            for p in promos
        ],
    )


@router.post("/owner/promos", response_model=PromoResponse)
async def scoped_create_promo(
    request: CreatePromoRequest,
    ctx: ShopContext = Depends(get_shop_context_from_slug),
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    """Create a new promo."""
    await require_owner_or_manager(ctx, user_id, session)
    
    from .models import Promo, PromoType, PromoDiscountType, PromoTriggerPoint
    
    try:
        discount_type = PromoDiscountType(request.discount_type)
    except ValueError:
        discount_type = PromoDiscountType.PERCENT
    
    try:
        promo_type = PromoType(request.promo_type)
    except ValueError:
        promo_type = PromoType.DAILY_PROMO
    
    try:
        trigger_point = PromoTriggerPoint(request.trigger_point)
    except ValueError:
        trigger_point = PromoTriggerPoint.AT_CHAT_START
    
    promo = Promo(
        shop_id=ctx.shop_id,
        type=promo_type,
        discount_type=discount_type,
        discount_value=int(request.discount_value),
        trigger_point=trigger_point,
        custom_copy=request.custom_copy,
        service_id=request.service_id,
        active=True,
    )
    session.add(promo)
    await session.commit()
    await session.refresh(promo)
    
    return PromoResponse(
        id=promo.id,
        promo_type=promo.type.value,
        discount_type=promo.discount_type.value,
        discount_value=promo.discount_value,
        trigger_point=promo.trigger_point.value,
        active=promo.active,
        custom_copy=promo.custom_copy,
        service_id=promo.service_id,
        starts_at=promo.start_at_utc.isoformat() if promo.start_at_utc else None,
        ends_at=promo.end_at_utc.isoformat() if promo.end_at_utc else None,
    )


@router.patch("/owner/promos/{promo_id}", response_model=PromoResponse)
async def scoped_update_promo(
    promo_id: int,
    request: UpdatePromoRequest,
    ctx: ShopContext = Depends(get_shop_context_from_slug),
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    """Update a promo."""
    await require_owner_or_manager(ctx, user_id, session)
    
    from .models import Promo, PromoDiscountType
    
    result = await session.execute(
        select(Promo).where(Promo.id == promo_id, Promo.shop_id == ctx.shop_id)
    )
    promo = result.scalar_one_or_none()
    if not promo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Promo not found")
    
    if request.discount_value is not None:
        promo.discount_value = int(request.discount_value)
    if request.active is not None:
        promo.active = request.active
    if request.discount_type is not None:
        try:
            promo.discount_type = PromoDiscountType(request.discount_type)
        except ValueError:
            pass
    if request.custom_copy is not None:
        promo.custom_copy = request.custom_copy
    
    await session.commit()
    await session.refresh(promo)
    
    return PromoResponse(
        id=promo.id,
        promo_type=promo.type.value,
        discount_type=promo.discount_type.value,
        discount_value=promo.discount_value,
        trigger_point=promo.trigger_point.value,
        active=promo.active,
        custom_copy=promo.custom_copy,
        service_id=promo.service_id,
        starts_at=promo.start_at_utc.isoformat() if promo.start_at_utc else None,
        ends_at=promo.end_at_utc.isoformat() if promo.end_at_utc else None,
    )


@router.delete("/owner/promos/{promo_id}")
async def scoped_delete_promo(
    promo_id: int,
    ctx: ShopContext = Depends(get_shop_context_from_slug),
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    """Delete a promo."""
    await require_owner_or_manager(ctx, user_id, session)
    
    from .models import Promo
    
    result = await session.execute(
        select(Promo).where(Promo.id == promo_id, Promo.shop_id == ctx.shop_id)
    )
    promo = result.scalar_one_or_none()
    if not promo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Promo not found")
    
    await session.delete(promo)
    await session.commit()
    
    return {"status": "deleted", "promo_id": promo_id}


# ────────────────────────────────────────────────────────────────
# Owner Analytics Endpoints
# ────────────────────────────────────────────────────────────────

class AnalyticsSummaryResponse(BaseModel):
    """Basic analytics summary."""
    total_bookings: int
    confirmed_bookings: int
    total_revenue_cents: int
    active_stylists: int
    active_services: int


@router.get("/owner/analytics/summary", response_model=AnalyticsSummaryResponse)
async def scoped_analytics_summary(
    ctx: ShopContext = Depends(get_shop_context_from_slug),
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    """Get analytics summary for a shop."""
    await require_owner_or_manager(ctx, user_id, session)
    
    from sqlalchemy import func
    
    # Count bookings
    total_result = await session.execute(
        select(func.count(Booking.id)).where(Booking.shop_id == ctx.shop_id)
    )
    total_bookings = total_result.scalar() or 0
    
    confirmed_result = await session.execute(
        select(func.count(Booking.id)).where(
            Booking.shop_id == ctx.shop_id,
            Booking.status == BookingStatus.CONFIRMED
        )
    )
    confirmed_bookings = confirmed_result.scalar() or 0
    
    # Calculate revenue from confirmed bookings (simple estimate)
    revenue_result = await session.execute(
        select(func.sum(Service.price_cents))
        .select_from(Booking)
        .join(Service, Service.id == Booking.service_id)
        .where(
            Booking.shop_id == ctx.shop_id,
            Booking.status == BookingStatus.CONFIRMED
        )
    )
    total_revenue = revenue_result.scalar() or 0
    
    # Count active stylists
    stylists_result = await session.execute(
        select(func.count(Stylist.id)).where(
            Stylist.shop_id == ctx.shop_id,
            Stylist.active == True
        )
    )
    active_stylists = stylists_result.scalar() or 0
    
    # Count services
    services_result = await session.execute(
        select(func.count(Service.id)).where(Service.shop_id == ctx.shop_id)
    )
    active_services = services_result.scalar() or 0
    
    return AnalyticsSummaryResponse(
        total_bookings=total_bookings,
        confirmed_bookings=confirmed_bookings,
        total_revenue_cents=total_revenue,
        active_stylists=active_stylists,
        active_services=active_services,
    )


# ────────────────────────────────────────────────────────────────
# Call Summaries Endpoint
# ────────────────────────────────────────────────────────────────

class CallSummaryItem(BaseModel):
    """Call summary item."""
    id: str
    call_sid: str
    customer_name: str | None
    customer_phone: str
    service: str | None
    stylist: str | None
    appointment_date: str | None
    appointment_time: str | None
    booking_status: str
    key_notes: str | None
    created_at: str


@router.get("/owner/call-summaries", response_model=list[CallSummaryItem])
async def scoped_call_summaries(
    limit: int = 20,
    ctx: ShopContext = Depends(get_shop_context_from_slug),
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    """Get recent call summaries for a shop."""
    await require_owner_or_manager(ctx, user_id, session)
    
    from .models import CallSummary
    
    result = await session.execute(
        select(CallSummary)
        .where(CallSummary.shop_id == ctx.shop_id)
        .order_by(CallSummary.created_at.desc())
        .limit(limit)
    )
    summaries = result.scalars().all()
    
    return [
        CallSummaryItem(
            id=str(s.id),
            call_sid=s.call_sid,
            customer_name=s.customer_name,
            customer_phone=s.customer_phone,
            service=s.service,
            stylist=s.stylist,
            appointment_date=s.appointment_date,
            appointment_time=s.appointment_time,
            booking_status=s.booking_status or "unknown",
            key_notes=s.key_notes,
            created_at=s.created_at.isoformat() if s.created_at else "",
        )
        for s in summaries
    ]


# ────────────────────────────────────────────────────────────────
# Time Off Requests Endpoint
# ────────────────────────────────────────────────────────────────

class TimeOffRequestItem(BaseModel):
    """Time off request item."""
    id: int
    stylist_id: int
    stylist_name: str
    start_at_utc: str
    end_at_utc: str
    reason: str | None


class CreateTimeOffRequest(BaseModel):
    """Request to create time off."""
    stylist_id: int
    date: str  # YYYY-MM-DD
    start_time: str | None = None  # HH:MM
    end_time: str | None = None  # HH:MM
    reason: str | None = None
    tz_offset_minutes: int = 0


@router.get("/time-off-requests", response_model=list[TimeOffRequestItem])
async def scoped_list_time_off(
    ctx: ShopContext = Depends(get_shop_context_from_slug),
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    """List all pending time off for stylists."""
    await require_owner_or_manager(ctx, user_id, session)
    
    now = datetime.now(timezone.utc)
    result = await session.execute(
        select(TimeOffBlock, Stylist)
        .join(Stylist, Stylist.id == TimeOffBlock.stylist_id)
        .where(
            Stylist.shop_id == ctx.shop_id,
            TimeOffBlock.end_at_utc > now,
        )
        .order_by(TimeOffBlock.start_at_utc)
    )
    
    return [
        TimeOffRequestItem(
            id=block.id,
            stylist_id=stylist.id,
            stylist_name=stylist.name,
            start_at_utc=block.start_at_utc.isoformat(),
            end_at_utc=block.end_at_utc.isoformat(),
            reason=block.reason,
        )
        for block, stylist in result.all()
    ]


@router.post("/time-off-requests", response_model=TimeOffRequestItem)
async def scoped_create_time_off(
    request: CreateTimeOffRequest,
    ctx: ShopContext = Depends(get_shop_context_from_slug),
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    """Create a time off block for a stylist."""
    await require_owner_or_manager(ctx, user_id, session)
    
    # Verify stylist belongs to shop
    result = await session.execute(
        select(Stylist).where(Stylist.id == request.stylist_id, Stylist.shop_id == ctx.shop_id)
    )
    stylist = result.scalar_one_or_none()
    if not stylist:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stylist not found")
    
    # Parse date and times
    try:
        local_date = datetime.strptime(request.date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid date format")
    
    start_time = time(0, 0) if not request.start_time else datetime.strptime(request.start_time, "%H:%M").time()
    end_time = time(23, 59) if not request.end_time else datetime.strptime(request.end_time, "%H:%M").time()
    
    start_utc = to_utc_from_local(local_date, start_time, request.tz_offset_minutes)
    end_utc = to_utc_from_local(local_date, end_time, request.tz_offset_minutes)
    
    block = TimeOffBlock(
        stylist_id=stylist.id,
        start_at_utc=start_utc,
        end_at_utc=end_utc,
        reason=request.reason,
    )
    session.add(block)
    await session.commit()
    await session.refresh(block)
    
    return TimeOffRequestItem(
        id=block.id,
        stylist_id=stylist.id,
        stylist_name=stylist.name,
        start_at_utc=block.start_at_utc.isoformat(),
        end_at_utc=block.end_at_utc.isoformat(),
        reason=block.reason,
    )


@router.delete("/time-off-requests/{time_off_id}")
async def scoped_delete_time_off(
    time_off_id: int,
    ctx: ShopContext = Depends(get_shop_context_from_slug),
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    """Delete a time off block."""
    await require_owner_or_manager(ctx, user_id, session)
    
    result = await session.execute(
        select(TimeOffBlock)
        .join(Stylist, Stylist.id == TimeOffBlock.stylist_id)
        .where(TimeOffBlock.id == time_off_id, Stylist.shop_id == ctx.shop_id)
    )
    block = result.scalar_one_or_none()
    if not block:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Time off not found")
    
    await session.delete(block)
    await session.commit()
    
    return {"status": "deleted", "time_off_id": time_off_id}


# ────────────────────────────────────────────────────────────────
# Service Booking Counts Endpoint
# ────────────────────────────────────────────────────────────────

class ServiceBookingCount(BaseModel):
    """Service with booking count."""
    id: int
    name: str
    booking_count: int


@router.get("/services/booking-counts", response_model=list[ServiceBookingCount])
async def scoped_service_booking_counts(
    ctx: ShopContext = Depends(get_shop_context_from_slug),
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    """Get booking counts per service."""
    await require_owner_or_manager(ctx, user_id, session)
    
    from sqlalchemy import func
    
    result = await session.execute(
        select(
            Service.id,
            Service.name,
            func.count(Booking.id).label("booking_count")
        )
        .outerjoin(Booking, Booking.service_id == Service.id)
        .where(Service.shop_id == ctx.shop_id)
        .group_by(Service.id, Service.name)
        .order_by(Service.name)
    )
    
    return [
        ServiceBookingCount(id=row[0], name=row[1], booking_count=row[2] or 0)
        for row in result.all()
    ]


# ────────────────────────────────────────────────────────────────
# Booking Management Endpoints
# ────────────────────────────────────────────────────────────────

class RescheduleBookingRequest(BaseModel):
    """Request to reschedule a booking."""
    booking_id: str
    new_date: str  # YYYY-MM-DD
    new_time: str  # HH:MM
    tz_offset_minutes: int = 0


class CancelBookingRequest(BaseModel):
    """Request to cancel a booking."""
    booking_id: str


@router.post("/owner/bookings/reschedule")
async def scoped_reschedule_booking(
    request: RescheduleBookingRequest,
    ctx: ShopContext = Depends(get_shop_context_from_slug),
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    """Reschedule a booking to a new date/time."""
    await require_owner_or_manager(ctx, user_id, session)
    
    import uuid
    
    try:
        booking_uuid = uuid.UUID(request.booking_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid booking ID")
    
    result = await session.execute(
        select(Booking).where(Booking.id == booking_uuid, Booking.shop_id == ctx.shop_id)
    )
    booking = result.scalar_one_or_none()
    if not booking:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")
    
    # Parse new date/time
    try:
        new_date = datetime.strptime(request.new_date, "%Y-%m-%d").date()
        new_time = datetime.strptime(request.new_time, "%H:%M").time()
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid date or time format")
    
    # Get service duration
    service_result = await session.execute(
        select(Service).where(Service.id == booking.service_id)
    )
    service = service_result.scalar_one_or_none()
    duration_minutes = service.duration_minutes if service else 30
    
    # Calculate new times
    new_start_utc = to_utc_from_local(new_date, new_time, request.tz_offset_minutes)
    new_end_utc = new_start_utc + timedelta(minutes=duration_minutes)
    
    booking.start_at_utc = new_start_utc
    booking.end_at_utc = new_end_utc
    await session.commit()
    
    return {
        "status": "rescheduled",
        "booking_id": str(booking.id),
        "new_start": new_start_utc.isoformat(),
        "new_end": new_end_utc.isoformat(),
    }


@router.post("/owner/bookings/cancel")
async def scoped_cancel_booking(
    request: CancelBookingRequest,
    ctx: ShopContext = Depends(get_shop_context_from_slug),
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    """Cancel a booking."""
    await require_owner_or_manager(ctx, user_id, session)
    
    import uuid
    
    try:
        booking_uuid = uuid.UUID(request.booking_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid booking ID")
    
    result = await session.execute(
        select(Booking).where(Booking.id == booking_uuid, Booking.shop_id == ctx.shop_id)
    )
    booking = result.scalar_one_or_none()
    if not booking:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")
    
    booking.status = BookingStatus.CANCELLED
    await session.commit()
    
    return {"status": "cancelled", "booking_id": str(booking.id)}


# ────────────────────────────────────────────────────────────────
# Customer Profile Endpoint
# ────────────────────────────────────────────────────────────────

class CustomerProfileResponse(BaseModel):
    """Customer profile with booking history."""
    name: str | None
    phone: str | None
    email: str | None
    total_bookings: int
    bookings: list[dict]


@router.get("/owner/customer-profile")
async def scoped_customer_profile(
    phone: str | None = None,
    email: str | None = None,
    ctx: ShopContext = Depends(get_shop_context_from_slug),
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    """Look up a customer profile by phone or email."""
    await require_owner_or_manager(ctx, user_id, session)
    
    if not phone and not email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Phone or email required")
    
    query = select(Booking).where(Booking.shop_id == ctx.shop_id)
    if phone:
        query = query.where(Booking.customer_phone == phone)
    elif email:
        query = query.where(Booking.customer_email == email.lower())
    
    query = query.order_by(Booking.start_at_utc.desc()).limit(20)
    result = await session.execute(query)
    bookings = result.scalars().all()
    
    if not bookings:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    
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
    
    return CustomerProfileResponse(
        name=customer_name,
        phone=customer_phone,
        email=customer_email,
        total_bookings=len(bookings),
        bookings=booking_history,
    )


# ────────────────────────────────────────────────────────────────
# PIN Management Endpoints
# ────────────────────────────────────────────────────────────────

class PINVerifyRequest(BaseModel):
    """Request to verify or set PIN."""
    pin: str


class PINGenerateResponse(BaseModel):
    """Response with generated PIN."""
    pin: str


@router.post("/owner/pin/verify")
async def scoped_verify_pin(
    request: PINVerifyRequest,
    ctx: ShopContext = Depends(get_shop_context_from_slug),
    session: AsyncSession = Depends(get_session),
):
    """
    Verify a shop PIN for access.
    This is a simplified PIN check - in production, use proper hashing.
    """
    from .models import Shop
    
    result = await session.execute(
        select(Shop).where(Shop.id == ctx.shop_id)
    )
    shop = result.scalar_one_or_none()
    if not shop:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shop not found")
    
    # Check if shop has a PIN set (stored in api_key for now - simplified)
    stored_pin = getattr(shop, 'owner_pin', None)
    if not stored_pin:
        # No PIN set, any 4-digit PIN is accepted for initial setup
        if len(request.pin) == 4 and request.pin.isdigit():
            return {"valid": True, "message": "PIN accepted (no PIN configured)"}
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid PIN format")
    
    if stored_pin == request.pin:
        return {"valid": True}
    
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid PIN")


@router.post("/owner/pin/generate", response_model=PINGenerateResponse)
async def scoped_generate_pin(
    ctx: ShopContext = Depends(get_shop_context_from_slug),
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    """Generate a new random PIN for the shop."""
    await require_owner_or_manager(ctx, user_id, session)
    
    import random
    
    # Generate a 4-digit PIN
    pin = ''.join(random.choices('0123456789', k=4))
    
    # In production, you'd save this to the shop record
    # For now, just return it
    return PINGenerateResponse(pin=pin)

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


# ────────────────────────────────────────────────────────────────
# Phase 6: Shop-Scoped Employee Routes
# ────────────────────────────────────────────────────────────────

from fastapi import Header, Query
import uuid
import hashlib
import secrets

from .models import (
    AppointmentStatus, 
    Customer, 
    CustomerStylistPreference, 
    CustomerServicePreference,
    TimeOffRequest,
    TimeOffRequestStatus,
)

# In-memory session store for employees: {token: {"stylist_id": int, "shop_id": int, "expires_at": datetime}}
_employee_sessions: dict[str, dict] = {}
EMPLOYEE_SESSION_TTL_HOURS = 12


def hash_pin(pin: str) -> str:
    """Hash a PIN using SHA-256."""
    return hashlib.sha256(pin.encode()).hexdigest()


def verify_pin(pin: str, pin_hash: str) -> bool:
    """Verify a PIN against its hash."""
    return hash_pin(pin) == pin_hash


def create_employee_session(stylist_id: int, shop_id: int) -> str:
    """Create a new session token for an employee."""
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=EMPLOYEE_SESSION_TTL_HOURS)
    _employee_sessions[token] = {
        "stylist_id": stylist_id,
        "shop_id": shop_id,
        "expires_at": expires_at,
    }
    return token


def get_employee_from_token(token: str) -> tuple[int, int] | None:
    """Get (stylist_id, shop_id) from session token, or None if invalid/expired."""
    session = _employee_sessions.get(token)
    if not session:
        return None
    if datetime.now(timezone.utc) > session["expires_at"]:
        del _employee_sessions[token]
        return None
    return session["stylist_id"], session["shop_id"]


async def get_authenticated_stylist(
    ctx: ShopContext,
    authorization: str = Header(None),
) -> int:
    """
    Dependency to extract and validate employee authentication.
    Returns stylist_id if valid, raises 401 otherwise.
    Also validates that the stylist belongs to the current shop context.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
    
    token = authorization.split(" ", 1)[1]
    result = get_employee_from_token(token)
    
    if result is None:
        raise HTTPException(status_code=401, detail="Invalid or expired session token")
    
    stylist_id, shop_id = result
    
    # Validate stylist belongs to this shop
    if shop_id != ctx.shop_id:
        raise HTTPException(status_code=403, detail="Session not valid for this shop")
    
    return stylist_id


# ────────────────────────────────────────────────────────────────
# Employee Models
# ────────────────────────────────────────────────────────────────

class EmployeeLoginRequest(BaseModel):
    stylist_id: int
    pin: str


class EmployeeLoginResponse(BaseModel):
    token: str
    stylist_id: int
    stylist_name: str
    shop_slug: str
    shop_name: str


class EmployeeScheduleBooking(BaseModel):
    id: str
    service_name: str
    secondary_service_name: str | None = None
    customer_name: str | None
    customer_phone: str | None
    customer_email: str | None = None
    start_time: str
    end_time: str
    start_at_utc: datetime
    end_at_utc: datetime
    appointment_status: str
    acknowledged: bool
    internal_notes: str | None = None
    # Customer preferences
    customer_preferences: dict | None = None


class EmployeeScheduleResponse(BaseModel):
    stylist_id: int
    stylist_name: str
    shop_slug: str
    shop_name: str
    date: str
    bookings: list[EmployeeScheduleBooking]


class AcknowledgeBookingRequest(BaseModel):
    booking_id: str


class UpdateAppointmentStatusRequest(BaseModel):
    booking_id: str
    status: str  # SCHEDULED, IN_PROGRESS, RUNNING_LATE, COMPLETED, NO_SHOW


class UpdateInternalNotesRequest(BaseModel):
    booking_id: str
    notes: str


class TimeOffRequestCreate(BaseModel):
    start_date: str  # YYYY-MM-DD
    end_date: str  # YYYY-MM-DD
    reason: str | None = None


class TimeOffRequestResponse(BaseModel):
    id: int
    stylist_id: int
    start_date: str
    end_date: str
    reason: str | None
    status: str
    created_at: datetime
    reviewed_at: datetime | None = None
    reviewer: str | None = None


class CustomerPreferences(BaseModel):
    """Customer preferences for a specific booking."""
    preferred_stylist: bool = False
    total_visits: int = 0
    preferred_style_text: str | None = None
    preferred_style_image_url: str | None = None


# ────────────────────────────────────────────────────────────────
# Employee Endpoints
# ────────────────────────────────────────────────────────────────

@router.get("/employee/stylists-for-login")
async def get_stylists_for_employee_login(
    ctx: ShopContext = Depends(get_shop_context_from_slug),
    session: AsyncSession = Depends(get_session),
):
    """Get list of stylists available for employee login (those with PINs set)."""
    result = await session.execute(
        select(Stylist)
        .where(
            Stylist.shop_id == ctx.shop_id, 
            Stylist.pin_hash.isnot(None),
            Stylist.active == True
        )
        .order_by(Stylist.name)
    )
    stylists = result.scalars().all()
    return [{"id": s.id, "name": s.name} for s in stylists]


@router.post("/employee/login", response_model=EmployeeLoginResponse)
async def employee_login(
    req: EmployeeLoginRequest,
    ctx: ShopContext = Depends(get_shop_context_from_slug),
    session: AsyncSession = Depends(get_session),
):
    """Authenticate an employee using their PIN for this shop."""
    result = await session.execute(
        select(Stylist).where(
            Stylist.id == req.stylist_id, 
            Stylist.shop_id == ctx.shop_id
        )
    )
    stylist = result.scalar_one_or_none()
    
    if not stylist:
        raise HTTPException(status_code=404, detail="Stylist not found")
    
    if not stylist.pin_hash:
        raise HTTPException(status_code=400, detail="PIN not set for this stylist")
    
    if not verify_pin(req.pin, stylist.pin_hash):
        raise HTTPException(status_code=401, detail="Invalid PIN")
    
    token = create_employee_session(stylist.id, ctx.shop_id)
    
    return EmployeeLoginResponse(
        token=token,
        stylist_id=stylist.id,
        stylist_name=stylist.name,
        shop_slug=ctx.shop_slug,
        shop_name=ctx.shop_name or ctx.shop_slug,
    )


@router.get("/employee/schedule", response_model=EmployeeScheduleResponse)
async def get_employee_schedule(
    date_str: str | None = Query(None, description="Date in YYYY-MM-DD format"),
    ctx: ShopContext = Depends(get_shop_context_from_slug),
    authorization: str = Header(None),
    session: AsyncSession = Depends(get_session),
):
    """
    Get the employee's schedule for a specific date.
    
    Returns bookings assigned to this stylist with customer preferences.
    """
    # Validate auth
    stylist_id = await get_authenticated_stylist(ctx, authorization)
    
    # Get stylist
    stylist_result = await session.execute(
        select(Stylist).where(
            Stylist.id == stylist_id, 
            Stylist.shop_id == ctx.shop_id
        )
    )
    stylist = stylist_result.scalar_one_or_none()
    if not stylist:
        raise HTTPException(status_code=404, detail="Stylist not found")
    
    tz = ZoneInfo(ctx.shop_timezone or settings.chat_timezone)
    
    # Parse date or use today
    if date_str:
        try:
            target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
    else:
        target_date = datetime.now(tz).date()
    
    # Get start and end of day in UTC
    start_of_day = datetime.combine(target_date, time.min, tzinfo=tz)
    end_of_day = datetime.combine(target_date, time.max, tzinfo=tz)
    start_utc = start_of_day.astimezone(timezone.utc)
    end_utc = end_of_day.astimezone(timezone.utc)
    
    # Fetch confirmed bookings for this stylist on this day
    from sqlalchemy import and_
    result = await session.execute(
        select(Booking)
        .where(
            and_(
                Booking.stylist_id == stylist_id,
                Booking.shop_id == ctx.shop_id,
                Booking.start_at_utc >= start_utc,
                Booking.start_at_utc <= end_utc,
                Booking.status == BookingStatus.CONFIRMED,
            )
        )
        .order_by(Booking.start_at_utc)
    )
    bookings = result.scalars().all()
    
    # Get service info
    service_ids = set()
    for b in bookings:
        service_ids.add(b.service_id)
        if b.secondary_service_id:
            service_ids.add(b.secondary_service_id)
    
    services_map = {}
    if service_ids:
        svc_result = await session.execute(
            select(Service).where(
                Service.id.in_(service_ids), 
                Service.shop_id == ctx.shop_id
            )
        )
        for svc in svc_result.scalars().all():
            services_map[svc.id] = svc.name
    
    # Get customer preferences for bookings with customer IDs
    customer_ids = set()
    for b in bookings:
        if b.customer_id:
            customer_ids.add(b.customer_id)
    
    customer_prefs = {}
    if customer_ids:
        # Get stylist preferences
        stylist_pref_result = await session.execute(
            select(CustomerStylistPreference)
            .where(
                CustomerStylistPreference.customer_id.in_(customer_ids),
                CustomerStylistPreference.stylist_id == stylist_id,
                CustomerStylistPreference.shop_id == ctx.shop_id,
            )
        )
        for pref in stylist_pref_result.scalars().all():
            if pref.customer_id not in customer_prefs:
                customer_prefs[pref.customer_id] = {}
            customer_prefs[pref.customer_id]["preferred_stylist"] = True
            customer_prefs[pref.customer_id]["total_visits"] = pref.booking_count
        
        # Get service preferences for the services being booked
        for b in bookings:
            if b.customer_id and b.service_id:
                svc_pref_result = await session.execute(
                    select(CustomerServicePreference)
                    .where(
                        CustomerServicePreference.customer_id == b.customer_id,
                        CustomerServicePreference.service_id == b.service_id,
                        CustomerServicePreference.shop_id == ctx.shop_id,
                    )
                )
                svc_pref = svc_pref_result.scalar_one_or_none()
                if svc_pref:
                    if b.customer_id not in customer_prefs:
                        customer_prefs[b.customer_id] = {}
                    customer_prefs[b.customer_id]["preferred_style_text"] = svc_pref.preferred_style_text
                    customer_prefs[b.customer_id]["preferred_style_image_url"] = svc_pref.preferred_style_image_url
    
    # Format response
    schedule_bookings = []
    for b in bookings:
        local_start = b.start_at_utc.astimezone(tz)
        local_end = b.end_at_utc.astimezone(tz)
        
        # Get appointment_status safely
        appt_status = getattr(b, 'appointment_status', None)
        if appt_status is None:
            appt_status_str = "SCHEDULED"
        else:
            appt_status_str = appt_status.value if hasattr(appt_status, 'value') else str(appt_status)
        
        # Build customer preferences
        prefs = None
        if b.customer_id and b.customer_id in customer_prefs:
            prefs = customer_prefs[b.customer_id]
        
        schedule_bookings.append(EmployeeScheduleBooking(
            id=str(b.id),
            service_name=services_map.get(b.service_id, "Unknown Service"),
            secondary_service_name=services_map.get(b.secondary_service_id) if b.secondary_service_id else None,
            customer_name=b.customer_name,
            customer_phone=b.customer_phone,
            customer_email=b.customer_email,
            start_time=local_start.strftime("%I:%M %p"),
            end_time=local_end.strftime("%I:%M %p"),
            start_at_utc=b.start_at_utc,
            end_at_utc=b.end_at_utc,
            appointment_status=appt_status_str,
            acknowledged=b.acknowledged_at_utc is not None if hasattr(b, 'acknowledged_at_utc') else False,
            internal_notes=getattr(b, 'internal_notes', None),
            customer_preferences=prefs,
        ))
    
    return EmployeeScheduleResponse(
        stylist_id=stylist_id,
        stylist_name=stylist.name,
        shop_slug=ctx.shop_slug,
        shop_name=ctx.shop_name or ctx.shop_slug,
        date=target_date.isoformat(),
        bookings=schedule_bookings,
    )


@router.post("/employee/bookings/{booking_id}/acknowledge")
async def acknowledge_booking(
    booking_id: str,
    ctx: ShopContext = Depends(get_shop_context_from_slug),
    authorization: str = Header(None),
    session: AsyncSession = Depends(get_session),
):
    """Mark a booking as acknowledged by the employee."""
    stylist_id = await get_authenticated_stylist(ctx, authorization)
    
    try:
        booking_uuid = uuid.UUID(booking_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid booking ID format")
    
    from sqlalchemy import and_
    result = await session.execute(
        select(Booking).where(
            and_(
                Booking.id == booking_uuid,
                Booking.stylist_id == stylist_id,
                Booking.shop_id == ctx.shop_id,
            )
        )
    )
    booking = result.scalar_one_or_none()
    
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    
    booking.acknowledged_at_utc = datetime.now(timezone.utc)
    await session.commit()
    
    logger.info(f"[EMPLOYEE] Booking {booking_id} acknowledged by stylist {stylist_id} in shop {ctx.shop_slug}")
    
    return {"success": True, "acknowledged_at": booking.acknowledged_at_utc.isoformat()}


@router.post("/employee/bookings/{booking_id}/status")
async def update_booking_status(
    booking_id: str,
    req: UpdateAppointmentStatusRequest,
    ctx: ShopContext = Depends(get_shop_context_from_slug),
    authorization: str = Header(None),
    session: AsyncSession = Depends(get_session),
):
    """
    Employee marks booking status.
    
    Valid statuses: SCHEDULED, IN_PROGRESS, RUNNING_LATE, COMPLETED, NO_SHOW
    """
    stylist_id = await get_authenticated_stylist(ctx, authorization)
    
    # Validate status
    valid_statuses = ["SCHEDULED", "IN_PROGRESS", "RUNNING_LATE", "COMPLETED", "NO_SHOW"]
    if req.status not in valid_statuses:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}"
        )
    
    try:
        booking_uuid = uuid.UUID(booking_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid booking ID format")
    
    from sqlalchemy import and_
    result = await session.execute(
        select(Booking).where(
            and_(
                Booking.id == booking_uuid,
                Booking.stylist_id == stylist_id,
                Booking.shop_id == ctx.shop_id,
            )
        )
    )
    booking = result.scalar_one_or_none()
    
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    
    booking.appointment_status = AppointmentStatus(req.status)
    booking.appointment_status_updated_at_utc = datetime.now(timezone.utc)
    await session.commit()
    
    logger.info(f"[EMPLOYEE] Booking {booking_id} status updated to {req.status} by stylist {stylist_id} in shop {ctx.shop_slug}")
    
    return {"success": True, "status": req.status}


@router.post("/employee/bookings/{booking_id}/notes")
async def update_booking_notes(
    booking_id: str,
    req: UpdateInternalNotesRequest,
    ctx: ShopContext = Depends(get_shop_context_from_slug),
    authorization: str = Header(None),
    session: AsyncSession = Depends(get_session),
):
    """Update internal notes for a booking."""
    stylist_id = await get_authenticated_stylist(ctx, authorization)
    
    try:
        booking_uuid = uuid.UUID(booking_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid booking ID format")
    
    from sqlalchemy import and_
    result = await session.execute(
        select(Booking).where(
            and_(
                Booking.id == booking_uuid,
                Booking.stylist_id == stylist_id,
                Booking.shop_id == ctx.shop_id,
            )
        )
    )
    booking = result.scalar_one_or_none()
    
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    
    booking.internal_notes = req.notes
    await session.commit()
    
    return {"success": True}


@router.post("/employee/time-off", response_model=TimeOffRequestResponse)
async def create_time_off_request(
    req: TimeOffRequestCreate,
    ctx: ShopContext = Depends(get_shop_context_from_slug),
    authorization: str = Header(None),
    session: AsyncSession = Depends(get_session),
):
    """Submit a time-off request."""
    stylist_id = await get_authenticated_stylist(ctx, authorization)
    
    tz = ZoneInfo(ctx.shop_timezone or settings.chat_timezone)
    
    try:
        start_date = datetime.strptime(req.start_date, "%Y-%m-%d").date()
        end_date = datetime.strptime(req.end_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
    
    if end_date < start_date:
        raise HTTPException(status_code=400, detail="End date must be after start date")
    
    # Convert to UTC (start of start day, end of end day)
    start_utc = datetime.combine(start_date, time.min, tzinfo=tz).astimezone(timezone.utc)
    end_utc = datetime.combine(end_date, time.max, tzinfo=tz).astimezone(timezone.utc)
    
    time_off_request = TimeOffRequest(
        stylist_id=stylist_id,
        start_at_utc=start_utc,
        end_at_utc=end_utc,
        reason=req.reason,
        status=TimeOffRequestStatus.PENDING,
    )
    session.add(time_off_request)
    await session.commit()
    await session.refresh(time_off_request)
    
    logger.info(f"[EMPLOYEE] Time-off request created by stylist {stylist_id} in shop {ctx.shop_slug}: {start_date} to {end_date}")
    
    return TimeOffRequestResponse(
        id=time_off_request.id,
        stylist_id=time_off_request.stylist_id,
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        reason=time_off_request.reason,
        status=time_off_request.status.value,
        created_at=time_off_request.created_at,
    )


@router.get("/employee/time-off", response_model=list[TimeOffRequestResponse])
async def get_my_time_off_requests(
    ctx: ShopContext = Depends(get_shop_context_from_slug),
    authorization: str = Header(None),
    session: AsyncSession = Depends(get_session),
):
    """Get all time-off requests for the current employee."""
    stylist_id = await get_authenticated_stylist(ctx, authorization)
    
    tz = ZoneInfo(ctx.shop_timezone or settings.chat_timezone)
    
    result = await session.execute(
        select(TimeOffRequest)
        .where(TimeOffRequest.stylist_id == stylist_id)
        .order_by(TimeOffRequest.created_at.desc())
    )
    requests = result.scalars().all()
    
    return [
        TimeOffRequestResponse(
            id=r.id,
            stylist_id=r.stylist_id,
            start_date=r.start_at_utc.astimezone(tz).date().isoformat(),
            end_date=r.end_at_utc.astimezone(tz).date().isoformat(),
            reason=r.reason,
            status=r.status.value,
            created_at=r.created_at,
            reviewed_at=r.reviewed_at_utc,
            reviewer=r.reviewer,
        )
        for r in requests
    ]


@router.get("/employee/customer/{booking_id}/preferences")
async def get_customer_preferences_for_booking(
    booking_id: str,
    ctx: ShopContext = Depends(get_shop_context_from_slug),
    authorization: str = Header(None),
    session: AsyncSession = Depends(get_session),
):
    """
    Get detailed customer preferences for a specific booking.
    
    Returns:
    - Customer visit history with this stylist
    - Preferred style text and images
    - Service preferences
    """
    stylist_id = await get_authenticated_stylist(ctx, authorization)
    
    try:
        booking_uuid = uuid.UUID(booking_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid booking ID format")
    
    from sqlalchemy import and_
    # Get the booking
    result = await session.execute(
        select(Booking).where(
            and_(
                Booking.id == booking_uuid,
                Booking.stylist_id == stylist_id,
                Booking.shop_id == ctx.shop_id,
            )
        )
    )
    booking = result.scalar_one_or_none()
    
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    
    if not booking.customer_id:
        return {
            "customer_name": booking.customer_name or "Guest",
            "has_preferences": False,
            "preferences": None,
        }
    
    # Get customer details
    customer_result = await session.execute(
        select(Customer).where(Customer.id == booking.customer_id)
    )
    customer = customer_result.scalar_one_or_none()
    
    # Get stylist preference
    stylist_pref_result = await session.execute(
        select(CustomerStylistPreference)
        .where(
            CustomerStylistPreference.customer_id == booking.customer_id,
            CustomerStylistPreference.stylist_id == stylist_id,
            CustomerStylistPreference.shop_id == ctx.shop_id,
        )
    )
    stylist_pref = stylist_pref_result.scalar_one_or_none()
    
    # Get service preference
    service_pref_result = await session.execute(
        select(CustomerServicePreference)
        .where(
            CustomerServicePreference.customer_id == booking.customer_id,
            CustomerServicePreference.service_id == booking.service_id,
            CustomerServicePreference.shop_id == ctx.shop_id,
        )
    )
    service_pref = service_pref_result.scalar_one_or_none()
    
    # Get booking history count
    from sqlalchemy import func
    history_result = await session.execute(
        select(func.count(Booking.id))
        .where(
            Booking.customer_id == booking.customer_id,
            Booking.shop_id == ctx.shop_id,
            Booking.status == BookingStatus.CONFIRMED,
        )
    )
    total_bookings = history_result.scalar() or 0
    
    preferences = {
        "is_preferred_stylist": stylist_pref is not None,
        "visits_with_stylist": stylist_pref.booking_count if stylist_pref else 0,
        "total_visits_to_shop": total_bookings,
        "preferred_style_text": service_pref.preferred_style_text if service_pref else None,
        "preferred_style_image_url": service_pref.preferred_style_image_url if service_pref else None,
        "booking_preferred_style_text": booking.preferred_style_text,
        "booking_preferred_style_image_url": booking.preferred_style_image_url,
    }
    
    return {
        "customer_name": customer.name if customer else booking.customer_name,
        "customer_email": customer.email if customer else booking.customer_email,
        "customer_phone": customer.phone if customer else booking.customer_phone,
        "has_preferences": any([
            preferences["is_preferred_stylist"],
            preferences["preferred_style_text"],
            preferences["preferred_style_image_url"],
            preferences["booking_preferred_style_text"],
        ]),
        "preferences": preferences,
    }


# ────────────────────────────────────────────────────────────────
# CAB BOOKING ENDPOINTS (Phase 10: Cab Services Vertical)
# ────────────────────────────────────────────────────────────────

from .cab_booking import (
    CabBookingCreateRequest,
    CabBookingResponse,
    CabBookingDetailResponse,
    CabBookingListItem,
    get_pricing_rule_for_shop,
    calculate_route_and_price,
    create_cab_booking_record,
    booking_to_response,
    booking_to_detail_response,
    booking_to_list_item,
)
from .cab_models import (
    CabBooking, 
    CabBookingStatus, 
    CabBookingChannel, 
    CabVehicleType,
    CabOwner, 
    CabDriver, 
    CabDriverStatus,
    CabPricingRule,
)
from .cab_distance import RouteError


@router.post(
    "/cab/bookings",
    response_model=CabBookingResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["cab-booking"],
    summary="Create a cab booking",
    description="Create a new cab booking request. Returns distance, duration, and price estimate.",
)
async def create_cab_booking(
    request: CabBookingCreateRequest,
    ctx: ShopContext = Depends(get_shop_context_from_slug),
    session: AsyncSession = Depends(get_session),
):
    """
    Create a new cab booking (public, no auth required).
    
    This endpoint:
    1. Validates the request
    2. Calculates route distance and duration via Google Maps
    3. Calculates price based on shop's pricing rules
    4. Creates a PENDING booking with pricing snapshot
    5. Sends notification to owner
    6. Returns booking details with price breakdown
    """
    logger.info(
        f"Creating cab booking for shop={ctx.shop_slug}: "
        f"{request.pickup_text} -> {request.drop_text}"
    )
    
    try:
        # Get pricing rule for this shop
        pricing_rule = await get_pricing_rule_for_shop(session, ctx.shop_id)
        
        # Calculate route and price
        calc_result = await calculate_route_and_price(
            pickup_text=request.pickup_text,
            drop_text=request.drop_text,
            pricing_rule=pricing_rule,
            vehicle_type=request.vehicle_type,
        )
        
        # Create booking record
        booking = await create_cab_booking_record(
            session=session,
            shop_id=ctx.shop_id,
            request=request,
            calc_result=calc_result,
        )
        
        # Trigger notification (async, don't block on failure)
        try:
            from .cab_notifications import notify_owner_new_booking
            await notify_owner_new_booking(session, booking)
        except Exception as e:
            logger.error(f"Failed to send notification for booking {booking.id}: {e}")
        
        return booking_to_response(booking, calc_result["pricing_breakdown"])
        
    except RouteError as e:
        logger.warning(f"Route calculation failed: {e.message}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "route_calculation_failed",
                "message": e.message,
                "status": e.status,
            }
        )
    except Exception as e:
        logger.exception(f"Failed to create cab booking: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create booking. Please try again.",
        )


@router.get(
    "/cab/bookings/{booking_id}",
    response_model=CabBookingDetailResponse,
    tags=["cab-booking"],
    summary="Get cab booking details",
    description="Get detailed information about a cab booking.",
)
async def get_cab_booking(
    booking_id: str,
    ctx: ShopContext = Depends(get_shop_context_from_slug),
    session: AsyncSession = Depends(get_session),
):
    """
    Get details of a specific cab booking (public).
    """
    from uuid import UUID
    
    try:
        booking_uuid = UUID(booking_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid booking ID format",
        )
    
    result = await session.execute(
        select(CabBooking).where(
            CabBooking.id == booking_uuid,
            CabBooking.shop_id == ctx.shop_id,
        )
    )
    booking = result.scalar_one_or_none()
    
    if not booking:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Booking not found",
        )
    
    return booking_to_detail_response(booking)


# ────────────────────────────────────────────────────────────────
# DEV TEST ENDPOINT (Development Only)
# ────────────────────────────────────────────────────────────────

import os

@router.post(
    "/owner/cab/test-booking",
    response_model=CabBookingResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["cab-owner", "dev"],
    summary="Create test cab booking (DEV ONLY)",
    description="Development endpoint to create a test cab booking for UI testing. Disabled in production.",
)
async def create_test_cab_booking(
    ctx: ShopContext = Depends(get_shop_context_from_slug),
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    """
    Create a test cab booking for development/testing.
    
    This endpoint:
    - Only works in development mode (when DEV_MODE env is set)
    - Requires owner/manager authentication
    - Creates a PENDING booking with mock data
    """
    # Check if dev mode is enabled
    dev_mode = os.getenv("DEV_MODE", "").lower() in ("true", "1", "yes")
    if not dev_mode:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Test endpoints disabled in production. Set DEV_MODE=true to enable.",
        )
    
    await require_owner_or_manager(ctx, user_id, session)
    
    # Get or create default pricing rule
    from .cab_booking import get_or_create_default_pricing_rule
    pricing_rule = await get_or_create_default_pricing_rule(session, ctx.shop_id)
    
    # Create test booking with mock data
    from datetime import timedelta
    import uuid
    from decimal import Decimal
    
    test_booking = CabBooking(
        id=uuid.uuid4(),
        shop_id=ctx.shop_id,
        channel=CabBookingChannel.WEB,
        pickup_text="123 Main St, Test City, AZ 85001",
        drop_text="Phoenix Sky Harbor International Airport (PHX), Phoenix, AZ",
        pickup_time=datetime.utcnow() + timedelta(days=1, hours=10),
        vehicle_type=CabVehicleType.SEDAN_4,
        passengers=2,
        luggage=2,
        customer_name="Test Customer",
        customer_email="test@example.com",
        customer_phone="+16025551234",
        distance_miles=Decimal("15.5"),
        duration_minutes=25,
        per_mile_rate_snapshot=pricing_rule.per_mile_rate,
        rounding_step_snapshot=pricing_rule.rounding_step,
        minimum_fare_snapshot=pricing_rule.minimum_fare,
        vehicle_multiplier_snapshot=Decimal("1.0"),
        raw_price=Decimal("65.00"),
        final_price=Decimal("65.00"),
        status=CabBookingStatus.PENDING,
        notes="[DEV TEST] Auto-generated test booking",
    )
    
    session.add(test_booking)
    await session.commit()
    await session.refresh(test_booking)
    
    logger.info(f"Created test booking {test_booking.id} for shop={ctx.shop_slug}")
    
    return booking_to_response(test_booking)


# ────────────────────────────────────────────────────────────────
# OWNER CAB MANAGEMENT ENDPOINTS (Authenticated)
# ────────────────────────────────────────────────────────────────

class CabBookingListResponse(BaseModel):
    """Response for listing cab bookings."""
    items: list[CabBookingListItem]
    total: int
    page: int
    page_size: int


class PriceOverrideRequest(BaseModel):
    """Request to override a booking's price."""
    price: float = Field(..., ge=0, description="New price in dollars")
    reason: str | None = Field(None, max_length=500, description="Reason for override")


class CabBookingActionResponse(BaseModel):
    """Response for confirm/reject actions."""
    success: bool
    booking_id: str
    status: str
    message: str


@router.get(
    "/owner/cab/requests",
    response_model=CabBookingListResponse,
    tags=["cab-owner"],
    summary="List cab booking requests",
    description="Get paginated list of PENDING cab booking requests for owner review.",
)
async def list_cab_requests(
    ctx: ShopContext = Depends(get_shop_context_from_slug),
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """
    List all PENDING cab booking requests for owner/manager review.
    
    Requires OWNER or MANAGER role.
    """
    await require_owner_or_manager(ctx, user_id, session)
    
    # Count total
    count_result = await session.execute(
        select(func.count(CabBooking.id)).where(
            CabBooking.shop_id == ctx.shop_id,
            CabBooking.status == CabBookingStatus.PENDING,
        )
    )
    total = count_result.scalar() or 0
    
    # Get paginated results
    offset = (page - 1) * page_size
    result = await session.execute(
        select(CabBooking)
        .options(joinedload(CabBooking.assigned_driver))
        .where(
            CabBooking.shop_id == ctx.shop_id,
            CabBooking.status == CabBookingStatus.PENDING,
        )
        .order_by(CabBooking.pickup_time.asc())
        .offset(offset)
        .limit(page_size)
    )
    bookings = result.scalars().all()
    
    return CabBookingListResponse(
        items=[booking_to_list_item(b) for b in bookings],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/owner/cab/requests/{booking_id}",
    response_model=CabBookingDetailResponse,
    tags=["cab-owner"],
    summary="Get cab request details",
    description="Get detailed information about a cab booking request.",
)
async def get_cab_request(
    booking_id: str,
    ctx: ShopContext = Depends(get_shop_context_from_slug),
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    """
    Get details of a specific cab booking request for owner review.
    
    Requires OWNER or MANAGER role.
    """
    await require_owner_or_manager(ctx, user_id, session)
    
    from uuid import UUID
    
    try:
        booking_uuid = UUID(booking_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid booking ID format",
        )
    
    result = await session.execute(
        select(CabBooking).where(
            CabBooking.id == booking_uuid,
            CabBooking.shop_id == ctx.shop_id,
        )
    )
    booking = result.scalar_one_or_none()
    
    if not booking:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Booking not found",
        )
    
    return booking_to_detail_response(booking)


@router.post(
    "/owner/cab/requests/{booking_id}/override-price",
    response_model=CabBookingDetailResponse,
    tags=["cab-owner"],
    summary="Override booking price",
    description="Override the calculated price for a PENDING cab booking.",
)
async def override_cab_price(
    booking_id: str,
    request: PriceOverrideRequest,
    ctx: ShopContext = Depends(get_shop_context_from_slug),
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    """
    Override the price for a PENDING booking.
    
    Requires OWNER or MANAGER role. Can only override PENDING bookings.
    """
    await require_owner_or_manager(ctx, user_id, session)
    
    from uuid import UUID
    
    try:
        booking_uuid = UUID(booking_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid booking ID format",
        )
    
    result = await session.execute(
        select(CabBooking).where(
            CabBooking.id == booking_uuid,
            CabBooking.shop_id == ctx.shop_id,
        )
    )
    booking = result.scalar_one_or_none()
    
    if not booking:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Booking not found",
        )
    
    if not booking.can_override_price():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot override price for booking with status {booking.status.value}",
        )
    
    # Store original price if not already overridden
    if booking.price_override is None:
        booking.original_price = booking.final_price
    
    booking.price_override = request.price
    booking.final_price = request.price
    
    await session.commit()
    await session.refresh(booking)
    
    logger.info(
        f"Price overridden for cab booking {booking.id}: "
        f"${booking.original_price} -> ${request.price} by user {user_id}"
    )
    
    return booking_to_detail_response(booking)


@router.post(
    "/owner/cab/requests/{booking_id}/confirm",
    response_model=CabBookingActionResponse,
    tags=["cab-owner"],
    summary="Confirm cab booking",
    description="Confirm a PENDING cab booking request.",
)
async def confirm_cab_booking(
    booking_id: str,
    ctx: ShopContext = Depends(get_shop_context_from_slug),
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    """
    Confirm a PENDING cab booking.
    
    Requires OWNER or MANAGER role.
    """
    await require_owner_or_manager(ctx, user_id, session)
    
    from uuid import UUID
    
    try:
        booking_uuid = UUID(booking_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid booking ID format",
        )
    
    result = await session.execute(
        select(CabBooking).where(
            CabBooking.id == booking_uuid,
            CabBooking.shop_id == ctx.shop_id,
        )
    )
    booking = result.scalar_one_or_none()
    
    if not booking:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Booking not found",
        )
    
    if not booking.can_confirm():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot confirm booking with status {booking.status.value}",
        )
    
    booking.status = CabBookingStatus.CONFIRMED
    booking.confirmed_at = datetime.utcnow()
    booking.confirmed_by = user_id
    
    await session.commit()
    
    logger.info(f"Cab booking {booking.id} confirmed by user {user_id}")
    
    # Send WhatsApp confirmation to customer
    try:
        from .whatsapp import send_whatsapp_message, format_owner_confirmation_message
        
        if booking.customer_phone:
            confirmation_msg = format_owner_confirmation_message(
                booking_id=str(booking.id),
                pickup_text=booking.pickup_text,
                drop_text=booking.drop_text,
                pickup_time=booking.pickup_time.isoformat(),
                final_price=booking.final_price,
            )
            send_whatsapp_message(booking.customer_phone, confirmation_msg)
            logger.info(f"✅ WhatsApp confirmation sent to {booking.customer_phone}")
    except Exception as e:
        logger.error(f"Failed to send WhatsApp confirmation: {e}")
    
    return CabBookingActionResponse(
        success=True,
        booking_id=str(booking.id),
        status=booking.status.value,
        message="Booking confirmed successfully",
    )


@router.post(
    "/owner/cab/requests/{booking_id}/reject",
    response_model=CabBookingActionResponse,
    tags=["cab-owner"],
    summary="Reject cab booking",
    description="Reject a PENDING cab booking request.",
)
async def reject_cab_booking(
    booking_id: str,
    reason: str | None = None,
    ctx: ShopContext = Depends(get_shop_context_from_slug),
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    """
    Reject a PENDING cab booking.
    
    Requires OWNER or MANAGER role.
    """
    await require_owner_or_manager(ctx, user_id, session)
    
    from uuid import UUID
    
    try:
        booking_uuid = UUID(booking_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid booking ID format",
        )
    
    result = await session.execute(
        select(CabBooking).where(
            CabBooking.id == booking_uuid,
            CabBooking.shop_id == ctx.shop_id,
        )
    )
    booking = result.scalar_one_or_none()
    
    if not booking:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Booking not found",
        )
    
    if not booking.can_reject():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot reject booking with status {booking.status.value}",
        )
    
    booking.status = CabBookingStatus.REJECTED
    booking.rejected_at = datetime.utcnow()
    booking.rejected_by = user_id
    booking.rejection_reason = reason
    
    await session.commit()
    
    logger.info(f"Cab booking {booking.id} rejected by user {user_id}: {reason}")
    
    # Send WhatsApp notification to customer
    if booking.customer_phone:
        try:
            from .whatsapp import send_whatsapp_message, format_rejection_notification
            
            customer_number = booking.customer_phone
            if not customer_number.startswith('whatsapp:'):
                customer_number = f'whatsapp:{customer_number}'
            
            rejection_msg = format_rejection_notification(
                booking_id=str(booking.id),
                pickup_text=booking.pickup_text,
                drop_text=booking.drop_text,
                reason=reason,
            )
            send_whatsapp_message(customer_number, rejection_msg)
            logger.info(f"✅ WhatsApp rejection notice sent to {customer_number}")
        except Exception as e:
            logger.error(f"Failed to send rejection WhatsApp: {e}")
    
    return CabBookingActionResponse(
        success=True,
        booking_id=str(booking.id),
        status=booking.status.value,
        message="Booking rejected",
    )


@router.get(
    "/owner/cab/rides",
    response_model=CabBookingListResponse,
    tags=["cab-owner"],
    summary="List confirmed cab rides",
    description="Get paginated list of CONFIRMED cab rides for the owner dashboard.",
)
async def list_cab_rides(
    ctx: ShopContext = Depends(get_shop_context_from_slug),
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    upcoming_only: bool = Query(False, description="Only show rides with future pickup times"),
):
    """
    List all CONFIRMED cab rides.
    
    Requires OWNER or MANAGER role.
    """
    await require_owner_or_manager(ctx, user_id, session)
    
    # Build query with joined driver relationship
    query = select(CabBooking).options(
        joinedload(CabBooking.assigned_driver)
    ).where(
        CabBooking.shop_id == ctx.shop_id,
        CabBooking.status == CabBookingStatus.CONFIRMED,
    )
    
    count_query = select(func.count(CabBooking.id)).where(
        CabBooking.shop_id == ctx.shop_id,
        CabBooking.status == CabBookingStatus.CONFIRMED,
    )
    
    if upcoming_only:
        now = datetime.utcnow()
        query = query.where(CabBooking.pickup_time > now)
        count_query = count_query.where(CabBooking.pickup_time > now)
    
    # Count total
    count_result = await session.execute(count_query)
    total = count_result.scalar() or 0
    
    # Get paginated results
    offset = (page - 1) * page_size
    result = await session.execute(
        query.order_by(CabBooking.pickup_time.asc())
        .offset(offset)
        .limit(page_size)
    )
    bookings = result.scalars().all()
    
    return CabBookingListResponse(
        items=[booking_to_list_item(b) for b in bookings],
        total=total,
        page=page,
        page_size=page_size,
    )


# ============================================================================
# CAB OWNER MANAGEMENT ENDPOINTS
# ============================================================================

class CabOwnerResponse(BaseModel):
    """Response model for cab owner info."""
    id: str
    shop_id: int
    business_name: str
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    whatsapp_phone: Optional[str] = None
    is_active: bool
    created_at: datetime


class CabOwnerSetupRequest(BaseModel):
    """Request to set up cab owner for a shop."""
    business_name: str = Field(..., min_length=2, max_length=255)
    contact_email: Optional[str] = Field(default=None, max_length=255)
    contact_phone: Optional[str] = Field(default=None, max_length=32)
    whatsapp_phone: Optional[str] = Field(default=None, max_length=32)


@router.get(
    "/owner/cab/owner",
    response_model=CabOwnerResponse,
    tags=["cab-owner"],
    summary="Get cab owner for this shop",
    description="Get cab owner configuration for this shop. Returns 404 if not set up.",
)
async def get_cab_owner(
    ctx: ShopContext = Depends(get_shop_context_from_slug),
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    """Get cab owner for the shop."""
    await require_owner_or_manager(ctx, user_id, session)
    
    result = await session.execute(
        select(CabOwner).where(
            CabOwner.shop_id == ctx.shop_id,
            CabOwner.active == True,
        )
    )
    owner = result.scalar_one_or_none()
    
    if not owner:
        raise HTTPException(status_code=404, detail="Cab owner not configured for this shop")
    
    return CabOwnerResponse(
        id=str(owner.id),
        shop_id=owner.shop_id,
        business_name=owner.business_name,
        contact_email=owner.email,
        contact_phone=owner.phone,
        whatsapp_phone=owner.whatsapp_phone,
        is_active=owner.active,
        created_at=owner.created_at,
    )


@router.post(
    "/owner/cab/setup",
    response_model=CabOwnerResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["cab-owner"],
    summary="Set up cab owner for this shop",
    description="Create or update cab owner configuration for this shop.",
)
async def setup_cab_owner(
    request: CabOwnerSetupRequest,
    ctx: ShopContext = Depends(get_shop_context_from_slug),
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    """Create or update cab owner for the shop."""
    await require_owner_or_manager(ctx, user_id, session)
    
    # Check if owner already exists
    result = await session.execute(
        select(CabOwner).where(CabOwner.shop_id == ctx.shop_id)
    )
    existing = result.scalar_one_or_none()
    
    if existing:
        # Update existing
        existing.business_name = request.business_name
        existing.email = request.contact_email
        existing.phone = request.contact_phone
        existing.whatsapp_phone = request.whatsapp_phone
        existing.active = True
        owner = existing
    else:
        # Create new
        owner = CabOwner(
            shop_id=ctx.shop_id,
            business_name=request.business_name,
            email=request.contact_email,
            phone=request.contact_phone,
            whatsapp_phone=request.whatsapp_phone,
        )
        session.add(owner)
    
    await session.commit()
    await session.refresh(owner)
    
    logger.info(f"Cab owner set up for shop={ctx.shop_slug}: {owner.business_name}")
    
    return CabOwnerResponse(
        id=str(owner.id),
        shop_id=owner.shop_id,
        business_name=owner.business_name,
        contact_email=owner.email,
        contact_phone=owner.phone,
        whatsapp_phone=owner.whatsapp_phone,
        is_active=owner.active,
        created_at=owner.created_at,
    )


# ============================================================================
# CAB PRICING MANAGEMENT ENDPOINTS
# ============================================================================

class CabPricingResponse(BaseModel):
    """Response model for pricing rule."""
    id: int
    shop_id: int
    per_mile_rate: float
    rounding_step: float
    minimum_fare: float
    currency: str
    vehicle_multipliers: dict
    active: bool


class UpdatePricingRateRequest(BaseModel):
    """Request to update per-mile rate."""
    per_mile_rate: float = Field(..., ge=0.5, le=50.0, description="Rate per mile in dollars")


@router.get(
    "/owner/cab/pricing",
    response_model=CabPricingResponse,
    tags=["cab-owner"],
    summary="Get cab pricing rule",
    description="Get the current pricing configuration for this shop's cab service.",
)
async def get_cab_pricing(
    ctx: ShopContext = Depends(get_shop_context_from_slug),
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    """Get pricing rule for the shop."""
    await require_owner_or_manager(ctx, user_id, session)
    
    result = await session.execute(
        select(CabPricingRule).where(
            CabPricingRule.shop_id == ctx.shop_id,
            CabPricingRule.active == True,
        )
    )
    pricing_rule = result.scalar_one_or_none()
    
    if not pricing_rule:
        raise HTTPException(status_code=404, detail="Pricing rule not configured for this shop")
    
    return CabPricingResponse(
        id=pricing_rule.id,
        shop_id=pricing_rule.shop_id,
        per_mile_rate=float(pricing_rule.per_mile_rate),
        rounding_step=float(pricing_rule.rounding_step),
        minimum_fare=float(pricing_rule.minimum_fare),
        currency=pricing_rule.currency,
        vehicle_multipliers=pricing_rule.vehicle_multipliers,
        active=pricing_rule.active,
    )


@router.patch(
    "/owner/cab/pricing/rate",
    response_model=CabPricingResponse,
    tags=["cab-owner"],
    summary="Update per-mile rate",
    description="Update the per-mile rate for cab pricing. This will apply to new bookings.",
)
async def update_per_mile_rate(
    request: UpdatePricingRateRequest,
    ctx: ShopContext = Depends(get_shop_context_from_slug),
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    """Update per-mile rate for the shop's cab service."""
    await require_owner_or_manager(ctx, user_id, session)
    
    from decimal import Decimal
    
    # Get existing pricing rule
    result = await session.execute(
        select(CabPricingRule).where(
            CabPricingRule.shop_id == ctx.shop_id,
            CabPricingRule.active == True,
        )
    )
    pricing_rule = result.scalar_one_or_none()
    
    if not pricing_rule:
        raise HTTPException(status_code=404, detail="Pricing rule not configured for this shop")
    
    # Update the rate
    old_rate = float(pricing_rule.per_mile_rate)
    pricing_rule.per_mile_rate = Decimal(str(request.per_mile_rate))
    
    await session.commit()
    await session.refresh(pricing_rule)
    
    logger.info(
        f"Per-mile rate updated for shop={ctx.shop_slug}: "
        f"${old_rate:.2f} -> ${request.per_mile_rate:.2f} by user {user_id}"
    )
    
    return CabPricingResponse(
        id=pricing_rule.id,
        shop_id=pricing_rule.shop_id,
        per_mile_rate=float(pricing_rule.per_mile_rate),
        rounding_step=float(pricing_rule.rounding_step),
        minimum_fare=float(pricing_rule.minimum_fare),
        currency=pricing_rule.currency,
        vehicle_multipliers=pricing_rule.vehicle_multipliers,
        active=pricing_rule.active,
    )


# ============================================================================
# CAB DRIVER MANAGEMENT ENDPOINTS
# ============================================================================

class CabDriverResponse(BaseModel):
    """Response model for driver info."""
    id: str
    name: str
    phone: str
    whatsapp_phone: Optional[str] = None
    status: str
    created_at: datetime


class CabDriverListResponse(BaseModel):
    """Response for driver list."""
    items: list[CabDriverResponse]
    total: int


class CabDriverCreateRequest(BaseModel):
    """Request to create a driver."""
    name: str = Field(..., min_length=2, max_length=255)
    phone: str = Field(..., min_length=5, max_length=32)
    whatsapp_phone: Optional[str] = Field(default=None, max_length=32)


class CabDriverUpdateRequest(BaseModel):
    """Request to update a driver."""
    name: Optional[str] = Field(default=None, min_length=2, max_length=255)
    phone: Optional[str] = Field(default=None, min_length=5, max_length=32)
    whatsapp_phone: Optional[str] = Field(default=None, max_length=32)
    status: Optional[str] = Field(default=None)


@router.get(
    "/owner/cab/drivers",
    response_model=CabDriverListResponse,
    tags=["cab-owner"],
    summary="List cab drivers",
    description="Get list of cab drivers for this shop.",
)
async def list_cab_drivers(
    ctx: ShopContext = Depends(get_shop_context_from_slug),
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    """List all drivers for this shop's cab owner."""
    await require_owner_or_manager(ctx, user_id, session)
    
    # Get cab owner
    result = await session.execute(
        select(CabOwner).where(
            CabOwner.shop_id == ctx.shop_id,
            CabOwner.active == True,
        )
    )
    owner = result.scalar_one_or_none()
    
    if not owner:
        raise HTTPException(status_code=404, detail="Cab owner not configured")
    
    # Get drivers
    result = await session.execute(
        select(CabDriver).where(CabDriver.cab_owner_id == owner.id)
        .order_by(CabDriver.created_at.desc())
    )
    drivers = result.scalars().all()
    
    return CabDriverListResponse(
        items=[
            CabDriverResponse(
                id=str(d.id),
                name=d.name,
                phone=d.phone,
                whatsapp_phone=d.whatsapp_phone,
                status=d.status.value,
                created_at=d.created_at,
            )
            for d in drivers
        ],
        total=len(drivers),
    )


@router.post(
    "/owner/cab/drivers",
    response_model=CabDriverResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["cab-owner"],
    summary="Add a cab driver",
    description="Add a new driver to this shop's cab service.",
)
async def create_cab_driver(
    request: CabDriverCreateRequest,
    ctx: ShopContext = Depends(get_shop_context_from_slug),
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    """Create a new driver."""
    await require_owner_or_manager(ctx, user_id, session)
    
    # Get cab owner
    result = await session.execute(
        select(CabOwner).where(
            CabOwner.shop_id == ctx.shop_id,
            CabOwner.active == True,
        )
    )
    owner = result.scalar_one_or_none()
    
    if not owner:
        raise HTTPException(status_code=404, detail="Cab owner not configured")
    
    driver = CabDriver(
        cab_owner_id=owner.id,
        name=request.name,
        phone=request.phone,
        whatsapp_phone=request.whatsapp_phone,
    )
    session.add(driver)
    await session.commit()
    await session.refresh(driver)
    
    logger.info(f"Driver added for shop={ctx.shop_slug}: {driver.name}")
    
    return CabDriverResponse(
        id=str(driver.id),
        name=driver.name,
        phone=driver.phone,
        whatsapp_phone=driver.whatsapp_phone,
        status=driver.status.value,
        created_at=driver.created_at,
    )


@router.patch(
    "/owner/cab/drivers/{driver_id}",
    response_model=CabDriverResponse,
    tags=["cab-owner"],
    summary="Update a cab driver",
    description="Update driver info or status.",
)
async def update_cab_driver(
    driver_id: int = Path(..., description="Driver ID"),
    request: CabDriverUpdateRequest = ...,
    ctx: ShopContext = Depends(get_shop_context_from_slug),
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    """Update a driver."""
    await require_owner_or_manager(ctx, user_id, session)
    
    # Get cab owner
    result = await session.execute(
        select(CabOwner).where(
            CabOwner.shop_id == ctx.shop_id,
            CabOwner.active == True,
        )
    )
    owner = result.scalar_one_or_none()
    
    if not owner:
        raise HTTPException(status_code=404, detail="Cab owner not configured")
    
    # Get driver (ensure it belongs to this owner)
    result = await session.execute(
        select(CabDriver).where(
            CabDriver.id == driver_id,
            CabDriver.cab_owner_id == owner.id,
        )
    )
    driver = result.scalar_one_or_none()
    
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")
    
    # Update fields
    if request.name is not None:
        driver.name = request.name
    if request.phone is not None:
        driver.phone = request.phone
    if request.whatsapp_phone is not None:
        driver.whatsapp_phone = request.whatsapp_phone
    if request.status is not None:
        driver.status = CabDriverStatus(request.status)
    
    await session.commit()
    await session.refresh(driver)
    
    logger.info(f"Driver updated for shop={ctx.shop_slug}: {driver.name}")
    
    return CabDriverResponse(
        id=str(driver.id),
        name=driver.name,
        phone=driver.phone,
        whatsapp_phone=driver.whatsapp_phone,
        status=driver.status.value,
        created_at=driver.created_at,
    )


@router.get(
    "/owner/cab/drivers/{driver_id}/bookings",
    response_model=CabBookingListResponse,
    tags=["cab-owner"],
    summary="Get driver's bookings",
    description="Get all bookings assigned to a specific driver.",
)
async def get_driver_bookings(
    driver_id: int = Path(..., description="Driver ID"),
    ctx: ShopContext = Depends(get_shop_context_from_slug),
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
    upcoming_only: bool = Query(False, description="Only show upcoming bookings"),
):
    """Get all bookings for a specific driver."""
    await require_owner_or_manager(ctx, user_id, session)
    
    # Verify driver exists
    result = await session.execute(
        select(CabDriver).where(
            CabDriver.id == driver_id,
        )
    )
    driver = result.scalar_one_or_none()
    
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")
    
    # Build query for driver's bookings
    query = select(CabBooking).options(
        joinedload(CabBooking.assigned_driver)
    ).where(
        CabBooking.shop_id == ctx.shop_id,
        CabBooking.assigned_driver_id == driver_id,
        CabBooking.status == CabBookingStatus.CONFIRMED,
    )
    
    if upcoming_only:
        now = datetime.utcnow()
        query = query.where(CabBooking.pickup_time > now)
    
    # Order by pickup time
    query = query.order_by(CabBooking.pickup_time.asc())
    
    result = await session.execute(query)
    bookings = result.scalars().all()
    
    return CabBookingListResponse(
        items=[booking_to_list_item(b) for b in bookings],
        total=len(bookings),
        page=1,
        page_size=len(bookings),
    )


# ============================================================================
# DRIVER ASSIGNMENT ENDPOINT
# ============================================================================

class AssignDriverRequest(BaseModel):
    """Request to assign a driver to a booking."""
    driver_id: str


class AssignDriverResponse(BaseModel):
    """Response after assigning driver."""
    booking_id: str
    status: str
    assigned_driver_id: str
    assigned_driver: CabDriverResponse
    assigned_at: datetime


@router.post(
    "/owner/cab/requests/{booking_id}/assign-driver",
    response_model=AssignDriverResponse,
    tags=["cab-owner"],
    summary="Assign driver to booking",
    description="Assign a driver to a confirmed cab booking.",
)
async def assign_driver_to_booking(
    booking_id: str = Path(..., description="Booking UUID"),
    request: AssignDriverRequest = ...,
    ctx: ShopContext = Depends(get_shop_context_from_slug),
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    """Assign a driver to a booking."""
    await require_owner_or_manager(ctx, user_id, session)
    
    from uuid import UUID
    try:
        booking_uuid = UUID(booking_id)
        # Driver ID is an integer, not a UUID
        driver_id = int(request.driver_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid booking or driver ID")
    
    # Get booking
    result = await session.execute(
        select(CabBooking).where(
            CabBooking.id == booking_uuid,
            CabBooking.shop_id == ctx.shop_id,
        )
    )
    booking = result.scalar_one_or_none()
    
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    
    if booking.status != CabBookingStatus.CONFIRMED:
        raise HTTPException(status_code=400, detail="Can only assign driver to confirmed bookings")
    
    # Get cab owner
    result = await session.execute(
        select(CabOwner).where(
            CabOwner.shop_id == ctx.shop_id,
            CabOwner.active == True,
        )
    )
    owner = result.scalar_one_or_none()
    
    if not owner:
        raise HTTPException(status_code=404, detail="Cab owner not configured")
    
    # Get driver (ensure belongs to this owner)
    result = await session.execute(
        select(CabDriver).where(
            CabDriver.id == driver_id,
            CabDriver.cab_owner_id == owner.id,
        )
    )
    driver = result.scalar_one_or_none()
    
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")
    
    if driver.status != CabDriverStatus.ACTIVE:
        raise HTTPException(status_code=400, detail="Driver is not active")
    
    # Assign driver
    booking.assigned_driver_id = driver.id
    booking.assigned_at = datetime.utcnow()
    
    await session.commit()
    await session.refresh(booking)
    
    logger.info(f"Driver {driver.name} assigned to booking {booking_id} for shop={ctx.shop_slug}")
    
    # Send WhatsApp notification to customer if booking was via WhatsApp
    if booking.channel == CabBookingChannel.WHATSAPP and booking.customer_phone:
        try:
            from .whatsapp import send_whatsapp_message, format_driver_assigned_message
            
            customer_number = booking.customer_phone
            if not customer_number.startswith('whatsapp:'):
                customer_number = f'whatsapp:{customer_number}'
            
            vehicle_info = f"{booking.vehicle_type.value.replace('_', ' ').title()}"
            
            message = format_driver_assigned_message(
                booking_id=str(booking.id),
                driver_name=driver.name,
                driver_phone=driver.phone or driver.whatsapp_phone or "Contact via app",
                vehicle_info=vehicle_info
            )
            
            # Add full booking details
            message += f"\n\n📍 Pickup: {booking.pickup_text}"
            message += f"\n📍 Dropoff: {booking.drop_text}"
            
            try:
                dt = booking.pickup_time
                time_display = dt.strftime("%B %d at %I:%M %p")
                message += f"\n🕐 Time: {time_display}"
            except:
                message += f"\n🕐 Time: {booking.pickup_time}"
            
            message += f"\n💵 Fare: ${booking.final_price:.2f}"
            
            send_whatsapp_message(customer_number, message)
            logger.info(f"Driver assignment WhatsApp notification sent to {customer_number}")
        except Exception as e:
            logger.error(f"Failed to send driver assignment WhatsApp: {e}")
    
    return AssignDriverResponse(
        booking_id=str(booking.id),
        status=booking.status.value,
        assigned_driver_id=str(driver.id),
        assigned_driver=CabDriverResponse(
            id=str(driver.id),
            name=driver.name,
            phone=driver.phone,
            whatsapp_phone=driver.whatsapp_phone,
            status=driver.status.value,
            created_at=driver.created_at,
        ),
        assigned_at=booking.assigned_at,
    )


# ============================================================================
# CAB OWNER SUMMARY/ANALYTICS ENDPOINT
# ============================================================================

class CabSummaryData(BaseModel):
    """Summary metrics data for cab owner dashboard."""
    total_rides: int = Field(..., description="Total number of rides in the period")
    confirmed_revenue: float = Field(..., description="Revenue from COMPLETED rides")
    upcoming_revenue: float = Field(..., description="Revenue from CONFIRMED rides with future pickup")
    avg_ride_price: float = Field(..., description="Average price of confirmed/completed rides")
    acceptance_rate: float = Field(..., description="Percentage of accepted bookings (0-100)")
    cancellation_rate: float = Field(..., description="Percentage of cancelled bookings (0-100)")


class CabSummaryResponse(BaseModel):
    """Response for cab owner summary endpoint."""
    data: CabSummaryData
    status: str = "ok"
    range_days: int = Field(..., description="Number of days in the query range")


@router.get(
    "/owner/cab/summary",
    response_model=CabSummaryResponse,
    tags=["cab-owner"],
    summary="Get cab business summary metrics",
    description="Get computed summary metrics for the cab owner dashboard (last 7 or 30 days).",
)
async def get_cab_summary(
    ctx: ShopContext = Depends(get_shop_context_from_slug),
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
    range: str = Query("7d", regex="^(7d|30d)$", description="Time range: 7d or 30d"),
):
    """
    Get computed summary metrics for the cab owner dashboard.
    
    Metrics are computed on-demand, NOT stored in the database.
    
    Requires OWNER or MANAGER role.
    
    Args:
        range: Time range filter - "7d" for last 7 days, "30d" for last 30 days
    
    Returns:
        CabSummaryResponse with computed metrics
    """
    await require_owner_or_manager(ctx, user_id, session)
    
    # Determine the date range
    range_days = 7 if range == "7d" else 30
    now = datetime.utcnow()
    start_date = now - timedelta(days=range_days)
    
    logger.info(f"Computing cab summary for shop={ctx.shop_slug}, range={range_days}d, user={user_id}")
    
    try:
        # Single efficient query to get all the metrics we need
        # Using SQL aggregation for performance
        
        from sqlalchemy import case, and_, or_
        
        # Count queries for status breakdown
        status_counts_query = select(
            func.count(CabBooking.id).label('total'),
            func.count(case((CabBooking.status == CabBookingStatus.CONFIRMED, 1))).label('confirmed_count'),
            func.count(case((CabBooking.status == CabBookingStatus.COMPLETED, 1))).label('completed_count'),
            func.count(case((CabBooking.status == CabBookingStatus.REJECTED, 1))).label('rejected_count'),
            func.count(case((CabBooking.status == CabBookingStatus.CANCELLED, 1))).label('cancelled_count'),
            func.count(case((CabBooking.status == CabBookingStatus.PENDING, 1))).label('pending_count'),
        ).where(
            CabBooking.shop_id == ctx.shop_id,
            CabBooking.created_at >= start_date,
        )
        
        status_result = await session.execute(status_counts_query)
        status_row = status_result.one()
        
        total_rides = status_row.total or 0
        confirmed_count = status_row.confirmed_count or 0
        completed_count = status_row.completed_count or 0
        rejected_count = status_row.rejected_count or 0
        cancelled_count = status_row.cancelled_count or 0
        
        # Revenue from COMPLETED rides (Confirmed Revenue)
        completed_revenue_query = select(
            func.coalesce(func.sum(CabBooking.final_price), 0).label('revenue')
        ).where(
            CabBooking.shop_id == ctx.shop_id,
            CabBooking.created_at >= start_date,
            CabBooking.status == CabBookingStatus.COMPLETED,
        )
        completed_revenue_result = await session.execute(completed_revenue_query)
        confirmed_revenue = float(completed_revenue_result.scalar() or 0)
        
        # Revenue from CONFIRMED rides with FUTURE pickup time (Upcoming Revenue)
        upcoming_revenue_query = select(
            func.coalesce(func.sum(CabBooking.final_price), 0).label('revenue')
        ).where(
            CabBooking.shop_id == ctx.shop_id,
            CabBooking.created_at >= start_date,
            CabBooking.status == CabBookingStatus.CONFIRMED,
            CabBooking.pickup_time > now,
        )
        upcoming_revenue_result = await session.execute(upcoming_revenue_query)
        upcoming_revenue = float(upcoming_revenue_result.scalar() or 0)
        
        # Average ride price for CONFIRMED and COMPLETED rides
        avg_price_query = select(
            func.avg(CabBooking.final_price).label('avg_price')
        ).where(
            CabBooking.shop_id == ctx.shop_id,
            CabBooking.created_at >= start_date,
            or_(
                CabBooking.status == CabBookingStatus.CONFIRMED,
                CabBooking.status == CabBookingStatus.COMPLETED,
            ),
            CabBooking.final_price.isnot(None),
        )
        avg_price_result = await session.execute(avg_price_query)
        avg_ride_price = float(avg_price_result.scalar() or 0)
        
        # Calculate acceptance rate
        # Formula: (confirmed + completed) / total_requests * 100
        # Where total_requests = total rides that had a decision made (not pending)
        total_requests = total_rides  # All bookings that came in
        accepted_count = confirmed_count + completed_count
        
        if total_requests > 0:
            acceptance_rate = (accepted_count / total_requests) * 100
        else:
            acceptance_rate = 0.0
        
        # Calculate cancellation rate
        # Formula: cancelled / total_requests * 100
        if total_requests > 0:
            cancellation_rate = (cancelled_count / total_requests) * 100
        else:
            cancellation_rate = 0.0
        
        logger.info(
            f"Cab summary computed for shop={ctx.shop_slug}: "
            f"total={total_rides}, confirmed_revenue=${confirmed_revenue:.2f}, "
            f"upcoming=${upcoming_revenue:.2f}, avg=${avg_ride_price:.2f}, "
            f"accept={acceptance_rate:.1f}%, cancel={cancellation_rate:.1f}%"
        )
        
        return CabSummaryResponse(
            data=CabSummaryData(
                total_rides=total_rides,
                confirmed_revenue=round(confirmed_revenue, 2),
                upcoming_revenue=round(upcoming_revenue, 2),
                avg_ride_price=round(avg_ride_price, 2),
                acceptance_rate=round(acceptance_rate, 1),
                cancellation_rate=round(cancellation_rate, 1),
            ),
            status="ok",
            range_days=range_days,
        )
        
    except Exception as e:
        logger.error(f"Error computing cab summary for shop={ctx.shop_slug}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to compute summary: {str(e)}"
        )


# ============================================================================
# MARK RIDE AS COMPLETED ENDPOINT
# ============================================================================

class CompleteRideResponse(BaseModel):
    """Response after marking a ride as completed."""
    booking_id: str
    status: str
    completed_at: datetime
    message: str


@router.post(
    "/owner/cab/rides/{booking_id}/complete",
    response_model=CompleteRideResponse,
    tags=["cab-owner"],
    summary="Mark ride as completed",
    description="Mark a CONFIRMED cab ride as COMPLETED after the trip is done.",
)
async def complete_cab_ride(
    booking_id: str = Path(..., description="Booking UUID"),
    ctx: ShopContext = Depends(get_shop_context_from_slug),
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    """
    Mark a cab ride as COMPLETED.
    
    Can only complete CONFIRMED rides.
    
    Requires OWNER or MANAGER role.
    """
    await require_owner_or_manager(ctx, user_id, session)
    
    from uuid import UUID
    try:
        booking_uuid = UUID(booking_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid booking ID format"
        )
    
    # Fetch booking
    result = await session.execute(
        select(CabBooking).where(
            CabBooking.id == booking_uuid,
            CabBooking.shop_id == ctx.shop_id,
        )
    )
    booking = result.scalar_one_or_none()
    
    if not booking:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Booking not found"
        )
    
    if booking.status != CabBookingStatus.CONFIRMED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot complete a {booking.status.value} booking. Only CONFIRMED rides can be completed."
        )
    
    # Mark as completed
    booking.status = CabBookingStatus.COMPLETED
    completed_at = datetime.utcnow()
    booking.updated_at = completed_at
    
    await session.commit()
    
    logger.info(f"Ride {booking_id} marked as COMPLETED for shop={ctx.shop_slug} by user={user_id}")
    
    return CompleteRideResponse(
        booking_id=str(booking.id),
        status=booking.status.value,
        completed_at=completed_at,
        message="Ride marked as completed",
    )


@router.post(
    "/cab/cancel",
    response_model=CabBookingActionResponse,
    tags=["cab-customer"],
    summary="Customer cancel ride",
    description="Allow customer to cancel their own ride via phone number authentication.",
)
async def customer_cancel_ride(
    booking_id: str,
    customer_phone: str,
    ctx: ShopContext = Depends(get_shop_context_from_slug),
    session: AsyncSession = Depends(get_session),
):
    """
    Customer self-service cancellation endpoint.
    
    Validates that the phone number matches the booking.
    Only allows cancellation of PENDING or CONFIRMED rides.
    """
    from uuid import UUID
    
    try:
        booking_uuid = UUID(booking_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid booking ID format",
        )
    
    # Normalize phone number
    normalized_phone = customer_phone.strip()
    if normalized_phone.startswith('whatsapp:'):
        normalized_phone = normalized_phone.replace('whatsapp:', '')
    if not normalized_phone.startswith('+'):
        normalized_phone = f'+{normalized_phone}'
    
    result = await session.execute(
        select(CabBooking).where(
            CabBooking.id == booking_uuid,
            CabBooking.shop_id == ctx.shop_id,
        )
    )
    booking = result.scalar_one_or_none()
    
    if not booking:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Booking not found",
        )
    
    # Verify customer owns this booking
    booking_phone = booking.customer_phone.strip()
    if booking_phone.startswith('whatsapp:'):
        booking_phone = booking_phone.replace('whatsapp:', '')
    if not booking_phone.startswith('+'):
        booking_phone = f'+{booking_phone}'
    
    if booking_phone != normalized_phone:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Phone number does not match booking",
        )
    
    # Check if booking can be cancelled
    if booking.status not in [CabBookingStatus.PENDING, CabBookingStatus.CONFIRMED]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot cancel a {booking.status.value} booking",
        )
    
    # Cancel the booking
    booking.status = CabBookingStatus.CANCELLED
    booking.cancelled_at = datetime.utcnow()
    booking.cancelled_by = f"customer:{normalized_phone}"
    
    await session.commit()
    
    logger.info(f"Cab booking {booking.id} cancelled by customer {normalized_phone}")
    
    # Notify owner/shop about cancellation
    try:
        # Parse pickup time for display
        try:
            if hasattr(booking.pickup_time, 'strftime'):
                time_display = booking.pickup_time.strftime("%B %d at %I:%M %p")
            else:
                dt = datetime.fromisoformat(str(booking.pickup_time).replace('Z', '+00:00'))
                time_display = dt.strftime("%B %d at %I:%M %p")
        except:
            time_display = str(booking.pickup_time)
        
        # Log detailed notification (in production, send email/SMS to shop owner)
        logger.warning(
            f"🔔 OWNER ALERT: Customer cancelled booking!\n"
            f"   Booking ID: {booking.id}\n"
            f"   Customer: {booking.customer_name} ({booking.customer_phone})\n"
            f"   Route: {booking.pickup_text} → {booking.drop_text}\n"
            f"   Pickup Time: {time_display}\n"
            f"   Fare: ${booking.final_price:.2f}\n"
            f"   Shop: {ctx.shop_slug}"
        )
        
        # TODO: Send actual notification via email/SMS to shop owner
        # Example: await send_email(shop_owner_email, subject, body)
        # Example: send_sms(shop_owner_phone, message)
        
    except Exception as e:
        logger.error(f"Failed to notify owner of cancellation: {e}")
    
    return CabBookingActionResponse(
        success=True,
        booking_id=str(booking.id),
        status=booking.status.value,
        message="Ride cancelled successfully",
    )


# ============================================================================
# PUBLIC CAB BOOKING (for customer-facing page)
# ============================================================================

@router.post(
    "/cab/book",
    response_model=CabBookingResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["cab-booking"],
    summary="Create a cab booking (public)",
    description="Public endpoint for customers to create cab bookings.",
)
async def create_public_cab_booking(
    request: CabBookingCreateRequest,
    ctx: ShopContext = Depends(get_shop_context_from_slug),
    session: AsyncSession = Depends(get_session),
):
    """
    Create a cab booking from public booking page.
    
    This is the same as /cab/bookings but more semantically named
    for the public booking flow.
    """
    logger.info(
        f"Public cab booking for shop={ctx.shop_slug}: "
        f"{request.pickup_text} -> {request.drop_text}"
    )
    
    try:
        # Get pricing rule (creates default if none exists)
        pricing_rule = await get_pricing_rule_for_shop(session, ctx.shop_id)
        
        # Calculate route and price
        calc_result = await calculate_route_and_price(
            pickup_text=request.pickup_text,
            drop_text=request.drop_text,
            pricing_rule=pricing_rule,
            vehicle_type=request.vehicle_type,
        )
        
        # Create booking record
        booking = await create_cab_booking_record(
            session=session,
            shop_id=ctx.shop_id,
            request=request,
            calc_result=calc_result,
        )
        
        # Send notification (non-blocking)
        try:
            from .cab_notifications import notify_owner_new_booking
            await notify_owner_new_booking(session, booking)
        except Exception as e:
            logger.warning(f"Failed to send booking notification: {e}")
        
        return booking_to_response(booking, calc_result.get("pricing_breakdown"))
        
    except RouteError as e:
        logger.warning(f"Route calculation failed: {e.message}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Route calculation failed: {e.message}"
        )
    except Exception as e:
        logger.exception(f"Cab booking error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create booking. Please try again."
        )


# ────────────────────────────────────────────────────────────────
# WhatsApp Webhook (Twilio Integration)
# ────────────────────────────────────────────────────────────────

@router.post(
    "/webhook/whatsapp",
    tags=["whatsapp"],
    summary="WhatsApp webhook for cab bookings",
    description="Receives incoming WhatsApp messages from Twilio for cab booking requests.",
)
async def whatsapp_webhook(
    ctx: ShopContext = Depends(get_shop_context_from_slug),
    session: AsyncSession = Depends(get_session),
    Body: str = Form(...),
    From: str = Form(...),
    MessageSid: Optional[str] = Form(None),
):
    """
    Twilio WhatsApp webhook endpoint.
    
    Handles incoming customer messages for cab bookings and cancellations.
    
    Flow:
    1. Parse message to extract booking details OR detect cancel intent
    2. If cancel: Show list of rides, handle selection
    3. If booking: Calculate route and price
    4. Send price quote to customer
    5. Create booking (auto-confirm for now)
    6. Send confirmation message
    
    Twilio sends form-encoded data:
    - From: Customer's WhatsApp number (e.g., whatsapp:+1234567890)
    - Body: Message text
    - MessageSid: Unique message ID
    """
    from .whatsapp import (
        parse_booking_request,
        BookingParseError,
        format_price_quote,
        format_booking_confirmation,
        format_error_message,
        send_whatsapp_message,
        get_help_message,
        format_ride_selection_list,
        format_no_rides_to_cancel,
        format_cancellation_confirmation,
    )
    from .whatsapp_ai import parse_booking_with_ai, detect_cancel_intent
    from .whatsapp_session import get_session as get_whatsapp_session, set_session, clear_session
    from .cab_booking import (
        get_pricing_rule_for_shop,
        calculate_route_and_price,
        create_cab_booking_record,
        RouteError,
    )
    
    logger.info(f"📱 WhatsApp message from {From} to shop {ctx.shop_slug}: {Body}")
    
    message_body = Body.strip()
    customer_number = From  # Format: whatsapp:+1234567890
    
    # Normalize phone for lookups
    normalized_phone = customer_number.replace('whatsapp:', '')
    if not normalized_phone.startswith('+'):
        normalized_phone = f'+{normalized_phone}'
    
    # Check if customer has an active session (e.g., selecting ride to cancel)
    whatsapp_session = get_whatsapp_session(customer_number)
    
    if whatsapp_session and whatsapp_session.get('state') == 'awaiting_cancel_selection':
        # Customer is selecting which ride to cancel
        try:
            # Extract number from message
            selection = message_body.strip()
            
            if selection.upper() == 'CANCEL':
                clear_session(customer_number)
                send_whatsapp_message(customer_number, "❌ Cancellation aborted.")
                return {"status": "cancel_aborted"}
            
            # Try to parse as number
            ride_index = int(selection) - 1
            bookings = whatsapp_session.get('data', {}).get('bookings', [])
            
            if ride_index < 0 or ride_index >= len(bookings):
                send_whatsapp_message(
                    customer_number,
                    f"Invalid selection. Please reply with a number between 1 and {len(bookings)}, or 'CANCEL' to abort."
                )
                return {"status": "invalid_selection"}
            
            # Get the selected booking
            selected_booking_data = bookings[ride_index]
            booking_id = selected_booking_data['id']
            
            # Cancel the booking via the endpoint
            result = await session.execute(
                select(CabBooking).where(
                    CabBooking.id == booking_id,
                    CabBooking.shop_id == ctx.shop_id,
                )
            )
            booking = result.scalar_one_or_none()
            
            if not booking:
                clear_session(customer_number)
                send_whatsapp_message(customer_number, "❌ Booking not found.")
                return {"status": "booking_not_found"}
            
            # Cancel it
            booking.status = CabBookingStatus.CANCELLED
            booking.cancelled_at = datetime.utcnow()
            booking.cancelled_by = f"customer:{normalized_phone}"
            
            await session.commit()
            
            # Log owner notification
            logger.warning(
                f"🔔 OWNER ALERT: Customer cancelled booking via WhatsApp!\n"
                f"   Booking ID: {booking.id}\n"
                f"   Customer: {booking.customer_name} ({booking.customer_phone})\n"
                f"   Route: {booking.pickup_text} → {booking.drop_text}\n"
                f"   Shop: {ctx.shop_slug}"
            )
            
            # Send confirmation
            confirmation_msg = format_cancellation_confirmation(
                booking_id=str(booking.id),
                pickup_text=booking.pickup_text,
                drop_text=booking.drop_text,
            )
            send_whatsapp_message(customer_number, confirmation_msg)
            
            # Clear session
            clear_session(customer_number)
            
            logger.info(f"✅ Booking {booking.id} cancelled by customer {normalized_phone}")
            return {"status": "booking_cancelled", "booking_id": str(booking.id)}
            
        except ValueError:
            send_whatsapp_message(
                customer_number,
                "Invalid input. Please reply with a number or 'CANCEL'."
            )
            return {"status": "invalid_input"}
        except Exception as e:
            logger.exception(f"Error processing cancel selection: {e}")
            clear_session(customer_number)
            send_whatsapp_message(customer_number, "❌ An error occurred. Please try again.")
            return {"status": "error"}
    
    # Handle HELP command
    if message_body.upper() in ['HELP', 'HI', 'HELLO', 'START']:
        help_text = get_help_message()
        send_whatsapp_message(customer_number, help_text)
        return {"status": "help_sent"}
    
    # Check for cancel intent
    is_cancel_request = await detect_cancel_intent(message_body)
    
    if is_cancel_request:
        # Customer wants to cancel a ride
        # Find their active bookings (PENDING or CONFIRMED)
        result = await session.execute(
            select(CabBooking).where(
                CabBooking.shop_id == ctx.shop_id,
                CabBooking.customer_phone.in_([customer_number, normalized_phone]),
                CabBooking.status.in_([CabBookingStatus.PENDING, CabBookingStatus.CONFIRMED]),
            ).order_by(CabBooking.pickup_time)
        )
        active_bookings = result.scalars().all()
        
        if not active_bookings:
            # No rides to cancel
            no_rides_msg = format_no_rides_to_cancel()
            send_whatsapp_message(customer_number, no_rides_msg)
            return {"status": "no_rides_to_cancel"}
        
        if len(active_bookings) == 1:
            # Only one ride - cancel it directly
            booking = active_bookings[0]
            booking.status = CabBookingStatus.CANCELLED
            booking.cancelled_at = datetime.utcnow()
            booking.cancelled_by = f"customer:{normalized_phone}"
            
            await session.commit()
            
            # Log owner notification
            logger.warning(
                f"🔔 OWNER ALERT: Customer cancelled booking via WhatsApp!\n"
                f"   Booking ID: {booking.id}\n"
                f"   Customer: {booking.customer_name} ({booking.customer_phone})\n"
                f"   Route: {booking.pickup_text} → {booking.drop_text}\n"
                f"   Shop: {ctx.shop_slug}"
            )
            
            confirmation_msg = format_cancellation_confirmation(
                booking_id=str(booking.id),
                pickup_text=booking.pickup_text,
                drop_text=booking.drop_text,
            )
            send_whatsapp_message(customer_number, confirmation_msg)
            
            logger.info(f"✅ Booking {booking.id} cancelled by customer {normalized_phone}")
            return {"status": "booking_cancelled", "booking_id": str(booking.id)}
        
        else:
            # Multiple rides - show selection list
            selection_msg = format_ride_selection_list(active_bookings)
            send_whatsapp_message(customer_number, selection_msg)
            
            # Store bookings in session
            booking_data = [
                {
                    'id': booking.id,
                    'pickup_text': booking.pickup_text,
                    'drop_text': booking.drop_text,
                }
                for booking in active_bookings
            ]
            set_session(customer_number, 'awaiting_cancel_selection', {'bookings': booking_data})
            
            logger.info(f"📋 Showed {len(active_bookings)} rides to {customer_number} for cancellation")
            return {"status": "awaiting_selection", "ride_count": len(active_bookings)}
    
    # Handle YES/NO confirmation (simplified - in production use session state)
    if message_body.upper() in ['YES', 'NO', 'CONFIRM', 'CANCEL']:
        if message_body.upper() in ['YES', 'CONFIRM']:
            response = "✅ To create a booking, please send a new request with your pickup and dropoff locations."
        else:
            response = "❌ Booking cancelled. Send a new message anytime to book a ride."
        send_whatsapp_message(customer_number, response)
        return {"status": "confirmation_handled"}
    
    # Parse booking request - try AI first, fallback to regex
    parsed = None
    try:
        # Try OpenAI parsing first
        parsed = await parse_booking_with_ai(message_body)
        if parsed:
            logger.info(f"✅ AI parsed booking: {parsed}")
        else:
            # Fallback to regex parsing
            parsed = parse_booking_request(message_body)
            logger.info(f"✅ Regex parsed booking: {parsed}")
        
    except BookingParseError as e:
        error_msg = format_error_message('parse_error')
        send_whatsapp_message(customer_number, error_msg)
        return {"status": "parse_error", "message": str(e)}
    
    # Calculate route and price
    try:
        pricing_rule = await get_pricing_rule_for_shop(session, ctx.shop_id)
        
        # Ensure vehicle_type is a string, not an enum
        vehicle_type_str = parsed['vehicle_type']
        if hasattr(vehicle_type_str, 'value'):
            vehicle_type_str = vehicle_type_str.value
        
        calc_result = await calculate_route_and_price(
            pickup_text=parsed['pickup_text'],
            drop_text=parsed['drop_text'],
            pricing_rule=pricing_rule,
            vehicle_type=vehicle_type_str,
        )
        
        # Send price quote
        quote_msg = format_price_quote(
            pickup_text=parsed['pickup_text'],
            drop_text=parsed['drop_text'],
            distance_miles=calc_result['distance_miles'],
            final_price=calc_result['final_price'],
            vehicle_type=vehicle_type_str,
            duration_minutes=calc_result['duration_minutes'],
        )
        
        # Send via Twilio or log (dev mode)
        if not send_whatsapp_message(customer_number, quote_msg):
            logger.info(f"📱 [DEV] Would send quote: {quote_msg}")
        
        # Auto-create booking (simplified - in production wait for YES confirmation)
        from .models import CabBookingChannel, CabVehicleType
        
        # Create booking request object
        # Convert enums to their string values for Pydantic
        vehicle_type_value = vehicle_type_str.value if hasattr(vehicle_type_str, 'value') else vehicle_type_str
        channel_value = "whatsapp"  # Use lowercase string value
        
        # DEBUG: Log what we're passing
        logger.info(f"🔍 DEBUG: Passing channel_value={channel_value} (type={type(channel_value)})")
        logger.info(f"🔍 DEBUG: Passing vehicle_type_value={vehicle_type_value} (type={type(vehicle_type_value)})")
        
        booking_request = CabBookingCreateRequest(
            channel=channel_value,
            pickup_text=parsed['pickup_text'],
            drop_text=parsed['drop_text'],
            pickup_time=parsed['pickup_time'],
            vehicle_type=vehicle_type_value,
            passengers=parsed['passengers'],
            customer_name="WhatsApp Customer",  # Extract from Twilio profile in production
            customer_phone=From.replace('whatsapp:', ''),
            customer_email=None,
        )
        
        # DEBUG: Log what Pydantic created
        logger.info(f"🔍 DEBUG: After Pydantic: booking_request.channel={booking_request.channel} (type={type(booking_request.channel)})")
        logger.info(f"🔍 DEBUG: After Pydantic: booking_request.channel.value={booking_request.channel.value if hasattr(booking_request.channel, 'value') else 'no .value'}")
        
        booking = await create_cab_booking_record(
            session=session,
            shop_id=ctx.shop_id,
            request=booking_request,
            calc_result=calc_result,
        )
        
        # Send confirmation
        confirmation_msg = format_booking_confirmation(
            booking_id=str(booking.id),
            pickup_text=parsed['pickup_text'],
            drop_text=parsed['drop_text'],
            pickup_time=parsed['pickup_time'],
            final_price=calc_result['final_price'],
        )
        
        if not send_whatsapp_message(customer_number, confirmation_msg):
            logger.info(f"📱 [DEV] Would send confirmation: {confirmation_msg}")
        
        logger.info(f"✅ WhatsApp booking created: {booking.id}")
        return {"status": "booking_created", "booking_id": str(booking.id)}
        
    except RouteError as e:
        logger.warning(f"Route calculation failed: {e.message}")
        error_msg = format_error_message('calc_error')
        send_whatsapp_message(customer_number, error_msg)
        return {"status": "route_error", "message": e.message}
        
    except Exception as e:
        logger.exception(f"WhatsApp booking error: {e}")
        error_msg = format_error_message('booking_error')
        send_whatsapp_message(customer_number, error_msg)
        return {"status": "error", "message": str(e)}
