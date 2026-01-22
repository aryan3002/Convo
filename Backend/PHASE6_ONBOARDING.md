# Phase 6: Onboarding & Scale

## 🚀 Quick Start RUNBOOK (For Absolute Beginners)

### Prerequisites
- ✅ Local PostgreSQL installed and running
- ✅ Python 3.12+ installed
- ✅ Backend dependencies installed (`pip install -r requirements.txt`)

### Step-by-Step Setup

#### 1. Create Test Database

```bash
# Create local test database (one-time setup)
createdb convo_test

# Verify it was created
psql -l | grep convo_test
# Should show: convo_test | your_username | UTF8 ...
```

#### 2. Initialize Database Schema

```bash
# Set environment variable (required for all commands)
export DATABASE_URL="postgresql+asyncpg://localhost:5432/convo_test"

# Initialize schema (creates all tables)
python3 Backend/scripts/init_test_db.py
```

**Expected output:**
```
🔧 Initializing test database...
   Database: postgresql+asyncpg://localhost:5432/convo_test
✅ Test database schema initialized successfully!

📋 Tables created:
   - shops (with slug column)
   - shop_phone_numbers
   - shop_members (Phase 6)
   - services, stylists, bookings
   ...
```

#### 3. Run Phase 6 Tests

**Option A: Using Makefile (Recommended)**
```bash
make test-phase6
```

**Option B: Using shell script**
```bash
chmod +x Backend/scripts/test_phase6.sh
./Backend/scripts/test_phase6.sh
```

**Option C: Manual commands**
```bash
export DATABASE_URL="postgresql+asyncpg://localhost:5432/convo_test"
cd Backend
pytest tests/test_phase6_onboarding.py -v
```

**Expected output:**
```
================================== test session starts ==================================
tests/test_phase6_onboarding.py::test_create_shop_minimal PASSED                  [  6%]
tests/test_phase6_onboarding.py::test_create_shop_with_phone PASSED               [ 13%]
...
================================== 15 passed in 1.25s ===================================
```

#### 4. Seed Test Data (For Manual Testing)

```bash
# Insert realistic sample data
export DATABASE_URL="postgresql+asyncpg://localhost:5432/convo_test"
python3 Backend/scripts/seed_convo_test.py
```

**Or using Makefile:**
```bash
make seed-test
```

**Expected output:**
```
🌱 Seeding test database...
✅ Created shop: Bishops Tempe (ID: 1)
✅ Created shop owner membership (user_id: test_owner_1)
✅ Created phone number: +14801234567
✅ Created services: Men's Haircut ($35), Beard Trim ($15)
✅ Created stylist: Alex (9 AM - 6 PM)

🎉 Seed complete!
```

#### 5. Verify Data

**In pgAdmin:**
1. Launch pgAdmin
2. Add New Server:
   - Name: `Local Postgres`
   - Host: `localhost`
   - Port: `5432`
   - Database: `convo_test`
   - Username: your postgres username
3. Browse: `Servers > Local Postgres > Databases > convo_test > Schemas > public > Tables`
4. Right-click on `shops` → View/Edit Data → All Rows
5. You should see "Bishops Tempe" shop

**Using psql:**
```bash
# Connect to database
psql convo_test

# View shops
SELECT * FROM shops;

# View shop members
SELECT * FROM shop_members;

# View services
SELECT * FROM services;

# Exit
\q
```

**Using curl (with backend running):**
```bash
# Start backend in another terminal
cd Backend
uvicorn app.main:app --reload --port 8000

# Test shop registry endpoint
curl http://localhost:8000/shops/bishops-tempe | python3 -m json.tool

# Expected response:
# {
#   "id": 1,
#   "name": "Bishops Tempe",
#   "slug": "bishops-tempe",
#   "phone_number": "+14801234567",
#   "timezone": "America/Phoenix",
#   "address": "123 Mill Ave, Tempe, AZ 85281",
#   "category": "Barbershop"
# }
```

