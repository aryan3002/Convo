# Phase 6 Test Workflow - Implementation Complete ✅

## What Was Implemented

### 1. Test Database Initialization Script
**File:** `Backend/scripts/init_test_db.py`

- ✅ Reads `DATABASE_URL` from environment
- ✅ Safety check: Refuses to run against Neon
- ✅ Creates all tables using SQLAlchemy metadata
- ✅ Idempotent: Safe to run multiple times
- ✅ Clear output with next steps

### 2. Seed Script for Manual Testing
**File:** `Backend/scripts/seed_convo_test.py`

- ✅ Reads `DATABASE_URL` from environment
- ✅ Safety check: Refuses to run against Neon
- ✅ Creates realistic multi-tenant test data:
  - 1 shop: Bishops Tempe (slug: bishops-tempe)
  - 1 shop owner membership (user_id: test_owner_1, role: OWNER)
  - 1 phone number: +14801234567 (primary)
  - 2 services: Men's Haircut ($35), Beard Trim ($15)
  - 1 stylist: Alex (9 AM - 6 PM, active)
- ✅ Idempotent: Skips if shop already exists
- ✅ Helpful output with verification steps

### 3. Test Runner Shell Script
**File:** `Backend/scripts/test_phase6.sh`

- ✅ Sets DATABASE_URL automatically
- ✅ Verifies convo_test exists
- ✅ Initializes schema
- ✅ Runs Phase 6 tests

### 4. Makefile Targets
**File:** `Makefile`

- ✅ `make help` - Show all available commands
- ✅ `make init-test-db` - Initialize schema
- ✅ `make seed-test` - Seed sample data
- ✅ `make test-phase6` - Run Phase 6 tests

### 5. Updated Documentation
**File:** `Backend/PHASE6_ONBOARDING.md`

- ✅ Complete "For Absolute Beginners" runbook
- ✅ Step-by-step setup instructions
- ✅ Multiple ways to run tests (Makefile, script, manual)
- ✅ How to verify data (pgAdmin, psql, curl)
- ✅ Troubleshooting section
- ✅ Safety features documentation

## Test Results

### All 15 Tests Pass ✅

```
tests/test_phase6_onboarding.py::test_create_shop_minimal PASSED         [  6%]
tests/test_phase6_onboarding.py::test_create_shop_with_phone PASSED      [ 13%]
tests/test_phase6_onboarding.py::test_slug_generation_special_chars PASSED [ 20%]
tests/test_phase6_onboarding.py::test_slug_uniqueness_conflict_resolution PASSED [ 26%]
tests/test_phase6_onboarding.py::test_duplicate_name_conflict PASSED     [ 33%]
tests/test_phase6_onboarding.py::test_duplicate_phone_conflict_shop_phone_numbers PASSED [ 40%]
tests/test_phase6_onboarding.py::test_duplicate_phone_conflict_legacy_column PASSED [ 46%]
tests/test_phase6_onboarding.py::test_create_shop_invalid_name PASSED    [ 53%]
tests/test_phase6_onboarding.py::test_create_shop_invalid_phone PASSED   [ 60%]
tests/test_phase6_onboarding.py::test_create_shop_missing_owner_user_id PASSED [ 66%]
tests/test_phase6_onboarding.py::test_get_shop_by_slug_success PASSED    [ 73%]
tests/test_phase6_onboarding.py::test_get_shop_by_slug_not_found PASSED  [ 80%]
tests/test_phase6_onboarding.py::test_get_shop_by_slug_case_sensitive PASSED [ 86%]
tests/test_phase6_onboarding.py::test_full_onboarding_workflow PASSED    [ 93%]
tests/test_phase6_onboarding.py::test_multiple_shops_same_owner PASSED   [100%]

============================== 15 passed in 1.05s ==============================
```

### Seeded Data Verified ✅

**Shop:**
```
 id |     name      |     slug      | phone_number |    timezone     
----+---------------+---------------+--------------+-----------------
 33 | Bishops Tempe | bishops-tempe | +14801234567 | America/Phoenix
```

**Shop Member:**
```
 id | shop_id |   user_id    | role  
----+---------+--------------+-------
 31 |      33 | test_owner_1 | OWNER
```

**Services:**
```
 id | shop_id |     name      |    price_dollars    | duration_minutes 
----+---------+---------------+---------------------+------------------
  1 |      33 | Men's Haircut | 35.0000000000000000 |               30
  2 |      33 | Beard Trim    | 15.0000000000000000 |               15
```

## How to Use

### First-Time Setup (One-Time)

