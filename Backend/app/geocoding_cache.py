"""
Geocoding Cache Module

Phase 3: RouterGPT Integration (Performance Optimization)

This module provides database-backed caching for geocoding results.
It wraps the main geocoding functions to check cache first, reducing
external API calls and improving latency.

Usage:
    from .geocoding_cache import CachedGeocoder
    
    geocoder = CachedGeocoder(db_session)
    lat, lon = await geocoder.geocode("123 Mill Ave, Tempe, AZ 85281")
"""

import logging
import re
from datetime import datetime, timedelta
from typing import Optional
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert

from .geocoding import geocode_address, lookup_known_location

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────
# Address Normalization
# ────────────────────────────────────────────────────────────────

def normalize_address(address: str) -> str:
    """
    Normalize an address for consistent cache lookups.
    
    Transformations:
    - Lowercase
    - Strip whitespace
    - Collapse multiple spaces
    - Standardize common abbreviations
    
    Args:
        address: Raw address string
    
    Returns:
        Normalized address string
    """
    if not address:
        return ""
    
    # Lowercase and strip
    normalized = address.lower().strip()
    
    # Collapse multiple spaces
    normalized = re.sub(r'\s+', ' ', normalized)
    
    # Standardize common abbreviations
    replacements = {
        r'\bstreet\b': 'st',
        r'\bavenue\b': 'ave',
        r'\bboulevard\b': 'blvd',
        r'\bdrive\b': 'dr',
        r'\broad\b': 'rd',
        r'\blane\b': 'ln',
        r'\bcourt\b': 'ct',
        r'\bplace\b': 'pl',
        r'\bnorth\b': 'n',
        r'\bsouth\b': 's',
        r'\beast\b': 'e',
        r'\bwest\b': 'w',
        r'\bapartment\b': 'apt',
        r'\bsuite\b': 'ste',
    }
    
    for pattern, replacement in replacements.items():
        normalized = re.sub(pattern, replacement, normalized)
    
    return normalized


# ────────────────────────────────────────────────────────────────
# SQLAlchemy Model for Cache Table
# ────────────────────────────────────────────────────────────────

from sqlalchemy import Column, String, Numeric, DateTime, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base

# Use the existing Base if available, otherwise create a new one
try:
    from .models import Base
except ImportError:
    Base = declarative_base()


class GeocodingCache(Base):
    """SQLAlchemy model for geocoding_cache table."""
    
    __tablename__ = "geocoding_cache"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    address_normalized = Column(String(500), nullable=False, unique=True, index=True)
    address_original = Column(String(500), nullable=False)
    latitude = Column(Numeric(10, 7), nullable=False)
    longitude = Column(Numeric(10, 7), nullable=False)
    provider = Column(String(50), default="nominatim")
    confidence = Column(Numeric(3, 2), default=1.0)
    raw_response = Column(JSON)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    last_used_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    expires_at = Column(DateTime(timezone=True))
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.expires_at:
            self.expires_at = datetime.utcnow() + timedelta(days=90)


# ────────────────────────────────────────────────────────────────
# Cached Geocoder Class
# ────────────────────────────────────────────────────────────────