### Quick Reference Commands

```bash
# Full workflow (run all at once)
createdb convo_test
export DATABASE_URL="postgresql+asyncpg://localhost:5432/convo_test"
make init-test-db    # Initialize schema
make test-phase6     # Run tests
make seed-test       # Seed sample data

# Individual commands
make help            # Show all available commands
make init-test-db    # Just initialize schema
make seed-test       # Just seed data
make test-phase6     # Just run tests

# Reset database (if needed)
dropdb convo_test && createdb convo_test
make init-test-db
```

### Troubleshooting

**Error: "createdb: database creation failed: ERROR: permission denied"**
```bash
# Solution: Use postgres superuser
sudo -u postgres createdb convo_test
sudo -u postgres psql -c "GRANT ALL ON DATABASE convo_test TO your_username;"
```

**Error: "DATABASE_URL environment variable not set"**
```bash
# Solution: Export the variable
export DATABASE_URL="postgresql+asyncpg://localhost:5432/convo_test"

# Or add to your shell profile (~/.zshrc or ~/.bashrc)
echo 'export DATABASE_URL="postgresql+asyncpg://localhost:5432/convo_test"' >> ~/.zshrc
source ~/.zshrc
```

**Error: "FATAL: Cannot seed production Neon database"**
- ✅ Good! The safety check is working
- Make sure DATABASE_URL points to local convo_test, not Neon

**Error: "relation shops.slug does not exist"**
```bash
# Solution: Reinitialize schema
make init-test-db
```

**Tests fail with "Future attached to a different loop"**
- ✅ This should NOT happen with the new conftest.py fixtures
- If it does, verify you're using pytest-asyncio 0.24.0+

### Safety Features

🛡️ **All scripts refuse to run against production Neon:**
- init_test_db.py checks for "neon" or "neondb" in DATABASE_URL
- seed_convo_test.py has the same check
- conftest.py test fixtures also refuse Neon URLs

❌ **You CANNOT accidentally modify production**

---

## 🚀 Quick Start RUNBOOK (For Production)

### For Testing (Local Development)

```bash
# 1. Create local test database
createdb convo_test

# 2. Initialize schema with SQLAlchemy models
cd Backend
export DATABASE_URL="postgresql+asyncpg://localhost:5432/convo_test"
python3 tests/init_test_db.py

# 3. Run tests
pytest tests/test_phase6_onboarding.py -v
```

**Expected output:** ✅ 15 passed in ~1.5s

### For Production (Neon Database)

```bash
# ⚠️ PRODUCTION ONLY - DO NOT RUN AGAINST TEST DB
# shop_members table must be created manually in Neon

# Apply Phase 6 migration to Neon
psql -d neondb -f Backend/migrations/004_phase6_shop_members.sql

# Verify shop_members table exists
psql -d neondb -c "\d shop_members"
```

**DO NOT** run tests against production Neon. Tests are designed to run against `convo_test` only.

---

## Overview

Phase 6 introduces **global shop onboarding** and **public shop registry** endpoints that enable self-service shop creation without developer intervention. These endpoints do NOT require shop context resolution, making them suitable for initial onboarding flows.

## Key Features

1. **POST /shops** - Create new shops without shop context
2. **GET /shops/{slug}** - Public shop registry for discovery/resolution
3. **shop_members table** - Multi-user access control and ownership tracking
4. **Automatic slug generation** - URL-safe slugs with uniqueness handling
5. **Phone number conflict detection** - 409 errors for duplicate phones
6. **Owner membership creation** - Automatic OWNER role assignment

## Architecture

### No Shop Context Required

These endpoints are **global** and do not require the shop context middleware:

```
POST /shops          # Creates the shop itself
GET /shops/{slug}    # Discovers shops by slug
```

All other endpoints (e.g., `/s/{slug}/...`) continue to require shop context resolution.

