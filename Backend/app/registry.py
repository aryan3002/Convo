"""
Shop Registry API for multi-tenancy.

This module provides the /registry/* endpoints for shop lookup and resolution.

PHASE 2 STATUS:
    - GET /registry/resolve queries actual shops table by slug
    - Returns real shop metadata
    - Currently public (no auth required)
    
PHASE 6 TODO:
    - Add rate limiting
    - Consider auth for sensitive operations
    - Add shop search endpoint for RouterGPT
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .core.db import get_session
from .models import Shop, Service
from .tenancy import LEGACY_DEFAULT_SHOP_ID


router = APIRouter(prefix="/registry", tags=["registry"])


# ────────────────────────────────────────────────────────────────
# Response Models
# ────────────────────────────────────────────────────────────────

class ShopResolveResponse(BaseModel):
    """Response for shop resolution by slug."""
    
    shop_id: int
    slug: str
    name: str
    found: bool
    
    class Config:
        json_schema_extra = {
            "example": {
                "shop_id": 1,
                "slug": "bishops-tempe",
                "name": "Bishops Tempe",
                "found": True,
            }
        }


class ShopPublicInfo(BaseModel):
    """Public shop information (safe for RouterGPT/search)."""
    
    slug: str
    name: str
    city: Optional[str] = None
    state: Optional[str] = None
    services_summary: Optional[str] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "slug": "bishops-tempe",
                "name": "Bishops Tempe",
                "city": "Tempe",
                "state": "AZ",
                "services_summary": "Haircuts, Beard Trims, Hot Towel Shaves",
            }
        }


# ────────────────────────────────────────────────────────────────
# Endpoints
# ────────────────────────────────────────────────────────────────

@router.get(
    "/resolve",
    response_model=ShopResolveResponse,
    summary="Resolve shop by slug",
    description="""
    Resolve a shop's ID and metadata from its URL slug.
    
    **PHASE 2 STATUS:** Queries actual shops table by slug.
    Returns found=False if slug not found.
    
    **PHASE 6 TODO:**
    - Add rate limiting
    - Consider auth requirements
    - Cache results for performance
    """,
)
async def resolve_shop(
    slug: str = Query(
        ...,
        description="Shop URL slug (e.g., 'bishops-tempe')",
        min_length=1,
        max_length=100,
        pattern=r"^[a-z0-9-]+$",
    ),
    session: AsyncSession = Depends(get_session),
) -> ShopResolveResponse:
    """
    Resolve a shop by its URL slug.
    
    Phase 2: Queries shops table.
    """
    result = await session.execute(
        select(Shop).where(Shop.slug == slug)
    )
    shop = result.scalar_one_or_none()
    
    if not shop:
        return ShopResolveResponse(
            shop_id=0,
            slug=slug,
            name="",
            found=False,
        )
    
    return ShopResolveResponse(
        shop_id=shop.id,
        slug=shop.slug,
        name=shop.name,
        found=True,
    )


@router.get(
    "/shops/{slug}",
    response_model=ShopPublicInfo,
    summary="Get public shop info",
    description="""
    Get public information about a shop (for RouterGPT search results).
    
    **PHASE 2 STATUS:** Returns real shop data from database.
    
    **PHASE 4 TODO:**
    - Include services summary for search
    - Support search endpoint for RouterGPT
    """,
)
async def get_shop_public_info(
    slug: str,
    session: AsyncSession = Depends(get_session),
) -> ShopPublicInfo:
    """
    Get public shop information by slug.
    
    Phase 2: Returns real shop data.
    """
    result = await session.execute(
        select(Shop).where(Shop.slug == slug)
    )
    shop = result.scalar_one_or_none()
    
    if not shop:
        # Return empty response for not found (or could raise HTTPException)
        return ShopPublicInfo(
            slug=slug,
            name="",
            city=None,
            state=None,
            services_summary=None,
        )
    
    # Get top services for summary
    services_result = await session.execute(
        select(Service.name).where(Service.shop_id == shop.id).limit(5)
    )
    services_list = list(services_result.scalars())
    
    # Parse city/state from address if available
    city = None
    state = None
    if shop.address:
        # Simple extraction - could be improved
        parts = shop.address.split(",")
        if len(parts) >= 2:
            city = parts[-2].strip() if len(parts) > 2 else parts[-1].strip()
            state_part = parts[-1].strip()
            # Extract state code if present
            import re
            state_match = re.search(r'\b([A-Z]{2})\b', state_part)
            if state_match:
                state = state_match.group(1)
    
    return ShopPublicInfo(
        slug=shop.slug,
        name=shop.name,
        city=city,
        state=state,
        services_summary=", ".join(services_list) if services_list else None,
    )
