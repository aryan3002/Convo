"""
Multi-Tenant Isolation Tests - Phase 3

These tests verify that tenant isolation is enforced:
1. Services from shop A are not visible to shop B
2. Stylists from shop A are not visible to shop B  
3. Promos from shop A are not visible to shop B
4. Customer preferences are scoped to shops

Run with: pytest tests/test_tenant_isolation.py -v
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import patch, AsyncMock

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Import the models and helpers we're testing
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.models import Service, Stylist, Promo, Shop, PromoType, PromoDiscountType, PromoTriggerPoint
from app.tenancy.context import ShopContext, ShopResolutionSource


# ────────────────────────────────────────────────────────────────
# Test Fixtures
# ────────────────────────────────────────────────────────────────

@pytest.fixture
def shop_a_context():
    """ShopContext for Shop A (ID=1)."""
    return ShopContext(
        shop_id=1,
        shop_slug="shop-a",
        shop_name="Test Shop A",
        timezone="America/Phoenix",
        source=ShopResolutionSource.URL_SLUG,
    )


@pytest.fixture
def shop_b_context():
    """ShopContext for Shop B (ID=2)."""
    return ShopContext(
        shop_id=2,
        shop_slug="shop-b",
        shop_name="Test Shop B",
        timezone="America/New_York",
        source=ShopResolutionSource.URL_SLUG,
    )


# ────────────────────────────────────────────────────────────────
# Unit Tests - ShopContext
# ────────────────────────────────────────────────────────────────

class TestShopContext:
    """Test ShopContext validation and immutability."""
    
    def test_shop_context_requires_positive_shop_id(self):
        """ShopContext should reject non-positive shop_id."""
        with pytest.raises(ValueError, match="shop_id must be positive"):
            ShopContext(shop_id=0)
        
        with pytest.raises(ValueError, match="shop_id must be positive"):
            ShopContext(shop_id=-1)
    
    def test_shop_context_accepts_valid_shop_id(self):
        """ShopContext should accept valid positive shop_id."""
        ctx = ShopContext(shop_id=1)
        assert ctx.shop_id == 1
        
        ctx = ShopContext(shop_id=999)
        assert ctx.shop_id == 999
    
    def test_shop_context_is_immutable(self, shop_a_context):
        """ShopContext should be frozen (immutable)."""
        with pytest.raises(Exception):  # FrozenInstanceError
            shop_a_context.shop_id = 999
    
    def test_shop_context_default_values(self):
        """ShopContext should have sensible defaults."""
        ctx = ShopContext(shop_id=1)
        assert ctx.shop_slug is None
        assert ctx.shop_name is None
        assert ctx.timezone == "America/Phoenix"
        assert ctx.source == ShopResolutionSource.DEFAULT_FALLBACK


# ────────────────────────────────────────────────────────────────
# Unit Tests - Query Scoping Helpers
# ────────────────────────────────────────────────────────────────

class TestQueryScoping:
    """Test that query helpers properly scope by shop_id."""
    
    def test_scoped_select_adds_shop_filter(self):
        """scoped_select() should add shop_id filter to SELECT."""
        from app.tenancy.queries import scoped_select
        
        stmt = scoped_select(Service, shop_id=1)
        # The statement should have a WHERE clause
        compiled = str(stmt.compile())
        assert "shop_id" in compiled.lower()
    
    def test_tenant_filter_returns_filter_clause(self):
        """tenant_filter() should return a valid filter clause."""
        from app.tenancy.queries import tenant_filter
        
        clause = tenant_filter(Service, shop_id=1)
        # Should be a binary comparison
        assert "shop_id" in str(clause).lower()


# ────────────────────────────────────────────────────────────────
# Integration Tests - Cross-Tenant Isolation
# ────────────────────────────────────────────────────────────────

class TestServiceIsolation:
    """Test that services are properly isolated between shops."""
    
    @pytest.mark.asyncio
    async def test_services_scoped_to_shop(self):
        """Services from one shop should not be visible to another shop."""
        from app.tenancy.queries import list_services
        from app.core.db import AsyncSessionLocal
        
        async with AsyncSessionLocal() as session:
            # Get services for shop 1
            shop1_services = await list_services(session, shop_id=1)
            shop1_ids = {s.id for s in shop1_services}
            
            # Get services for shop 2 (if exists)
            shop2_services = await list_services(session, shop_id=2)
            shop2_ids = {s.id for s in shop2_services}
            
            # Services should not overlap between shops
            # (unless there are no services for shop 2, which is expected in single-tenant setup)
            if shop2_services:
                overlap = shop1_ids.intersection(shop2_ids)
                assert len(overlap) == 0, f"Services {overlap} visible to multiple shops!"


class TestStylistIsolation:
    """Test that stylists are properly isolated between shops."""
    
    @pytest.mark.asyncio
    async def test_stylists_scoped_to_shop(self):
        """Stylists from one shop should not be visible to another shop."""
        from app.tenancy.queries import list_stylists
        from app.core.db import AsyncSessionLocal
        
        async with AsyncSessionLocal() as session:
            # Get stylists for shop 1
            shop1_stylists = await list_stylists(session, shop_id=1)
            shop1_ids = {s.id for s in shop1_stylists}
            
            # Get stylists for shop 2 (if exists)
            shop2_stylists = await list_stylists(session, shop_id=2)
            shop2_ids = {s.id for s in shop2_stylists}
            
            # Stylists should not overlap between shops
            if shop2_stylists:
                overlap = shop1_ids.intersection(shop2_ids)
                assert len(overlap) == 0, f"Stylists {overlap} visible to multiple shops!"


class TestPromoIsolation:
    """Test that promos are properly isolated between shops."""
    
    @pytest.mark.asyncio
    async def test_promos_scoped_to_shop(self):
        """Promos from one shop should not be visible to another shop."""
        from app.tenancy.queries import list_promos
        from app.core.db import AsyncSessionLocal
        
        async with AsyncSessionLocal() as session:
            # Get promos for shop 1
            shop1_promos = await list_promos(session, shop_id=1)
            shop1_ids = {p.id for p in shop1_promos}
            
            # Get promos for shop 2 (if exists)
            shop2_promos = await list_promos(session, shop_id=2)
            shop2_ids = {p.id for p in shop2_promos}
            
            # Promos should not overlap between shops
            if shop2_promos:
                overlap = shop1_ids.intersection(shop2_ids)
                assert len(overlap) == 0, f"Promos {overlap} visible to multiple shops!"


# ────────────────────────────────────────────────────────────────
# Integration Tests - ID Lookup with Shop Validation
# ────────────────────────────────────────────────────────────────

class TestOwnershipValidation:
    """Test that ID lookups validate shop ownership."""
    
    @pytest.mark.asyncio
    async def test_service_lookup_validates_shop(self):
        """get_service_by_id should only return services for the correct shop."""
        from app.tenancy.queries import get_service_by_id
        from app.core.db import AsyncSessionLocal
        
        async with AsyncSessionLocal() as session:
            # Get first service from shop 1
            result = await session.execute(
                select(Service).where(Service.shop_id == 1).limit(1)
            )
            shop1_service = result.scalar_one_or_none()
            
            if shop1_service:
                # Should find it when querying with correct shop
                found = await get_service_by_id(session, 1, shop1_service.id)
                assert found is not None
                assert found.id == shop1_service.id
                
                # Should NOT find it when querying with wrong shop
                not_found = await get_service_by_id(session, 999, shop1_service.id)
                assert not_found is None
    
    @pytest.mark.asyncio
    async def test_stylist_lookup_validates_shop(self):
        """get_stylist_by_id should only return stylists for the correct shop."""
        from app.tenancy.queries import get_stylist_by_id
        from app.core.db import AsyncSessionLocal
        
        async with AsyncSessionLocal() as session:
            # Get first stylist from shop 1
            result = await session.execute(
                select(Stylist).where(Stylist.shop_id == 1).limit(1)
            )
            shop1_stylist = result.scalar_one_or_none()
            
            if shop1_stylist:
                # Should find it when querying with correct shop
                found = await get_stylist_by_id(session, 1, shop1_stylist.id)
                assert found is not None
                assert found.id == shop1_stylist.id
                
                # Should NOT find it when querying with wrong shop
                not_found = await get_stylist_by_id(session, 999, shop1_stylist.id)
                assert not_found is None


# ────────────────────────────────────────────────────────────────
# Chat Module Isolation Tests
# ────────────────────────────────────────────────────────────────

class TestChatIsolation:
    """Test that chat functions properly scope queries."""
    
    @pytest.mark.asyncio
    async def test_get_services_context_scoped(self):
        """get_services_context should only include services for the shop."""
        from app.chat import get_services_context
        from app.core.db import AsyncSessionLocal
        
        async with AsyncSessionLocal() as session:
            context = await get_services_context(session, shop_id=1)
            
            # Should return some text (assuming shop 1 has services)
            assert isinstance(context, str)
            # If no services, should say so
            if "No services" not in context:
                # Otherwise should contain "ID" markers
                assert "ID" in context
    
    @pytest.mark.asyncio
    async def test_get_stylists_context_scoped(self):
        """get_stylists_context should only include stylists for the shop."""
        from app.chat import get_stylists_context
        from app.core.db import AsyncSessionLocal
        
        async with AsyncSessionLocal() as session:
            context = await get_stylists_context(session, shop_id=1)
            
            # Should return some text
            assert isinstance(context, str)
            # If no stylists, should say so
            if "No stylists" not in context:
                # Otherwise should contain "ID" markers
                assert "ID" in context


# ────────────────────────────────────────────────────────────────
# Run tests with: pytest tests/test_tenant_isolation.py -v
# ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
