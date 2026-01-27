"""
Phase 6: Onboarding & Scale
Phase 7: Added audit logging for shop creation

Global shop onboarding and public shop registry endpoints.

These endpoints DO NOT require shop context resolution.
"""
import re
import unicodedata
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.models import Shop, ShopPhoneNumber, ShopMember, ShopMemberRole
from app.auth import log_audit, AUDIT_SHOP_CREATED, AUDIT_MEMBER_ADDED

router = APIRouter()


# === Request/Response Models ===

class CreateShopRequest(BaseModel):
    """Request to create a new shop."""
    name: str = Field(..., min_length=1, max_length=100)
    phone_number: str | None = Field(None, pattern=r"^\+?[1-9]\d{1,14}$")
    timezone: str = Field(default="America/Phoenix")
    address: str | None = None
    category: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    owner_user_id: str = Field(..., min_length=1, max_length=255, description="Auth provider user ID")

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Ensure name is not just whitespace."""
        if not v.strip():
            raise ValueError("Shop name cannot be empty or whitespace")
        return v.strip()


class ShopResponse(BaseModel):
    """Public shop information."""
    id: int
    name: str
    slug: str
    phone_number: str | None
    timezone: str
    address: str | None
    category: str | None
    
    model_config = {"from_attributes": True}


# === Helper Functions ===

def generate_slug(name: str) -> str:
    """
    Generate a URL-safe slug from shop name.
    
    Rules:
    - Lowercase
    - ASCII-safe (unicode -> ascii)
    - Hyphens for spaces/special chars
    - No leading/trailing hyphens
    - Max 100 chars
    
    Examples:
        "Bella's Salon" -> "bellas-salon"
        "Café Beauté" -> "cafe-beaute"
        "Hair & Nails!!!" -> "hair-nails"
    """
    # Normalize unicode to ASCII
    normalized = unicodedata.normalize('NFKD', name)
    ascii_str = normalized.encode('ascii', 'ignore').decode('ascii')
    
    # Lowercase and replace non-alphanumeric with hyphens
    slug = re.sub(r'[^a-z0-9]+', '-', ascii_str.lower())
    
    # Remove leading/trailing hyphens
    slug = slug.strip('-')
    
    # Limit length
    return slug[:100]


async def ensure_unique_slug(db: AsyncSession, base_slug: str) -> str:
    """
    Ensure slug is unique by appending -2, -3, etc. if needed.
    
    Returns the first available unique slug.
    """
    candidate = base_slug
    counter = 2
    
    while True:
        result = await db.execute(
            select(Shop).where(Shop.slug == candidate)
        )
        if result.scalar_one_or_none() is None:
            return candidate
        
        candidate = f"{base_slug}-{counter}"
        counter += 1
        
        if counter > 1000:  # Safety: prevent infinite loop
            raise HTTPException(
                status_code=500, 
                detail="Unable to generate unique slug after 1000 attempts"
            )


# === Endpoints ===

@router.post("/shops", response_model=ShopResponse, status_code=201)
async def create_shop(
    request: CreateShopRequest,
    db: AsyncSession = Depends(get_session)
):
    """
    Create a new shop (global onboarding endpoint).
    
    This endpoint does NOT require shop context - it creates the shop itself.
    
    Process:
    1. Generate unique slug from name
    2. Check for shop name uniqueness (409 if exists)
    3. Check for phone number uniqueness (409 if exists)
    4. Create shop record
    5. Create shop_phone_numbers entry if phone provided
    6. Create shop_members OWNER record
    7. Return shop info
    
    Error Codes:
    - 409: Shop name already exists OR phone number already in use
    - 422: Invalid input (name too long, invalid phone format, etc.)
    """
    # Check name uniqueness
    existing_name = await db.execute(
        select(Shop).where(Shop.name == request.name)
    )
    if existing_name.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail=f"Shop with name '{request.name}' already exists"
        )
    
    # Check phone number uniqueness (both tables)
    if request.phone_number:
        # Check shop_phone_numbers table
        existing_phone_sn = await db.execute(
            select(ShopPhoneNumber).where(ShopPhoneNumber.phone_number == request.phone_number)
        )
        if existing_phone_sn.scalar_one_or_none():
            raise HTTPException(
                status_code=409,
                detail=f"Phone number {request.phone_number} is already registered to another shop"
            )
        
        # Check shops.phone_number (legacy/fallback column)
        existing_phone_shop = await db.execute(
            select(Shop).where(Shop.phone_number == request.phone_number)
        )
        if existing_phone_shop.scalar_one_or_none():
            raise HTTPException(
                status_code=409,
                detail=f"Phone number {request.phone_number} is already registered to another shop"
            )
    
    # Generate unique slug
    base_slug = generate_slug(request.name)
    unique_slug = await ensure_unique_slug(db, base_slug)
    
    # Create shop
    new_shop = Shop(
        name=request.name,
        slug=unique_slug,
        timezone=request.timezone,
        address=request.address,
        category=request.category,
        phone_number=request.phone_number,  # Also store in legacy column
        latitude=request.latitude,
        longitude=request.longitude
    )
    db.add(new_shop)
    await db.flush()  # Get shop.id without committing
    
    # Create shop_phone_numbers entry if phone provided
    if request.phone_number:
        shop_phone = ShopPhoneNumber(
            shop_id=new_shop.id,
            phone_number=request.phone_number,
            is_primary=True,
            label="Primary"
        )
        db.add(shop_phone)
    
    # Create shop_members OWNER record
    owner_member = ShopMember(
        shop_id=new_shop.id,
        user_id=request.owner_user_id,
        role=ShopMemberRole.OWNER.value
    )
    db.add(owner_member)
    
    # Phase 7: Audit logging for shop creation
    # Note: We log the shop_id after creation, no PII in metadata
    await log_audit(
        db,
        actor_user_id=request.owner_user_id,
        action=AUDIT_SHOP_CREATED,
        shop_id=new_shop.id,
        target_type="shop",
        target_id=str(new_shop.id),
        metadata={
            "slug": unique_slug,
            "name": request.name,
            "category": request.category,
            "timezone": request.timezone,
        }
    )
    
    await db.commit()
    await db.refresh(new_shop)
    
    return ShopResponse.model_validate(new_shop)


@router.get("/shops/{slug}", response_model=ShopResponse)
async def get_shop_by_slug(
    slug: str,
    db: AsyncSession = Depends(get_session)
):
    """
    Get public shop information by slug (shop registry endpoint).
    
    This endpoint does NOT require shop context - it's for discovery/resolution.
    
    Use cases:
    - Frontend routing: resolve /s/{slug} to shop details
    - Public shop profile pages
    - Shop existence verification
    
    Returns:
    - 200: Shop found
    - 404: Shop not found
    """
    result = await db.execute(
        select(Shop).where(Shop.slug == slug)
    )
    shop = result.scalar_one_or_none()
    
    if not shop:
        raise HTTPException(
            status_code=404,
            detail=f"Shop with slug '{slug}' not found"
        )
    
    return ShopResponse.model_validate(shop)


@router.get("/users/{user_id}/shops", response_model=list[ShopResponse])
async def get_user_shops(
    user_id: str,
    db: AsyncSession = Depends(get_session)
):
    """
    Get all shops where the user is a member.
    
    Returns a list of shops where the user has any role (OWNER, MANAGER, EMPLOYEE).
    Useful for displaying "My Shops" in the UI.
    
    Returns:
    - 200: List of shops (may be empty if user has no memberships)
    """
    result = await db.execute(
        select(Shop)
        .join(ShopMember, Shop.id == ShopMember.shop_id)
        .where(ShopMember.user_id == user_id)
        .order_by(Shop.created_at.desc())
    )
    shops = result.scalars().all()
    
    return [ShopResponse.model_validate(shop) for shop in shops]
