"""
Multi-tenancy context module for Convo.

This module provides the ShopContext abstraction for tenant isolation.

PHASE 2 STATUS:
    - ShopContext dataclass defined
    - Real DB-backed resolution from slug, phone number, API key
    - FastAPI dependency for route injection
    - Legacy fallback to shop_id=1 for old routes
"""

import hashlib
import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.db import get_session
from ..models import Shop, ShopPhoneNumber


logger = logging.getLogger(__name__)


class ShopResolutionSource(str, Enum):
    """How the shop context was determined."""
    
    URL_SLUG = "url_slug"           # From /s/[slug]/ or /api/s/[slug]/ in URL path
    AUTH_TOKEN = "auth_token"       # From JWT claim in authenticated request
    TWILIO_TO = "twilio_to"         # From Twilio webhook To phone number
    API_KEY = "api_key"             # From API key lookup (ChatGPT, etc.)
    SUBDOMAIN = "subdomain"         # From subdomain (future)
    DEFAULT_FALLBACK = "default"    # Fallback to default shop (legacy routes only)


@dataclass(frozen=True)
class ShopContext:
    """
    Immutable context representing the current tenant for a request.
    
    This object MUST be established before any tenant-specific database operation.
    
    Attributes:
        shop_id: The database ID of the shop (shops.id)
        shop_slug: URL-safe identifier (e.g., "bishops-tempe"), may be None if resolved by ID
        shop_name: Human-readable shop name
        timezone: IANA timezone string (e.g., "America/Phoenix")
        source: How this context was determined (for audit logging)
    """
    
    shop_id: int
    shop_slug: Optional[str] = None
    shop_name: Optional[str] = None
    timezone: str = "America/Phoenix"
    source: ShopResolutionSource = ShopResolutionSource.DEFAULT_FALLBACK
    
    def __post_init__(self):
        if self.shop_id <= 0:
            raise ValueError(f"shop_id must be positive, got {self.shop_id}")


# ────────────────────────────────────────────────────────────────
# Legacy Default Shop (for backward compatibility)
# ────────────────────────────────────────────────────────────────

# TODO [Phase 3]: Remove this after frontend routing is updated
LEGACY_DEFAULT_SHOP_ID = 1


async def get_legacy_default_shop_context(session: AsyncSession) -> ShopContext:
    """
    Get the default shop context for legacy routes.
    
    This should ONLY be used for old routes that don't have shop slug/auth.
    New routes should use proper resolution.
    """
    result = await session.execute(select(Shop).where(Shop.id == LEGACY_DEFAULT_SHOP_ID))
    shop = result.scalar_one_or_none()
    
    if not shop:
        # Critical: default shop must exist
        raise HTTPException(
            status_code=500,
            detail="Default shop not found. Run database migrations."
        )
    
    return ShopContext(
        shop_id=shop.id,
        shop_slug=shop.slug,
        shop_name=shop.name,
        timezone=shop.timezone,
        source=ShopResolutionSource.DEFAULT_FALLBACK,
    )


# ────────────────────────────────────────────────────────────────
# Resolution Functions
# ────────────────────────────────────────────────────────────────

async def resolve_shop_from_slug(
    session: AsyncSession,
    slug: str,
) -> Optional[ShopContext]:
    """
    Resolve shop context from a URL slug.
    
    Args:
        session: Database session
        slug: Shop URL slug (e.g., "bishops-tempe")
        
    Returns:
        ShopContext if found, None if slug not found
    """
    result = await session.execute(select(Shop).where(Shop.slug == slug))
    shop = result.scalar_one_or_none()
    
    if not shop:
        return None
    
    return ShopContext(
        shop_id=shop.id,
        shop_slug=shop.slug,
        shop_name=shop.name,
        timezone=shop.timezone,
        source=ShopResolutionSource.URL_SLUG,
    )


def normalize_phone_for_lookup(phone: str) -> str:
    """Normalize phone number for database lookup."""
    if not phone:
        return ""
    # Remove all non-digit chars except leading +
    if phone.startswith("+"):
        digits = re.sub(r"\D", "", phone[1:])
        return f"+{digits}"
    digits = re.sub(r"\D", "", phone)
    if len(digits) == 10:
        return f"+1{digits}"
    if len(digits) >= 11:
        return f"+{digits}"
    return phone


