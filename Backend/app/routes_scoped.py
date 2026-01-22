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
from .models import Service, Stylist, ShopMemberRole
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
