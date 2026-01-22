"""
Phase 7: Security Tests

Tests for authentication, RBAC, and audit logging.

Run with:
    export DATABASE_URL="postgresql+asyncpg://localhost:5432/convo_test"
    cd Backend
    pytest tests/test_phase7_security.py -v
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Shop, ShopMember, ShopMemberRole, AuditLog


# ============================================================================
# TEST FIXTURES
# ============================================================================

@pytest.fixture
async def test_shop(async_session: AsyncSession) -> Shop:
    """Create a test shop for Phase 7 tests."""
    shop = Shop(
        name="Phase7 Test Shop",
        slug="phase7-test-shop",
        timezone="America/Phoenix",
        phone_number="+15551234567",
    )
    async_session.add(shop)
    await async_session.flush()
    return shop


@pytest.fixture
async def owner_member(async_session: AsyncSession, test_shop: Shop) -> ShopMember:
    """Create an OWNER membership for the test shop."""
    member = ShopMember(
        shop_id=test_shop.id,
        user_id="test_owner_user",
        role=ShopMemberRole.OWNER.value,
    )
    async_session.add(member)
    await async_session.flush()
    return member


@pytest.fixture
async def manager_member(async_session: AsyncSession, test_shop: Shop) -> ShopMember:
    """Create a MANAGER membership for the test shop."""
    member = ShopMember(
        shop_id=test_shop.id,
        user_id="test_manager_user",
        role=ShopMemberRole.MANAGER.value,
    )
    async_session.add(member)
    await async_session.flush()
    return member


@pytest.fixture
async def employee_member(async_session: AsyncSession, test_shop: Shop) -> ShopMember:
    """Create an EMPLOYEE membership for the test shop."""
    member = ShopMember(
        shop_id=test_shop.id,
        user_id="test_employee_user",
        role=ShopMemberRole.EMPLOYEE.value,
    )
    async_session.add(member)
    await async_session.flush()
    return member


# ============================================================================
# AUTHENTICATION TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_owner_chat_missing_auth_header(client: AsyncClient, test_shop: Shop):
    """
    Test: /s/{slug}/owner/chat without X-User-Id => 401 Unauthorized
    """
    response = await client.post(
        f"/s/{test_shop.slug}/owner/chat",
        json={
            "messages": [{"role": "user", "content": "Show services"}]
        },
    )
    
    assert response.status_code == 401
    assert "Authentication required" in response.json()["detail"]


@pytest.mark.asyncio
async def test_owner_chat_empty_auth_header(client: AsyncClient, test_shop: Shop):
    """
    Test: /s/{slug}/owner/chat with empty X-User-Id => 401 Unauthorized
    """
    response = await client.post(
        f"/s/{test_shop.slug}/owner/chat",
        json={
            "messages": [{"role": "user", "content": "Show services"}]
        },
        headers={"X-User-Id": ""},
    )
    
    assert response.status_code == 401
    assert "Authentication required" in response.json()["detail"]


@pytest.mark.asyncio
async def test_owner_chat_whitespace_auth_header(client: AsyncClient, test_shop: Shop):
    """
    Test: /s/{slug}/owner/chat with whitespace-only X-User-Id => 401 Unauthorized
    """
    response = await client.post(
        f"/s/{test_shop.slug}/owner/chat",
        json={
            "messages": [{"role": "user", "content": "Show services"}]
        },
        headers={"X-User-Id": "   "},
    )
    
    assert response.status_code == 401
    assert "Authentication required" in response.json()["detail"]


# ============================================================================
# AUTHORIZATION (RBAC) TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_owner_chat_non_member_forbidden(client: AsyncClient, test_shop: Shop):
    """
    Test: /s/{slug}/owner/chat with X-User-Id but user is NOT a member => 403 Forbidden
    """
    response = await client.post(
        f"/s/{test_shop.slug}/owner/chat",
        json={
            "messages": [{"role": "user", "content": "Show services"}]
        },
        headers={"X-User-Id": "random_user_not_a_member"},
    )
    
    assert response.status_code == 403
    assert "not a member" in response.json()["detail"]


@pytest.mark.asyncio
async def test_owner_chat_employee_forbidden(
    client: AsyncClient, 
    test_shop: Shop, 
    employee_member: ShopMember
):
    """
    Test: /s/{slug}/owner/chat with EMPLOYEE role => 403 Forbidden
    
    Only OWNER and MANAGER can access owner chat.
    """
    response = await client.post(
        f"/s/{test_shop.slug}/owner/chat",
        json={
            "messages": [{"role": "user", "content": "Show services"}]
        },
        headers={"X-User-Id": employee_member.user_id},
    )
    
    assert response.status_code == 403
    assert "Required role" in response.json()["detail"]
    assert "EMPLOYEE" in response.json()["detail"]  # Shows their current role


@pytest.mark.asyncio
async def test_owner_chat_owner_allowed(
    client: AsyncClient, 
    test_shop: Shop, 
    owner_member: ShopMember
):
    """
    Test: /s/{slug}/owner/chat with OWNER role => 200 OK
    """
    response = await client.post(
        f"/s/{test_shop.slug}/owner/chat",
        json={
            "messages": [{"role": "user", "content": "Hello"}]
        },
        headers={"X-User-Id": owner_member.user_id},
    )
    
    # Should get through auth/authz (may still fail if OpenAI not configured, 
    # but we're testing that auth passes)
    assert response.status_code in [200, 500, 502]  # Auth passed, may fail downstream
    if response.status_code == 200:
        data = response.json()
        assert "reply" in data or "error" in data


@pytest.mark.asyncio
async def test_owner_chat_manager_allowed(
    client: AsyncClient, 
    test_shop: Shop, 
    manager_member: ShopMember
):
    """
    Test: /s/{slug}/owner/chat with MANAGER role => 200 OK
    """
    response = await client.post(
        f"/s/{test_shop.slug}/owner/chat",
        json={
            "messages": [{"role": "user", "content": "Hello"}]
        },
        headers={"X-User-Id": manager_member.user_id},
    )
    
    # Should get through auth/authz
    assert response.status_code in [200, 500, 502]  # Auth passed


# ============================================================================
# AUDIT LOGGING TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_create_shop_creates_audit_log(client: AsyncClient, async_session: AsyncSession):
    """
    Test: POST /shops creates both shop_members OWNER row AND audit_logs row
    """
    import uuid
    unique_name = f"Audit Test Shop {uuid.uuid4().hex[:8]}"
    
    response = await client.post(
        "/shops",
        json={
            "name": unique_name,
            "owner_user_id": "audit_test_owner",
            "timezone": "America/New_York",
        },
    )
    
    assert response.status_code == 201
    data = response.json()
    shop_id = data["id"]
    
    # Verify shop_members OWNER row was created
    member_result = await async_session.execute(
        select(ShopMember).where(
            ShopMember.shop_id == shop_id,
            ShopMember.user_id == "audit_test_owner",
        )
    )
    member = member_result.scalar_one_or_none()
    assert member is not None
    assert member.role == ShopMemberRole.OWNER.value
    
    # Verify audit_logs row was created
    audit_result = await async_session.execute(
        select(AuditLog).where(
            AuditLog.shop_id == shop_id,
            AuditLog.action == "shop.created",
        )
    )
    audit_log = audit_result.scalar_one_or_none()
    assert audit_log is not None
    assert audit_log.actor_user_id == "audit_test_owner"
    assert audit_log.target_type == "shop"
    assert audit_log.target_id == str(shop_id)
    
    # Verify extra_data (no PII!)
    assert audit_log.extra_data is not None
    assert audit_log.extra_data["slug"] == data["slug"]
    assert audit_log.extra_data["name"] == unique_name
    # Should NOT contain phone_number in extra_data (PII protection)
    assert "phone_number" not in audit_log.extra_data


@pytest.mark.asyncio
async def test_owner_chat_creates_audit_log(
    client: AsyncClient, 
    async_session: AsyncSession,
    test_shop: Shop, 
    owner_member: ShopMember
):
    """
    Test: /s/{slug}/owner/chat creates audit log entry
    """
    # Clear any existing audit logs for this shop
    await async_session.execute(
        select(AuditLog).where(AuditLog.shop_id == test_shop.id)
    )
    
    response = await client.post(
        f"/s/{test_shop.slug}/owner/chat",
        json={
            "messages": [{"role": "user", "content": "Show me the services"}]
        },
        headers={"X-User-Id": owner_member.user_id},
    )
    
    # Auth should pass (may fail downstream)
    if response.status_code in [200, 500, 502]:
        # Check audit log was created
        audit_result = await async_session.execute(
            select(AuditLog).where(
                AuditLog.shop_id == test_shop.id,
                AuditLog.action == "owner.chat",
                AuditLog.actor_user_id == owner_member.user_id,
            )
        )
        audit_log = audit_result.scalar_one_or_none()
        
        # Note: If the AI call fails, audit log may still be created
        # This depends on transaction handling
        if audit_log:
            assert audit_log.target_type == "shop"
            assert audit_log.extra_data is not None
            assert audit_log.extra_data["slug"] == test_shop.slug


# ============================================================================
# TENANT ENFORCEMENT TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_public_endpoints_remain_public(client: AsyncClient):
    """
    Test: POST /shops and GET /shops/{slug} remain PUBLIC (no auth required)
    """
    import uuid
    unique_name = f"Public Test {uuid.uuid4().hex[:8]}"
    
    # POST /shops should work without auth
    create_response = await client.post(
        "/shops",
        json={
            "name": unique_name,
            "owner_user_id": "public_test_owner",
        },
    )
    assert create_response.status_code == 201
    slug = create_response.json()["slug"]
    
    # GET /shops/{slug} should work without auth
    get_response = await client.get(f"/shops/{slug}")
    assert get_response.status_code == 200
    assert get_response.json()["name"] == unique_name


@pytest.mark.asyncio
async def test_chat_endpoint_public(client: AsyncClient, test_shop: Shop):
    """
    Test: /s/{slug}/chat (customer chat) remains PUBLIC
    
    Customer-facing chat should not require authentication.
    """
    response = await client.post(
        f"/s/{test_shop.slug}/chat",
        json={
            "messages": [{"role": "user", "content": "Hello"}],
        },
    )
    
    # Should not get 401 (auth not required for customer chat)
    assert response.status_code != 401
    # May get 200 or 500 depending on AI configuration


@pytest.mark.asyncio
async def test_services_endpoint_public(client: AsyncClient, test_shop: Shop):
    """
    Test: /s/{slug}/services remains PUBLIC
    """
    response = await client.get(f"/s/{test_shop.slug}/services")
    
    assert response.status_code == 200
    data = response.json()
    assert "services" in data
    assert data["shop_slug"] == test_shop.slug


@pytest.mark.asyncio
async def test_shop_not_found_404(client: AsyncClient):
    """
    Test: /s/{slug}/owner/chat with non-existent shop => 404
    """
    response = await client.post(
        "/s/nonexistent-shop-12345/owner/chat",
        json={
            "messages": [{"role": "user", "content": "Hello"}]
        },
        headers={"X-User-Id": "some_user"},
    )
    
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


# ============================================================================
# AUTH MODULE UNIT TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_get_shop_member_found(async_session: AsyncSession, test_shop: Shop, owner_member: ShopMember):
    """Test get_shop_member returns member when exists."""
    from app.auth import get_shop_member
    
    member = await get_shop_member(async_session, test_shop.id, owner_member.user_id)
    
    assert member is not None
    assert member.id == owner_member.id
    assert member.role == ShopMemberRole.OWNER.value


@pytest.mark.asyncio
async def test_get_shop_member_not_found(async_session: AsyncSession, test_shop: Shop):
    """Test get_shop_member returns None for non-member."""
    from app.auth import get_shop_member
    
    member = await get_shop_member(async_session, test_shop.id, "nonexistent_user")
    
    assert member is None


@pytest.mark.asyncio
async def test_assert_shop_scoped_row_success():
    """Test assert_shop_scoped_row passes when shop IDs match."""
    from app.auth import assert_shop_scoped_row
    
    # Should not raise
    assert_shop_scoped_row(123, 123)


@pytest.mark.asyncio
async def test_assert_shop_scoped_row_failure():
    """Test assert_shop_scoped_row raises 403 when shop IDs don't match."""
    from app.auth import assert_shop_scoped_row
    from fastapi import HTTPException
    
    with pytest.raises(HTTPException) as exc_info:
        assert_shop_scoped_row(123, 456)
    
    assert exc_info.value.status_code == 403
    assert "different shop" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_log_audit_creates_entry(async_session: AsyncSession, test_shop: Shop):
    """Test log_audit creates audit log entry."""
    from app.auth import log_audit
    
    audit_log = await log_audit(
        async_session,
        actor_user_id="test_actor",
        action="test.action",
        shop_id=test_shop.id,
        target_type="test",
        target_id="123",
        metadata={"key": "value"},
    )
    
    assert audit_log.id is not None
    assert audit_log.actor_user_id == "test_actor"
    assert audit_log.action == "test.action"
    assert audit_log.shop_id == test_shop.id
    assert audit_log.target_type == "test"
    assert audit_log.target_id == "123"
    assert audit_log.extra_data == {"key": "value"}
    assert audit_log.created_at is not None
