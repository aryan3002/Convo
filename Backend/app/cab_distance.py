"""
Cab Distance Service - Google Maps Distance Matrix API Integration

This module provides route metrics (distance and duration) for cab bookings
using the Google Maps Distance Matrix API.

Usage:
    from .cab_distance import get_route_metrics
    
    result = await get_route_metrics("Phoenix Sky Harbor Airport", "Tempe, AZ")
    # Returns: {"distance_miles": 12.5, "duration_minutes": 18, "status": "OK"}
"""

import logging
import os
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

import httpx

from .core.config import get_settings

logger = logging.getLogger(__name__)

# Get settings for API key
settings = get_settings()

# Constants
METERS_PER_MILE = 1609.344
GOOGLE_DISTANCE_MATRIX_URL = "https://maps.googleapis.com/maps/api/distancematrix/json"


@dataclass
class RouteMetrics:
    """Result of a route calculation."""
    distance_miles: Decimal
    duration_minutes: int
    status: str = "OK"
    error_message: Optional[str] = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "distance_miles": float(self.distance_miles),
            "duration_minutes": self.duration_minutes,
            "status": self.status,
            "error_message": self.error_message,
        }


class RouteError(Exception):
    """Exception raised when route calculation fails."""
    def __init__(self, message: str, status: str = "ERROR"):
        self.message = message
        self.status = status
        super().__init__(message)


async def get_route_metrics(
    pickup_text: str,
    drop_text: str,
    api_key: Optional[str] = None,
) -> RouteMetrics:
    """
    Calculate distance and duration between two locations using Google Maps Distance Matrix API.
    
    Args:
        pickup_text: Pickup location (address or place name)
        drop_text: Drop-off location (address or place name)
        api_key: Google Maps API key (optional, defaults to GOOGLE_MAPS_API_KEY env var)
    
    Returns:
        RouteMetrics with distance_miles and duration_minutes
    
    Raises:
        RouteError: If API call fails or locations are invalid
    
    Example:
        >>> result = await get_route_metrics("LAX Airport", "Downtown Los Angeles")
        >>> print(f"{result.distance_miles} miles, {result.duration_minutes} minutes")
        18.5 miles, 25 minutes
    """
    # Get API key from settings
    api_key = api_key or settings.google_maps_api_key
    if not api_key:
        logger.error("GOOGLE_MAPS_API_KEY not configured")
        raise RouteError(
            "Distance calculation service is not configured. Please contact support.",
            status="CONFIG_ERROR"
        )
    
    # Validate inputs
    if not pickup_text or not pickup_text.strip():
        raise RouteError("Pickup location is required", status="INVALID_PICKUP")
    if not drop_text or not drop_text.strip():
        raise RouteError("Drop-off location is required", status="INVALID_DROP")
    
    pickup_text = pickup_text.strip()
    drop_text = drop_text.strip()
    
    # Build request
    params = {
        "origins": pickup_text,
        "destinations": drop_text,
        "units": "imperial",  # Get miles directly
        "key": api_key,
    }
    
    logger.info(f"Calculating route: '{pickup_text}' -> '{drop_text}'")
    
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(GOOGLE_DISTANCE_MATRIX_URL, params=params)
            response.raise_for_status()
            
            data = response.json()
            
            # Check API-level status
            api_status = data.get("status", "UNKNOWN")
            if api_status != "OK":
                logger.warning(f"Distance Matrix API error: {api_status}")
                raise RouteError(
                    _get_api_error_message(api_status),
                    status=api_status
                )
            
            # Parse response
            rows = data.get("rows", [])
            if not rows:
                raise RouteError("No route found between locations", status="NO_RESULTS")
            
            elements = rows[0].get("elements", [])
            if not elements:
                raise RouteError("No route found between locations", status="NO_RESULTS")
            
            element = elements[0]
            element_status = element.get("status", "UNKNOWN")
            
            if element_status != "OK":
                logger.warning(f"Route element status: {element_status}")
                raise RouteError(
                    _get_element_error_message(element_status),
                    status=element_status
                )
            
            # Extract distance and duration
            distance_data = element.get("distance", {})
            duration_data = element.get("duration", {})
            
            # Distance in meters -> miles
            distance_meters = distance_data.get("value", 0)
            distance_miles = Decimal(str(distance_meters)) / Decimal(str(METERS_PER_MILE))
            distance_miles = distance_miles.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            
            # Duration in seconds -> minutes (rounded up)
            duration_seconds = duration_data.get("value", 0)
            duration_minutes = (duration_seconds + 59) // 60  # Round up
            
            logger.info(
                f"Route calculated: {distance_miles} miles, {duration_minutes} minutes"
            )
            
            return RouteMetrics(
                distance_miles=distance_miles,
                duration_minutes=duration_minutes,
                status="OK",
            )
            
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error from Distance Matrix API: {e}")
        raise RouteError(
            "Distance calculation service is temporarily unavailable",
            status="HTTP_ERROR"
        )
    except httpx.RequestError as e:
        logger.error(f"Request error to Distance Matrix API: {e}")
        raise RouteError(
            "Unable to connect to distance calculation service",
            status="CONNECTION_ERROR"
        )
    except RouteError:
        raise  # Re-raise RouteErrors as-is
    except Exception as e:
        logger.exception(f"Unexpected error in get_route_metrics: {e}")
        raise RouteError(
            "An unexpected error occurred while calculating the route",
            status="INTERNAL_ERROR"
        )


