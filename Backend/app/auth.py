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
# ⚠️ HARDCODED TO TRUE FOR DEVELOPMENT - CHANGE BEFORE PRODUCTION!
DISABLE_AUTH_CHECKS = True  # Set to False before deploying to production


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
) -> str:
    """
    Extract current user identity from request headers.
    
    Phase 7: Uses X-User-Id header (temporary before Clerk/JWT integration).
    
    ⚠️ DEVELOPMENT MODE: Set DISABLE_AUTH_CHECKS=true to bypass requirement
    
    Raises:
        HTTPException 401: If X-User-Id header is missing or empty
    
    Returns:
        User ID string from the auth provider
    
    Example:
        curl -H "X-User-Id: user_abc123" http://localhost:8000/s/shop-slug/owner/chat
    
    FUTURE: Replace with JWT verification:
        - Decode JWT from Authorization header
        - Verify signature with Clerk public key
        - Extract user_id from claims
    """
    # DEVELOPMENT MODE: Return default user ID if auth checks disabled
    if DISABLE_AUTH_CHECKS:
        default_user = x_user_id.strip() if x_user_id else "dev-user"
        logger.warning(f"⚠️ DEVELOPMENT MODE: Auth bypassed, using user_id={default_user}")
        return default_user
    
    if not x_user_id or not x_user_id.strip():
        logger.warning("Authentication failed: Missing X-User-Id header")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Provide X-User-Id header.",
            headers={"WWW-Authenticate": "X-User-Id"},
        )
    
    user_id = x_user_id.strip()
    logger.debug(f"Authenticated user: {user_id}")
    return user_id


async def get_optional_user_id(
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
) -> Optional[str]:
    """
    Extract user identity if present, without requiring it.
    
    Useful for endpoints that behave differently for authenticated vs anonymous users.
    
    Returns:
        User ID string if provided, None otherwise
    """
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
        logger.warning(
            f"Authorization failed: User {user_id} is not a member of shop {ctx.shop_id} ({ctx.shop_slug})"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied. You are not a member of {ctx.shop_name or ctx.shop_slug}.",
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
# TENANT ENFORCEMENT HELPERS
# ============================================================================

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
