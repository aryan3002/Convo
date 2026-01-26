"""
Core module - configuration, database, request context, and response formatting.
"""
from .config import get_settings
from .db import get_session, Base, engine, AsyncSessionLocal
from .request_context import (
    RequestContext,
    resolve_request_context,
    require_shop_access,
    get_request_context,
    get_optional_request_context,
    AuthenticationError,
    AuthorizationError,
)
from .responses import (
    ApiResponse,
    ErrorDetail,
    ErrorCodes,
    success_response,
    error_response,
)

__all__ = [
    # Config
    "get_settings",
    # Database
    "get_session",
    "Base",
    "engine", 
    "AsyncSessionLocal",
    # Request Context
    "RequestContext",
    "resolve_request_context",
    "require_shop_access",
    "get_request_context",
    "get_optional_request_context",
    "AuthenticationError",
    "AuthorizationError",
    # Responses
    "ApiResponse",
    "ErrorDetail",
    "ErrorCodes",
    "success_response",
    "error_response",
]
