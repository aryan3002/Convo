"""
Phase 4: Entry Points & Routing Tests

Tests for:
1. Slug-scoped routes (/s/{slug}/...)
2. Voice Twilio To resolution (strict, no fallback)
3. Legacy route deprecation warnings
4. Shop info endpoint

Run with: pytest tests/test_phase4_routing.py -v
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timezone

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ────────────────────────────────────────────────────────────────
# Fixtures
# ────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_shop_context():
    """Mock ShopContext for testing."""
    from app.tenancy import ShopContext
    return ShopContext(
        shop_id=1,
        shop_slug="bishops-tempe",
        shop_name="Bishops Tempe",
        timezone="America/Phoenix",
    )


@pytest.fixture
def mock_db_session():
    """Mock async database session."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    return session


# ────────────────────────────────────────────────────────────────
# Test: Slug Resolution Dependency
# ────────────────────────────────────────────────────────────────

class TestSlugResolution:
    """Tests for get_shop_context_from_slug dependency."""
    
    @pytest.mark.asyncio
    async def test_valid_slug_returns_context(self, mock_shop_context, mock_db_session):
        """Valid slug should return ShopContext."""
        from app.routes_scoped import get_shop_context_from_slug
        
        with patch('app.routes_scoped.resolve_shop_from_slug', new_callable=AsyncMock) as mock_resolve:
            mock_resolve.return_value = mock_shop_context
            
            ctx = await get_shop_context_from_slug("bishops-tempe", mock_db_session)
            
            assert ctx.shop_id == 1
            assert ctx.shop_slug == "bishops-tempe"
            mock_resolve.assert_called_once_with(mock_db_session, "bishops-tempe")
    
    @pytest.mark.asyncio
    async def test_invalid_slug_raises_404(self, mock_db_session):
        """Invalid slug should raise 404."""
        from app.routes_scoped import get_shop_context_from_slug
        from fastapi import HTTPException
        
        with patch('app.routes_scoped.resolve_shop_from_slug', new_callable=AsyncMock) as mock_resolve:
            mock_resolve.return_value = None  # Shop not found
            
            with pytest.raises(HTTPException) as exc_info:
                await get_shop_context_from_slug("nonexistent-shop", mock_db_session)
            
            assert exc_info.value.status_code == 404
            assert "Shop not found" in str(exc_info.value.detail)


# ────────────────────────────────────────────────────────────────
# Test: Voice Twilio To Resolution
# ────────────────────────────────────────────────────────────────

class TestVoiceTwilioResolution:
    """Tests for voice.py strict Twilio To resolution."""
    
    def test_session_initial_shop_id_is_none(self):
        """New sessions should have shop_id=None (not legacy default)."""
        from app.voice import get_session, CALL_SESSIONS
        
        # Clear any existing session
        CALL_SESSIONS.clear()
        
        session = get_session("test-call-sid")
        
        # PHASE 4: shop_id must be None until resolved
        assert session["shop_id"] is None
    
    @pytest.mark.asyncio
    async def test_voice_endpoint_without_valid_to_returns_error_twiml(self):
        """Voice endpoint should return error TwiML if To number doesn't resolve."""
        from app.voice import twilio_voice
        from unittest.mock import MagicMock
        
        # Mock request with unrecognized To number
        mock_request = MagicMock()
        mock_request.form = AsyncMock(return_value={
            "CallSid": "test-call-sid-123",
            "To": "+15551234567",  # Unknown number
        })
        
        # Mock Twilio signature verification to pass
        with patch('app.voice.verify_twilio_signature', return_value=True):
            with patch('app.voice.resolve_shop_from_twilio_to', new_callable=AsyncMock) as mock_resolve:
                mock_resolve.return_value = None  # Shop not found
                
                response = await twilio_voice(mock_request)
                
                # Should return error TwiML with hangup
                assert response.status_code == 200
                body = response.body.decode() if hasattr(response.body, 'decode') else str(response.body)
                assert "not configured" in body.lower() or "Hangup" in body


# ────────────────────────────────────────────────────────────────
# Test: Scoped Routes Response Format
# ────────────────────────────────────────────────────────────────

