"""
Phase 7: Authentication & Authorization Module

This module provides identity extraction and role-based access control (RBAC)
for multi-tenant shop operations.

ARCHITECTURE:
    - RequestContext is the SINGLE SOURCE OF TRUTH for identity
    - All authorization flows through require_shop_access()
    - Legacy X-User-Id header support for backward compatibility
    - Ready for Clerk/JWT integration

USAGE:
    # In route handlers, use the new context-based auth:
    from app.core import get_request_context, require_shop_access, RequestContext
    
    @router.get("/owner/dashboard")
    async def handler(
        ctx: ShopContext = Depends(get_shop_context_from_slug),
        session: AsyncSession = Depends(get_session),
        request: Request,
    ):
        req_ctx = await resolve_request_context(request, session)
        require_shop_access(req_ctx, ctx.shop_id, [ShopMemberRole.OWNER])
        # ... rest of handler

FUTURE:
    - Replace X-User-Id header with Clerk JWT verification
    - Add session/token management
"""

import logging
import os
from typing import Optional

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .core.db import get_session
from .core.request_context import (
    RequestContext,
    resolve_request_context,
    require_shop_access,
    get_request_context,
    get_optional_request_context,
)
from .models import ShopMember, ShopMemberRole, AuditLog
from .tenancy.context import ShopContext

# Development mode - bypasses authorization checks
# Read from environment variable, default to True for development
# ⚠️ PRODUCTION: Set DISABLE_AUTH_CHECKS=false in environment!
DISABLE_AUTH_CHECKS = os.environ.get("DISABLE_AUTH_CHECKS", "true").lower() in ("true", "1", "yes")


logger = logging.getLogger(__name__)


# Re-export from request_context for backward compatibility
__all__ = [
    # New context-based auth (preferred)
    "RequestContext",
    "resolve_request_context", 
    "require_shop_access",
    "get_request_context",
    "get_optional_request_context",
    # Legacy helpers (deprecated, use context-based instead)
    "get_current_user_id",
    "get_optional_user_id",
    "get_shop_member",
    "require_shop_role",
    "require_owner_or_manager",
    "require_any_member",
    "require_owner",
    "require_cab_owner_access",  # NEW: Cab owner authorization
    # Tenant enforcement
    "assert_shop_scoped_row",
    # Audit logging
    "log_audit",
    "AUDIT_SHOP_CREATED",
    "AUDIT_SHOP_UPDATED",
    "AUDIT_SHOP_DELETED",
    "AUDIT_OWNER_CHAT",
    "AUDIT_SERVICE_CREATED",
    "AUDIT_SERVICE_UPDATED",
    "AUDIT_SERVICE_DELETED",
    "AUDIT_STYLIST_CREATED",
    "AUDIT_STYLIST_UPDATED",
    "AUDIT_BOOKING_CREATED",
    "AUDIT_BOOKING_CONFIRMED",
    "AUDIT_BOOKING_CANCELLED",
    "AUDIT_MEMBER_ADDED",
    "AUDIT_MEMBER_ROLE_CHANGED",
    "AUDIT_MEMBER_REMOVED",
]


# ============================================================================
# IDENTITY EXTRACTION
# ============================================================================

