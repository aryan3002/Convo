-- ============================================================================
-- Migration 002: Phase 1 Multi-Tenancy Foundation
-- Purpose: Extend shops table, add phone routing, add shop_id to call_summaries,
--          create customer_shop_profiles, add/verify indexes
-- 
-- PHASE 1 GOAL: Make database schema ready for multi-tenancy without changing
--               runtime behavior. All existing data backfilled to shop_id=1.
--
-- IMPORTANT: This migration is idempotent - safe to run multiple times.
-- ============================================================================

-- ============================================================================
-- PART A: Extend shops table with multi-tenant fields
-- ============================================================================

-- Add slug column (unique, URL-safe identifier)
ALTER TABLE shops ADD COLUMN IF NOT EXISTS slug VARCHAR(100);

-- Add timezone column (IANA timezone string)
ALTER TABLE shops ADD COLUMN IF NOT EXISTS timezone VARCHAR(50);

-- Add address column
ALTER TABLE shops ADD COLUMN IF NOT EXISTS address TEXT;

-- Add category column (e.g., 'barbershop', 'salon', 'spa')
ALTER TABLE shops ADD COLUMN IF NOT EXISTS category VARCHAR(50);

-- Add phone_number column (primary shop phone, for voice routing)
ALTER TABLE shops ADD COLUMN IF NOT EXISTS phone_number VARCHAR(20);

-- Add updated_at column
ALTER TABLE shops ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();

-- Backfill existing shop(s) with sensible defaults
UPDATE shops 
SET 
    slug = COALESCE(slug, LOWER(REGEXP_REPLACE(name, '[^a-zA-Z0-9]+', '-', 'g'))),
    timezone = COALESCE(timezone, 'America/Phoenix'),
    address = COALESCE(address, 'Tempe, Arizona'),
    category = COALESCE(category, 'barbershop'),
    updated_at = COALESCE(updated_at, NOW())
WHERE slug IS NULL OR timezone IS NULL;

-- Ensure shop id=1 exists with proper defaults (the original shop)
INSERT INTO shops (id, name, slug, timezone, address, category, created_at, updated_at)
VALUES (1, 'Bishops Tempe', 'bishops-tempe', 'America/Phoenix', 'Tempe, Arizona', 'barbershop', NOW(), NOW())
ON CONFLICT (id) DO UPDATE SET
    slug = COALESCE(shops.slug, EXCLUDED.slug),
    timezone = COALESCE(shops.timezone, EXCLUDED.timezone),
    address = COALESCE(shops.address, EXCLUDED.address),
    category = COALESCE(shops.category, EXCLUDED.category),
    updated_at = NOW();

-- Now set NOT NULL constraints (after backfill)
ALTER TABLE shops ALTER COLUMN slug SET NOT NULL;
ALTER TABLE shops ALTER COLUMN timezone SET NOT NULL;

-- Add unique constraint on slug (idempotent)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'uq_shops_slug'
    ) THEN
        ALTER TABLE shops ADD CONSTRAINT uq_shops_slug UNIQUE (slug);
    END IF;
END $$;

-- Add unique constraint on phone_number (optional, one number per shop for now)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'uq_shops_phone_number'
    ) THEN
        ALTER TABLE shops ADD CONSTRAINT uq_shops_phone_number UNIQUE (phone_number);
    END IF;
END $$;

-- Index on slug for fast lookups
CREATE INDEX IF NOT EXISTS idx_shops_slug ON shops(slug);

-- ============================================================================
-- PART B: Create shop_phone_numbers table (for multi-number voice routing)
-- ============================================================================

CREATE TABLE IF NOT EXISTS shop_phone_numbers (
    id SERIAL PRIMARY KEY,
    shop_id INTEGER NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
    phone_number VARCHAR(20) NOT NULL,
    label VARCHAR(50),  -- e.g., 'main', 'booking', 'support'
    is_primary BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    CONSTRAINT uq_shop_phone_number UNIQUE (phone_number)
);

