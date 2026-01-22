"""
Pytest configuration and fixtures for async database testing.

These fixtures ensure tests run against a local test database (convo_test)
with proper transaction isolation and rollback.
"""
import os
import asyncio
import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from httpx import AsyncClient, ASGITransport

# Ensure we're using a test database from environment
TEST_DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://localhost:5432/convo_test"
)

# Verify we're NOT using production Neon database
if "neon" in TEST_DATABASE_URL.lower() or "neondb" in TEST_DATABASE_URL.lower():
    raise RuntimeError(
        f"DANGER: Tests are configured to use production database!\n"
        f"DATABASE_URL: {TEST_DATABASE_URL}\n"
        f"Tests must ONLY run against local convo_test database.\n"
        f"Set DATABASE_URL='postgresql+asyncpg://localhost:5432/convo_test'"
    )


@pytest.fixture(scope="function")
def event_loop():
    """
    Create a new event loop for each test function.
    
    This ensures proper async context isolation and prevents
    "Future attached to a different loop" errors.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()


@pytest.fixture(scope="function")
async def async_engine():
    """
    Create async SQLAlchemy engine for test database.
    
    Engine is created per test to ensure clean state.
    """
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10
    )
    yield engine
    await engine.dispose()


@pytest.fixture(scope="function")
async def async_session(async_engine):
    """
    Create async database session with transaction rollback.
    
    Each test gets a fresh transaction that is rolled back after the test,
    ensuring test isolation and preventing database pollution.
    """
    # Create session factory
    async_session_maker = async_sessionmaker(
        async_engine,
        class_=AsyncSession,
        expire_on_commit=False
    )
    
    # Create connection and begin transaction
    async with async_engine.connect() as connection:
        async with connection.begin() as transaction:
            # Create session bound to this transaction
            async with async_session_maker(bind=connection) as session:
                yield session
                # Rollback transaction after test
                await transaction.rollback()


@pytest.fixture(scope="function")
async def client(async_session):
    """
    Create FastAPI AsyncClient with database session override.
    
    This client uses the test database session and ensures proper
    lifespan handling for FastAPI app initialization.
    """
    # Import here to avoid circular dependencies
    from app.main import app
    from app.core.db import get_session
    
    # Override database dependency to use test session
    async def override_get_session():
        yield async_session
    
    app.dependency_overrides[get_session] = override_get_session
    
    # Create client with proper ASGI transport and lifespan handling
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as ac:
        yield ac
    
    # Clean up overrides
    app.dependency_overrides.clear()
