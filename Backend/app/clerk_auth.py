"""
Clerk Authentication Module - JWT Verification for FastAPI Backend

This module provides JWT token verification using PyJWT with Clerk's JWKS.
It handles:
- Fetching public keys from Clerk's API
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
import json
from functools import lru_cache
from typing import Optional

from fastapi import HTTPException, Header, Depends, status
import httpx

from .core.config import get_settings

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def fetch_clerk_jwks() -> dict:
    """
    Fetch JWKS from Clerk's API with authentication.
    
    Clerk's JWKS endpoint at api.clerk.com requires the secret key.
    This is cached to avoid repeated requests.
    
    Returns:
        dict: The JWKS response containing public keys
    """
    settings = get_settings()
    url = "https://api.clerk.com/v1/jwks"
    
    try:
        # Use httpx instead of urllib - less likely to be blocked by Cloudflare
        with httpx.Client(timeout=10.0) as client:
            response = client.get(
                url,
                headers={
                    'Authorization': f'Bearer {settings.clerk_secret_key}',
                    'User-Agent': 'Convo-Backend/1.0',
                }
            )
            response.raise_for_status()
            jwks_data = response.json()
            logger.info(f"Successfully fetched JWKS from Clerk API")
            return jwks_data
            
    except httpx.HTTPStatusError as e:
        error_body = e.response.text if e.response else 'No error body'
        logger.error(f"HTTP {e.response.status_code} fetching JWKS: {error_body}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Unable to fetch Clerk JWKS: HTTP Error {e.response.status_code}"
        )
    except Exception as e:
        logger.error(f"Failed to fetch JWKS from Clerk: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Unable to fetch Clerk JWKS: {str(e)}"
        )


def verify_clerk_token(token: str) -> dict:
    """
    Verify a Clerk JWT token and return the decoded payload.
    
    This function:
    1. Fetches the signing keys from Clerk's JWKS endpoint (cached)
    2. Verifies the token signature using RS256
    3. Validates the issuer matches your Clerk domain
    4. Validates the token is not expired
    
    Args:
        token: The JWT token from the Authorization header
    
    Returns:
        Decoded token payload as dict with user information
        
    Raises:
        HTTPException 401: If token is invalid, expired, or signature doesn't match
        
    Example:
        token = "eyJhbGciOiJSUzI1NiIsImtpZCI6ImtleTEifQ..."
        payload = verify_clerk_token(token)
        user_id = payload["sub"]  # Clerk user ID like "user_2a1b3c4d5e6f"
    """
    try:
        settings = get_settings()
        
        # Fetch JWKS from Clerk API (cached)
        jwks_data = fetch_clerk_jwks()
        
        # Get the key ID from token header
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get('kid')
        
        if not kid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token header missing key ID (kid)",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Find the matching key in JWKS
        signing_key = None
        for key in jwks_data.get('keys', []):
            if key.get('kid') == kid:
                # PyJWT's PyJWK handles JWK to key conversion
                try:
                    from jwt import PyJWK
                    signing_key = PyJWK.from_dict(key).key
                except ImportError:
                    # Fallback: manually construct key from JWK (for older PyJWT versions)
                    # This should not happen with modern jwt library
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="Unable to import PyJWT utilities"
                    )
                break
        
        if not signing_key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"No matching key found for kid: {kid}",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Decode and verify the token
        # IMPORTANT: issuer MUST match your Clerk domain for security
        issuer = f"https://{settings.clerk_frontend_api}"
        
        # First, decode without verification to see what's in the token
        try:
            unverified_payload = jwt.decode(token, options={"verify_signature": False})
            token_issuer = unverified_payload.get('iss', 'MISSING')
            token_user = unverified_payload.get('sub', 'MISSING')
            
            logger.info(f"Incoming JWT - issuer: '{token_issuer}', user_id: '{token_user}'")
            logger.info(f"Expected issuer: '{issuer}'")
        except Exception as e:
            logger.warning(f"Could not decode unverified payload: {e}")
            token_issuer = None
            token_user = None
        
        decoded = jwt.decode(
            token,
            signing_key,
            algorithms=["RS256"],
            issuer=issuer,
            options={
                "verify_signature": True,
                "verify_exp": True,
                "verify_iss": True,
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
        # Try to provide more debugging info
        try:
            unverified = jwt.decode(token, options={"verify_signature": False})
            logger.warning(f"Token issuer: {unverified.get('iss')}, Expected: https://{settings.clerk_frontend_api}")
            logger.warning(f"Token sub (user_id): {unverified.get('sub')}")
        except:
            pass
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e
        
    except Exception as e:
        # Catch any other errors (including JWKS fetch failures)
        logger.error(f"Token verification error: {str(e)}")
        if isinstance(e, HTTPException):
            raise
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token verification failed: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
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
