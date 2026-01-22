"""
RouterGPT - Discovery & Delegation Layer (Phase 5)

This module provides a "global entry" layer for ChatGPT to discover and route
to shop-specific GPTs. RouterGPT NEVER books - it only helps users find the
right business and delegates to the appropriate multi-tenant endpoint.

Endpoints:
    GET  /router/search              - Search businesses by query/location/category
    GET  /router/business/{id}       - Get detailed business summary
    POST /router/handoff             - Generate handoff package for delegation

Design Principles:
    - Discovery only - never creates bookings or modifies data
    - Multi-tenant safe - only exposes public shop information
    - Stateless - each request is independent
    - Delegates to /s/{slug}/... endpoints for actual booking

Tools for ChatGPT:
    1. search_businesses - Find businesses matching user criteria
    2. get_business_summary - Get details about a specific business
    3. handoff_to_business_gpt - Generate delegation payload
"""

import logging
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Path, status
from pydantic import BaseModel, Field
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from .core.db import get_session
from .models import Shop, ShopPhoneNumber, Service, Stylist


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/router", tags=["router-gpt"])


# ────────────────────────────────────────────────────────────────
# Request/Response Models
# ────────────────────────────────────────────────────────────────

class BusinessSearchResult(BaseModel):
    """A single business in search results."""
    business_id: int = Field(..., description="Unique business ID (shop_id)")
    slug: str = Field(..., description="URL-safe slug for routing")
    name: str = Field(..., description="Business display name")
    category: Optional[str] = Field(None, description="Business category (e.g., 'barbershop', 'salon')")
    address: Optional[str] = Field(None, description="Business address")
    timezone: str = Field(..., description="IANA timezone")
    primary_phone: Optional[str] = Field(None, description="Primary contact phone")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Match confidence score")


class SearchResponse(BaseModel):
    """Response for business search."""
    query: str = Field(..., description="Original search query")
    results: list[BusinessSearchResult] = Field(default_factory=list)
    total_count: int = Field(..., description="Total matching businesses")


class BusinessCapabilities(BaseModel):
    """What a business supports."""
    supports_chat: bool = Field(True, description="Supports chat-based booking")
    supports_voice: bool = Field(..., description="Has phone number configured for voice")
    supports_owner_chat: bool = Field(True, description="Supports owner/management chat")


class BusinessSummary(BaseModel):
    """Detailed business information."""
    business_id: int
    slug: str
    name: str
    timezone: str
    address: Optional[str] = None
    category: Optional[str] = None
    primary_phone: Optional[str] = None
    service_count: int = Field(0, description="Number of services offered")
    stylist_count: int = Field(0, description="Number of active stylists")
    capabilities: BusinessCapabilities
    chat_endpoint: str = Field(..., description="Endpoint for chat-based booking")
    owner_chat_endpoint: str = Field(..., description="Endpoint for owner chat")
    services_endpoint: str = Field(..., description="Endpoint to list services")


class ConversationMessage(BaseModel):
    """A message in conversation context."""
    role: str = Field(..., description="Message role: 'user' or 'assistant'")
    content: str = Field(..., description="Message content")


class HandoffRequest(BaseModel):
    """Request to generate handoff package."""
    business_id: Optional[int] = Field(None, description="Business ID (use this OR slug)")
    slug: Optional[str] = Field(None, description="Business slug (use this OR business_id)")
    conversation_context: list[ConversationMessage] = Field(
        default_factory=list,
        description="Previous conversation messages to pass to business GPT"
    )
    user_intent: Optional[str] = Field(
        None, 
        description="Optional explicit user intent (e.g., 'book haircut for tomorrow')"
    )


class HandoffPayloadTemplate(BaseModel):
    """Template for the payload to send to business GPT."""
    messages: list[dict]  # List of {"role": str, "content": str} dicts
    metadata: dict


class HandoffResponse(BaseModel):
    """Handoff package for delegating to business GPT."""
    business_id: int
    slug: str
    name: str
    recommended_endpoint: str = Field(..., description="The /s/{slug}/chat endpoint to call")
    payload_template: HandoffPayloadTemplate = Field(..., description="Suggested payload structure")
    explanation: str = Field(..., description="Human-readable explanation of the handoff")