def _get_api_error_message(status: str) -> str:
    """Get user-friendly message for API-level errors."""
    messages = {
        "INVALID_REQUEST": "Invalid request. Please check the pickup and drop-off locations.",
        "MAX_ELEMENTS_EXCEEDED": "Too many locations requested. Please try again.",
        "MAX_DIMENSIONS_EXCEEDED": "Too many locations requested. Please try again.",
        "OVER_DAILY_LIMIT": "Distance calculation limit reached. Please try again later.",
        "OVER_QUERY_LIMIT": "Too many requests. Please wait a moment and try again.",
        "REQUEST_DENIED": "Distance calculation service is not available.",
        "UNKNOWN_ERROR": "An unknown error occurred. Please try again.",
    }
    return messages.get(status, f"Distance calculation failed: {status}")


def _get_element_error_message(status: str) -> str:
    """Get user-friendly message for element-level errors."""
    messages = {
        "NOT_FOUND": "One or both locations could not be found. Please check the addresses.",
        "ZERO_RESULTS": "No route found between the locations. They may be too far apart or in different regions.",
        "MAX_ROUTE_LENGTH_EXCEEDED": "The route is too long to calculate. Please choose closer locations.",
    }
    return messages.get(status, f"Route calculation failed: {status}")


# ============================================================================
# MOCK FUNCTION FOR TESTING (without API key)
# ============================================================================

async def get_route_metrics_mock(
    pickup_text: str,
    drop_text: str,
) -> RouteMetrics:
    """
    Mock implementation for testing without Google Maps API.
    
    Uses simple heuristics to estimate distance based on location names.
    NOT FOR PRODUCTION USE.
    """
    # Common test routes with realistic distances
    test_routes = {
        ("phoenix sky harbor airport", "tempe"): (12.5, 18),
        ("phoenix sky harbor airport", "scottsdale"): (15.2, 22),
        ("phoenix sky harbor airport", "downtown phoenix"): (8.3, 12),
        ("lax", "downtown los angeles"): (18.5, 35),
        ("lax", "santa monica"): (12.8, 25),
        ("jfk", "manhattan"): (18.0, 45),
        ("sfo", "downtown san francisco"): (14.0, 25),
    }
    
    # Normalize inputs
    pickup_lower = pickup_text.lower().strip()
    drop_lower = drop_text.lower().strip()
    
    # Check known routes
    for (p, d), (miles, mins) in test_routes.items():
        if p in pickup_lower and d in drop_lower:
            return RouteMetrics(
                distance_miles=Decimal(str(miles)),
                duration_minutes=mins,
                status="OK",
            )
        # Check reverse direction
        if d in pickup_lower and p in drop_lower:
            return RouteMetrics(
                distance_miles=Decimal(str(miles)),
                duration_minutes=mins,
                status="OK",
            )
    
    # Default: Generate a plausible random-ish distance
    # In production, this would fail - but for testing, return something reasonable
    import hashlib
    combined = f"{pickup_lower}:{drop_lower}"
    hash_val = int(hashlib.md5(combined.encode()).hexdigest()[:8], 16)
    
    # Distance between 5 and 50 miles
    distance_miles = Decimal(str(5 + (hash_val % 450) / 10))
    # Duration: roughly 2 minutes per mile (city driving)
    duration_minutes = int(distance_miles * 2)
    
    return RouteMetrics(
        distance_miles=distance_miles,
        duration_minutes=duration_minutes,
        status="OK",
    )
