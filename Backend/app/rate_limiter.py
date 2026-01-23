"""
Rate Limiting Middleware

Phase 3: RouterGPT Integration

This module provides rate limiting for RouterGPT endpoints to prevent abuse
and manage API costs.

Rate Limits:
- /router/search-by-location: 20 requests per minute per IP
- /router/delegate: 10 requests per minute per IP

Usage:
    from .rate_limiter import rate_limit_dependency
    
    @app.post("/router/search")
    async def search(request: Request, _: None = Depends(rate_limit_dependency(20))):
        ...
"""

import logging
import time
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, Tuple

from fastapi import HTTPException, Request, status

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────
# In-Memory Rate Limiter (Simple Implementation)
# ────────────────────────────────────────────────────────────────

class RateLimiter:
    """
    Simple in-memory rate limiter using sliding window.
    
    For production with multiple servers, consider Redis-based rate limiting.
    """
    
    def __init__(self):
        # Structure: {ip_address: [(timestamp, endpoint), ...]}
        self.requests: Dict[str, list] = defaultdict(list)
        self.cleanup_interval = 300  # Cleanup every 5 minutes
        self.last_cleanup = time.time()
    
    def _get_client_ip(self, request: Request) -> str:
        """
        Extract client IP from request.
        
        Checks X-Forwarded-For header first (for proxied requests),
        then falls back to client.host.
        """
        # Check X-Forwarded-For header (common with reverse proxies)
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            # X-Forwarded-For can contain multiple IPs, take the first one
            return forwarded.split(",")[0].strip()
        
        # Fallback to direct client IP
        if request.client:
            return request.client.host
        
        return "unknown"
    
    def _cleanup_old_requests(self):
        """Remove requests older than 1 hour to prevent memory bloat."""
        current_time = time.time()
        
        # Only cleanup periodically
        if current_time - self.last_cleanup < self.cleanup_interval:
            return
        
        cutoff = current_time - 3600  # 1 hour ago
        
        for ip in list(self.requests.keys()):
            self.requests[ip] = [
                (ts, endpoint) 
                for ts, endpoint in self.requests[ip] 
                if ts > cutoff
            ]
            
            # Remove IP if no recent requests
            if not self.requests[ip]:
                del self.requests[ip]
        
        self.last_cleanup = current_time
        logger.debug(f"Rate limiter cleanup: {len(self.requests)} IPs tracked")
    
    def check_rate_limit(
        self,
        request: Request,
        max_requests: int,
        window_seconds: int = 60,
        endpoint: str = None
    ) -> Tuple[bool, dict]:
        """
        Check if request is within rate limit.
        
        Args:
            request: FastAPI request object
            max_requests: Maximum requests allowed in window
            window_seconds: Time window in seconds (default: 60)
            endpoint: Optional endpoint identifier for per-endpoint limits
        
        Returns:
            (is_allowed, metadata) tuple
            metadata contains: remaining, reset_time, total_requests
        """
        self._cleanup_old_requests()
        
        client_ip = self._get_client_ip(request)
        current_time = time.time()
        window_start = current_time - window_seconds
        
        # Get requests for this IP in the time window
        if endpoint:
            # Filter by endpoint if specified
            recent_requests = [
                ts for ts, ep in self.requests[client_ip]
                if ts > window_start and ep == endpoint
            ]
        else:
            # All endpoints
            recent_requests = [
                ts for ts, _ in self.requests[client_ip]
                if ts > window_start
            ]
        
        request_count = len(recent_requests)
        remaining = max(0, max_requests - request_count)
        is_allowed = request_count < max_requests
        
        # Calculate reset time (when oldest request in window expires)
        if recent_requests:
            oldest_request = min(recent_requests)
            reset_time = oldest_request + window_seconds
        else:
            reset_time = current_time + window_seconds
        
        metadata = {
            "remaining": remaining,
            "reset_time": int(reset_time),
            "total_requests": request_count,
            "limit": max_requests,
            "window_seconds": window_seconds,
        }
        
        # Record this request if allowed
        if is_allowed:
            endpoint_name = endpoint or request.url.path
            self.requests[client_ip].append((current_time, endpoint_name))
        
        return is_allowed, metadata


