"""
Request Context Resolution Module

This module provides the SINGLE SOURCE OF TRUTH for identity resolution.
All API routes should use this module for authentication.

ARCHITECTURE:
    1. resolveRequestContext() extracts identity from request
    2. It verifies Clerk JWT tokens
    3. Returns a standardized RequestContext object
    4. All authorization checks use this context

AUTH METHOD:
    - JWT Bearer token verified against Clerk's public keys
    - NO fallback to headers or dev-users
"""

import logging
from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING

from fastapi import Request, HTTPException, status, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .db import get_session

# Deferred import to avoid circular dependency
if TYPE_CHECKING:
    from ..models import Shop, ShopMember, ShopMemberRole

logger = logging.getLogger(__name__)


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
    
    # Verify JWT Bearer token (only method - Clerk authentication)
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        try:
            from ..clerk_auth import verify_clerk_token
            user_data = verify_clerk_token(token)
            user_id = user_data.get("sub")
            if user_id:
                auth_method = "jwt"
                logger.debug(f"Auth via Clerk JWT: {user_id}")
        except Exception as e:
            logger.warning(f"JWT verification failed: {e}")
            if require_auth:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid or expired token. Please sign in again.",
                    headers={"WWW-Authenticate": "Bearer"},
                )
    
    # Check if we got a user
    if not user_id:
        if require_auth:
            logger.warning("Authentication failed: No valid JWT token found")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required. Please sign in.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return RequestContext(
            user_id="",
            auth_method="none",
            is_authenticated=False,
        )
    
    # Build the context with access info
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
    # Import here to avoid circular dependency
    from ..models import ShopMember
    
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
    allowed_roles: list["ShopMemberRole"] | None = None,
) -> str:
    """
    Check if the user has access to a specific shop.
    
    This is the ONE authorization rule for shop access:
    - User must be a member of the shop
    - If allowed_roles specified, user must have one of those roles
    
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
    # Import at runtime to avoid circular dependency
    from ..models import ShopMemberRole as SMR
    
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
        # Normalize role comparison - use local import SMR
        allowed_values = [r.value if isinstance(r, SMR) else r for r in allowed_roles]
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
