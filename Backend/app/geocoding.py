"""
Geocoding utility for converting addresses to coordinates.

Phase 3: RouterGPT Integration

This module provides address-to-coordinate conversion for location-based search.
It supports multiple geocoding providers with fallback logic.

Usage:
    from .geocoding import geocode_address
    
    lat, lon = await geocode_address("123 Mill Ave, Tempe, AZ 85281")
    if lat and lon:
        print(f"Coordinates: {lat}, {lon}")
"""

import logging
import os
from typing import Optional
import httpx

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────
# Haversine Distance Calculation
# ────────────────────────────────────────────────────────────────

from math import radians, sin, cos, sqrt, atan2

EARTH_RADIUS_MILES = 3959.0  # Earth's radius in miles


def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate the great-circle distance between two points using the Haversine formula.
    
    Args:
        lat1: Latitude of first point (degrees)
        lon1: Longitude of first point (degrees)
        lat2: Latitude of second point (degrees)
        lon2: Longitude of second point (degrees)
    
    Returns:
        Distance in miles
    """
    # Convert to radians
    lat1_rad = radians(lat1)
    lat2_rad = radians(lat2)
    delta_lat = radians(lat2 - lat1)
    delta_lon = radians(lon2 - lon1)
    
    # Haversine formula
    a = sin(delta_lat / 2) ** 2 + cos(lat1_rad) * cos(lat2_rad) * sin(delta_lon / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    
    return EARTH_RADIUS_MILES * c


# ────────────────────────────────────────────────────────────────
# Geocoding Functions
# ────────────────────────────────────────────────────────────────

async def geocode_with_nominatim(address: str) -> tuple[float | None, float | None]:
    """
    Geocode using OpenStreetMap Nominatim (free, no API key required).
    
    Note: This service has rate limits (~1 request per second).
    Only use for occasional lookups, not high-volume requests.
    
    Args:
        address: Full address string
    
    Returns:
        (latitude, longitude) tuple or (None, None) if geocoding fails
    """
    url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": address,
        "format": "json",
        "limit": 1,
    }
    headers = {
        "User-Agent": "Convo-BookingApp/1.0 (contact@convo.ai)",  # Required by Nominatim
    }
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, params=params, headers=headers)
            response.raise_for_status()
            
            data = response.json()
            if data and len(data) > 0:
                lat = float(data[0]["lat"])
                lon = float(data[0]["lon"])
                logger.info(f"Nominatim geocoded '{address}' to ({lat}, {lon})")
                return lat, lon
            
            logger.warning(f"Nominatim: No results for address '{address}'")
            return None, None
            
    except Exception as e:
        logger.error(f"Nominatim geocoding error for '{address}': {e}")
        return None, None


async def geocode_with_google(address: str) -> tuple[float | None, float | None]:
    """
    Geocode using Google Maps Geocoding API.
    
    Requires GOOGLE_MAPS_API_KEY environment variable.
    
    Args:
        address: Full address string
    
    Returns:
        (latitude, longitude) tuple or (None, None) if geocoding fails
    """
    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not api_key:
        logger.debug("Google Maps API key not configured, skipping Google geocoding")
        return None, None
    
    url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {
        "address": address,
        "key": api_key,
    }
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            
            data = response.json()
            if data.get("status") == "OK" and data.get("results"):
                location = data["results"][0]["geometry"]["location"]
                lat = location["lat"]
                lon = location["lng"]
                logger.info(f"Google geocoded '{address}' to ({lat}, {lon})")
                return lat, lon
            
            logger.warning(f"Google geocoding: {data.get('status')} for address '{address}'")
            return None, None
            
    except Exception as e:
        logger.error(f"Google geocoding error for '{address}': {e}")
        return None, None


async def geocode_address(address: str) -> tuple[float | None, float | None]:
    """
    Convert an address string to latitude/longitude coordinates.
    
    Tries multiple geocoding providers in order of preference:
    1. Google Maps API (if GOOGLE_MAPS_API_KEY is set)
    2. OpenStreetMap Nominatim (free fallback)
    
    Args:
        address: Full address string (e.g., "123 Mill Ave, Tempe, AZ 85281")
    
    Returns:
        (latitude, longitude) tuple, or (None, None) if all providers fail
    
    Example:
        lat, lon = await geocode_address("Tempe, AZ")
        # Returns approximately (33.4255, -111.9400)
    """
    if not address or len(address.strip()) < 3:
        logger.warning("geocode_address: Invalid or empty address")
        return None, None
    
    address = address.strip()
    
    # Try Google first (more accurate)
    lat, lon = await geocode_with_google(address)
    if lat is not None and lon is not None:
        return lat, lon
    
    # Fallback to Nominatim
    lat, lon = await geocode_with_nominatim(address)
    if lat is not None and lon is not None:
        return lat, lon
    
    logger.warning(f"All geocoding providers failed for address: '{address}'")
    return None, None


# ────────────────────────────────────────────────────────────────
# Known Location Lookup (for common cities)
# ────────────────────────────────────────────────────────────────

KNOWN_LOCATIONS = {
    # Arizona cities
    "tempe": (33.4255, -111.9400),
    "tempe, az": (33.4255, -111.9400),
    "tempe, arizona": (33.4255, -111.9400),
    "phoenix": (33.4484, -112.0740),
    "phoenix, az": (33.4484, -112.0740),
    "scottsdale": (33.4942, -111.9261),
    "scottsdale, az": (33.4942, -111.9261),
    "mesa": (33.4152, -111.8315),
    "mesa, az": (33.4152, -111.8315),
    "chandler": (33.3062, -111.8413),
    "chandler, az": (33.3062, -111.8413),
    "gilbert": (33.3528, -111.7890),
    "gilbert, az": (33.3528, -111.7890),
    # California cities
    "los angeles": (34.0522, -118.2437),
    "los angeles, ca": (34.0522, -118.2437),
    "san francisco": (37.7749, -122.4194),
    "san francisco, ca": (37.7749, -122.4194),
    "san diego": (32.7157, -117.1611),
    "san diego, ca": (32.7157, -117.1611),
    # Major US cities
    "new york": (40.7128, -74.0060),
    "new york, ny": (40.7128, -74.0060),
    "chicago": (41.8781, -87.6298),
    "chicago, il": (41.8781, -87.6298),
    "houston": (29.7604, -95.3698),
    "houston, tx": (29.7604, -95.3698),
    "dallas": (32.7767, -96.7970),
    "dallas, tx": (32.7767, -96.7970),
    "austin": (30.2672, -97.7431),
    "austin, tx": (30.2672, -97.7431),
    "seattle": (47.6062, -122.3321),
    "seattle, wa": (47.6062, -122.3321),
    "denver": (39.7392, -104.9903),
    "denver, co": (39.7392, -104.9903),
    "miami": (25.7617, -80.1918),
    "miami, fl": (25.7617, -80.1918),
    "atlanta": (33.7490, -84.3880),
    "atlanta, ga": (33.7490, -84.3880),
    "boston": (42.3601, -71.0589),
    "boston, ma": (42.3601, -71.0589),
}


def lookup_known_location(location_text: str) -> tuple[float | None, float | None]:
    """
    Look up coordinates for common cities without API call.
    
    Args:
        location_text: City name or "city, state" format
    
    Returns:
        (latitude, longitude) tuple or (None, None) if not found
    """
    normalized = location_text.strip().lower()
    
    if normalized in KNOWN_LOCATIONS:
        lat, lon = KNOWN_LOCATIONS[normalized]
        logger.debug(f"Known location lookup: '{location_text}' -> ({lat}, {lon})")
        return lat, lon
    
    return None, None


async def geocode_or_lookup(location_text: str) -> tuple[float | None, float | None]:
    """
    Get coordinates for a location, trying known locations first.
    
    This is the recommended function for user-provided location strings.
    It first checks the known locations cache, then falls back to geocoding APIs.
    
    Args:
        location_text: Location string (city name, address, etc.)
    
    Returns:
        (latitude, longitude) tuple or (None, None) if lookup fails
    """
    # Try known locations first (instant, no API call)
    lat, lon = lookup_known_location(location_text)
    if lat is not None:
        return lat, lon
    
    # Fall back to geocoding APIs
    return await geocode_address(location_text)
