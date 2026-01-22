"""
Tests for Phase 6: Onboarding & Scale
Global shop onboarding and public shop registry.

Run with: export DATABASE_URL="postgresql+asyncpg://localhost:5432/convo_test"
Then: pytest tests/test_phase6_onboarding.py -v
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from sqlalchemy import select

from app.models import Shop, ShopPhoneNumber, ShopMember, ShopMemberRole


# === POST /shops Tests ===

@pytest.mark.asyncio
async def test_create_shop_minimal(client, async_session):
    """Test creating a shop with minimal required fields."""
    response = await client.post(
        "/shops",
        json={
            "name": "Test Salon",
            "owner_user_id": "user_123"
        }
    )
    
    assert response.status_code == 201
    data = response.json()
    
    # Verify response structure
    assert data["name"] == "Test Salon"
    assert data["slug"] == "test-salon"
    assert data["timezone"] == "America/Phoenix"  # default
    assert data["phone_number"] is None
    assert data["address"] is None
    assert data["category"] is None
    assert "id" in data
    
    # Verify DB records
    shop = await async_session.scalar(select(Shop).where(Shop.slug == "test-salon"))
    assert shop is not None
    assert shop.name == "Test Salon"
    
    # Verify shop_members record created
    member = await async_session.scalar(
        select(ShopMember).where(
            ShopMember.shop_id == shop.id,
            ShopMember.user_id == "user_123"
        )
    )
    assert member is not None
    assert member.role == ShopMemberRole.OWNER.value


@pytest.mark.asyncio
async def test_create_shop_with_phone(client, async_session):
    """Test creating a shop with phone number creates shop_phone_numbers entry."""
    response = await client.post(
        "/shops",
        json={
            "name": "Beauty Bar",
            "phone_number": "+15551234567",
            "owner_user_id": "user_456",
            "timezone": "America/New_York",
            "address": "123 Main St",
            "category": "Salon"
        }
    )
    
    assert response.status_code == 201
    data = response.json()
    
    assert data["name"] == "Beauty Bar"
    assert data["slug"] == "beauty-bar"
    assert data["phone_number"] == "+15551234567"
    assert data["timezone"] == "America/New_York"
    assert data["address"] == "123 Main St"
    assert data["category"] == "Salon"
    
    # Verify shop_phone_numbers entry
    shop = await async_session.scalar(select(Shop).where(Shop.slug == "beauty-bar"))
    phone_entry = await async_session.scalar(
        select(ShopPhoneNumber).where(
            ShopPhoneNumber.shop_id == shop.id,
            ShopPhoneNumber.phone_number == "+15551234567"
        )
    )
    assert phone_entry is not None
    assert phone_entry.is_primary is True
    assert phone_entry.label == "Primary"


@pytest.mark.asyncio
async def test_slug_generation_special_chars(client, async_session):
    """Test slug generation handles special characters correctly."""
    test_cases = [
        ("Bella's Salon", "bella-s-salon"),  # Apostrophe becomes hyphen
        ("Café Beauté", "cafe-beaute"),
        ("Hair & Nails!!!", "hair-nails"),
        ("   Trim  Spaces  ", "trim-spaces"),
        ("Mix123Numbers", "mix123numbers"),
    ]
    
    for i, (name, expected_slug) in enumerate(test_cases):
        response = await client.post(
            "/shops",
            json={
                "name": name,
                "owner_user_id": f"user_{i}"
            }
        )
            
        assert response.status_code == 201
        assert response.json()["slug"] == expected_slug


@pytest.mark.asyncio
async def test_slug_uniqueness_conflict_resolution(client, async_session):
    """Test slug uniqueness handling with -2, -3 suffixes."""
    # Create first shop
    response1 = await client.post(
        "/shops",
        json={"name": "Hair Studio", "owner_user_id": "user_a"}
    )
    assert response1.status_code == 201
    assert response1.json()["slug"] == "hair-studio"
    
    # Create second shop with same slug base
    response2 = await client.post(
        "/shops",
        json={"name": "Hair Studio", "owner_user_id": "user_b"}
    )
    # Should fail due to name uniqueness
    assert response2.status_code == 409
    assert "already exists" in response2.json()["detail"]
    
    # Create shop with name that generates same slug but is unique
    response3 = await client.post(
        "/shops",
        json={"name": "Hair-Studio", "owner_user_id": "user_c"}
    )
    assert response3.status_code == 201
    assert response3.json()["slug"] == "hair-studio-2"
    
    # Create another
    response4 = await client.post(
        "/shops",
        json={"name": "HAIR STUDIO!", "owner_user_id": "user_d"}
    )
    assert response4.status_code == 201
    assert response4.json()["slug"] == "hair-studio-3"


@pytest.mark.asyncio
async def test_duplicate_name_conflict(client, async_session):
    """Test that duplicate shop names are rejected."""
    # Create first shop
    response1 = await client.post(
        "/shops",
        json={"name": "Unique Salon", "owner_user_id": "user_1"}
    )
    assert response1.status_code == 201
    
    # Try to create shop with same name
    response2 = await client.post(
        "/shops",
        json={"name": "Unique Salon", "owner_user_id": "user_2"}
    )
    assert response2.status_code == 409
    assert "already exists" in response2.json()["detail"]


@pytest.mark.asyncio
async def test_duplicate_phone_conflict_shop_phone_numbers(client, async_session):
    """Test that duplicate phone numbers in shop_phone_numbers are rejected."""
    # Create first shop with phone
    response1 = await client.post(
        "/shops",
        json={
            "name": "First Salon",
            "phone_number": "+15559876543",
            "owner_user_id": "user_1"
        }
    )
    assert response1.status_code == 201
    
    # Try to create shop with same phone
    response2 = await client.post(
        "/shops",
        json={
            "name": "Second Salon",
            "phone_number": "+15559876543",
            "owner_user_id": "user_2"
        }
    )
    assert response2.status_code == 409
    assert "already registered" in response2.json()["detail"].lower()


@pytest.mark.asyncio
async def test_duplicate_phone_conflict_legacy_column(client, async_session):
    """Test that duplicate phone numbers in shops.phone_number are detected."""
    # Manually create shop with phone_number in legacy column only
    shop = Shop(
        name="Legacy Shop",
        slug="legacy-shop",
        phone_number="+15551111111",
        timezone="America/Phoenix"
    )
    async_session.add(shop)
    await async_session.commit()
    
    # Try to create new shop with same phone
    response = await client.post(
        "/shops",
        json={
            "name": "New Shop",
            "phone_number": "+15551111111",
            "owner_user_id": "user_new"
        }
    )
    assert response.status_code == 409
    assert "already registered" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_create_shop_invalid_name(client, async_session):
    """Test validation for invalid shop names."""
    # Empty name
    response1 = await client.post(
        "/shops",
        json={"name": "", "owner_user_id": "user_1"}
    )
    assert response1.status_code == 422
    
    # Whitespace only
    response2 = await client.post(
        "/shops",
        json={"name": "   ", "owner_user_id": "user_2"}
    )
    assert response2.status_code == 422


@pytest.mark.asyncio
async def test_create_shop_invalid_phone(client, async_session):
    """Test validation for invalid phone numbers."""
    # Invalid format
    response = await client.post(
        "/shops",
        json={
            "name": "Test Shop",
            "phone_number": "not-a-phone",
            "owner_user_id": "user_1"
        }
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_shop_missing_owner_user_id(client, async_session):
    """Test that owner_user_id is required."""
    response = await client.post(
        "/shops",
        json={"name": "Test Shop"}
    )
    assert response.status_code == 422


# === GET /shops/{slug} Tests ===

@pytest.mark.asyncio
async def test_get_shop_by_slug_success(client, async_session):
    """Test retrieving a shop by slug."""
    # Create shop via API
    create_response = await client.post(
        "/shops",
        json={
            "name": "Find Me Salon",
            "phone_number": "+15552223333",
            "timezone": "America/Chicago",
            "address": "456 Oak Ave",
            "category": "Hair Salon",
            "owner_user_id": "user_finder"
        }
    )
    assert create_response.status_code == 201
    shop_data = create_response.json()
    
    # Retrieve by slug
    get_response = await client.get(f"/shops/{shop_data['slug']}")
    assert get_response.status_code == 200
    
    retrieved = get_response.json()
    assert retrieved["id"] == shop_data["id"]
    assert retrieved["name"] == "Find Me Salon"
    assert retrieved["slug"] == "find-me-salon"
    assert retrieved["phone_number"] == "+15552223333"
    assert retrieved["timezone"] == "America/Chicago"
    assert retrieved["address"] == "456 Oak Ave"
    assert retrieved["category"] == "Hair Salon"


@pytest.mark.asyncio
async def test_get_shop_by_slug_not_found(client, async_session):
    """Test 404 for non-existent shop slug."""
    response = await client.get("/shops/does-not-exist")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_get_shop_by_slug_case_sensitive(client, async_session):
    """Test that slug lookup is case-sensitive (slugs are lowercase)."""
    # Create shop
    create_response = await client.post(
        "/shops",
        json={"name": "Case Test", "owner_user_id": "user_case"}
    )
    assert create_response.status_code == 201
    
    # Try uppercase slug
    response = await client.get("/shops/CASE-TEST")
    assert response.status_code == 404


# === Integration Tests ===

@pytest.mark.asyncio
async def test_full_onboarding_workflow(client, async_session):
    """Test complete onboarding workflow: create shop -> verify records -> retrieve by slug."""
    # Step 1: Create shop
    create_response = await client.post(
        "/shops",
        json={
            "name": "Full Workflow Salon",
            "phone_number": "+15554445555",
            "timezone": "America/Los_Angeles",
            "address": "789 Pine St",
            "category": "Beauty",
            "owner_user_id": "user_workflow"
        }
    )
    assert create_response.status_code == 201
    shop_data = create_response.json()
    
    # Step 2: Verify shop record
    shop = await async_session.scalar(
        select(Shop).where(Shop.id == shop_data["id"])
    )
    assert shop is not None
    assert shop.name == "Full Workflow Salon"
    assert shop.slug == "full-workflow-salon"
    
    # Step 3: Verify shop_phone_numbers record
    phone_entry = await async_session.scalar(
        select(ShopPhoneNumber).where(
            ShopPhoneNumber.shop_id == shop.id,
            ShopPhoneNumber.phone_number == "+15554445555"
        )
    )
    assert phone_entry is not None
    assert phone_entry.is_primary is True
    
    # Step 4: Verify shop_members record
    member = await async_session.scalar(
        select(ShopMember).where(
            ShopMember.shop_id == shop.id,
            ShopMember.user_id == "user_workflow"
        )
    )
    assert member is not None
    assert member.role == ShopMemberRole.OWNER.value
    
    # Step 5: Retrieve by slug
    get_response = await client.get(f"/shops/{shop_data['slug']}")
    assert get_response.status_code == 200
    retrieved = get_response.json()
    assert retrieved["id"] == shop_data["id"]
    assert retrieved["name"] == shop_data["name"]


@pytest.mark.asyncio
async def test_multiple_shops_same_owner(client, async_session):
    """Test that one user can own multiple shops."""
    # Create first shop
    response1 = await client.post(
        "/shops",
        json={"name": "Shop One", "owner_user_id": "multi_owner"}
    )
    assert response1.status_code == 201
    
    # Create second shop with same owner
    response2 = await client.post(
        "/shops",
        json={"name": "Shop Two", "owner_user_id": "multi_owner"}
    )
    assert response2.status_code == 201
    
    # Verify both shops exist
    shop1_id = response1.json()["id"]
    shop2_id = response2.json()["id"]
    
    member1 = await async_session.scalar(
        select(ShopMember).where(
            ShopMember.shop_id == shop1_id,
            ShopMember.user_id == "multi_owner"
        )
    )
    member2 = await async_session.scalar(
        select(ShopMember).where(
            ShopMember.shop_id == shop2_id,
            ShopMember.user_id == "multi_owner"
        )
    )
    
    assert member1 is not None
    assert member2 is not None
    assert member1.role == ShopMemberRole.OWNER.value
    assert member2.role == ShopMemberRole.OWNER.value
