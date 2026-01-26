"""
Standardized API Response Module

Provides consistent response formatting across all API endpoints.

RESPONSE FORMAT:
    All API responses follow this structure:
    
    Success:
        {
            "data": <response data>,
            "status": "success"
        }
    
    Error:
        {
            "error": {
                "code": "ERROR_CODE",
                "message": "Human-readable message",
                "details": {...}  # Optional extra context
            },
            "status": "error"
        }

ERROR CODES:
    - AUTHENTICATION_REQUIRED: No valid auth credentials provided
    - AUTHORIZATION_DENIED: User doesn't have required permissions
    - NOT_FOUND: Resource not found
    - VALIDATION_ERROR: Request data failed validation
    - CONFLICT: Resource already exists or state conflict
    - INTERNAL_ERROR: Server-side error
"""

from typing import Any, Generic, Optional, TypeVar
from pydantic import BaseModel

T = TypeVar("T")


class ErrorDetail(BaseModel):
    """Structured error information."""
    code: str
    message: str
    details: Optional[dict[str, Any]] = None


class ApiResponse(BaseModel, Generic[T]):
    """
    Standardized API response wrapper.
    
    Usage:
        # Success response
        return ApiResponse(data={"id": 123, "name": "Test"}, status="success")
        
        # Error response
        return ApiResponse(
            error=ErrorDetail(
                code="NOT_FOUND",
                message="Shop not found",
                details={"slug": "invalid-slug"}
            ),
            status="error"
        )
    """
    data: Optional[T] = None
    error: Optional[ErrorDetail] = None
    status: str = "success"
    
    @classmethod
    def success(cls, data: T) -> "ApiResponse[T]":
        """Create a success response."""
        return cls(data=data, status="success")
    
    @classmethod
    def error(
        cls,
        code: str,
        message: str,
        details: Optional[dict] = None,
    ) -> "ApiResponse[None]":
        """Create an error response."""
        return cls(
            error=ErrorDetail(code=code, message=message, details=details),
            status="error"
        )


# ============================================================================
# COMMON ERROR CODES
# ============================================================================

class ErrorCodes:
    """Standard error codes for API responses."""
    
    # Authentication errors (401)
    AUTHENTICATION_REQUIRED = "AUTHENTICATION_REQUIRED"
    INVALID_TOKEN = "INVALID_TOKEN"
    TOKEN_EXPIRED = "TOKEN_EXPIRED"
    
    # Authorization errors (403)
    AUTHORIZATION_DENIED = "AUTHORIZATION_DENIED"
    INSUFFICIENT_ROLE = "INSUFFICIENT_ROLE"
    NOT_SHOP_MEMBER = "NOT_SHOP_MEMBER"
    
    # Not found errors (404)
    NOT_FOUND = "NOT_FOUND"
    SHOP_NOT_FOUND = "SHOP_NOT_FOUND"
    RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"
    
    # Validation errors (422)
    VALIDATION_ERROR = "VALIDATION_ERROR"
    INVALID_INPUT = "INVALID_INPUT"
    MISSING_FIELD = "MISSING_FIELD"
    
    # Conflict errors (409)
    CONFLICT = "CONFLICT"
    ALREADY_EXISTS = "ALREADY_EXISTS"
    STATE_CONFLICT = "STATE_CONFLICT"
    
    # Server errors (500)
    INTERNAL_ERROR = "INTERNAL_ERROR"
    DATABASE_ERROR = "DATABASE_ERROR"


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def success_response(data: Any) -> dict:
    """
    Create a standardized success response dict.
    
    Use this for simple responses where Pydantic model isn't needed.
    """
    return {"data": data, "status": "success"}


def error_response(
    code: str,
    message: str,
    details: Optional[dict] = None,
) -> dict:
    """
    Create a standardized error response dict.
    
    Use this for simple error responses.
    """
    response = {
        "error": {
            "code": code,
            "message": message,
        },
        "status": "error",
    }
    if details:
        response["error"]["details"] = details
    return response
