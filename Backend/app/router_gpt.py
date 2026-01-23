"""
RouterGPT - Discovery & Delegation Layer (Phase 5)

This module provides a "global entry" layer for ChatGPT to discover and route
to shop-specific GPTs. RouterGPT NEVER books - it only helps users find the
right business and delegates to the appropriate multi-tenant endpoint.

Endpoints:
    GET  /router/search              - Search businesses by query/location/category
    POST /router/search-by-location  - Search businesses by lat/lon coordinates
    GET  /router/business/{id}       - Get detailed business summary
    POST /router/handoff             - Generate handoff package for delegation
    POST /router/delegate            - Delegate to a shop's booking agent

Design Principles:
    - Discovery only - never creates bookings or modifies data
    - Multi-tenant safe - only exposes public shop information
    - Stateless - each request is independent
    - Delegates to /s/{slug}/... endpoints for actual booking

Tools for ChatGPT:
    1. search_businesses - Find businesses matching user criteria
    2. search_by_location - Find nearby businesses by coordinates
    3. get_business_summary - Get details about a specific business
    4. handoff_to_business_gpt - Generate delegation payload
    5. delegate_to_shop - Hand off to shop's booking agent
"""

import logging
import re
import uuid
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Path, Body, status, Request
from pydantic import BaseModel, Field
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from .core.db import get_session
from .models import Shop, ShopPhoneNumber, Service, Stylist
from .geocoding import calculate_distance, geocode_or_lookup
from .rate_limiter import rate_limit_dependency
from .router_analytics import track_search, track_delegation


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
# Phase 3: Location Search & Delegation Models
# ────────────────────────────────────────────────────────────────

class LocationSearchRequest(BaseModel):
    """Request for location-based business search."""
    latitude: float = Field(..., ge=-90, le=90, description="Latitude coordinate")
    longitude: float = Field(..., ge=-180, le=180, description="Longitude coordinate")
    radius_miles: float = Field(5.0, gt=0, le=50, description="Search radius in miles")
    category: Optional[str] = Field(None, description="Filter by category (e.g., 'barbershop', 'salon')")
    query: Optional[str] = Field(None, description="Additional text filter")


class LocationSearchResult(BaseModel):
    """A single business in location search results."""
    business_id: int = Field(..., description="Unique business ID (shop_id)")
    slug: str = Field(..., description="URL-safe slug for routing")
    name: str = Field(..., description="Business display name")
    category: Optional[str] = Field(None, description="Business category")
    address: Optional[str] = Field(None, description="Business address")
    timezone: str = Field(..., description="IANA timezone")
    primary_phone: Optional[str] = Field(None, description="Primary contact phone")
    distance_miles: float = Field(..., description="Distance from search coordinates in miles")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Match confidence score")


class LocationSearchResponse(BaseModel):
    """Response for location-based search."""
    query: str = Field(..., description="Description of the search")
    latitude: float = Field(..., description="Search center latitude")
    longitude: float = Field(..., description="Search center longitude")
    radius_miles: float = Field(..., description="Search radius used")
    results: list[LocationSearchResult] = Field(default_factory=list)
    total_count: int = Field(..., description="Total matching businesses")


class CustomerContext(BaseModel):
    """Context about the customer from RouterGPT."""
    location: Optional[dict] = Field(None, description="Customer location {lat, lon}")
    intent: Optional[str] = Field(None, description="Extracted intent (e.g., 'haircut')")
    preferred_time: Optional[str] = Field(None, description="Preferred time (e.g., 'afternoon')")


class DelegateRequest(BaseModel):
    """Request to delegate to a shop's booking agent."""
    shop_slug: str = Field(..., description="Target shop slug")
    customer_context: Optional[CustomerContext] = Field(None, description="Context from RouterGPT")
    conversation_history: list[ConversationMessage] = Field(
        default_factory=list,
        description="Conversation history to preserve"
    )


class ServiceInfo(BaseModel):
    """Service information for delegation response."""
    id: int
    name: str
    duration_minutes: int
    price_cents: int
    price_display: str