async def resolve_shop_from_twilio_to(
    session: AsyncSession,
    to_number: str,
) -> Optional[ShopContext]:
    """
    Resolve shop context from a Twilio To phone number.
    
    Checks both shop_phone_numbers table and shops.phone_number.
        
    Args:
        session: Database session
        to_number: The Twilio To number (e.g., "+16234048440")
        
    Returns:
        ShopContext if found, None if number not configured
    """
    normalized = normalize_phone_for_lookup(to_number)
    
    if not normalized:
        return None
    
    # First check shop_phone_numbers table (preferred for multi-number routing)
    result = await session.execute(
        select(Shop)
        .join(ShopPhoneNumber, ShopPhoneNumber.shop_id == Shop.id)
        .where(ShopPhoneNumber.phone_number == normalized)
    )
    shop = result.scalar_one_or_none()
    
    if not shop:
        # Fallback: check shops.phone_number directly
        result = await session.execute(
            select(Shop).where(Shop.phone_number == normalized)
        )
        shop = result.scalar_one_or_none()
    
    if not shop:
        return None
    
    return ShopContext(
        shop_id=shop.id,
        shop_slug=shop.slug,
        shop_name=shop.name,
        timezone=shop.timezone,
        source=ShopResolutionSource.TWILIO_TO,
    )


def hash_api_key(api_key: str) -> str:
    """Hash an API key for secure storage/comparison."""
    return hashlib.sha256(api_key.encode()).hexdigest()


async def resolve_shop_from_api_key(
    session: AsyncSession,
    api_key: str,
) -> Optional[ShopContext]:
    """
    Resolve shop context from an API key.
    
    Checks shop_api_keys table for a matching key hash.
        
    Args:
        session: Database session
        api_key: The API key from X-API-Key header
        
    Returns:
        ShopContext if valid key found, None if key not found or revoked
    """
    from ..models import ShopApiKey
    
    key_hash = hash_api_key(api_key)
    
    result = await session.execute(
        select(Shop)
        .join(ShopApiKey, ShopApiKey.shop_id == Shop.id)
        .where(
            ShopApiKey.api_key_hash == key_hash,
            ShopApiKey.revoked_at.is_(None),  # Not revoked
        )
    )
    shop = result.scalar_one_or_none()
    
    if not shop:
        return None
    
    return ShopContext(
        shop_id=shop.id,
        shop_slug=shop.slug,
        shop_name=shop.name,
        timezone=shop.timezone,
        source=ShopResolutionSource.API_KEY,
    )


# ────────────────────────────────────────────────────────────────
# URL Path Helpers
# ────────────────────────────────────────────────────────────────

def extract_slug_from_path(path: str) -> Optional[str]:
    """
    Extract shop slug from URL path.
    
    Expected patterns:
        /s/<slug>/...      -> returns <slug>
        /api/s/<slug>/...  -> returns <slug>
        /o/<slug>/...      -> returns <slug>  (owner routes)
        
    Args:
        path: Request URL path
        
    Returns:
        Shop slug if found, None otherwise
    """
    # Match /s/slug/ or /api/s/slug/ or /o/slug/
    match = re.match(r"^(?:/api)?/([so])/([a-z0-9-]+)(?:/|$)", path)
    if match:
        return match.group(2)
    return None


# ────────────────────────────────────────────────────────────────
# FastAPI Dependencies
# ────────────────────────────────────────────────────────────────