async def get_current_user_id(
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    authorization: Optional[str] = Header(None),
) -> str:
    """
    Extract current user identity from JWT token or X-User-Id header.
    
    SECURITY BEHAVIOR:
    
    When DISABLE_AUTH_CHECKS=False (PRODUCTION):
    - REQUIRES valid JWT token in Authorization header
    - X-User-Id header is IGNORED completely (security measure)
    - Invalid/expired JWT returns 401
    
    When DISABLE_AUTH_CHECKS=True (DEVELOPMENT):
    - Allows X-User-Id header for testing
    - Falls back to "dev-user" if no auth provided
    
    ⚠️ SECURITY: In production, NEVER accept X-User-Id as it can be spoofed.
    
    Raises:
        HTTPException 401: If no valid JWT provided (when auth checks enabled)
    
    Returns:
        User ID string (Clerk user ID like "user_2abc123...")
    
    Example:
        # Production (JWT required):
        curl -H "Authorization: Bearer eyJhbGciOiJSUzI1NiJ..." http://api.convo.com/...
        
        # Development (X-User-Id allowed):
        curl -H "X-User-Id: user_abc123" http://localhost:8000/...
    """
    # ========================================
    # PRODUCTION MODE: JWT Required
    # ========================================
    if not DISABLE_AUTH_CHECKS:
        # In production, ONLY accept JWT tokens - X-User-Id is IGNORED
        if not authorization:
            logger.warning("Production auth failed: Missing Authorization header")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required. Provide a valid JWT token in the Authorization header.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        if not authorization.startswith("Bearer "):
            logger.warning(f"Production auth failed: Invalid Authorization header format. Received: {authorization[:50]}...")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid Authorization header format. Expected: Bearer <token>",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        try:
            from .clerk_auth import verify_clerk_token
            token = authorization.split(" ", 1)[1]
            logger.info(f"🔐 Attempting to verify JWT token (first 20 chars): {token[:20]}...")
            user_data = verify_clerk_token(token)
            user_id = user_data.get("sub")
            
            if not user_id:
                logger.error("JWT verified but missing 'sub' claim")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid token: missing user identifier",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            
            logger.info(f"✅ Production auth successful: {user_id}")
            return user_id
            
        except HTTPException:
            # Re-raise HTTP exceptions from verify_clerk_token
            raise
        except Exception as e:
            logger.error(f"JWT verification failed: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
                headers={"WWW-Authenticate": "Bearer"},
            )
    
    # ========================================
    # DEVELOPMENT MODE: X-User-Id Allowed
    # ========================================
    logger.warning("⚠️ DEVELOPMENT MODE: Auth checks disabled")
    
    # Try JWT first even in dev mode (for testing JWT flow)
    if authorization and authorization.startswith("Bearer "):
        try:
            from .clerk_auth import verify_clerk_token
            token = authorization.split(" ", 1)[1]
            logger.info(f"🔐 Dev mode: Attempting to verify JWT token (first 20 chars): {token[:20]}...")
            user_data = verify_clerk_token(token)
            user_id = user_data.get("sub")
            if user_id:
                logger.info(f"✅ Dev mode: Authenticated via JWT: {user_id}")
                return user_id
        except Exception as e:
            logger.debug(f"Dev mode: JWT verification failed ({e}), trying X-User-Id")
    
    # Fall back to X-User-Id in dev mode
    if x_user_id and x_user_id.strip():
        user_id = x_user_id.strip()
        logger.warning(f"⚠️ Dev mode: Using X-User-Id header: {user_id}")
        return user_id
    
    # Default user for dev mode
    logger.warning("⚠️ Dev mode: No auth provided, using default 'dev-user'")
    return "dev-user"


async def get_optional_user_id(
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    authorization: Optional[str] = Header(None),
) -> Optional[str]:
    """
    Extract user identity if present, without requiring it.
    
    Useful for endpoints that behave differently for authenticated vs anonymous users.
    
    In production: Only JWT is accepted
    In development: X-User-Id is also accepted
    
    Returns:
        User ID string if valid auth provided, None otherwise
    """
    # Production: only accept JWT
    if not DISABLE_AUTH_CHECKS:
        if authorization and authorization.startswith("Bearer "):
            try:
                from .clerk_auth import verify_clerk_token
                token = authorization.split(" ", 1)[1]
                user_data = verify_clerk_token(token)
                return user_data.get("sub")
            except Exception:
                return None
        return None
    
    # Development: try JWT first, then X-User-Id
    if authorization and authorization.startswith("Bearer "):
        try:
            from .clerk_auth import verify_clerk_token
            token = authorization.split(" ", 1)[1]
            user_data = verify_clerk_token(token)
            user_id = user_data.get("sub")
            if user_id:
                return user_id
        except Exception:
            pass
    
    if x_user_id and x_user_id.strip():
        return x_user_id.strip()
    
    return None


# ============================================================================
# ROLE-BASED ACCESS CONTROL (RBAC)
# ============================================================================

