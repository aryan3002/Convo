"""
Tests for cab_distance module.

Run with: pytest tests/test_cab_distance.py -v
"""

import pytest
from decimal import Decimal
from unittest.mock import patch, MagicMock, AsyncMock
import httpx

from app.cab_distance import (
    get_route_metrics,
    get_route_metrics_mock,
    RouteMetrics,
    RouteError,
    METERS_PER_MILE,
)


# ============================================================================
# MOCK RESPONSE DATA
# ============================================================================

MOCK_SUCCESS_RESPONSE = {
    "status": "OK",
    "rows": [
        {
            "elements": [
                {
                    "status": "OK",
                    "distance": {
                        "text": "12.5 mi",
                        "value": 20117  # meters (approximately 12.5 miles)
                    },
                    "duration": {
                        "text": "18 mins",
                        "value": 1080  # seconds
                    }
                }
            ]
        }
    ]
}

MOCK_NOT_FOUND_RESPONSE = {
    "status": "OK",
    "rows": [
        {
            "elements": [
                {
                    "status": "NOT_FOUND"
                }
            ]
        }
    ]
}

MOCK_API_ERROR_RESPONSE = {
    "status": "REQUEST_DENIED",
    "error_message": "The provided API key is invalid."
}


# ============================================================================
# UNIT TESTS - MOCK MODE
# ============================================================================

@pytest.mark.asyncio
async def test_get_route_metrics_mock_known_route():
    """Test mock function with known route."""
    result = await get_route_metrics_mock(
        "Phoenix Sky Harbor Airport",
        "Tempe, AZ"
    )
    
    assert result.status == "OK"
    assert result.distance_miles == Decimal("12.5")
    assert result.duration_minutes == 18


@pytest.mark.asyncio
async def test_get_route_metrics_mock_reverse_route():
    """Test mock function with reversed route."""
    result = await get_route_metrics_mock(
        "Tempe",
        "Phoenix Sky Harbor Airport"
    )
    
    assert result.status == "OK"
    assert result.distance_miles == Decimal("12.5")
    assert result.duration_minutes == 18


@pytest.mark.asyncio
async def test_get_route_metrics_mock_unknown_route():
    """Test mock function with unknown route generates plausible values."""
    result = await get_route_metrics_mock(
        "Some Random Place",
        "Another Random Place"
    )
    
    assert result.status == "OK"
    assert result.distance_miles >= Decimal("5")
    assert result.distance_miles <= Decimal("50")
    assert result.duration_minutes > 0


# ============================================================================
# UNIT TESTS - WITH MOCKED HTTP
# ============================================================================

@pytest.mark.asyncio
async def test_get_route_metrics_success():
    """Test successful route calculation with mocked API response."""
    
    # Create mock response with sync json() method
    mock_response = MagicMock()
    mock_response.json.return_value = MOCK_SUCCESS_RESPONSE
    mock_response.raise_for_status = MagicMock()
    
    with patch.dict('os.environ', {'GOOGLE_MAPS_API_KEY': 'test-key'}):
        with patch('httpx.AsyncClient') as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get.return_value = mock_response
            mock_instance.__aenter__.return_value = mock_instance
            mock_instance.__aexit__.return_value = None
            mock_client.return_value = mock_instance
            
            result = await get_route_metrics(
                "Phoenix Sky Harbor Airport",
                "Tempe, AZ"
            )
            
            assert result.status == "OK"
            # 20117 meters / 1609.344 = 12.50 miles (approximately)
            assert result.distance_miles == Decimal("12.50")
            assert result.duration_minutes == 18


@pytest.mark.asyncio
async def test_get_route_metrics_no_api_key():
    """Test error when API key is missing."""
    
    with patch.dict('os.environ', {}, clear=True):
        # Ensure GOOGLE_MAPS_API_KEY is not set
        import os
        if 'GOOGLE_MAPS_API_KEY' in os.environ:
            del os.environ['GOOGLE_MAPS_API_KEY']
        
        with pytest.raises(RouteError) as exc_info:
            await get_route_metrics("Origin", "Destination")
        
        assert exc_info.value.status == "CONFIG_ERROR"


@pytest.mark.asyncio
async def test_get_route_metrics_invalid_pickup():
    """Test error with empty pickup location."""
    
    with patch.dict('os.environ', {'GOOGLE_MAPS_API_KEY': 'test-key'}):
        with pytest.raises(RouteError) as exc_info:
            await get_route_metrics("", "Destination")
        
        assert exc_info.value.status == "INVALID_PICKUP"


@pytest.mark.asyncio
async def test_get_route_metrics_invalid_drop():
    """Test error with empty drop location."""
    
    with patch.dict('os.environ', {'GOOGLE_MAPS_API_KEY': 'test-key'}):
        with pytest.raises(RouteError) as exc_info:
            await get_route_metrics("Origin", "   ")
        
        assert exc_info.value.status == "INVALID_DROP"


@pytest.mark.asyncio
async def test_get_route_metrics_location_not_found():
    """Test error when location is not found."""
    
    mock_response = MagicMock()
    mock_response.json.return_value = MOCK_NOT_FOUND_RESPONSE
    mock_response.raise_for_status = MagicMock()
    
    with patch.dict('os.environ', {'GOOGLE_MAPS_API_KEY': 'test-key'}):
        with patch('httpx.AsyncClient') as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get.return_value = mock_response
            mock_instance.__aenter__.return_value = mock_instance
            mock_instance.__aexit__.return_value = None
            mock_client.return_value = mock_instance
            
            with pytest.raises(RouteError) as exc_info:
                await get_route_metrics("Invalid Location XYZ", "Destination")
            
            assert exc_info.value.status == "NOT_FOUND"


@pytest.mark.asyncio
async def test_get_route_metrics_api_error():
    """Test error when API returns error status."""
    
    mock_response = MagicMock()
    mock_response.json.return_value = MOCK_API_ERROR_RESPONSE
    mock_response.raise_for_status = MagicMock()
    
    with patch.dict('os.environ', {'GOOGLE_MAPS_API_KEY': 'test-key'}):
        with patch('httpx.AsyncClient') as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get.return_value = mock_response
            mock_instance.__aenter__.return_value = mock_instance
            mock_instance.__aexit__.return_value = None
            mock_client.return_value = mock_instance
            
            with pytest.raises(RouteError) as exc_info:
                await get_route_metrics("Origin", "Destination")
            
            assert exc_info.value.status == "REQUEST_DENIED"


# ============================================================================
# ROUTE METRICS DATACLASS TESTS
# ============================================================================

def test_route_metrics_to_dict():
    """Test RouteMetrics serialization."""
    metrics = RouteMetrics(
        distance_miles=Decimal("25.50"),
        duration_minutes=35,
        status="OK",
        error_message=None
    )
    
    result = metrics.to_dict()
    
    assert result["distance_miles"] == 25.50
    assert result["duration_minutes"] == 35
    assert result["status"] == "OK"
    assert result["error_message"] is None


def test_route_metrics_with_error():
    """Test RouteMetrics with error message."""
    metrics = RouteMetrics(
        distance_miles=Decimal("0"),
        duration_minutes=0,
        status="NOT_FOUND",
        error_message="Location not found"
    )
    
    result = metrics.to_dict()
    
    assert result["status"] == "NOT_FOUND"
    assert result["error_message"] == "Location not found"