### Database Schema

#### shop_members Table (New in Phase 6)

```sql
CREATE TABLE shop_members (
    id SERIAL PRIMARY KEY,
    shop_id INTEGER NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
    user_id VARCHAR(255) NOT NULL,  -- Auth provider user ID
    role VARCHAR(20) NOT NULL DEFAULT 'EMPLOYEE',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    
    CONSTRAINT uq_shop_member UNIQUE (shop_id, user_id)
);

CREATE INDEX idx_shop_members_shop_id ON shop_members(shop_id);
CREATE INDEX idx_shop_members_user_id ON shop_members(user_id);
```

**Roles:**
- `OWNER` - Full access, shop creator
- `MANAGER` - Administrative access
- `EMPLOYEE` - Limited access

**Purpose:**
- Track which users have access to which shops
- Support multi-user businesses
- Enable future RBAC features

#### Related Tables

**shops:**
- `slug` (VARCHAR(100), UNIQUE, indexed) - URL-safe shop identifier
- `name` (VARCHAR(100), UNIQUE) - Display name
- `phone_number` (VARCHAR(20), UNIQUE, nullable) - Legacy/fallback phone

**shop_phone_numbers:**
- `phone_number` (VARCHAR(20), UNIQUE) - Primary phone number table
- `shop_id` (FK to shops) - Shop association
- `is_primary` (BOOLEAN) - Primary phone flag
- `label` (VARCHAR(50), nullable) - Phone label (e.g., "Primary")

## API Reference

### POST /shops

Creates a new shop (global onboarding endpoint).

**Request:**

```json
{
  "name": "Bella's Beauty Bar",
  "phone_number": "+15551234567",  // Optional, E.164 format
  "timezone": "America/Phoenix",    // Optional, default: America/Phoenix
  "address": "123 Main St",         // Optional
  "category": "Hair Salon",         // Optional
  "owner_user_id": "clerk_abc123"   // Required: auth provider user ID
}
```

**Response (201 Created):**

```json
{
  "id": 42,
  "name": "Bella's Beauty Bar",
  "slug": "bellas-beauty-bar",
  "phone_number": "+15551234567",
  "timezone": "America/Phoenix",
  "address": "123 Main St",
  "category": "Hair Salon"
}
```

**Process:**

1. Validate inputs (name, phone format, timezone)
2. Check name uniqueness (409 if exists)
3. Check phone number uniqueness in both `shop_phone_numbers` and `shops.phone_number` (409 if exists)
4. Generate slug from name (lowercase, ascii-safe, hyphenated)
5. Ensure slug uniqueness (append `-2`, `-3`, etc. if needed)
6. Create `shops` record
7. If `phone_number` provided:
   - Create `shop_phone_numbers` entry (is_primary=true, label="Primary")
   - Also store in `shops.phone_number` (legacy/fallback)
8. Create `shop_members` record (role=OWNER)
9. Commit transaction
10. Return shop info

**Error Codes:**

| Code | Reason |
|------|--------|
| 201 | Shop created successfully |
| 409 | Shop name already exists OR phone number already in use |
| 422 | Invalid input (empty name, invalid phone format, etc.) |
| 500 | Server error (e.g., slug generation failed after 1000 attempts) |

**Slug Generation Rules:**

```python
"Bella's Salon"    -> "bellas-salon"
"Café Beauté"      -> "cafe-beaute"
"Hair & Nails!!!"  -> "hair-nails"
"  Spaces  "       -> "spaces"
```

- Normalize unicode to ASCII (NFKD)
- Lowercase
- Replace non-alphanumeric with hyphens
- Remove leading/trailing hyphens
- Max 100 chars
- If duplicate, append `-2`, `-3`, etc.

**Phone Number Conflict Handling:**

The endpoint checks BOTH tables to prevent conflicts:

```sql
-- Check shop_phone_numbers table
SELECT * FROM shop_phone_numbers WHERE phone_number = '+15551234567';

-- Check shops.phone_number (legacy/fallback)
SELECT * FROM shops WHERE phone_number = '+15551234567';
```

If either query returns a result, return 409 Conflict.

**Uniqueness Constraints:**

- `shops.name` - UNIQUE (prevents duplicate business names)
- `shops.slug` - UNIQUE (ensures URL uniqueness)
- `shop_phone_numbers.phone_number` - UNIQUE (one phone per shop)
- `shops.phone_number` - UNIQUE (legacy column, still enforced)

### GET /shops/{slug}

Retrieves public shop information by slug (shop registry endpoint).

**Request:**

```
GET /shops/bellas-beauty-bar
```

**Response (200 OK):**

```json
{
  "id": 42,
  "name": "Bella's Beauty Bar",
  "slug": "bellas-beauty-bar",
  "phone_number": "+15551234567",
  "timezone": "America/Phoenix",
  "address": "123 Main St",
  "category": "Hair Salon"
}
```

**Error Codes:**

| Code | Reason |
|------|--------|
| 200 | Shop found |
| 404 | Shop with slug not found |

**Use Cases:**

- **Frontend routing:** Resolve `/s/{slug}` to shop details before rendering
- **Public shop profiles:** Display shop info without authentication
- **Shop existence verification:** Check if slug is taken during registration
- **SEO/metadata:** Generate page titles, descriptions, etc.

**Case Sensitivity:**

Slugs are lowercase and case-sensitive:

```
/shops/bella-salon  ✅ Found
/shops/BELLA-SALON  ❌ 404
```

## Implementation Details

### Module Structure

```
Backend/
  app/
    onboarding.py          # NEW: Global onboarding router
    models.py              # UPDATED: ShopMember, ShopMemberRole
    main.py                # UPDATED: Register onboarding_router
  migrations/
    004_phase6_shop_members.sql  # NEW: shop_members table
  tests/
    test_phase6_onboarding.py    # NEW: Comprehensive tests
```

### Model Changes

**models.py:**

```python
class ShopMemberRole(str, Enum):
    """Roles for shop members (Phase 6)."""
    OWNER = "OWNER"
    MANAGER = "MANAGER"
    EMPLOYEE = "EMPLOYEE"

class ShopMember(Base):
    """Shop membership for multi-user access control."""
    __tablename__ = "shop_members"
    
    id: Mapped[int]
    shop_id: Mapped[int]  # FK to shops
    user_id: Mapped[str]  # Auth provider user ID
    role: Mapped[str] = mapped_column(default="EMPLOYEE")
    created_at: Mapped[datetime]
    
    __table_args__ = (
        UniqueConstraint("shop_id", "user_id", name="uq_shop_member"),
    )
```

### Router Registration

**main.py:**

```python
from .onboarding import router as onboarding_router

app.include_router(onboarding_router)  # BEFORE scoped_router
```

**Order matters:**
1. `onboarding_router` - Global endpoints (no shop context)
2. `scoped_router` - Shop-scoped endpoints (`/s/{slug}/...`)

This ensures `/shops` routes are handled before shop context middleware.

## Testing

### Test Database Setup

**CRITICAL: Tests run against a LOCAL test database, NOT production Neon.**

**The database schema is created automatically by `init_test_db.py` using SQLAlchemy models.**

#### Quick Setup

```bash
# One-time setup
createdb convo_test
cd Backend
export DATABASE_URL="postgresql+asyncpg://localhost:5432/convo_test"
python3 tests/init_test_db.py

# Run tests anytime
pytest tests/test_phase6_onboarding.py -v
```

#### What init_test_db.py Does

- Reads `DATABASE_URL` from environment
- **Safety check:** Refuses to run against Neon (prevents production accidents)
- Creates all tables using SQLAlchemy `Base.metadata.create_all()`
- Includes:
  - `shops` table with `slug` column
  - `shop_members` table (Phase 6)
  - All other tables (services, stylists, bookings, etc.)

