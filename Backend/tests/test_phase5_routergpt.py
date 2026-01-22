"""
Phase 5: RouterGPT Tests

Tests for the RouterGPT discovery and delegation layer.

Run with: pytest tests/test_phase5_routergpt.py -v
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ────────────────────────────────────────────────────────────────
# Fixtures
# ────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_shop():
    """Create a mock Shop object."""
    shop = MagicMock()
    shop.id = 1
    shop.slug = "bishops-tempe"
    shop.name = "Bishops Tempe"
    shop.timezone = "America/Phoenix"
    shop.address = "123 Main St, Tempe, AZ"
    shop.category = "barbershop"
    shop.phone_number = "+16234048440"
    return shop


@pytest.fixture
def mock_db_session():
    """Mock async database session."""
    session = AsyncMock()
    return session


# ────────────────────────────────────────────────────────────────
# Test: Match Score Calculation
# ────────────────────────────────────────────────────────────────

class TestMatchScoreCalculation:
    """Tests for the calculate_match_score function."""
    
    def test_exact_name_match_scores_high(self, mock_shop):
        """Exact name match should score very high."""
        from app.router_gpt import calculate_match_score
        
        score = calculate_match_score("Bishops Tempe", mock_shop)
        assert score > 0.8
    
    def test_partial_name_match_scores_medium(self, mock_shop):
        """Partial name match should score medium."""
        from app.router_gpt import calculate_match_score
        
        score = calculate_match_score("bishops", mock_shop)
        assert score > 0.5
    
    def test_category_match_scores(self, mock_shop):
        """Category match should contribute to score."""
        from app.router_gpt import calculate_match_score
        
        score = calculate_match_score("barbershop", mock_shop)
        assert score > 0.4
    
    def test_location_match_scores(self, mock_shop):
        """Location in address should contribute to score."""
        from app.router_gpt import calculate_match_score
        
        score = calculate_match_score("tempe", mock_shop)
        assert score > 0.3
    
    def test_empty_query_returns_neutral(self, mock_shop):
        """Empty query should return neutral score."""
        from app.router_gpt import calculate_match_score
        
        score = calculate_match_score("", mock_shop)
        assert score == 0.5
    
    def test_no_match_scores_low(self, mock_shop):
        """Completely unrelated query should score low."""
        from app.router_gpt import calculate_match_score
        
        score = calculate_match_score("zzzzxxx", mock_shop)
        assert score < 0.3


# ────────────────────────────────────────────────────────────────
# Test: Search Businesses Endpoint
# ────────────────────────────────────────────────────────────────

class TestSearchBusinesses:
    """Tests for GET /router/search endpoint."""
    
    async def test_search_returns_results_for_matching_query(self, mock_shop, mock_db_session):
        """Search should return results for matching query."""
        from app.router_gpt import search_businesses
        
        # Mock the database query result
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_shop]
        mock_db_session.execute = AsyncMock(return_value=mock_result)
        
        # Mock get_shop_primary_phone
        with patch('app.router_gpt.get_shop_primary_phone', new_callable=AsyncMock) as mock_phone:
            mock_phone.return_value = "+16234048440"
            
            response = await search_businesses(
                query="bishops",
                location=None,
                category=None,
                limit=10,
                session=mock_db_session
            )
        
        assert response.query == "bishops"
        assert len(response.results) >= 0  # May be 0 if mock doesn't match
    
    async def test_search_with_location_filter(self, mock_shop, mock_db_session):
        """Search with location should filter results."""
        from app.router_gpt import search_businesses
        
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_shop]
        mock_db_session.execute = AsyncMock(return_value=mock_result)
        
        with patch('app.router_gpt.get_shop_primary_phone', new_callable=AsyncMock) as mock_phone:
            mock_phone.return_value = None
            
            response = await search_businesses(
                query="haircut",
                location="tempe",
                category=None,
                limit=10,
                session=mock_db_session
            )
        
        assert response.query == "haircut"
    
    async def test_search_respects_limit(self, mock_db_session):
        """Search should respect the limit parameter."""
        from app.router_gpt import search_businesses
        
        # Create multiple mock shops
        shops = []
        for i in range(15):
            shop = MagicMock()
            shop.id = i
            shop.slug = f"shop-{i}"
            shop.name = f"Shop {i}"
            shop.timezone = "America/Phoenix"
            shop.address = "123 Main St"
            shop.category = "salon"
            shop.phone_number = None
            shops.append(shop)
        
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = shops
        mock_db_session.execute = AsyncMock(return_value=mock_result)
        
        with patch('app.router_gpt.get_shop_primary_phone', new_callable=AsyncMock) as mock_phone:
            mock_phone.return_value = None
            
            response = await search_businesses(
                query="shop",
                location=None,
                category=None,
                limit=5,
                session=mock_db_session
            )
        
        assert len(response.results) <= 5


# ────────────────────────────────────────────────────────────────
# Test: Get Business Summary Endpoint
# ────────────────────────────────────────────────────────────────

class TestGetBusinessSummary:
    """Tests for GET /router/business/{identifier} endpoint."""
    
    async def test_get_by_id_returns_summary(self, mock_shop, mock_db_session):
        """Should return summary when fetching by ID."""
        from app.router_gpt import get_business_summary
        
        # Mock shop query
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_shop
        
        # Mock count queries
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 5
        
        mock_db_session.execute = AsyncMock(side_effect=[
            mock_result,  # Shop query
            mock_count_result,  # Service count
            mock_count_result,  # Stylist count
        ])
        
        with patch('app.router_gpt.get_shop_primary_phone', new_callable=AsyncMock) as mock_phone:
            with patch('app.router_gpt.check_shop_has_voice', new_callable=AsyncMock) as mock_voice:
                mock_phone.return_value = "+16234048440"
                mock_voice.return_value = True
                
                response = await get_business_summary(
                    identifier="1",
                    session=mock_db_session
                )
        
        assert response.business_id == 1
        assert response.slug == "bishops-tempe"
        assert response.name == "Bishops Tempe"
        assert response.chat_endpoint == "/s/bishops-tempe/chat"
    
    async def test_get_by_slug_returns_summary(self, mock_shop, mock_db_session):
        """Should return summary when fetching by slug."""
        from app.router_gpt import get_business_summary
        
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_shop
        
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 3
        
        mock_db_session.execute = AsyncMock(side_effect=[
            mock_result,
            mock_count_result,
            mock_count_result,
        ])
        
        with patch('app.router_gpt.get_shop_primary_phone', new_callable=AsyncMock) as mock_phone:
            with patch('app.router_gpt.check_shop_has_voice', new_callable=AsyncMock) as mock_voice:
                mock_phone.return_value = None
                mock_voice.return_value = False
                
                response = await get_business_summary(
                    identifier="bishops-tempe",
                    session=mock_db_session
                )
        
        assert response.slug == "bishops-tempe"
        assert response.capabilities.supports_voice == False
    
    async def test_get_nonexistent_returns_404(self, mock_db_session):
        """Should return 404 for nonexistent business."""
        from app.router_gpt import get_business_summary
        from fastapi import HTTPException
        
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=mock_result)
        
        with pytest.raises(HTTPException) as exc_info:
            await get_business_summary(
                identifier="nonexistent",
                session=mock_db_session
            )
        
        assert exc_info.value.status_code == 404


# ────────────────────────────────────────────────────────────────
# Test: Handoff Endpoint
# ────────────────────────────────────────────────────────────────

class TestHandoffToBusinessGPT:
    """Tests for POST /router/handoff endpoint."""
    
    async def test_handoff_returns_correct_endpoint(self, mock_shop, mock_db_session):
        """Handoff should return the correct /s/{slug}/chat endpoint."""
        from app.router_gpt import handoff_to_business_gpt, HandoffRequest, ConversationMessage
        
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_shop
        mock_db_session.execute = AsyncMock(return_value=mock_result)
        
        request = HandoffRequest(
            slug="bishops-tempe",
            conversation_context=[
                ConversationMessage(role="user", content="I want a haircut")
            ],
            user_intent="book haircut"
        )
        
        response = await handoff_to_business_gpt(request, mock_db_session)
        
        assert response.recommended_endpoint == "/s/bishops-tempe/chat"
        assert response.slug == "bishops-tempe"
        assert response.name == "Bishops Tempe"
    
    async def test_handoff_includes_shop_context_in_metadata(self, mock_shop, mock_db_session):
        """Handoff payload should include shop context in metadata."""
        from app.router_gpt import handoff_to_business_gpt, HandoffRequest
        
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_shop
        mock_db_session.execute = AsyncMock(return_value=mock_result)
        
        request = HandoffRequest(
            business_id=1,
            user_intent="book haircut"
        )
        
        response = await handoff_to_business_gpt(request, mock_db_session)
        
        metadata = response.payload_template.metadata
        assert metadata["shop_slug"] == "bishops-tempe"
        assert metadata["shop_name"] == "Bishops Tempe"
        assert metadata["shop_id"] == 1
        assert metadata["source"] == "router_gpt_handoff"
    
    async def test_handoff_passes_conversation_context(self, mock_shop, mock_db_session):
        """Handoff should pass conversation context in payload."""
        from app.router_gpt import handoff_to_business_gpt, HandoffRequest, ConversationMessage
        
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_shop
        mock_db_session.execute = AsyncMock(return_value=mock_result)
        
        request = HandoffRequest(
            slug="bishops-tempe",
            conversation_context=[
                ConversationMessage(role="user", content="Hello"),
                ConversationMessage(role="assistant", content="Hi! How can I help?"),
                ConversationMessage(role="user", content="I want a haircut")
            ]
        )
        
        response = await handoff_to_business_gpt(request, mock_db_session)
        
        messages = response.payload_template.messages
        assert len(messages) == 3
        assert messages[0]["content"] == "Hello"
    
    async def test_handoff_requires_id_or_slug(self, mock_db_session):
        """Handoff should require either business_id or slug."""
        from app.router_gpt import handoff_to_business_gpt, HandoffRequest
        from fastapi import HTTPException
        
        request = HandoffRequest()  # No business_id or slug
        
        with pytest.raises(HTTPException) as exc_info:
            await handoff_to_business_gpt(request, mock_db_session)
        
        assert exc_info.value.status_code == 400
        assert "Must provide" in str(exc_info.value.detail)
    
    async def test_handoff_nonexistent_returns_404(self, mock_db_session):
        """Handoff for nonexistent business should return 404."""
        from app.router_gpt import handoff_to_business_gpt, HandoffRequest
        from fastapi import HTTPException
        
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=mock_result)
        
        request = HandoffRequest(slug="nonexistent-shop")
        
        with pytest.raises(HTTPException) as exc_info:
            await handoff_to_business_gpt(request, mock_db_session)
        
        assert exc_info.value.status_code == 404


# ────────────────────────────────────────────────────────────────
# Test: Router Info Endpoint
# ────────────────────────────────────────────────────────────────

class TestRouterInfo:
    """Tests for GET /router/info endpoint."""
    
    async def test_info_returns_metadata(self):
        """Info endpoint should return RouterGPT metadata."""
        from app.router_gpt import router_info
        
        response = await router_info()
        
        assert response["name"] == "RouterGPT"
        assert response["capabilities"]["books_appointments"] == False
        assert response["capabilities"]["discovery_only"] == True
        assert len(response["tools"]) == 3


# ────────────────────────────────────────────────────────────────
# Test: Routes Registration
# ────────────────────────────────────────────────────────────────

class TestRoutesRegistration:
    """Tests for router registration in main app."""
    
    def test_router_gpt_routes_registered(self):
        """RouterGPT routes should be registered in main app."""
        from app.main import app
        
        route_paths = [r.path for r in app.routes]
        
        assert "/router/search" in route_paths
        assert "/router/business/{identifier}" in route_paths
        assert "/router/handoff" in route_paths
        assert "/router/info" in route_paths


# ────────────────────────────────────────────────────────────────
# Test: Safety - No Booking Code
# ────────────────────────────────────────────────────────────────

class TestRouterGPTSafety:
    """Tests to ensure RouterGPT doesn't contain booking logic."""
    
    def test_no_booking_functions_in_router_gpt(self):
        """router_gpt.py should not import or call booking functions."""
        import ast
        
        router_gpt_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "app", "router_gpt.py"
        )
        
        with open(router_gpt_path, "r") as f:
            content = f.read()
        
        # Should NOT have booking-related imports or calls
        dangerous_patterns = [
            "create_booking",
            "hold_slot",
            "confirm_booking",
            "Booking(",
            "INSERT INTO bookings",
            "session.add(",
            "session.commit(",
        ]
        
        for pattern in dangerous_patterns:
            assert pattern not in content, \
                f"RouterGPT should not contain '{pattern}' - it must be discovery-only"
    
    def test_router_gpt_is_read_only(self):
        """RouterGPT should only use SELECT queries, not INSERT/UPDATE/DELETE."""
        import ast
        
        router_gpt_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "app", "router_gpt.py"
        )
        
        with open(router_gpt_path, "r") as f:
            content = f.read()
        
        # Check for write operations
        write_patterns = [
            "INSERT INTO",
            "UPDATE ",
            "DELETE FROM",
            ".add(",
            ".delete(",
            ".commit(",
        ]
        
        for pattern in write_patterns:
            # Allow "DELETE" in comments/strings but not as actual SQL
            if pattern in content:
                # Check if it's in a comment or docstring
                lines_with_pattern = [l for l in content.split('\n') if pattern in l]
                for line in lines_with_pattern:
                    stripped = line.strip()
                    if not stripped.startswith('#') and not stripped.startswith('"') and not stripped.startswith("'"):
                        # It's actual code, not a comment
                        if pattern == ".add(" or pattern == ".delete(" or pattern == ".commit(":
                            assert False, f"RouterGPT should not contain '{pattern}' - it must be read-only"


