#!/usr/bin/env python3
"""
Initialize test database schema using SQLAlchemy models.

This script creates all tables in the convo_test database.
Safe to run multiple times (idempotent).

Usage:
    export DATABASE_URL="postgresql+asyncpg://localhost:5432/convo_test"
    python3 Backend/scripts/init_test_db.py
"""
import asyncio
import os
import sys
from pathlib import Path

# Add Backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.ext.asyncio import create_async_engine
from app.models import Base

# Get test database URL from environment
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    print("❌ ERROR: DATABASE_URL environment variable not set")
    print("   Use: export DATABASE_URL='postgresql+asyncpg://localhost:5432/convo_test'")
    sys.exit(1)

# Safety check - NEVER run against production
if "neon" in DATABASE_URL.lower() or "neondb" in DATABASE_URL.lower():
    print("❌ FATAL: Cannot initialize production Neon database!")
    print(f"   DATABASE_URL: {DATABASE_URL}")
    print("   This script is for LOCAL TEST DATABASES ONLY")
    print("   Use: export DATABASE_URL='postgresql+asyncpg://localhost:5432/convo_test'")
    sys.exit(1)


async def init_db():
    """Create all tables in test database."""
    print(f"🔧 Initializing test database...")
    print(f"   Database: {DATABASE_URL}")
    
    # Create async engine
    engine = create_async_engine(DATABASE_URL, echo=False)
    
    try:
        # Create all tables
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        
        print("✅ Test database schema initialized successfully!")
        print("\n📋 Tables created:")
        print("   - shops (with slug column)")
        print("   - shop_phone_numbers")
        print("   - shop_api_keys")
        print("   - shop_members (Phase 6)")
        print("   - services, stylists, bookings")
        print("   - customers, customer_shop_profiles")
        print("   - time_off_blocks, time_off_requests")
        print("   - promos, promo_impressions")
        print("   - call_summaries")
        print("\n🎯 Next steps:")
        print("   1. Run tests:")
        print("      pytest Backend/tests/test_phase6_onboarding.py -v")
        print("   2. Seed data for manual testing:")
        print("      python3 Backend/scripts/seed_convo_test.py")
        
    except Exception as e:
        print(f"❌ Error initializing database: {e}")
        sys.exit(1)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(init_db())