**No manual migrations needed for testing!** The init script creates everything.

#### Safety Check

```python
# conftest.py verifies you're NOT using production
if "neon" in TEST_DATABASE_URL.lower():
    raise RuntimeError("DANGER: Tests configured for production!")
```

This prevents accidental test runs against Neon.

### Test Coverage

**test_phase6_onboarding.py** includes:

- ✅ Create shop with minimal fields
- ✅ Create shop with phone number (shop_phone_numbers entry)
- ✅ Slug generation with special characters
- ✅ Slug uniqueness conflict resolution (-2, -3 suffixes)
- ✅ Duplicate name conflict (409)
- ✅ Duplicate phone conflict in shop_phone_numbers (409)
- ✅ Duplicate phone conflict in shops.phone_number (409)
- ✅ Invalid name validation (empty, whitespace)
- ✅ Invalid phone validation (bad format)
- ✅ Missing owner_user_id (422)
- ✅ Get shop by slug success
- ✅ Get shop by slug not found (404)
- ✅ Get shop by slug case sensitivity
- ✅ Full onboarding workflow integration
- ✅ Multiple shops same owner

### Test Fixtures (conftest.py)

The test suite uses proper async SQLAlchemy fixtures:

```python
@pytest.fixture(scope="function")
def event_loop():
    """Creates new event loop per test (prevents async loop errors)"""

@pytest.fixture(scope="function")
async def async_engine():
    """Creates async engine for test database"""

@pytest.fixture(scope="function")
async def async_session(async_engine):
    """Provides database session with automatic rollback"""

@pytest.fixture(scope="function")
async def client(async_session):
    """FastAPI AsyncClient with test database override"""
```

**Key Features:**
- Each test gets a fresh transaction
- Automatic rollback after each test (test isolation)
- No database pollution between tests
- Single event loop per test (no async errors)

### Troubleshooting Tests

**Error: "column shops.slug does not exist"**

```bash
# Solution: Apply Phase 1 migration
psql -d convo_test -f Backend/migrations/002_phase1_multitenancy.sql
```

**Error: "relation shop_members does not exist"**

```bash
# Solution: Apply Phase 6 migration
psql -d convo_test -f Backend/migrations/004_phase6_shop_members.sql
```

**Error: "DANGER: Tests are configured to use production database"**

```bash
# Solution: Set correct DATABASE_URL
export DATABASE_URL="postgresql+asyncpg://localhost:5432/convo_test"
```

**Error: "Future attached to a different loop"**

- Fixed by `conftest.py` event_loop fixture
- Ensure you're using fixtures from conftest, not creating your own

**Tests pass but data persists:**

- Check that `async_session` fixture is being used (not `async_engine` directly)
- Fixture should rollback transactions automatically

### Resetting Test Database

```bash
# Drop and recreate (nukes all data)
dropdb convo_test
createdb convo_test

# Reapply migrations
psql -d convo_test -f Backend/migrations/002_phase1_multitenancy.sql
psql -d convo_test -f Backend/migrations/004_phase6_shop_members.sql
```

### Running Tests

```bash
# Set test database
export DATABASE_URL="postgresql+asyncpg://localhost:5432/convo_test"

# Run Phase 6 tests only
pytest tests/test_phase6_onboarding.py -v

# Run all phases
pytest tests/test_phase4_routing.py tests/test_phase5_routergpt.py tests/test_phase6_onboarding.py -v

# Run with output
pytest tests/test_phase6_onboarding.py -v -s
```

**Expected Output:**