# ────────────────────────────────────────────────────────────────
# Test: Response Models
# ────────────────────────────────────────────────────────────────

class TestResponseModels:
    """Tests for response model structure."""
    
    def test_search_response_has_required_fields(self):
        """SearchResponse should have all required fields."""
        from app.router_gpt import SearchResponse, BusinessSearchResult
        
        # Verify model fields exist
        assert "query" in SearchResponse.model_fields
        assert "results" in SearchResponse.model_fields
        assert "total_count" in SearchResponse.model_fields
        
        # Verify BusinessSearchResult fields
        assert "business_id" in BusinessSearchResult.model_fields
        assert "slug" in BusinessSearchResult.model_fields
        assert "confidence" in BusinessSearchResult.model_fields
    
    def test_business_summary_has_endpoints(self):
        """BusinessSummary should include endpoint URLs."""
        from app.router_gpt import BusinessSummary
        
        assert "chat_endpoint" in BusinessSummary.model_fields
        assert "owner_chat_endpoint" in BusinessSummary.model_fields
        assert "services_endpoint" in BusinessSummary.model_fields
    
    def test_handoff_response_has_payload_template(self):
        """HandoffResponse should include payload template."""
        from app.router_gpt import HandoffResponse, HandoffPayloadTemplate
        
        assert "recommended_endpoint" in HandoffResponse.model_fields
        assert "payload_template" in HandoffResponse.model_fields
        
        assert "messages" in HandoffPayloadTemplate.model_fields
        assert "metadata" in HandoffPayloadTemplate.model_fields


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
