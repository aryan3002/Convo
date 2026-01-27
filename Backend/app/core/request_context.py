"""
Request Context Resolution Module

This module provides the SINGLE SOURCE OF TRUTH for identity resolution.
All API routes should use this module instead of directly reading X-User-Id.

ARCHITECTURE:
    1. resolveRequestContext() extracts identity from request
    2. It checks multiple auth methods in order of security
    3. Returns a standardized RequestContext object
    4. All authorization checks use this context

AUTH METHODS (in order of precedence):
    1. JWT Bearer token (production - when Clerk is integrated)
    2. Session cookie (server-side sessions)
    3. X-User-Id header (development/transitional only)

FUTURE:
    - Integrate Clerk JWT verification
    - Remove X-User-Id support in production
"""

import logging
import os
from dataclasses import dataclass, field
from typing import Optional

from fastapi import Request, HTTPException, status, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Shop, ShopMember, ShopMemberRole
from .db import get_session

logger = logging.getLogger(__name__)

# Development mode - bypasses authorization checks
# Read from environment variable DISABLE_AUTH_CHECKS
import os
DISABLE_AUTH_CHECKS = os.environ.get("DISABLE_AUTH_CHECKS", "false").lower() in ("true", "1", "yes")


@dataclass
class RequestContext:
    """
    Resolved request context containing identity and access information.
    
    This is the SINGLE SOURCE OF TRUTH for who is making the request
    and what they can access.
    """
    # Identity (required once authenticated)
    user_id: str
    
    # Auth metadata
    auth_method: str  # 'jwt', 'session', 'header'
    is_authenticated: bool = True
    
    # Cached access info (populated lazily)
    accessible_shop_ids: list[int] = field(default_factory=list)
    roles_by_shop: dict[int, str] = field(default_factory=dict)
    
    # Request metadata
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None


class AuthenticationError(Exception):
    """Raised when authentication fails."""
    def __init__(self, message: str, status_code: int = 401):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class AuthorizationError(Exception):
    """Raised when authorization fails."""
    def __init__(self, message: str, shop_id: Optional[int] = None):
        self.message = message
        self.shop_id = shop_id
        super().__init__(message)


async def resolve_request_context(
    request: Request,
    session: AsyncSession,
    require_auth: bool = True,
) -> RequestContext:
    """
    Resolve the identity and context from a request.
    
    This is the CENTRAL function for identity resolution. All API routes
    should use this instead of directly reading headers.
    
    Args:
        request: The FastAPI request object
        session: Database session for looking up memberships
        require_auth: If True, raises 401 when no identity found
    
    Returns:
        RequestContext with resolved identity and access info
    
    Raises:
        HTTPException 401: If require_auth=True and no valid identity found
    
    Example:
        @router.get("/owner/dashboard")
        async def owner_dashboard(
            request: Request,
            session: AsyncSession = Depends(get_session),
        ):
            ctx = await resolve_request_context(request, session)
            # ctx.user_id is now the authenticated user
            # ctx.accessible_shop_ids contains shops they can access
    """
    user_id: Optional[str] = None
    auth_method: str = "none"
    
    # 1. Try JWT Bearer token (highest precedence, most secure)
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        # TODO: Integrate Clerk JWT verification
        # For now, we don't support JWT yet
        # user_id = await verify_clerk_jwt(token)
        # auth_method = "jwt"
        pass
    
    # 2. Try session cookie (server-side sessions)
    # TODO: Implement session-based auth
    # session_id = request.cookies.get("session_id")
    # if session_id:
    #     user_id = await get_user_from_session(session_id)
    #     auth_method = "session"
    
    # 3. Fall back to X-User-Id header (development/transitional)
    if not user_id:
        x_user_id = request.headers.get("X-User-Id", "").strip()
        if x_user_id:
            user_id = x_user_id
            auth_method = "header"
            logger.debug(f"Auth via X-User-Id header: {user_id}")
    
    # 4. Check if we got a user
    if not user_id:
        if require_auth:
            logger.warning("Authentication failed: No valid identity found")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required. Please log in.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return RequestContext(
            user_id="",
            auth_method="none",
            is_authenticated=False,
        )
    
    # 5. Build the context with access info
    ctx = RequestContext(
        user_id=user_id,
        auth_method=auth_method,
        is_authenticated=True,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("User-Agent"),
    )
    
    # 6. Preload accessible shops (for use in authorization)
    await _populate_access_info(ctx, session)
    
    return ctx


