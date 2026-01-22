#!/usr/bin/env python3
"""
Seed convo_test database with realistic multi-tenant test data.

This script inserts minimal but realistic data for manual testing:
- 1 shop (Bishops Tempe)
- 1 shop owner membership
- 1 phone number
- 2 services
- 1 stylist

IDEMPOTENT: Safe to run multiple times. Skips existing records.

Usage:
    export DATABASE_URL="postgresql+asyncpg://localhost:5432/convo_test"
    python3 Backend/scripts/seed_convo_test.py
"""
import asyncio
import os
import sys
from pathlib import Path
from datetime import time

# Add Backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import select
from app.models import (
    Base,
    Shop,
    ShopPhoneNumber,
    ShopMember,
    ShopMemberRole,
    Service,
    Stylist,
)

# Get database URL from environment
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    print("❌ ERROR: DATABASE_URL environment variable not set")
    print("   Use: export DATABASE_URL='postgresql+asyncpg://localhost:5432/convo_test'")
    sys.exit(1)

# Safety check - NEVER seed production
if "neon" in DATABASE_URL.lower() or "neondb" in DATABASE_URL.lower():
    print("❌ FATAL: Cannot seed production Neon database!")
    print(f"   DATABASE_URL: {DATABASE_URL}")
    print("   This script is for LOCAL TEST DATABASES ONLY")
    print("   Use: export DATABASE_URL='postgresql+asyncpg://localhost:5432/convo_test'")
    sys.exit(1)


async def seed_data():
    """Seed test database with realistic multi-tenant data."""
    print(f"🌱 Seeding test database...")
    print(f"   Database: {DATABASE_URL}")
    
    # Create async engine and session
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    try:
        # Ensure tables exist (convenience for local dev)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        
        async with async_session_maker() as session:
            # Check if shop already exists
            existing_shop = await session.scalar(
                select(Shop).where(Shop.slug == "bishops-tempe")
            )
            
            if existing_shop:
                print("ℹ️  Shop 'bishops-tempe' already exists. Skipping seed.")
                print(f"   Shop ID: {existing_shop.id}")
                shop = existing_shop
            else:
                # Create shop
                shop = Shop(
                    name="Bishops Tempe",
                    slug="bishops-tempe",
                    timezone="America/Phoenix",
                    address="123 Mill Ave, Tempe, AZ 85281",
                    category="Barbershop",
                    phone_number="+14801234567"
                )
                session.add(shop)
                await session.flush()
                print(f"✅ Created shop: {shop.name} (ID: {shop.id})")
                
                # Create shop owner membership
                owner_member = ShopMember(
                    shop_id=shop.id,
                    user_id="test_owner_1",
                    role=ShopMemberRole.OWNER.value
                )
                session.add(owner_member)
                print(f"✅ Created shop owner membership (user_id: test_owner_1)")
                
                # Create shop phone number
                shop_phone = ShopPhoneNumber(
                    shop_id=shop.id,
                    phone_number="+14801234567",
                    label="Booking Line",
                    is_primary=True
                )
                session.add(shop_phone)
                print(f"✅ Created phone number: +14801234567")
                
                # Create services
                service_mens_cut = Service(
                    shop_id=shop.id,
                    name="Men's Haircut",
                    duration_minutes=30,
                    price_cents=3500  # $35.00
                )
                session.add(service_mens_cut)
                
                service_beard = Service(
                    shop_id=shop.id,
                    name="Beard Trim",
                    duration_minutes=15,
                    price_cents=1500  # $15.00
                )
                session.add(service_beard)
                print(f"✅ Created services: Men's Haircut ($35), Beard Trim ($15)")
                
                # Create stylist
                stylist = Stylist(
                    shop_id=shop.id,
                    name="Alex",
                    work_start=time(9, 0),   # 9:00 AM
                    work_end=time(18, 0),    # 6:00 PM
                    active=True
                )
                session.add(stylist)
                print(f"✅ Created stylist: Alex (9 AM - 6 PM)")
                
                # Commit all changes
                await session.commit()
            
            print("\n🎉 Seed complete!")
            print("\n📊 Database contains:")
            print(f"   - Shop: {shop.name} (slug: {shop.slug})")
            print(f"   - Shop ID: {shop.id}")
            print(f"   - Phone: +14801234567")
            print(f"   - Services: 2 (Men's Haircut, Beard Trim)")
            print(f"   - Stylists: 1 (Alex)")
            print("\n🔍 Verify in pgAdmin:")
            print("   1. Connect to localhost:5432")
            print("   2. Open convo_test database")
            print("   3. Browse tables: shops, shop_members, services, stylists")
            print("\n🧪 Test with curl:")
            print(f"   curl http://localhost:8000/shops/{shop.slug}")
            
    except Exception as e:
        print(f"❌ Error seeding database: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed_data())
