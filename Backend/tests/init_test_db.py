"""
Initialize test database schema using SQLAlchemy models.

This script creates all tables in the convo_test database
using the SQLAlchemy Base.metadata.

Usage:
    export DATABASE_URL="postgresql+asyncpg://localhost:5432/convo_test"
    python tests/init_test_db.py
"""
import asyncio
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.ext.asyncio import create_async_engine
from app.models import Base

# Get test database URL from environment
TEST_DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://localhost:5432/convo_test"
)

# Safety check
if "neon" in TEST_DATABASE_URL.lower() or "neondb" in TEST_DATABASE_URL.lower():
    print("❌ ERROR: Cannot initialize production Neon database!")
    print(f"   DATABASE_URL: {TEST_DATABASE_URL}")
    print("   Use: export DATABASE_URL='postgresql+asyncpg://localhost:5432/convo_test'")
    sys.exit(1)


async def init_db():
    """Create all tables in test database."""
    print(f"🔧 Initializing test database: {TEST_DATABASE_URL}")
    
    # Create async engine
    engine = create_async_engine(TEST_DATABASE_URL, echo=True)
    
    try:
        # Create all tables
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        
        print("✅ Test database initialized successfully!")
        print("\nNext steps:")
        print("1. Apply Phase 1 migration:")
        print("   psql -d convo_test -f migrations/002_phase1_multitenancy.sql")
        print("2. Apply Phase 6 migration:")
        print("   psql -d convo_test -f migrations/004_phase6_shop_members.sql")
        print("3. Run tests:")
        print("   pytest tests/test_phase6_onboarding.py -v")
        
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(init_db())