# ────────────────────────────────────────────────────────────────
# Helper Functions
# ────────────────────────────────────────────────────────────────

def calculate_match_score(query: str, shop: Shop) -> float:
    """
    Calculate a match confidence score between query and shop.
    
    Uses fuzzy matching on name, slug, category, and address.
    Returns score between 0.0 and 1.0.
    """
    query_lower = query.lower().strip()
    if not query_lower:
        return 0.5  # Neutral score for empty query
    
    scores = []
    
    # Name match (highest weight)
    if shop.name:
        name_score = SequenceMatcher(None, query_lower, shop.name.lower()).ratio()
        scores.append(name_score * 1.5)  # Weight name heavily
        
        # Bonus for exact substring match
        if query_lower in shop.name.lower():
            scores.append(1.0)
    
    # Slug match
    if shop.slug:
        slug_score = SequenceMatcher(None, query_lower, shop.slug.lower()).ratio()
        scores.append(slug_score)
    
    # Category match
    if shop.category:
        category_score = SequenceMatcher(None, query_lower, shop.category.lower()).ratio()
        scores.append(category_score * 0.8)
        
        # Bonus for exact category match
        if query_lower == shop.category.lower():
            scores.append(0.8)
    
    # Address match (for location queries)
    if shop.address:
        address_words = re.findall(r'\w+', shop.address.lower())
        query_words = re.findall(r'\w+', query_lower)
        
        matching_words = set(query_words) & set(address_words)
        if matching_words:
            scores.append(len(matching_words) / max(len(query_words), 1) * 0.7)
    
    if not scores:
        return 0.1  # Minimum score
    
    # Return normalized average
    return min(sum(scores) / len(scores), 1.0)


async def get_shop_primary_phone(session: AsyncSession, shop_id: int) -> Optional[str]:
    """Get primary phone for a shop (checks shop_phone_numbers first, then shop.phone_number)."""
    # Check shop_phone_numbers table first
    result = await session.execute(
        select(ShopPhoneNumber.phone_number)
        .where(ShopPhoneNumber.shop_id == shop_id)
        .where(ShopPhoneNumber.is_primary == True)
        .limit(1)
    )
    phone = result.scalar_one_or_none()
    
    if phone:
        return phone
    
    # Fallback to shops.phone_number
    result = await session.execute(
        select(Shop.phone_number).where(Shop.id == shop_id)
    )
    return result.scalar_one_or_none()


async def check_shop_has_voice(session: AsyncSession, shop_id: int) -> bool:
    """Check if shop has any phone number configured for voice."""
    # Check shop_phone_numbers
    result = await session.execute(
        select(func.count(ShopPhoneNumber.id))
        .where(ShopPhoneNumber.shop_id == shop_id)
    )
    count = result.scalar() or 0
    
    if count > 0:
        return True
    
    # Check shops.phone_number
    result = await session.execute(
        select(Shop.phone_number).where(Shop.id == shop_id)
    )
    phone = result.scalar_one_or_none()
    
    return bool(phone)


# ────────────────────────────────────────────────────────────────
# Tool 1: search_businesses
# ────────────────────────────────────────────────────────────────