CREATE INDEX IF NOT EXISTS idx_shop_phone_numbers_shop ON shop_phone_numbers(shop_id);
CREATE INDEX IF NOT EXISTS idx_shop_phone_numbers_phone ON shop_phone_numbers(phone_number);

-- Comment for documentation
COMMENT ON TABLE shop_phone_numbers IS 
    'Maps Twilio phone numbers to shops for voice/SMS routing. Used in Phase 2 for shop resolution from inbound calls.';

-- ============================================================================
-- PART C: Add shop_id to call_summaries table
-- ============================================================================

-- Step 1: Add column as nullable first
ALTER TABLE call_summaries ADD COLUMN IF NOT EXISTS shop_id INTEGER REFERENCES shops(id) ON DELETE CASCADE;

-- Step 2: Backfill existing rows to shop_id=1
UPDATE call_summaries SET shop_id = 1 WHERE shop_id IS NULL;

-- Step 3: Set NOT NULL constraint
ALTER TABLE call_summaries ALTER COLUMN shop_id SET NOT NULL;

-- Step 4: Add index for tenant-scoped queries
CREATE INDEX IF NOT EXISTS idx_call_summaries_shop_created 
    ON call_summaries(shop_id, created_at DESC);

-- ============================================================================
-- PART D: Create customer_shop_profiles table (per-shop customer data)
-- ============================================================================

CREATE TABLE IF NOT EXISTS customer_shop_profiles (
    id SERIAL PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    shop_id INTEGER NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
    
    -- Shop-specific preferences (moved from customers table in future)
    preferred_stylist_id INTEGER REFERENCES stylists(id) ON DELETE SET NULL,
    
    -- Shop-specific stats (moved from customer_booking_stats in future)
    total_bookings INTEGER NOT NULL DEFAULT 0,
    total_spend_cents INTEGER NOT NULL DEFAULT 0,
    last_booking_at TIMESTAMPTZ,
    no_show_count INTEGER NOT NULL DEFAULT 0,
    
    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    CONSTRAINT uq_customer_shop_profile UNIQUE (customer_id, shop_id)
);

CREATE INDEX IF NOT EXISTS idx_customer_shop_profiles_shop ON customer_shop_profiles(shop_id);
CREATE INDEX IF NOT EXISTS idx_customer_shop_profiles_customer ON customer_shop_profiles(customer_id);
CREATE INDEX IF NOT EXISTS idx_customer_shop_profiles_stylist ON customer_shop_profiles(preferred_stylist_id) 
    WHERE preferred_stylist_id IS NOT NULL;

-- Backfill existing customer data to shop_id=1 profiles
INSERT INTO customer_shop_profiles (
    customer_id, 
    shop_id, 
    preferred_stylist_id, 
    total_bookings, 
    total_spend_cents, 
    last_booking_at, 
    no_show_count,
    created_at,
    updated_at
)
SELECT 
    c.id AS customer_id,
    1 AS shop_id,
    c.preferred_stylist_id,
    COALESCE(s.total_bookings, 0),
    COALESCE(s.total_spend_cents, 0),
    s.last_booking_at,
    c.no_show_count,
    c.created_at,
    NOW()
FROM customers c
LEFT JOIN customer_booking_stats s ON s.customer_id = c.id
ON CONFLICT (customer_id, shop_id) DO UPDATE SET
    total_bookings = EXCLUDED.total_bookings,
    total_spend_cents = EXCLUDED.total_spend_cents,
    last_booking_at = EXCLUDED.last_booking_at,
    no_show_count = EXCLUDED.no_show_count,
    updated_at = NOW();

COMMENT ON TABLE customer_shop_profiles IS 
    'Per-shop customer preferences and stats. Customers are global; this table holds shop-specific data. See ADR-0001.';

-- ============================================================================
-- PART E: Verify/add indexes on tenant-scoped tables
-- ============================================================================

-- services(shop_id, id) - composite for tenant queries
CREATE INDEX IF NOT EXISTS idx_services_shop_id ON services(shop_id, id);