```
tests/test_phase6_onboarding.py::test_create_shop_minimal PASSED
tests/test_phase6_onboarding.py::test_create_shop_with_phone PASSED
tests/test_phase6_onboarding.py::test_slug_generation_special_chars PASSED
tests/test_phase6_onboarding.py::test_slug_uniqueness_conflict_resolution PASSED
tests/test_phase6_onboarding.py::test_duplicate_name_conflict PASSED
tests/test_phase6_onboarding.py::test_duplicate_phone_conflict_shop_phone_numbers PASSED
tests/test_phase6_onboarding.py::test_duplicate_phone_conflict_legacy_column PASSED
tests/test_phase6_onboarding.py::test_create_shop_invalid_name PASSED
tests/test_phase6_onboarding.py::test_create_shop_invalid_phone PASSED
tests/test_phase6_onboarding.py::test_create_shop_missing_owner_user_id PASSED
tests/test_phase6_onboarding.py::test_get_shop_by_slug_success PASSED
tests/test_phase6_onboarding.py::test_get_shop_by_slug_not_found PASSED
tests/test_phase6_onboarding.py::test_get_shop_by_slug_case_sensitive PASSED
tests/test_phase6_onboarding.py::test_full_onboarding_workflow PASSED
tests/test_phase6_onboarding.py::test_multiple_shops_same_owner PASSED

==================== 15 passed in X.XXs ====================
```

## Migration Guide

### Applying the Migration

```bash
# Connect to database
psql -U convo -d convo_db

# Apply migration
\i Backend/migrations/004_phase6_shop_members.sql

# Verify table
\d shop_members
```

### Rollback (if needed)

```sql
DROP TABLE IF EXISTS shop_members CASCADE;
```

## Usage Examples

### Frontend Onboarding Flow

```typescript
// 1. User signs up with auth provider (Clerk, Auth0, etc.)
const userId = await clerk.user.id;

// 2. User fills out shop creation form
const shopData = {
  name: "Bella's Beauty Bar",
  phone_number: "+15551234567",
  timezone: "America/Phoenix",
  address: "123 Main St",
  category: "Hair Salon",
  owner_user_id: userId
};

// 3. Create shop via API
const response = await fetch("/shops", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(shopData)
});

if (response.status === 201) {
  const shop = await response.json();
  // 4. Redirect to shop dashboard
  window.location.href = `/s/${shop.slug}/dashboard`;
} else if (response.status === 409) {
  const error = await response.json();
  // Handle conflict (name or phone already exists)
  showError(error.detail);
}
```

### Public Shop Discovery

```typescript
// Resolve shop by slug before rendering page
async function loadShopPage(slug: string) {
  const response = await fetch(`/shops/${slug}`);
  
  if (response.status === 200) {
    const shop = await response.json();
    // Render shop page with shop.name, shop.address, etc.
    renderShopPage(shop);
  } else {
    // Show 404 page
    renderNotFound();
  }
}
```

### Multi-Shop Owner

```typescript
// List shops owned by current user
async function listMyShops(userId: string) {
  // Query shop_members table
  const members = await db.query(
    "SELECT shop_id FROM shop_members WHERE user_id = $1",
    [userId]
  );
  
  // Fetch shop details
  const shops = await Promise.all(
    members.map(m => fetch(`/shops/${m.shop_id}`))
  );
  
  return shops;
}
```

## Security Considerations

### No Authorization on Creation

- **POST /shops** does NOT verify `owner_user_id` authenticity
- Assumes frontend passes authenticated user ID
- Future: Add JWT/session validation middleware

### Public Shop Registry

- **GET /shops/{slug}** is intentionally public
- Only returns safe fields (no API keys, internal IDs, etc.)
- Suitable for SEO, metadata, public profiles

### Phone Number Privacy

- Phone numbers are public in shop registry
- Future: Add privacy controls (show/hide phone)

## Future Enhancements

### Phase 7+

- [ ] RBAC enforcement (OWNER/MANAGER/EMPLOYEE permissions)
- [ ] Shop member invitation flow (invite by email)
- [ ] Shop transfer (change owner)
- [ ] Shop deletion (soft delete with cascade)
- [ ] Shop suspension (disable all endpoints)
- [ ] Audit logging (track who made what changes)
- [ ] Rate limiting on shop creation (prevent spam)
- [ ] Email verification before shop activation
- [ ] Payment integration (subscription/billing)

