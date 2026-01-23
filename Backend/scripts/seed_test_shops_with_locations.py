#!/usr/bin/env python3
"""
Seed Test Shops with Locations

This script creates realistic test data for development and testing
of the RouterGPT location-based search feature.

Usage:
    cd Backend
    python scripts/seed_test_shops_with_locations.py
    
    # Clean up existing test shops first:
    python scripts/seed_test_shops_with_locations.py --clean
    
    # Only create shops if they don't exist:
    python scripts/seed_test_shops_with_locations.py --skip-existing

Creates:
    - 5 test shops in the Phoenix metro area
    - 3-5 services per shop
    - 2-3 stylists per shop
    - All with accurate geocoded locations
"""

import argparse
import asyncio
import logging
import os
import sys
from datetime import datetime, time

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.models import Shop, Service, Stylist

# ────────────────────────────────────────────────────────────────
# Configuration
# ────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Test owner ID for all seeded shops
TEST_OWNER_ID = "test-owner-routergpt"


# ────────────────────────────────────────────────────────────────
# Helper Functions
# ────────────────────────────────────────────────────────────────

def parse_time(time_str: str) -> time:
    """Convert 'HH:MM' string to datetime.time object."""
    hour, minute = map(int, time_str.split(':'))
    return time(hour, minute)


# ────────────────────────────────────────────────────────────────
# Test Data
# ────────────────────────────────────────────────────────────────

TEST_SHOPS = [
    {
        "name": "Bishop's Barbershop Tempe",
        "slug": "bishops-barbershop-tempe",
        "address": "123 Mill Avenue, Tempe, AZ 85281",
        "category": "barbershop",
        "latitude": 33.4255,
        "longitude": -111.9400,
        "timezone": "America/Phoenix",
        "phone": "+1-480-555-0101",
        "services": [
            {"name": "Men's Haircut", "duration": 30, "price": 3500},
            {"name": "Beard Trim", "duration": 15, "price": 2000},
            {"name": "Hot Towel Shave", "duration": 30, "price": 3000},
            {"name": "Haircut + Beard", "duration": 45, "price": 5000},
            {"name": "Kid's Haircut", "duration": 20, "price": 2500},
        ],
        "stylists": [
            {"name": "Marcus", "start": "09:00", "end": "17:00"},
            {"name": "Tony", "start": "10:00", "end": "18:00"},
            {"name": "Derek", "start": "11:00", "end": "19:00"},
        ],
    },
    {
        "name": "Tempe Hair Salon",
        "slug": "tempe-hair-salon",
        "address": "456 University Drive, Tempe, AZ 85281",
        "category": "salon",
        "latitude": 33.4356,
        "longitude": -111.9543,
        "timezone": "America/Phoenix",
        "phone": "+1-480-555-0102",
        "services": [
            {"name": "Women's Haircut", "duration": 45, "price": 5500},
            {"name": "Men's Haircut", "duration": 30, "price": 3500},
            {"name": "Hair Coloring", "duration": 90, "price": 12000},
            {"name": "Highlights", "duration": 120, "price": 15000},
            {"name": "Blowout", "duration": 30, "price": 4000},
        ],
        "stylists": [
            {"name": "Sarah", "start": "09:00", "end": "17:00"},
            {"name": "Emily", "start": "10:00", "end": "18:00"},
        ],
    },
    {
        "name": "Phoenix Beauty Studio",
        "slug": "phoenix-beauty-studio",
        "address": "789 Central Avenue, Phoenix, AZ 85004",
        "category": "beauty",
        "latitude": 33.4484,
        "longitude": -112.0740,
        "timezone": "America/Phoenix",
        "phone": "+1-602-555-0103",
        "services": [
            {"name": "Facial Treatment", "duration": 60, "price": 8000},
            {"name": "Manicure", "duration": 30, "price": 3500},
            {"name": "Pedicure", "duration": 45, "price": 5000},
            {"name": "Mani-Pedi Combo", "duration": 75, "price": 8000},
        ],
        "stylists": [
            {"name": "Jessica", "start": "09:00", "end": "18:00"},
            {"name": "Amanda", "start": "10:00", "end": "19:00"},
            {"name": "Lisa", "start": "08:00", "end": "16:00"},
        ],
    },
    {
        "name": "Scottsdale Styles",
        "slug": "scottsdale-styles",
        "address": "321 Scottsdale Road, Scottsdale, AZ 85251",
        "category": "salon",
        "latitude": 33.5092,
        "longitude": -111.8990,
        "timezone": "America/Phoenix",
        "phone": "+1-480-555-0104",
        "services": [
            {"name": "Luxury Haircut", "duration": 60, "price": 9000},
            {"name": "Keratin Treatment", "duration": 150, "price": 25000},
            {"name": "Balayage", "duration": 180, "price": 20000},
            {"name": "Scalp Treatment", "duration": 45, "price": 6000},
        ],
        "stylists": [
            {"name": "Michael", "start": "09:00", "end": "17:00"},
            {"name": "Rachel", "start": "10:00", "end": "18:00"},
        ],
    },
    {
        "name": "Mesa Cuts",
        "slug": "mesa-cuts",
        "address": "555 Main Street, Mesa, AZ 85201",
        "category": "barbershop",
        "latitude": 33.4152,
        "longitude": -111.8315,
        "timezone": "America/Phoenix",
        "phone": "+1-480-555-0105",
        "services": [
            {"name": "Classic Cut", "duration": 25, "price": 2500},
            {"name": "Fade", "duration": 35, "price": 3000},
            {"name": "Line Up", "duration": 15, "price": 1500},
            {"name": "Full Service", "duration": 45, "price": 4500},
            {"name": "Senior Cut", "duration": 25, "price": 2000},
        ],
        "stylists": [
            {"name": "Carlos", "start": "08:00", "end": "16:00"},
            {"name": "Juan", "start": "10:00", "end": "18:00"},
            {"name": "Mike", "start": "12:00", "end": "20:00"},
        ],
    },
]

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
# Seeding Functions
# ────────────────────────────────────────────────────────────────