async def get_shop_context(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> ShopContext:
    """
    FastAPI dependency to resolve shop context from request.
    
    Resolution order (first match wins):
    1. URL path slug (/s/{slug}/ or /api/s/{slug}/)
    2. Twilio To number (for voice/SMS webhooks)
    3. API key header (X-API-Key)
    4. Legacy fallback to shop_id=1 (ONLY for old routes)
    
    Usage:
        @router.get("/services")
        async def list_services(
            ctx: ShopContext = Depends(get_shop_context),
            session: AsyncSession = Depends(get_session),
        ):
            services = await list_services(session, ctx.shop_id)
    """
    # 1. Try URL path slug
    slug = extract_slug_from_path(request.url.path)
    if slug:
        ctx = await resolve_shop_from_slug(session, slug)
        if ctx:
            logger.debug(f"Resolved shop from slug: {slug} -> shop_id={ctx.shop_id}")
            return ctx
        raise HTTPException(status_code=404, detail=f"Shop not found: {slug}")
    
    # 2. Try Twilio To number (for voice/SMS webhooks)
    # Check form data for Twilio webhooks
    content_type = request.headers.get("content-type", "")
    if "form" in content_type.lower():
        try:
            form = await request.form()
            to_number = form.get("To")
            if to_number:
                ctx = await resolve_shop_from_twilio_to(session, str(to_number))
                if ctx:
                    logger.debug(f"Resolved shop from Twilio To: {to_number} -> shop_id={ctx.shop_id}")
                    return ctx
                # Number not configured - will fall through to default or error
        except Exception:
            pass  # Form parsing failed, continue
    
    # 3. Try API key header
    api_key = request.headers.get("X-API-Key")
    if api_key:
        ctx = await resolve_shop_from_api_key(session, api_key)
        if ctx:
            logger.debug(f"Resolved shop from API key -> shop_id={ctx.shop_id}")
            return ctx
        # Invalid API key - could be legacy key, fall through to default
    
    # 4. Legacy fallback
    # Only use for routes that haven't been migrated yet
    logger.debug("Using legacy default shop context (shop_id=1)")
    return await get_legacy_default_shop_context(session)


async def get_shop_context_or_none(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> Optional[ShopContext]:
    """
    Like get_shop_context but returns None instead of raising HTTPException.
    Useful for routes that handle missing shop gracefully.
    """
    try:
        return await get_shop_context(request, session)
    except HTTPException:
        return None


async def require_shop_context(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> ShopContext:
    """
    Strict shop context - fails if no shop can be resolved (no legacy fallback).
    
    Use this for new multi-tenant routes that MUST have explicit shop context.
    """
    # 1. Try URL path slug
    slug = extract_slug_from_path(request.url.path)
    if slug:
        ctx = await resolve_shop_from_slug(session, slug)
        if ctx:
            return ctx
        raise HTTPException(status_code=404, detail=f"Shop not found: {slug}")
    
    # 2. Try Twilio To number
    content_type = request.headers.get("content-type", "")
    if "form" in content_type.lower():
        try:
            form = await request.form()
            to_number = form.get("To")
            if to_number:
                ctx = await resolve_shop_from_twilio_to(session, str(to_number))
                if ctx:
                    return ctx
        except Exception:
            pass
    
    # 3. Try API key
    api_key = request.headers.get("X-API-Key")
    if api_key:
        ctx = await resolve_shop_from_api_key(session, api_key)
        if ctx:
            return ctx
        raise HTTPException(status_code=401, detail="Invalid API key")
    
    # No fallback - require explicit shop context
    raise HTTPException(
        status_code=400, 
        detail="Shop context required. Use /s/{slug}/ path or provide valid API key."
    )


# ────────────────────────────────────────────────────────────────
# Database Tenant Setting (for future RLS)
# ────────────────────────────────────────────────────────────────

async def set_db_tenant(session: AsyncSession, shop_id: int) -> None:
    """
    Set the current tenant context on the database session for RLS.
    
    PHASE 5 TODO:
        Execute: SET LOCAL app.current_shop_id = :shop_id
        This enables RLS policies to enforce tenant isolation.
    """
    # TODO [Phase 5]: Enable RLS with session variable
    # from sqlalchemy import text
    # await session.execute(
    #     text("SET LOCAL app.current_shop_id = :shop_id"),
    #     {"shop_id": shop_id}
    # )
    pass


# ────────────────────────────────────────────────────────────────
# Legacy compatibility alias
# ────────────────────────────────────────────────────────────────

async def resolve_shop_context(request: Request) -> ShopContext:
    """Legacy alias - prefer get_shop_context with Depends()."""
    # This needs a session, but for backward compat we create one
    from ..core.db import AsyncSessionLocal
    async with AsyncSessionLocal() as session:
        return await get_shop_context(request, session)


# ────────────────────────────────────────────────────────────────
# Exports
# ────────────────────────────────────────────────────────────────

__all__ = [
    "ShopContext",
    "ShopResolutionSource",
    "get_shop_context",
    "get_shop_context_or_none",
    "require_shop_context",
    "get_legacy_default_shop_context",
    "resolve_shop_context",
    "resolve_shop_from_slug",
    "resolve_shop_from_twilio_to",
    "resolve_shop_from_api_key",
    "extract_slug_from_path",
    "hash_api_key",
    "set_db_tenant",
    "LEGACY_DEFAULT_SHOP_ID",
]