@router.get("/search", response_model=SearchResponse)
async def search_businesses(
    query: str = Query(..., min_length=1, description="Search query (business name, category, location)"),
    location: Optional[str] = Query(None, description="Location filter (city, state, or address text)"),
    category: Optional[str] = Query(None, description="Category filter (e.g., 'barbershop', 'salon')"),
    limit: int = Query(10, ge=1, le=50, description="Maximum results to return"),
    session: AsyncSession = Depends(get_session),
) -> SearchResponse:
    """
    Search for businesses matching the query.
    
    This is RouterGPT's primary discovery tool. It searches shops by:
    - Name (fuzzy match)
    - Category
    - Address (simple text match for location)
    
    Returns ranked results with confidence scores.
    
    Example:
        GET /router/search?query=bishops&location=tempe
        GET /router/search?query=haircut&category=barbershop
    """
    logger.info(f"RouterGPT search: query='{query}', location='{location}', category='{category}'")
    
    # Build base query
    stmt = select(Shop)
    
    # Apply filters
    conditions = []
    
    # Category filter (exact match if provided)
    if category:
        conditions.append(Shop.category == category.lower())
    
    # Location filter (simple text match on address)
    if location:
        location_pattern = f"%{location}%"
        conditions.append(Shop.address.ilike(location_pattern))
    
    # Text search on name/slug
    query_pattern = f"%{query}%"
    text_conditions = or_(
        Shop.name.ilike(query_pattern),
        Shop.slug.ilike(query_pattern),
        Shop.category.ilike(query_pattern),
        Shop.address.ilike(query_pattern) if not location else False,
    )
    conditions.append(text_conditions)
    
    if conditions:
        stmt = stmt.where(*conditions)
    
    stmt = stmt.limit(limit * 2)  # Fetch extra for scoring/filtering
    
    result = await session.execute(stmt)
    shops = result.scalars().all()
    
    # Score and rank results
    scored_results = []
    for shop in shops:
        score = calculate_match_score(query, shop)
        
        # Boost score if location matches
        if location and shop.address:
            if location.lower() in shop.address.lower():
                score = min(score + 0.2, 1.0)
        
        # Get primary phone
        primary_phone = await get_shop_primary_phone(session, shop.id)
        
        scored_results.append((score, BusinessSearchResult(
            business_id=shop.id,
            slug=shop.slug,
            name=shop.name,
            category=shop.category,
            address=shop.address,
            timezone=shop.timezone,
            primary_phone=primary_phone,
            confidence=round(score, 3),
        )))
    
    # Sort by score descending and limit
    scored_results.sort(key=lambda x: x[0], reverse=True)
    final_results = [r for _, r in scored_results[:limit]]
    
    return SearchResponse(
        query=query,
        results=final_results,
        total_count=len(final_results),
    )


# ────────────────────────────────────────────────────────────────
# Tool 2: get_business_summary
# ────────────────────────────────────────────────────────────────

@router.get("/business/{identifier}", response_model=BusinessSummary)
async def get_business_summary(
    identifier: str = Path(..., description="Business ID (numeric) or slug"),
    session: AsyncSession = Depends(get_session),
) -> BusinessSummary:
    """
    Get detailed summary for a specific business.
    
    This tool provides all information needed for RouterGPT to describe
    a business to the user and prepare for handoff.
    
    Accepts either:
    - Numeric business_id: /router/business/1
    - Slug: /router/business/bishops-tempe
    
    Example:
        GET /router/business/1
        GET /router/business/bishops-tempe
    """
    logger.info(f"RouterGPT get_business_summary: identifier='{identifier}'")
    
    # Determine if identifier is numeric (ID) or string (slug)
    if identifier.isdigit():
        stmt = select(Shop).where(Shop.id == int(identifier))
    else:
        stmt = select(Shop).where(Shop.slug == identifier)
    
    result = await session.execute(stmt)
    shop = result.scalar_one_or_none()
    
    if not shop:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Business not found: {identifier}"
        )
    
    # Get service count
    service_result = await session.execute(
        select(func.count(Service.id)).where(Service.shop_id == shop.id)
    )
    service_count = service_result.scalar() or 0
    
    # Get active stylist count
    stylist_result = await session.execute(
        select(func.count(Stylist.id))
        .where(Stylist.shop_id == shop.id)
        .where(Stylist.active == True)
    )
    stylist_count = stylist_result.scalar() or 0
    
    # Get phone and voice capability
    primary_phone = await get_shop_primary_phone(session, shop.id)
    supports_voice = await check_shop_has_voice(session, shop.id)
    
    return BusinessSummary(
        business_id=shop.id,
        slug=shop.slug,
        name=shop.name,
        timezone=shop.timezone,
        address=shop.address,
        category=shop.category,
        primary_phone=primary_phone,
        service_count=service_count,
        stylist_count=stylist_count,
        capabilities=BusinessCapabilities(
            supports_chat=True,
            supports_voice=supports_voice,
            supports_owner_chat=True,
        ),
        chat_endpoint=f"/s/{shop.slug}/chat",
        owner_chat_endpoint=f"/s/{shop.slug}/owner/chat",
        services_endpoint=f"/s/{shop.slug}/services",
    )


