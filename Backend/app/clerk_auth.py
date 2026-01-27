"""
Clerk Authentication Module - JWT Verification for FastAPI Backend

This module provides JWT token verification using Clerk's public JWKS endpoint.
It handles:
- Fetching and caching public keys from Clerk
- Verifying JWT signatures using RS256
- Validating token expiration and issuer
- Extracting user information from verified tokens

Usage:
    from app.clerk_auth import verify_clerk_token, get_current_user_from_jwt
    from fastapi import Depends
    
    @router.get("/protected")
    async def protected_route(user_id: str = Depends(get_current_user_from_jwt)):
        return {"user": user_id}
"""

import logging
import jwt
import ssl
import certifi
from functools import lru_cache
from typing import Optional

from fastapi import HTTPException, Header, Depends, status
from jwt import PyJWKClient, PyJWKClientError

from .core.config import get_settings

logger = logging.getLogger(__name__)


def get_jwks_url() -> str:
    """Get the JWKS URL from Clerk frontend API domain."""
    settings = get_settings()
    if not settings.clerk_frontend_api:
        raise ValueError(
            "CLERK_FRONTEND_API environment variable is not set. "
            "Get this from your Clerk dashboard (usually something like 'myapp.clerk.accounts.dev')"
        )
    return f"https://{settings.clerk_frontend_api}/.well-known/jwks.json"


@lru_cache(maxsize=1)
def get_jwks_client() -> PyJWKClient:
    """
    Create and cache a PyJWKClient for JWKS verification.
    
    The client is cached to avoid repeated HTTP requests to Clerk's JWKS endpoint.
    In production, this typically fetches the keys once and caches them for hours.
    
    Uses certifi's SSL certificates to avoid certificate verification errors on macOS.
    """
    url = get_jwks_url()
    logger.info(f"Creating JWKS client for URL: {url}")
    
    # Create SSL context with certifi certificates (fixes macOS SSL issues)
    ssl_context = ssl.create_default_context(cafile=certifi.where())
    
    # PyJWKClient doesn't directly support ssl_context, but we can configure urllib
    # by setting the default SSL context for the process
    import urllib.request
    https_handler = urllib.request.HTTPSHandler(context=ssl_context)
    opener = urllib.request.build_opener(https_handler)
    urllib.request.install_opener(opener)
    
    return PyJWKClient(url)


def verify_clerk_token(token: str) -> dict:
    """
    Verify a Clerk JWT token and return the decoded payload.
    
    This function:
    1. Fetches the signing key from Clerk's JWKS endpoint
    2. Verifies the token signature using RS256
    3. Validates the issuer matches your Clerk domain
    4. Validates the token is not expired
    
    Args:
        token: The JWT token from the Authorization header
    
    Returns:
        Decoded token payload as dict with user information
        
    Raises:
        HTTPException 401: If token is invalid, expired, or signature doesn't match
        HTTPException 500: If Clerk JWKS endpoint is unreachable
        
    Example:
        token = "eyJhbGciOiJSUzI1NiIsImtpZCI6ImtleTEifQ..."
        payload = verify_clerk_token(token)
        user_id = payload["sub"]  # Clerk user ID like "user_2a1b3c4d5e6f"
    """
    try:
        settings = get_settings()
        
        # Get JWKS client (cached)
        jwks_client = get_jwks_client()
        
        # Extract signing key from JWKS
        # This fetches from Clerk's public endpoint and caches the keys
        signing_key = jwks_client.get_signing_key_from_jwt(token)
        
        # Decode and verify the token
        # IMPORTANT: issuer MUST match your Clerk domain for security
        issuer = f"https://{settings.clerk_frontend_api}"
        
        decoded = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=issuer,
            # Audience validation is optional - Clerk may not set it
            # If you set a custom audience in Clerk, add it here:
            # audience="your-custom-audience"
            options={
                "verify_signature": True,  # Always verify signature
                "verify_exp": True,        # Always check expiration
                "verify_iss": True,        # Always verify issuer
            }
        )
        
        logger.debug(f"Token verified for user: {decoded.get('sub')}")
        return decoded
        
    except jwt.ExpiredSignatureError as e:
        logger.warning(f"Token verification failed: Token has expired")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e
        
    except jwt.InvalidTokenError as e:
        logger.warning(f"Token verification failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e
        
    except PyJWKClientError as e:
        jwks_url = get_jwks_url()
        logger.error(f"JWKS client error (Clerk unreachable?): {str(e)}")
        logger.error(f"Attempted JWKS URL: {jwks_url}")
        logger.error(f"Check that CLERK_FRONTEND_API is correct: {get_settings().clerk_frontend_api}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Authentication service temporarily unavailable",
        ) from e


async def get_current_user_from_jwt(
    authorization: Optional[str] = Header(None),
) -> str:
    """
    Extract and verify Clerk user ID from JWT Authorization header.
    
    This is the main dependency for protecting routes with Clerk authentication.
    
    Args:
        authorization: The Authorization header (format: "Bearer <token>")
    
    Returns:
        The Clerk user ID (e.g., "user_2a1b3c4d5e6f")
    
    Raises:
        HTTPException 401: If token is missing, malformed, or invalid
        
    Usage in route handlers:
        @router.get("/protected")
        async def handler(user_id: str = Depends(get_current_user_from_jwt)):
            return {"user_id": user_id}
    """
    if not authorization:
        logger.warning("Authorization header missing")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Extract token from "Bearer <token>" format
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        logger.warning(f"Invalid Authorization header format: {authorization[:20]}...")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Authorization header format. Use: Bearer <token>",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    token = parts[1]
    
    # Verify token and extract user ID
    payload = verify_clerk_token(token)
    user_id = payload.get("sub")
    
    if not user_id:
        logger.error("Token verified but missing 'sub' claim")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token: missing user ID claim",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    logger.debug(f"Authenticated user: {user_id}")
    return user_id


async def get_optional_user_from_jwt(
    authorization: Optional[str] = Header(None),
) -> Optional[str]:
    """
    Extract user ID from JWT if present, without requiring it.
    
    Useful for endpoints that work both with and without authentication.
    
    Args:
        authorization: The Authorization header (optional)
    
    Returns:
        The Clerk user ID if valid token provided, None otherwise
        
    Usage:
        @router.get("/public-with-optional-auth")
        async def handler(
            user_id: Optional[str] = Depends(get_optional_user_from_jwt)
        ):
            if user_id:
                return {"message": "Hello authenticated user", "user": user_id}
            return {"message": "Hello anonymous user"}
    """
    if not authorization:
        return None
    
    try:
        return await get_current_user_from_jwt(authorization)
    except HTTPException:
        # Token was provided but invalid - return None for optional auth
        return None