class TestScopedRoutesResponse:
    """Tests for scoped route responses including shop_slug."""
    
    @pytest.mark.asyncio
    async def test_shop_info_endpoint_returns_context(self, mock_shop_context):
        """Shop info endpoint should return shop context fields."""
        from app.routes_scoped import scoped_shop_info
        
        result = await scoped_shop_info(mock_shop_context)
        
        assert result["shop_id"] == 1
        assert result["shop_slug"] == "bishops-tempe"
        assert result["shop_name"] == "Bishops Tempe"
        assert result["timezone"] == "America/Phoenix"
    
    def test_scoped_response_models_include_shop_slug(self):
        """Scoped response models should include shop_slug field."""
        from app.routes_scoped import ScopedChatResponse, ScopedOwnerChatResponse
        
        # Check that shop_slug is a valid field
        assert "shop_slug" in ScopedChatResponse.model_fields
        assert "shop_name" in ScopedChatResponse.model_fields
        assert "shop_slug" in ScopedOwnerChatResponse.model_fields
        assert "shop_name" in ScopedOwnerChatResponse.model_fields


# ────────────────────────────────────────────────────────────────
# Test: Routes Registration
# ────────────────────────────────────────────────────────────────

class TestRoutesRegistration:
    """Tests for route registration in main app."""
    
    def test_scoped_routes_registered(self):
        """Scoped routes should be registered in main app."""
        from app.main import app
        
        route_paths = [r.path for r in app.routes]
        
        assert "/s/{slug}/chat" in route_paths
        assert "/s/{slug}/owner/chat" in route_paths
        assert "/s/{slug}/services" in route_paths
        assert "/s/{slug}/stylists" in route_paths
        assert "/s/{slug}/info" in route_paths
    
    def test_legacy_routes_marked_deprecated(self):
        """Legacy /chat and /owner/chat should be marked deprecated."""
        from app.main import app
        
        deprecated_paths = []
        for route in app.routes:
            if hasattr(route, 'deprecated') and route.deprecated:
                deprecated_paths.append(route.path)
        
        assert "/chat" in deprecated_paths
        assert "/owner/chat" in deprecated_paths


# ────────────────────────────────────────────────────────────────
# Test: Voice Handler Shop ID Checks
# ────────────────────────────────────────────────────────────────

class TestVoiceHandlerShopIdChecks:
    """Tests for shop_id validation in voice handlers."""
    
    @pytest.mark.asyncio
    async def test_handle_get_service_fails_without_shop_id(self):
        """handle_get_service should fail gracefully without shop_id."""
        from app.voice import handle_get_service, update_session, get_session, CALL_SESSIONS
        
        # Clear and create session without shop_id
        CALL_SESSIONS.clear()
        session = get_session("test-call-no-shop")
        assert session["shop_id"] is None
        
        # Call handler - should return error TwiML
        response = await handle_get_service("test-call-no-shop", "haircut")
        
        twiml_str = str(response)
        assert "error" in twiml_str.lower() or "Hangup" in twiml_str
    
    @pytest.mark.asyncio
    async def test_handle_get_date_fails_without_shop_id(self):
        """handle_get_date should fail gracefully without shop_id."""
        from app.voice import handle_get_date, get_session, CALL_SESSIONS
        
        # Clear and create session without shop_id
        CALL_SESSIONS.clear()
        session = get_session("test-call-no-shop-2")
        assert session["shop_id"] is None
        
        # Call handler - should return error TwiML
        response = await handle_get_date("test-call-no-shop-2", "tomorrow")
        
        twiml_str = str(response)
        assert "error" in twiml_str.lower() or "Hangup" in twiml_str


# ────────────────────────────────────────────────────────────────
# Test: No Legacy Fallback in Production Routes
# ────────────────────────────────────────────────────────────────

class TestNoLegacyFallback:
    """Tests to ensure no silent fallback to shop_id=1."""
    
    def test_voice_py_no_legacy_fallback_import(self):
        """voice.py should not import LEGACY_DEFAULT_SHOP_ID."""
        import ast
        
        voice_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "app", "voice.py"
        )
        
        with open(voice_path, "r") as f:
            content = f.read()
        
        # Should NOT have LEGACY_DEFAULT_SHOP_ID import
        assert "LEGACY_DEFAULT_SHOP_ID" not in content, \
            "voice.py should not use LEGACY_DEFAULT_SHOP_ID - Phase 4 requires strict resolution"
    
    def test_routes_scoped_uses_strict_resolution(self):
        """routes_scoped.py should use strict resolution (no fallback)."""
        import ast
        
        routes_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "app", "routes_scoped.py"
        )
        
        with open(routes_path, "r") as f:
            content = f.read()
        
        # Should NOT have get_shop_context (fallback) - should use resolve_shop_from_slug
        assert "get_shop_context" not in content or "get_shop_context_from_slug" in content, \
            "routes_scoped.py should use strict slug resolution"
        
        # Should have 404 error handling
        assert "404" in content or "HTTP_404_NOT_FOUND" in content, \
            "routes_scoped.py should return 404 for invalid slugs"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