class DelegateResponse(BaseModel):
    """Response for delegation to shop booking agent."""
    success: bool = Field(..., description="Whether delegation was successful")
    shop_slug: str = Field(..., description="Target shop slug")
    shop_name: str = Field(..., description="Shop display name")
    session_id: str = Field(..., description="Unique session ID for tracking")
    initial_message: str = Field(..., description="Greeting from the business agent")
    available_services: list[ServiceInfo] = Field(default_factory=list, description="First few services")


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
# Phase 3: Location-Based Search Endpoint
# ────────────────────────────────────────────────────────────────

@router.post("/search-by-location", response_model=LocationSearchResponse)
async def search_by_location(
    request: LocationSearchRequest,
    req: Request,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(rate_limit_dependency(20, 60)),  # 20 requests per minute
) -> LocationSearchResponse:
    """
    Search for businesses near a geographic location.
    
    Rate Limit: 20 requests per minute per IP
    
    This endpoint enables RouterGPT to find nearby businesses based on
    customer coordinates (typically obtained from ChatGPT's location detection).
    
    The search:
    1. Finds all shops with valid coordinates
    2. Calculates distance using Haversine formula
    3. Filters by radius and optional category/query
    4. Ranks by distance (closest first)
    5. Calculates confidence score based on distance
    
    Example:
        POST /router/search-by-location
        {
            "latitude": 33.4255,
            "longitude": -111.9400,
            "radius_miles": 5,
            "category": "barbershop"
        }
    
    Returns:
        List of nearby businesses with distance and confidence scores.
    """
    logger.info(
        f"[ROUTER] Search: lat={request.latitude}, lon={request.longitude}, "
        f"radius={request.radius_miles}mi, category={request.category or 'all'}"
    )
    
    # Fetch all shops with coordinates
    stmt = select(Shop).where(
        Shop.latitude.isnot(None),
        Shop.longitude.isnot(None)
    )
    
    # Apply category filter if provided
    if request.category:
        stmt = stmt.where(Shop.category == request.category.lower())
    
    result = await session.execute(stmt)
    shops = result.scalars().all()
    
    # Calculate distances and filter by radius
    scored_results = []
    for shop in shops:
        # Calculate distance
        distance = calculate_distance(
            request.latitude, request.longitude,
            shop.latitude, shop.longitude
        )
        
        # Skip if outside radius
        if distance > request.radius_miles:
            continue
        
        # Apply text query filter if provided
        if request.query:
            query_lower = request.query.lower()
            name_match = query_lower in (shop.name or "").lower()
            address_match = query_lower in (shop.address or "").lower()
            category_match = query_lower in (shop.category or "").lower()
            if not (name_match or address_match or category_match):
                continue
        
        # Calculate confidence (closer = higher confidence)
        confidence = max(0.0, 1.0 - (distance / request.radius_miles))
        
        # Get primary phone
        primary_phone = await get_shop_primary_phone(session, shop.id)
        
        scored_results.append(LocationSearchResult(
            business_id=shop.id,
            slug=shop.slug,
            name=shop.name,
            category=shop.category,
            address=shop.address,
            timezone=shop.timezone,
            primary_phone=primary_phone,
            distance_miles=round(distance, 2),
            confidence=round(confidence, 3),
        ))
    
    # Sort by distance (closest first)
    scored_results.sort(key=lambda x: x.distance_miles)
    
    # Limit to top 10 results
    final_results = scored_results[:10]
    
    # Track search analytics
    try:
        await track_search(
            session=session,
            session_id=uuid.uuid4(),  # Generate unique search ID
            latitude=request.latitude,
            longitude=request.longitude,
            radius_miles=request.radius_miles,
            category=request.category,
            results_count=len(final_results),
            request=req,  # Pass FastAPI request for IP/user-agent
        )
        await session.commit()
    except Exception as e:
        logger.error(f"[ANALYTICS] Failed to track search: {e}")
        # Don't fail the request if analytics fails
    
    # Log search results
    logger.info(
        f"[ROUTER] Search results: {len(final_results)} businesses found "
        f"(total within radius: {len(scored_results)})"
    )
    
    query_desc = f"Businesses within {request.radius_miles} miles"
    if request.category:
        query_desc += f" in category '{request.category}'"
    if request.query:
        query_desc += f" matching '{request.query}'"
    
    return LocationSearchResponse(
        query=query_desc,
        latitude=request.latitude,
        longitude=request.longitude,
        radius_miles=request.radius_miles,
        results=final_results,
        total_count=len(final_results),
    )


