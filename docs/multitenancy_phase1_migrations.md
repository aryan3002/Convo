# Phase 1 Multi-Tenancy Migrations

**Phase:** 1 - Database & Foundation  
**Date:** 2026-01-21  
**Status:** Ready to Run

---

## Overview

This document describes the Phase 1 database migrations that prepare the schema for multi-tenancy without changing runtime behavior. All existing data is backfilled to `shop_id=1`.

---

## Migration File

**Location:** `Backend/migrations/002_phase1_multitenancy.sql`

### What It Does

| Part | Description |
|------|-------------|
| **A** | Extends `shops` table with: `slug`, `timezone`, `address`, `category`, `phone_number`, `updated_at` |
| **B** | Creates `shop_phone_numbers` table for voice/SMS routing |
| **C** | Adds `shop_id` to `call_summaries` table |
| **D** | Creates `customer_shop_profiles` table (per-shop customer data) |
| **E** | Adds/verifies indexes on tenant-scoped tables |
| **F** | Adds `shop_id` to `customer_stylist_preferences` and `customer_service_preferences` |
| **G** | Creates `schema_migrations` tracking table |

---

## How to Run Migrations Locally

### Prerequisites

1. PostgreSQL database running (local or remote)
2. Database URL configured in `Backend/.env`:
   ```
   DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/convo
   ```

### Option 1: Using psql (Recommended)

```bash
# From repo root
cd Backend

# Run the Phase 1 migration
psql "$DATABASE_URL" -f migrations/002_phase1_multitenancy.sql

# Verify migration was recorded
psql "$DATABASE_URL" -c "SELECT * FROM schema_migrations;"
```

### Option 2: Using Python Script

```bash
# From repo root
cd Backend

# Activate virtualenv
source venv/bin/activate  # or .venv/bin/activate

# Run migration via Python
python -c "
import asyncio
from sqlalchemy import text
from app.core.db import async_engine

async def run_migration():
    with open('migrations/002_phase1_multitenancy.sql', 'r') as f:
        sql = f.read()
    
    async with async_engine.begin() as conn:
        # Execute each statement
        for statement in sql.split(';'):
            stmt = statement.strip()
            if stmt and not stmt.startswith('--'):
                try:
                    await conn.execute(text(stmt))
                except Exception as e:
                    print(f'Statement failed: {stmt[:50]}...')
                    print(f'Error: {e}')
    print('Migration complete!')

asyncio.run(run_migration())
"
```

### Option 3: Using Docker Compose (if applicable)

```bash
# If using docker-compose with postgres service
docker-compose exec postgres psql -U postgres -d convo -f /migrations/002_phase1_multitenancy.sql
```

---

## Verification Steps

After running the migration, verify the changes:

### 1. Check Shops Table

```sql
SELECT id, name, slug, timezone, address, category, phone_number 
FROM shops 
WHERE id = 1;
```

Expected output:
```
 id |     name      |     slug      |    timezone     |    address     |  category  | phone_number
----+---------------+---------------+-----------------+----------------+------------+--------------
  1 | Bishops Tempe | bishops-tempe | America/Phoenix | Tempe, Arizona | barbershop | (null or set)
```

### 2. Check New Tables Exist

```sql
SELECT table_name FROM information_schema.tables 
WHERE table_schema = 'public' 
AND table_name IN ('shop_phone_numbers', 'customer_shop_profiles', 'schema_migrations');
```

### 3. Check call_summaries Has shop_id

```sql
SELECT column_name, is_nullable, data_type 
FROM information_schema.columns 
WHERE table_name = 'call_summaries' AND column_name = 'shop_id';
```

### 4. Check Backfill Worked

```sql
-- All call_summaries should have shop_id=1
SELECT COUNT(*) AS total, COUNT(*) FILTER (WHERE shop_id = 1) AS with_shop_1 
FROM call_summaries;

-- Customer profiles should be backfilled
SELECT COUNT(*) FROM customer_shop_profiles WHERE shop_id = 1;
```

### 5. Check Indexes

```sql
SELECT indexname, tablename 
FROM pg_indexes 
WHERE tablename IN ('shops', 'call_summaries', 'customer_shop_profiles')
ORDER BY tablename, indexname;
```

---

## Rollback (If Needed)

⚠️ **Warning:** Only use in development. Production rollback requires careful planning.

```sql
-- Rollback migration 002 (destructive!)
DROP TABLE IF EXISTS customer_shop_profiles CASCADE;
DROP TABLE IF EXISTS shop_phone_numbers CASCADE;
DROP TABLE IF EXISTS schema_migrations CASCADE;

ALTER TABLE call_summaries DROP COLUMN IF EXISTS shop_id;
ALTER TABLE customer_stylist_preferences DROP COLUMN IF EXISTS shop_id;
ALTER TABLE customer_service_preferences DROP COLUMN IF EXISTS shop_id;

ALTER TABLE shops DROP COLUMN IF EXISTS slug;
ALTER TABLE shops DROP COLUMN IF EXISTS timezone;
ALTER TABLE shops DROP COLUMN IF EXISTS address;
ALTER TABLE shops DROP COLUMN IF EXISTS category;
ALTER TABLE shops DROP COLUMN IF EXISTS phone_number;
ALTER TABLE shops DROP COLUMN IF EXISTS updated_at;
```

---

## Model Changes

The following SQLAlchemy models were updated to match the new schema:

### Updated Models

| Model | File | Changes |
|-------|------|---------|
| `Shop` | models.py | Added `slug`, `timezone`, `address`, `category`, `phone_number`, `updated_at` |
| `CallSummary` | models.py | Added `shop_id` |
| `CustomerStylistPreference` | models.py | Added `shop_id` |
| `CustomerServicePreference` | models.py | Added `shop_id` |

### New Models

| Model | File | Purpose |
|-------|------|---------|
| `ShopPhoneNumber` | models.py | Phone→shop mapping for voice routing |
| `CustomerShopProfile` | models.py | Per-shop customer preferences and stats |

---

## Code Changes for Compatibility

These code paths were updated to pass `shop_id` when creating records:

| File | Function | Change |
|------|----------|--------|
| `call_summary.py` | `generate_and_store_call_summary` | Added `shop_id` from session_data |
| `customer_memory.py` | `update_customer_stats` | Added `shop_id` from stylist when creating preference |
| `main.py` | `upsert_service_preference` | Added `shop_id` lookup from service |

All changes maintain **backward compatibility** - shop_id defaults to 1 if not provided.

---

## What's NOT Changed (Phase 2)

- ❌ Shop resolution from slug (still returns shop_id=1)
- ❌ Phone→shop routing for voice (placeholder only)
- ❌ Query scoping with shop_id filters
- ❌ Frontend routing with `/s/[slug]/`
- ❌ Removal of `get_default_shop()` helper

---

## Next Steps

After Phase 1 migration is complete:

1. **Run the app** and verify it starts without errors
2. **Test booking flow** to ensure shop_id=1 is used throughout
3. **Run tenant scoping check**:
   ```bash
   python3 scripts/check_tenant_scoping.py -v
   ```
4. **Proceed to Phase 2** for shop resolution and query scoping

---

*Last Updated: 2026-01-21 - Phase 1*