-- stylists(shop_id, id) - composite for tenant queries
CREATE INDEX IF NOT EXISTS idx_stylists_shop_id ON stylists(shop_id, id);

-- bookings(shop_id, start_at_utc) - for availability queries
CREATE INDEX IF NOT EXISTS idx_bookings_shop_start ON bookings(shop_id, start_at_utc);

-- bookings(shop_id, created_at) - for recent bookings
CREATE INDEX IF NOT EXISTS idx_bookings_shop_created ON bookings(shop_id, created_at DESC);

-- promos(shop_id, id) - for promo lookups
CREATE INDEX IF NOT EXISTS idx_promos_shop_id ON promos(shop_id, id);

-- promos(shop_id, active) - for active promo queries
CREATE INDEX IF NOT EXISTS idx_promos_shop_active ON promos(shop_id, active) WHERE active = TRUE;

-- promo_impressions already has shop_id index (from model definition)
-- embedded_chunks already has shop_id indexes (from migration 001)

-- ============================================================================
-- PART F: Add shop_id to customer_stylist_preferences and customer_service_preferences
--         (These link to shop-scoped entities, so need shop_id for Phase 2 queries)
-- ============================================================================

-- Note: These tables reference stylists/services which are already shop-scoped.
-- The shop_id is denormalized for query efficiency in Phase 2.
-- For now, we just add the column and backfill from the related entity.

-- customer_stylist_preferences
ALTER TABLE customer_stylist_preferences 
    ADD COLUMN IF NOT EXISTS shop_id INTEGER REFERENCES shops(id) ON DELETE CASCADE;

UPDATE customer_stylist_preferences csp
SET shop_id = s.shop_id
FROM stylists s
WHERE csp.stylist_id = s.id AND csp.shop_id IS NULL;

-- Set NOT NULL after backfill (if any rows exist)
DO $$
BEGIN
    -- Only set NOT NULL if all rows have been backfilled
    IF NOT EXISTS (SELECT 1 FROM customer_stylist_preferences WHERE shop_id IS NULL) THEN
        ALTER TABLE customer_stylist_preferences ALTER COLUMN shop_id SET NOT NULL;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_customer_stylist_prefs_shop 
    ON customer_stylist_preferences(shop_id);

-- customer_service_preferences
ALTER TABLE customer_service_preferences 
    ADD COLUMN IF NOT EXISTS shop_id INTEGER REFERENCES shops(id) ON DELETE CASCADE;

UPDATE customer_service_preferences csp
SET shop_id = s.shop_id
FROM services s
WHERE csp.service_id = s.id AND csp.shop_id IS NULL;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM customer_service_preferences WHERE shop_id IS NULL) THEN
        ALTER TABLE customer_service_preferences ALTER COLUMN shop_id SET NOT NULL;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_customer_service_prefs_shop 
    ON customer_service_preferences(shop_id);

-- ============================================================================
-- PART G: Migration tracking (optional but recommended)
-- ============================================================================

CREATE TABLE IF NOT EXISTS schema_migrations (
    version VARCHAR(50) PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    description TEXT
);

INSERT INTO schema_migrations (version, description)
VALUES ('002_phase1_multitenancy', 'Phase 1 multi-tenancy foundation: shops extensions, phone routing, call_summaries shop_id, customer profiles')
ON CONFLICT (version) DO NOTHING;

-- ============================================================================
-- VERIFICATION QUERIES (run manually to verify)
-- ============================================================================

-- Uncomment to verify:
-- SELECT id, name, slug, timezone, address, category FROM shops WHERE id = 1;
-- SELECT COUNT(*) FROM call_summaries WHERE shop_id = 1;
-- SELECT COUNT(*) FROM customer_shop_profiles WHERE shop_id = 1;
-- SELECT COUNT(*) FROM customer_stylist_preferences WHERE shop_id IS NOT NULL;
-- SELECT COUNT(*) FROM customer_service_preferences WHERE shop_id IS NOT NULL;

-- ============================================================================
-- END OF MIGRATION 002
-- ============================================================================