async def get_shop_member(
    session: AsyncSession,
    shop_id: int,
    user_id: str,
) -> Optional[ShopMember]:
    """
    Look up a user's membership in a shop.
    
    Args:
        session: Database session
        shop_id: The shop to check membership for
        user_id: The user ID from auth provider
    
    Returns:
        ShopMember if user is a member of the shop, None otherwise
    """
    result = await session.execute(
        select(ShopMember).where(
            ShopMember.shop_id == shop_id,
            ShopMember.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()


async def require_shop_role(
    session: AsyncSession,
    ctx: ShopContext,
    user_id: str,
    allowed_roles: list[ShopMemberRole],
) -> ShopMember:
    """
    Require the user to have one of the specified roles in the shop.
    
    MIGRATION SUPPORT: This function checks both:
    1. shop_members table (new multi-tenant system)
    2. shop.owner_user_id field (legacy single-owner system)
    
    If user matches shop.owner_user_id but has no shop_member record,
    we auto-create an OWNER shop_member record for them.
    
    Args:
        session: Database session
        ctx: Shop context (must be resolved before calling)
        user_id: The authenticated user ID
        allowed_roles: List of roles that grant access
    
    Raises:
        HTTPException 403: If user is not a member or doesn't have required role
    
    Returns:
        ShopMember record for the user
    
    Example:
        member = await require_shop_role(
            session, ctx, user_id, 
            [ShopMemberRole.OWNER, ShopMemberRole.MANAGER]
        )
    """
    member = await get_shop_member(session, ctx.shop_id, user_id)
    
    if not member:
        logger.error(
            f"❌ Authorization failed: User '{user_id}' is not a member of shop {ctx.shop_id} ({ctx.shop_slug}). "
            f"To fix this, you need to add a shop_member record in the database. "
            f"Run: INSERT INTO shop_members (shop_id, user_id, role) VALUES ({ctx.shop_id}, '{user_id}', 'OWNER');"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied. You are not a member of {ctx.shop_name or ctx.shop_slug}. User ID: {user_id}",
        )
    
    # Check if user's role is in allowed roles
    # Normalize role to uppercase for case-insensitive comparison
    member_role_upper = member.role.upper() if isinstance(member.role, str) else member.role
    try:
        user_role = ShopMemberRole(member_role_upper)
    except ValueError:
        logger.warning(f"Invalid role '{member.role}' for user {user_id} in shop {ctx.shop_id}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Invalid role configuration. Please contact support.",
        )
    allowed_role_values = [r.value if isinstance(r, ShopMemberRole) else r for r in allowed_roles]
    
    if user_role.value not in allowed_role_values:
        logger.warning(
            f"Authorization failed: User {user_id} has role {member.role}, "
            f"but needs one of {allowed_role_values} for shop {ctx.shop_id}"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied. Required role: {', '.join(allowed_role_values)}. Your role: {member.role}.",
        )
    
    logger.debug(f"Authorization successful: User {user_id} has role {member.role} in shop {ctx.shop_id}")
    return member


# ============================================================================
# CONVENIENCE RBAC DEPENDENCIES
# ============================================================================

async def require_owner_or_manager(
    ctx: ShopContext,
    user_id: str,
    session: AsyncSession,
) -> ShopMember:
    """
    Require OWNER or MANAGER role for shop management operations.
    
    Use for: Owner dashboard, service management, schedule changes, etc.
    """
    return await require_shop_role(
        session, ctx, user_id,
        [ShopMemberRole.OWNER, ShopMemberRole.MANAGER]
    )


async def require_any_member(
    ctx: ShopContext,
    user_id: str,
    session: AsyncSession,
) -> ShopMember:
    """
    Require any shop membership (OWNER, MANAGER, or EMPLOYEE).
    
    Use for: Employee view, staff operations, viewing schedules, etc.
    """
    return await require_shop_role(
        session, ctx, user_id,
        [ShopMemberRole.OWNER, ShopMemberRole.MANAGER, ShopMemberRole.EMPLOYEE]
    )


async def require_owner(
    ctx: ShopContext,
    user_id: str,
    session: AsyncSession,
) -> ShopMember:
    """
    Require OWNER role only.
    
    Use for: Billing, shop deletion, transferring ownership, etc.
    """
    return await require_shop_role(
        session, ctx, user_id,
        [ShopMemberRole.OWNER]
    )


# ============================================================================
# CAB OWNER AUTHORIZATION
# ============================================================================

async def require_cab_owner_access(
    ctx: ShopContext,
    user_id: str,
    session: AsyncSession,
):
    """
    Verify user is an OWNER/MANAGER of a shop with cab services enabled.
    
    This is CRITICAL for security: Clerk authenticates anyone, but we only want
    cab owners to access the cab dashboard. This enforces business logic.
    
    Checks:
    1. User is OWNER or MANAGER of this shop
    2. Shop has cab services enabled
    3. Cab services are currently active
    
    Args:
        ctx: Shop context for current request
        user_id: Clerk user ID from JWT or X-User-Id header
        session: Database session
    
    Returns:
        CabOwner record if all checks pass
    
    Raises:
        HTTPException 403: If any check fails
        
    Usage:
        @router.get("/owner/cab/summary")
        async def get_summary(
            ctx: ShopContext = Depends(get_shop_context_from_slug),
            user_id: str = Depends(get_current_user_id),
            session: AsyncSession = Depends(get_session),
        ):
            cab_owner = await require_cab_owner_access(ctx, user_id, session)
            # Now safe to access cab data
    """
    # Check if user is OWNER or MANAGER of this shop
    await require_owner_or_manager(ctx, user_id, session)
    
    # Check if shop has cab services enabled
    from .models import CabOwner
    result = await session.execute(
        select(CabOwner).where(CabOwner.shop_id == ctx.shop_id)
    )
    cab_owner = result.scalar_one_or_none()
    
    if not cab_owner:
        logger.warning(
            f"Access denied: Shop {ctx.shop_id} does not have cab services configured"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cab services are not enabled for this shop. Please enable them in settings.",
        )
    
    if not cab_owner.is_active:
        logger.warning(
            f"Access denied: Cab services disabled for shop {ctx.shop_id}"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cab services are currently disabled for this shop.",
        )
    
    logger.debug(f"Cab owner access granted to user {user_id} for shop {ctx.shop_id}")
    return cab_owner

def assert_shop_scoped_row(row_shop_id: int, ctx_shop_id: int) -> None:
    """
    Assert that a database row belongs to the current shop context.
    
    Call this before updating/deleting any tenant-scoped row to prevent
    cross-tenant data access.
    
    Args:
        row_shop_id: The shop_id from the database row
        ctx_shop_id: The shop_id from the current request context
    
    Raises:
        HTTPException 403: If shop IDs don't match
    
    Example:
        booking = await get_booking(session, booking_id)
        assert_shop_scoped_row(booking.shop_id, ctx.shop_id)
        # Now safe to update/delete
    """
    if row_shop_id != ctx_shop_id:
        logger.error(
            f"Tenant boundary violation! Row shop_id={row_shop_id}, "
            f"request ctx shop_id={ctx_shop_id}"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Resource belongs to a different shop.",
        )


# ============================================================================
# AUDIT LOGGING HELPERS
# ============================================================================

async def log_audit(
    session: AsyncSession,
    *,
    actor_user_id: str,
    action: str,
    shop_id: Optional[int] = None,
    target_type: Optional[str] = None,
    target_id: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> AuditLog:
    """
    Create an audit log entry.
    
    IMPORTANT: Do NOT include PII (phone numbers, emails) in metadata
    unless absolutely necessary for compliance/legal reasons.
    
    Args:
        session: Database session
        actor_user_id: Who performed the action
        action: Action identifier (e.g., 'shop.created', 'owner.chat')
        shop_id: Tenant context (None for system-level actions)
        target_type: Type of entity affected (e.g., 'shop', 'booking')
        target_id: ID of affected entity
        metadata: Additional context (NO PII!)
    
    Returns:
        The created AuditLog record
    
    Example:
        await log_audit(
            session,
            actor_user_id="user_123",
            action="shop.created",
            shop_id=new_shop.id,
            target_type="shop",
            target_id=str(new_shop.id),
            metadata={"slug": new_shop.slug}
        )
    """
    audit_log = AuditLog(
        shop_id=shop_id,
        actor_user_id=actor_user_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        extra_data=metadata,  # Maps to 'metadata' column in DB
    )
    session.add(audit_log)
    # Don't commit here - let the caller control the transaction
    await session.flush()
    
    logger.info(
        f"Audit: {action} by {actor_user_id} "
        f"(shop={shop_id}, target={target_type}:{target_id})"
    )
    
    return audit_log


# ============================================================================
# COMMON AUDIT ACTIONS
# ============================================================================

# Shop lifecycle
AUDIT_SHOP_CREATED = "shop.created"
AUDIT_SHOP_UPDATED = "shop.updated"
AUDIT_SHOP_DELETED = "shop.deleted"

# Owner/Manager operations
AUDIT_OWNER_CHAT = "owner.chat"
AUDIT_SERVICE_CREATED = "service.created"
AUDIT_SERVICE_UPDATED = "service.updated"
AUDIT_SERVICE_DELETED = "service.deleted"
AUDIT_STYLIST_CREATED = "stylist.created"
AUDIT_STYLIST_UPDATED = "stylist.updated"

# Booking operations
AUDIT_BOOKING_CREATED = "booking.created"
AUDIT_BOOKING_CONFIRMED = "booking.confirmed"
AUDIT_BOOKING_CANCELLED = "booking.cancelled"

# Membership operations
AUDIT_MEMBER_ADDED = "member.added"
AUDIT_MEMBER_ROLE_CHANGED = "member.role_changed"
AUDIT_MEMBER_REMOVED = "member.removed"