# ────────────────────────────────────────────────────────────────
# Phase 3: Delegation Endpoint
# ────────────────────────────────────────────────────────────────

@router.post("/delegate", response_model=DelegateResponse)
async def delegate_to_shop(
    request: DelegateRequest,
    req: Request,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(rate_limit_dependency(10, 60)),  # 10 requests per minute
) -> DelegateResponse:
    """
    Delegate to a shop's booking agent with context.
    
    Rate Limit: 10 requests per minute per IP
    
    This endpoint is called by RouterGPT after the customer selects a business.
    It prepares the handoff to the shop's booking agent with any context
    collected during discovery (location, intent, preferences).
    
    The response includes:
    - A unique session_id for tracking
    - An initial greeting message from the business
    - Available services to show the customer
    
    After calling this endpoint, RouterGPT should:
    1. Present the initial_message to the customer
    2. Route subsequent messages to POST /s/{slug}/chat
    3. Include router_session_id in the chat requests
    
    Example:
        POST /router/delegate
        {
            "shop_slug": "bishops-tempe",
            "customer_context": {
                "location": {"lat": 33.4255, "lon": -111.94},
                "intent": "haircut"
            }
        }
    """
    logger.info(f"RouterGPT delegate to shop: {request.shop_slug}")
    
    # Resolve shop
    stmt = select(Shop).where(Shop.slug == request.shop_slug)
    result = await session.execute(stmt)
    shop = result.scalar_one_or_none()
    
    if not shop:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Shop not found: {request.shop_slug}"
        )
    
    # Generate unique session ID for tracking
    session_id = str(uuid.uuid4())
    
    # Get first 5 services for context
    services_stmt = select(Service).where(Service.shop_id == shop.id).limit(5)
    services_result = await session.execute(services_stmt)
    services = services_result.scalars().all()
    
    # Format services
    available_services = [
        ServiceInfo(
            id=svc.id,
            name=svc.name,
            duration_minutes=svc.duration_minutes,
            price_cents=svc.price_cents,
            price_display=f"${svc.price_cents / 100:.2f}",
        )
        for svc in services
    ]
    
    # Build initial greeting based on context
    intent = request.customer_context.intent if request.customer_context else None
    
    if intent:
        greeting = f"Welcome to {shop.name}! I understand you're looking for {intent}. "
    else:
        greeting = f"Welcome to {shop.name}! I'm here to help you book an appointment. "
    
    # Add service suggestions
    if available_services:
        top_services = available_services[:3]
        service_list = ", ".join([s.name for s in top_services])
        greeting += f"We offer {service_list} and more. What would you like to book today?"
    else:
        greeting += "How can I help you today?"
    
    # Log delegation
    logger.info(
        f"[ROUTER] Delegate: shop={request.shop_slug}, session={session_id}, "
        f"intent={intent or 'none'}, services={len(available_services)}"
    )
    
    # Track delegation analytics
    try:
        await track_delegation(
            session=session,
            session_id=uuid.UUID(session_id),
            shop_id=shop.id,
            shop_slug=shop.slug,
            customer_latitude=request.customer_context.location.get("lat") if request.customer_context and request.customer_context.location else None,
            customer_longitude=request.customer_context.location.get("lon") if request.customer_context and request.customer_context.location else None,
            shop_latitude=shop.latitude,
            shop_longitude=shop.longitude,
            intent=intent,
            request=req,  # Pass FastAPI request for IP/user-agent
        )
        await session.commit()
    except Exception as e:
        logger.error(f"[ANALYTICS] Failed to track delegation: {e}")
        # Don't fail the request if analytics fails
    
    return DelegateResponse(
        success=True,
        shop_slug=shop.slug,
        shop_name=shop.name,
        session_id=session_id,
        initial_message=greeting,
        available_services=available_services,
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