## Troubleshooting

### Database Issues

**Check which database you're connected to:**

```bash
# Check DATABASE_URL
echo $DATABASE_URL

# List all databases
psql -l | grep convo

# Should see:
# convo_test   - LOCAL test database ✅
# neondb       - PRODUCTION (DO NOT USE FOR TESTS) ❌
```

**Verify migrations applied:**

```bash
# Check if slug column exists in shops table
psql -d convo_test -c "\d shops" | grep slug

# Check if shop_members table exists
psql -d convo_test -c "\dt" | grep shop_members
```

**Reset test database if corrupted:**

```bash
# Nuclear option: drop and recreate
dropdb convo_test && createdb convo_test

# Reapply migrations
psql -d convo_test -f Backend/migrations/002_phase1_multitenancy.sql
psql -d convo_test -f Backend/migrations/004_phase6_shop_members.sql
```

### Common Issues

**409 Conflict on Shop Creation:**

```json
{"detail": "Shop with name 'Bella's Salon' already exists"}
```

**Solution:** Choose a different name or check if shop already exists.

---

**409 Conflict on Phone Number:**

```json
{"detail": "Phone number +15551234567 is already registered to another shop"}
```

**Solution:** Use a different phone number or claim existing shop.

---

**422 Invalid Phone Format:**

```json
{"detail": "Invalid phone number format"}
```

**Solution:** Use E.164 format (`+15551234567`).

---

**404 Shop Not Found:**

```json
{"detail": "Shop with slug 'does-not-exist' not found"}
```

**Solution:** Verify slug is correct (lowercase, hyphenated).

---

**Slug Uniqueness Loop:**

```json
{"detail": "Unable to generate unique slug after 1000 attempts"}
```

**Solution:** This should never happen in practice. Check for database corruption or test data issues.

## Constraints & Guarantees

### Hard Constraints (Enforced by Code + DB)

- ✅ Shop name must be unique across all shops
- ✅ Shop slug must be unique across all shops
- ✅ Phone number must be unique across all shops (both tables)
- ✅ Shop member (shop_id, user_id) must be unique
- ✅ One user can own multiple shops
- ✅ One shop can have multiple members (future)

### Soft Constraints (Enforced by Code Only)

- ✅ Owner user_id must be provided at creation
- ✅ Timezone defaults to America/Phoenix if not provided
- ✅ Phone number is optional but recommended
- ✅ Slug generation handles unicode, special chars, whitespace

### Multi-Tenancy Safety

- ✅ These endpoints do NOT require shop context
- ✅ No default shop_id=1 fallback behavior
- ✅ All other endpoints continue to require shop context
- ✅ Shop resolution order unchanged (shop_phone_numbers, then shops.phone_number)

## Testing Checklist

Before merging:

- [ ] All 36+ tests pass (Phase 4, 5, 6)
- [ ] No pytest-asyncio warnings
- [ ] Migration applied successfully
- [ ] Shop creation works via API
- [ ] Shop retrieval by slug works
- [ ] Duplicate name/phone conflicts return 409
- [ ] shop_members records created correctly
- [ ] shop_phone_numbers records created when phone provided
- [ ] Slug generation handles special cases
- [ ] Frontend integration tested (if applicable)

## References

- **Phase 4:** URL-based shop routing (`/s/{slug}/...`)
- **Phase 5:** RouterGPT discovery layer
- **Migration 002:** Multi-tenancy foundation (shops, shop_phone_numbers)
- **Migration 003:** Shop API keys (shop_api_keys)
- **Migration 004:** Shop members (shop_members) - THIS PHASE

---

**Phase 6 Complete.** Self-service shop onboarding is now live. 🚀