# Global rate limiter instance
_rate_limiter = RateLimiter()


# ────────────────────────────────────────────────────────────────
# FastAPI Dependencies
# ────────────────────────────────────────────────────────────────

def rate_limit_dependency(max_requests: int, window_seconds: int = 60):
    """
    Create a rate limit dependency for FastAPI routes.
    
    Usage:
        @app.get("/api/endpoint", dependencies=[Depends(rate_limit_dependency(20))])
        async def my_endpoint():
            ...
    
    Args:
        max_requests: Maximum requests allowed in window
        window_seconds: Time window in seconds (default: 60)
    
    Returns:
        FastAPI dependency function
    """
    async def dependency(request: Request):
        endpoint = request.url.path
        
        is_allowed, metadata = _rate_limiter.check_rate_limit(
            request=request,
            max_requests=max_requests,
            window_seconds=window_seconds,
            endpoint=endpoint
        )
        
        if not is_allowed:
            reset_time = datetime.fromtimestamp(metadata["reset_time"])
            retry_after = metadata["reset_time"] - int(time.time())
            
            logger.warning(
                f"[RATE_LIMIT] Blocked request from {_rate_limiter._get_client_ip(request)} "
                f"to {endpoint}: {metadata['total_requests']}/{metadata['limit']} "
                f"in {metadata['window_seconds']}s window"
            )
            
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "error": "Rate limit exceeded",
                    "message": f"Too many requests. Limit: {max_requests} per {window_seconds}s",
                    "retry_after": retry_after,
                    "reset_time": reset_time.isoformat(),
                    "limit": max_requests,
                    "window_seconds": window_seconds,
                },
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(max_requests),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(metadata["reset_time"]),
                }
            )
        
        # Add rate limit headers to response (will be added by middleware)
        request.state.rate_limit_headers = {
            "X-RateLimit-Limit": str(metadata["limit"]),
            "X-RateLimit-Remaining": str(metadata["remaining"]),
            "X-RateLimit-Reset": str(metadata["reset_time"]),
        }
        
        return None
    
    return dependency


# ────────────────────────────────────────────────────────────────
# Middleware (Optional - for adding headers to all responses)
# ────────────────────────────────────────────────────────────────

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response


class RateLimitHeadersMiddleware(BaseHTTPMiddleware):
    """
    Middleware to add rate limit headers to responses.
    
    This runs after the rate limit dependency and adds the headers
    that were stored in request.state.
    """
    
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        
        # Add rate limit headers if they were set by the dependency
        if hasattr(request.state, "rate_limit_headers"):
            for header, value in request.state.rate_limit_headers.items():
                response.headers[header] = value
        
        return response


# ────────────────────────────────────────────────────────────────
# Utility Functions
# ────────────────────────────────────────────────────────────────

def get_rate_limit_stats() -> dict:
    """
    Get current rate limiter statistics.
    
    Returns:
        Dictionary with rate limiter stats
    """
    total_ips = len(_rate_limiter.requests)
    total_requests = sum(len(reqs) for reqs in _rate_limiter.requests.values())
    
    # Top IPs by request count
    top_ips = sorted(
        _rate_limiter.requests.items(),
        key=lambda x: len(x[1]),
        reverse=True
    )[:10]
    
    return {
        "total_tracked_ips": total_ips,
        "total_tracked_requests": total_requests,
        "top_ips": [
            {"ip": ip, "request_count": len(reqs)}
            for ip, reqs in top_ips
        ]
    }


def clear_rate_limits(ip_address: str = None):
    """
    Clear rate limits for a specific IP or all IPs.
    
    Args:
        ip_address: IP to clear, or None to clear all
    """
    if ip_address:
        if ip_address in _rate_limiter.requests:
            del _rate_limiter.requests[ip_address]
            logger.info(f"Cleared rate limits for IP: {ip_address}")
    else:
        _rate_limiter.requests.clear()
        logger.info("Cleared all rate limits")