async def _populate_access_info(ctx: RequestContext, session: AsyncSession) -> None:
    """
    Populate the accessible_shop_ids and roles_by_shop fields.
    
    This queries shop_members to find all shops the user can access
    and their roles in each shop.
    """
    result = await session.execute(
        select(ShopMember).where(ShopMember.user_id == ctx.user_id)
    )
    memberships = result.scalars().all()
    
    ctx.accessible_shop_ids = [m.shop_id for m in memberships]
    ctx.roles_by_shop = {m.shop_id: m.role for m in memberships}
    
    logger.debug(
        f"User {ctx.user_id} has access to {len(ctx.accessible_shop_ids)} shops: "
        f"{ctx.accessible_shop_ids}"
    )


def require_shop_access(
    ctx: RequestContext,
    shop_id: int,
    allowed_roles: list[ShopMemberRole] | None = None,
) -> str:
    """
    Check if the user has access to a specific shop.
    
    This is the ONE authorization rule for shop access:
    - User must be a member of the shop
    - If allowed_roles specified, user must have one of those roles
    
    ⚠️ DEVELOPMENT MODE: Set DISABLE_AUTH_CHECKS=true to bypass all checks
    
    Args:
        ctx: The resolved request context
        shop_id: The shop to check access for
        allowed_roles: Optional list of roles that grant access
    
    Returns:
        The user's role in the shop
    
    Raises:
        HTTPException 403: If user doesn't have access
    
    Example:
        ctx = await resolve_request_context(request, session)
        role = require_shop_access(ctx, shop_id, [ShopMemberRole.OWNER, ShopMemberRole.MANAGER])
    """
    # DEVELOPMENT MODE: Bypass all authorization checks
    if DISABLE_AUTH_CHECKS:
        logger.warning(
            f"⚠️ DEVELOPMENT MODE: Auth check bypassed for user {ctx.user_id} accessing shop {shop_id}"
        )
        return "OWNER"  # Return OWNER role so all operations succeed
    
    if shop_id not in ctx.accessible_shop_ids:
        logger.warning(
            f"Authorization failed: User {ctx.user_id} is not a member of shop {shop_id}"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You are not a member of this shop.",
        )
    
    user_role = ctx.roles_by_shop.get(shop_id, "")
    
    if allowed_roles:
        # Normalize role comparison
        allowed_values = [r.value if isinstance(r, ShopMemberRole) else r for r in allowed_roles]
        user_role_upper = user_role.upper() if user_role else ""
        
        if user_role_upper not in allowed_values:
            logger.warning(
                f"Authorization failed: User {ctx.user_id} has role {user_role}, "
                f"needs one of {allowed_values} for shop {shop_id}"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required role: {', '.join(allowed_values)}. Your role: {user_role}.",
            )
    
    logger.debug(f"Authorization successful: User {ctx.user_id} has role {user_role} in shop {shop_id}")
    return user_role


async def get_request_context(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> RequestContext:
    """
    FastAPI dependency for getting request context.
    
    Use this as a dependency in route handlers:
    
        @router.get("/something")
        async def handler(ctx: RequestContext = Depends(get_request_context)):
            # ctx.user_id is the authenticated user
            pass
    """
    return await resolve_request_context(request, session, require_auth=True)


async def get_optional_request_context(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> RequestContext:
    """
    FastAPI dependency for optional auth context.
    
    Returns context even if not authenticated (is_authenticated will be False).
    """
    return await resolve_request_context(request, session, require_auth=False)