```bash
# 1. Create local test database
createdb convo_test

# 2. Initialize schema
export DATABASE_URL="postgresql+asyncpg://localhost:5432/convo_test"
python3 Backend/scripts/init_test_db.py
```

### Running Tests

**Option 1: Makefile (Recommended)**
```bash
make test-phase6
```

**Option 2: Shell Script**
```bash
./Backend/scripts/test_phase6.sh
```

**Option 3: Manual**
```bash
export DATABASE_URL="postgresql+asyncpg://localhost:5432/convo_test"
cd Backend
pytest tests/test_phase6_onboarding.py -v
```

### Seeding Data for Manual Testing

```bash
# Using Makefile
make seed-test

# Or directly
export DATABASE_URL="postgresql+asyncpg://localhost:5432/convo_test"
python3 Backend/scripts/seed_convo_test.py
```

### Verifying Data

**Using psql:**
```bash
psql convo_test -c "SELECT * FROM shops WHERE slug = 'bishops-tempe';"
psql convo_test -c "SELECT * FROM shop_members WHERE shop_id = 33;"
psql convo_test -c "SELECT * FROM services WHERE shop_id = 33;"
```

**Using curl (with backend running):**
```bash
# Start backend
cd Backend
uvicorn app.main:app --reload --port 8000

# In another terminal
curl http://localhost:8000/shops/bishops-tempe | python3 -m json.tool
```

## Safety Features

### All Scripts Have Neon Protection

Every script checks DATABASE_URL and refuses to run against Neon:

```python
if "neon" in DATABASE_URL.lower() or "neondb" in DATABASE_URL.lower():
    print("❌ FATAL: Cannot run against production Neon database!")
    sys.exit(1)
```

**Files with protection:**
- ✅ `Backend/scripts/init_test_db.py`
- ✅ `Backend/scripts/seed_convo_test.py`
- ✅ `Backend/tests/conftest.py`

### You CANNOT Accidentally Modify Production

Even if you set DATABASE_URL to Neon by mistake, the scripts will refuse to run.

## File Structure

```
Convo-main/
├── Makefile                                 # ✅ NEW: Test management commands
├── Backend/
│   ├── scripts/                            # ✅ NEW: Test utility scripts
│   │   ├── init_test_db.py                # ✅ NEW: Initialize schema
│   │   ├── seed_convo_test.py             # ✅ NEW: Seed sample data
│   │   └── test_phase6.sh                 # ✅ NEW: Test runner script
│   ├── tests/
│   │   ├── conftest.py                     # ✅ Updated: Async fixtures
│   │   ├── test_phase6_onboarding.py      # ✅ Updated: Uses fixtures
│   │   └── init_test_db.py                # ℹ️  Kept for compatibility
│   ├── migrations/
│   │   └── 004_phase6_shop_members.sql    # Phase 6 migration
│   └── PHASE6_ONBOARDING.md               # ✅ Updated: Complete runbook
```

## Quick Reference

### Common Commands

```bash
# Show all available commands
make help

# Initialize test database
make init-test-db

# Run Phase 6 tests
make test-phase6

# Seed sample data
make seed-test

# Reset everything (nuclear option)
dropdb convo_test && createdb convo_test
make init-test-db
make seed-test

# View data
psql convo_test
\dt                                    # List tables
SELECT * FROM shops;                   # View shops
SELECT * FROM shop_members;            # View members
\q                                     # Exit
```

### Environment Variable

**Required for all commands:**
```bash
export DATABASE_URL="postgresql+asyncpg://localhost:5432/convo_test"
```

**Add to shell profile for persistence:**
```bash
echo 'export DATABASE_URL="postgresql+asyncpg://localhost:5432/convo_test"' >> ~/.zshrc
source ~/.zshrc
```

## Next Steps

1. ✅ **Tests pass** - All 15 Phase 6 tests passing
2. ✅ **Data seeded** - Sample shop with owner, phone, services, stylist
3. ✅ **Documentation updated** - Complete runbook in PHASE6_ONBOARDING.md
4. ✅ **Safety verified** - Scripts refuse to run against Neon

### For Production Deployment

When ready to deploy Phase 6 to production Neon:

```bash
# Apply migration to Neon (one-time)
psql -d neondb -f Backend/migrations/004_phase6_shop_members.sql

# Verify
psql -d neondb -c "\d shop_members"
```

**DO NOT** run init_test_db.py or seed_convo_test.py against Neon - they will refuse.

---

**Phase 6 is production-ready with complete local testing workflow!** 🚀
