#!/usr/bin/env python3
"""
Geocode Existing Shops Script

This script backfills latitude/longitude coordinates for existing shops
that have an address but no coordinates.

Usage:
    cd Backend
    python scripts/geocode_existing_shops.py
    
    # Dry run (no database updates):
    python scripts/geocode_existing_shops.py --dry-run
    
    # Use only Nominatim (no Google API key required):
    python scripts/geocode_existing_shops.py --nominatim-only

Requirements:
    - Database connection (DATABASE_URL env var)
    - Optional: GOOGLE_MAPS_API_KEY for better geocoding results
"""

import argparse
import asyncio
import logging
import os
import sys
import time
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.models import Shop
from app.geocoding import geocode_address, geocode_with_nominatim

# ────────────────────────────────────────────────────────────────
# Configuration
# ────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Rate limiting: seconds between geocoding requests
RATE_LIMIT_SECONDS = 1.0  # Nominatim requires ~1 second between requests

# ────────────────────────────────────────────────────────────────
# Database Setup
# ────────────────────────────────────────────────────────────────

def get_database_url() -> str:
    """Get database URL from environment."""
    url = os.getenv("DATABASE_URL")
    if not url:
        raise ValueError("DATABASE_URL environment variable is not set")
    return url


async def get_session() -> AsyncSession:
    """Create a database session."""
    engine = create_async_engine(get_database_url(), echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return async_session()


# ────────────────────────────────────────────────────────────────
# Main Logic
# ────────────────────────────────────────────────────────────────

async def get_shops_without_coordinates(session: AsyncSession) -> list[Shop]:
    """Query all shops that have an address but no coordinates."""
    stmt = select(Shop).where(
        Shop.address.isnot(None),
        Shop.address != "",
        (Shop.latitude.is_(None) | Shop.longitude.is_(None))
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def update_shop_coordinates(
    session: AsyncSession,
    shop_id: int,
    latitude: float,
    longitude: float
) -> None:
    """Update a shop's coordinates in the database."""
    stmt = update(Shop).where(Shop.id == shop_id).values(
        latitude=latitude,
        longitude=longitude,
        updated_at=datetime.utcnow()
    )
    await session.execute(stmt)
    await session.commit()


async def geocode_shop(
    address: str,
    nominatim_only: bool = False
) -> tuple[float | None, float | None]:
    """
    Geocode a single shop address.
    
    Args:
        address: Shop address string
        nominatim_only: If True, only use Nominatim (no Google)
    
    Returns:
        (latitude, longitude) tuple or (None, None) if failed
    """
    if nominatim_only:
        return await geocode_with_nominatim(address)
    else:
        return await geocode_address(address)


async def run_geocoding(
    dry_run: bool = False,
    nominatim_only: bool = False
) -> dict:
    """
    Main geocoding function.
    
    Args:
        dry_run: If True, don't actually update the database
        nominatim_only: If True, only use Nominatim
    
    Returns:
        Summary dict with success/failure counts
    """
    logger.info("=" * 60)
    logger.info("Geocode Existing Shops Script")
    logger.info("=" * 60)
    
    if dry_run:
        logger.info("🔍 DRY RUN MODE - No database changes will be made")
    
    if nominatim_only:
        logger.info("📍 Using Nominatim only (no Google API)")
    else:
        google_key = os.getenv("GOOGLE_MAPS_API_KEY")
        if google_key:
            logger.info("📍 Using Google Maps API (with Nominatim fallback)")
        else:
            logger.info("📍 Using Nominatim only (GOOGLE_MAPS_API_KEY not set)")
    
    logger.info("")
    
    # Connect to database
    session = await get_session()
    
    try:
        # Get shops without coordinates
        shops = await get_shops_without_coordinates(session)
        
        if not shops:
            logger.info("✅ All shops already have coordinates. Nothing to do!")
            return {"total": 0, "success": 0, "failed": 0, "skipped": 0}
        
        logger.info(f"Found {len(shops)} shop(s) without coordinates:")
        for shop in shops:
            logger.info(f"  - [{shop.id}] {shop.name}: {shop.address}")
        
        logger.info("")
        
        # Process each shop
        results = {"total": len(shops), "success": 0, "failed": 0, "skipped": 0}
        
        for i, shop in enumerate(shops, 1):
            logger.info(f"[{i}/{len(shops)}] Processing: {shop.name}")
            
            if not shop.address or len(shop.address.strip()) < 5:
                logger.warning(f"  ⚠️ Skipping - address too short or empty")
                results["skipped"] += 1
                continue
            
            # Geocode
            lat, lon = await geocode_shop(shop.address, nominatim_only)
            
            if lat is not None and lon is not None:
                logger.info(f"  ✅ Geocoded to: ({lat:.6f}, {lon:.6f})")
                
                if not dry_run:
                    await update_shop_coordinates(session, shop.id, lat, lon)
                    logger.info(f"  💾 Database updated")
                else:
                    logger.info(f"  🔍 [DRY RUN] Would update database")
                
                results["success"] += 1
            else:
                logger.error(f"  ❌ Failed to geocode address: {shop.address}")
                results["failed"] += 1
            
            # Rate limiting
            if i < len(shops):
                logger.info(f"  ⏳ Waiting {RATE_LIMIT_SECONDS}s (rate limit)...")
                await asyncio.sleep(RATE_LIMIT_SECONDS)
        
        return results
        
    finally:
        await session.close()


def print_summary(results: dict) -> None:
    """Print final summary."""
    logger.info("")
    logger.info("=" * 60)
    logger.info("SUMMARY")
    logger.info("=" * 60)
    logger.info(f"  Total shops processed: {results['total']}")
    logger.info(f"  Successfully geocoded: {results['success']} ✅")
    logger.info(f"  Failed to geocode:     {results['failed']} ❌")
    logger.info(f"  Skipped (no address):  {results['skipped']} ⚠️")
    logger.info("=" * 60)


# ────────────────────────────────────────────────────────────────
# CLI Entry Point
# ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Geocode existing shops that are missing coordinates"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't actually update the database, just show what would happen"
    )
    parser.add_argument(
        "--nominatim-only",
        action="store_true",
        help="Only use Nominatim for geocoding (no Google API key required)"
    )
    
    args = parser.parse_args()
    
    try:
        results = asyncio.run(run_geocoding(
            dry_run=args.dry_run,
            nominatim_only=args.nominatim_only
        ))
        print_summary(results)
        
        # Exit with error code if any failed
        if results["failed"] > 0:
            sys.exit(1)
        
    except KeyboardInterrupt:
        logger.info("\n🛑 Interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