class CachedGeocoder:
    """
    Geocoder with database caching.
    
    This class wraps the standard geocoding functions with a
    database cache layer for improved performance.
    
    Cache TTL: 90 days (configurable)
    
    Usage:
        async with get_session() as session:
            geocoder = CachedGeocoder(session)
            lat, lon = await geocoder.geocode("123 Main St, City, ST")
    """
    
    DEFAULT_TTL_DAYS = 90
    
    def __init__(self, session: AsyncSession, ttl_days: int = None):
        """
        Initialize the cached geocoder.
        
        Args:
            session: SQLAlchemy async session
            ttl_days: Cache TTL in days (default: 90)
        """
        self.session = session
        self.ttl_days = ttl_days or self.DEFAULT_TTL_DAYS
    
    async def geocode(
        self,
        address: str,
        skip_cache: bool = False
    ) -> tuple[float | None, float | None]:
        """
        Geocode an address with caching.
        
        Order of operations:
        1. Check known locations (instant, no DB)
        2. Check database cache (fast, local)
        3. Call external geocoding API (slow, remote)
        4. Store result in cache
        
        Args:
            address: Address string to geocode
            skip_cache: If True, bypass cache and call API directly
        
        Returns:
            (latitude, longitude) tuple or (None, None) if geocoding fails
        """
        if not address or len(address.strip()) < 3:
            logger.warning("CachedGeocoder: Invalid or empty address")
            return None, None
        
        # 1. Try known locations first (no DB/API needed)
        lat, lon = lookup_known_location(address)
        if lat is not None:
            logger.debug(f"Geocode from known locations: {address}")
            return lat, lon
        
        normalized = normalize_address(address)
        
        # 2. Check cache (unless skip_cache is True)
        if not skip_cache:
            cached = await self._get_from_cache(normalized)
            if cached:
                lat, lon = cached
                logger.debug(f"Geocode from cache: {address} -> ({lat}, {lon})")
                return lat, lon
        
        # 3. Call external geocoding API
        lat, lon = await geocode_address(address)
        
        # 4. Store in cache if successful
        if lat is not None and lon is not None:
            await self._store_in_cache(
                address_normalized=normalized,
                address_original=address,
                latitude=lat,
                longitude=lon
            )
        
        return lat, lon
    
    async def _get_from_cache(
        self,
        normalized_address: str
    ) -> tuple[float, float] | None:
        """
        Retrieve coordinates from cache.
        
        Also updates last_used_at timestamp for cache hit tracking.
        
        Args:
            normalized_address: Normalized address string
        
        Returns:
            (latitude, longitude) tuple or None if not in cache
        """
        try:
            # Query cache
            result = await self.session.execute(
                select(GeocodingCache)
                .where(GeocodingCache.address_normalized == normalized_address)
                .where(GeocodingCache.expires_at > datetime.utcnow())
            )
            cached = result.scalar_one_or_none()
            
            if cached:
                # Update last_used_at
                await self.session.execute(
                    update(GeocodingCache)
                    .where(GeocodingCache.id == cached.id)
                    .values(last_used_at=datetime.utcnow())
                )
                await self.session.commit()
                
                return float(cached.latitude), float(cached.longitude)
            
            return None
            
        except Exception as e:
            logger.error(f"Cache lookup error: {e}")
            return None
    
    async def _store_in_cache(
        self,
        address_normalized: str,
        address_original: str,
        latitude: float,
        longitude: float,
        provider: str = "nominatim"
    ):
        """
        Store geocoding result in cache.
        
        Uses upsert to handle race conditions.
        
        Args:
            address_normalized: Normalized address string
            address_original: Original address string
            latitude: Geocoded latitude
            longitude: Geocoded longitude
            provider: Geocoding provider name
        """
        try:
            expires_at = datetime.utcnow() + timedelta(days=self.ttl_days)
            
            # Use PostgreSQL upsert
            stmt = insert(GeocodingCache).values(
                id=uuid4(),
                address_normalized=address_normalized,
                address_original=address_original,
                latitude=latitude,
                longitude=longitude,
                provider=provider,
                created_at=datetime.utcnow(),
                last_used_at=datetime.utcnow(),
                expires_at=expires_at
            ).on_conflict_do_update(
                index_elements=['address_normalized'],
                set_={
                    'latitude': latitude,
                    'longitude': longitude,
                    'last_used_at': datetime.utcnow(),
                    'expires_at': expires_at
                }
            )
            
            await self.session.execute(stmt)
            await self.session.commit()
            
            logger.debug(f"Cached geocoding result for: {address_original}")
            
        except Exception as e:
            logger.error(f"Cache store error: {e}")
            # Don't fail the request if caching fails
            await self.session.rollback()
    
    async def invalidate(self, address: str):
        """
        Remove an address from the cache.
        
        Args:
            address: Address to invalidate
        """
        normalized = normalize_address(address)
        
        try:
            from sqlalchemy import delete
            
            await self.session.execute(
                delete(GeocodingCache)
                .where(GeocodingCache.address_normalized == normalized)
            )
            await self.session.commit()
            
            logger.info(f"Invalidated cache for: {address}")
            
        except Exception as e:
            logger.error(f"Cache invalidation error: {e}")
            await self.session.rollback()
    
    async def cleanup_expired(self) -> int:
        """
        Remove expired cache entries.
        
        Returns:
            Number of deleted entries
        """
        try:
            from sqlalchemy import delete
            
            result = await self.session.execute(
                delete(GeocodingCache)
                .where(GeocodingCache.expires_at < datetime.utcnow())
            )
            await self.session.commit()
            
            count = result.rowcount
            logger.info(f"Cleaned up {count} expired geocoding cache entries")
            return count
            
        except Exception as e:
            logger.error(f"Cache cleanup error: {e}")
            await self.session.rollback()
            return 0
    
    async def get_stats(self) -> dict:
        """
        Get cache statistics.
        
        Returns:
            Dictionary with cache stats
        """
        try:
            from sqlalchemy import func
            
            # Total entries
            total_result = await self.session.execute(
                select(func.count(GeocodingCache.id))
            )
            total = total_result.scalar() or 0
            
            # Expired entries
            expired_result = await self.session.execute(
                select(func.count(GeocodingCache.id))
                .where(GeocodingCache.expires_at < datetime.utcnow())
            )
            expired = expired_result.scalar() or 0
            
            # By provider
            provider_result = await self.session.execute(
                select(
                    GeocodingCache.provider,
                    func.count(GeocodingCache.id)
                )
                .group_by(GeocodingCache.provider)
            )
            by_provider = {row[0]: row[1] for row in provider_result.all()}
            
            return {
                "total_entries": total,
                "active_entries": total - expired,
                "expired_entries": expired,
                "by_provider": by_provider,
                "ttl_days": self.ttl_days
            }
            
        except Exception as e:
            logger.error(f"Cache stats error: {e}")
            return {"error": str(e)}


# ────────────────────────────────────────────────────────────────
# Convenience Functions
# ────────────────────────────────────────────────────────────────

async def geocode_with_cache(
    session: AsyncSession,
    address: str
) -> tuple[float | None, float | None]:
    """
    Convenience function for one-off cached geocoding.
    
    Args:
        session: SQLAlchemy async session
        address: Address to geocode
    
    Returns:
        (latitude, longitude) tuple or (None, None)
    """
    geocoder = CachedGeocoder(session)
    return await geocoder.geocode(address)