async def shop_exists(session: AsyncSession, slug: str) -> bool:
    """Check if a shop with the given slug exists."""
    stmt = select(Shop).where(Shop.slug == slug)
    result = await session.execute(stmt)
    return result.scalar_one_or_none() is not None


async def clean_test_shops(session: AsyncSession) -> int:
    """Remove all test shops created by this script."""
    # Get test shop IDs
    stmt = select(Shop.id).where(Shop.owner_user_id == TEST_OWNER_ID)
    result = await session.execute(stmt)
    shop_ids = [row[0] for row in result.fetchall()]
    
    if not shop_ids:
        return 0
    
    # Delete services and stylists first (foreign key constraints)
    for shop_id in shop_ids:
        await session.execute(delete(Service).where(Service.shop_id == shop_id))
        await session.execute(delete(Stylist).where(Stylist.shop_id == shop_id))
    
    # Delete shops
    await session.execute(delete(Shop).where(Shop.owner_user_id == TEST_OWNER_ID))
    await session.commit()
    
    return len(shop_ids)


async def create_shop(session: AsyncSession, shop_data: dict) -> Shop:
    """Create a shop with services and stylists."""
    # Create shop
    shop = Shop(
        name=shop_data["name"],
        slug=shop_data["slug"],
        address=shop_data["address"],
        category=shop_data["category"],
        latitude=shop_data["latitude"],
        longitude=shop_data["longitude"],
        timezone=shop_data["timezone"],
        phone_number=shop_data.get("phone"),
    )
    session.add(shop)
    await session.flush()  # Get the shop ID
    
    # Create services
    for svc_data in shop_data["services"]:
        service = Service(
            shop_id=shop.id,
            name=svc_data["name"],
            duration_minutes=svc_data["duration"],
            price_cents=svc_data["price"],
        )
        session.add(service)
    
    # Create stylists
    for stylist_data in shop_data["stylists"]:
        stylist = Stylist(
            shop_id=shop.id,
            name=stylist_data["name"],
            work_start=parse_time(stylist_data["start"]),
            work_end=parse_time(stylist_data["end"]),
            active=True,
        )
        session.add(stylist)
    
    await session.commit()
    return shop


async def run_seeding(clean: bool = False, skip_existing: bool = False) -> dict:
    """
    Main seeding function.
    
    Args:
        clean: If True, delete existing test shops first
        skip_existing: If True, skip shops that already exist
    
    Returns:
        Summary dict with counts
    """
    logger.info("=" * 60)
    logger.info("Seed Test Shops with Locations")
    logger.info("=" * 60)
    logger.info(f"Test owner ID: {TEST_OWNER_ID}")
    logger.info("")
    
    session = await get_session()
    
    try:
        results = {"created": 0, "skipped": 0, "cleaned": 0}
        
        # Clean if requested
        if clean:
            logger.info("🧹 Cleaning existing test shops...")
            cleaned = await clean_test_shops(session)
            results["cleaned"] = cleaned
            logger.info(f"  Removed {cleaned} test shop(s)")
            logger.info("")
        
        # Create shops
        logger.info(f"📍 Creating {len(TEST_SHOPS)} test shops...")
        logger.info("")
        
        for shop_data in TEST_SHOPS:
            logger.info(f"  {shop_data['name']}")
            logger.info(f"    📍 {shop_data['address']}")
            logger.info(f"    🌐 ({shop_data['latitude']}, {shop_data['longitude']})")
            
            if skip_existing and await shop_exists(session, shop_data["slug"]):
                logger.info(f"    ⏭️  Skipped (already exists)")
                results["skipped"] += 1
                continue
            
            await create_shop(session, shop_data)
            logger.info(f"    ✅ Created with {len(shop_data['services'])} services, {len(shop_data['stylists'])} stylists")
            results["created"] += 1
        
        return results
        
    finally:
        await session.close()


def print_summary(results: dict) -> None:
    """Print final summary."""
    logger.info("")
    logger.info("=" * 60)
    logger.info("SUMMARY")
    logger.info("=" * 60)
    if results["cleaned"] > 0:
        logger.info(f"  Cleaned:  {results['cleaned']} shop(s) 🧹")
    logger.info(f"  Created:  {results['created']} shop(s) ✅")
    logger.info(f"  Skipped:  {results['skipped']} shop(s) ⏭️")
    logger.info("=" * 60)
    logger.info("")
    logger.info("Test the location search with:")
    logger.info("  curl -X POST http://localhost:8000/router/search-by-location \\")
    logger.info("    -H 'Content-Type: application/json' \\")
    logger.info("    -d '{\"latitude\": 33.4255, \"longitude\": -111.94, \"radius_miles\": 25}'")


# ────────────────────────────────────────────────────────────────
# CLI Entry Point
# ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Seed test shops with locations for RouterGPT testing"
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Remove existing test shops before creating new ones"
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip shops that already exist (by slug)"
    )
    
    args = parser.parse_args()
    
    try:
        results = asyncio.run(run_seeding(
            clean=args.clean,
            skip_existing=args.skip_existing
        ))
        print_summary(results)
        
    except KeyboardInterrupt:
        logger.info("\n🛑 Interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