# ────────────────────────────────────────────────────────────────
# Tool 3: handoff_to_business_gpt
# ────────────────────────────────────────────────────────────────

@router.post("/handoff", response_model=HandoffResponse)
async def handoff_to_business_gpt(
    request: HandoffRequest,
    session: AsyncSession = Depends(get_session),
) -> HandoffResponse:
    """
    Generate handoff package for delegating to a business-specific GPT.
    
    This tool DOES NOT book anything. It prepares the payload structure
    for the client (ChatGPT) to call the business's /s/{slug}/chat endpoint.
    
    Requires either business_id OR slug in the request.
    
    Example:
        POST /router/handoff
        {
            "slug": "bishops-tempe",
            "conversation_context": [
                {"role": "user", "content": "I want to book a haircut"}
            ],
            "user_intent": "book haircut"
        }
    
    Returns:
        Handoff package with recommended endpoint and payload template.
    """
    logger.info(f"RouterGPT handoff: business_id={request.business_id}, slug={request.slug}")
    
    # Resolve shop
    if request.business_id:
        stmt = select(Shop).where(Shop.id == request.business_id)
    elif request.slug:
        stmt = select(Shop).where(Shop.slug == request.slug)
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Must provide either business_id or slug"
        )
    
    result = await session.execute(stmt)
    shop = result.scalar_one_or_none()
    
    if not shop:
        identifier = request.business_id or request.slug
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Business not found: {identifier}"
        )
    
    # Build the payload template
    messages_for_handoff = list(request.conversation_context)
    
    # If there's user intent and no context, add it as the first user message
    if request.user_intent and not messages_for_handoff:
        messages_for_handoff.append(ConversationMessage(
            role="user",
            content=request.user_intent
        ))
    
    payload_template = HandoffPayloadTemplate(
        messages=[msg.model_dump() for msg in messages_for_handoff],
        metadata={
            "shop_slug": shop.slug,
            "shop_name": shop.name,
            "shop_id": shop.id,
            "timezone": shop.timezone,
            "source": "router_gpt_handoff",
        }
    )
    
    # Build explanation
    intent_str = f" for: {request.user_intent}" if request.user_intent else ""
    explanation = f"Delegating to {shop.name} GPT{intent_str}. " \
                  f"Call POST {f'/s/{shop.slug}/chat'} with the payload template."
    
    return HandoffResponse(
        business_id=shop.id,
        slug=shop.slug,
        name=shop.name,
        recommended_endpoint=f"/s/{shop.slug}/chat",
        payload_template=payload_template,
        explanation=explanation,
    )


# ────────────────────────────────────────────────────────────────
# Health / Info Endpoint
# ────────────────────────────────────────────────────────────────

@router.get("/info")
async def router_info():
    """
    Get RouterGPT info and available tools.
    
    Returns metadata about the RouterGPT discovery layer.
    """
    return {
        "name": "RouterGPT",
        "version": "1.0.0",
        "description": "Discovery and delegation layer for multi-tenant booking",
        "capabilities": {
            "books_appointments": False,
            "modifies_data": False,
            "discovery_only": True,
        },
        "tools": [
            {
                "name": "search_businesses",
                "endpoint": "GET /router/search",
                "description": "Search for businesses by name, location, or category",
            },
            {
                "name": "get_business_summary",
                "endpoint": "GET /router/business/{id}",
                "description": "Get detailed information about a specific business",
            },
            {
                "name": "handoff_to_business_gpt",
                "endpoint": "POST /router/handoff",
                "description": "Generate handoff package for delegation to business GPT",
            },
        ],
        "delegation_pattern": "/s/{slug}/chat",
    }
