-- ============================================================================
-- Migration 012: Cab Owners and Drivers
-- Purpose: Add cab_owners table for per-shop cab service config,
--          and cab_drivers table for driver assignment.
-- ============================================================================

-- ============================================================================
-- PART A: Create cab_owners table
-- Represents a shop that has enabled cab services
-- ============================================================================

CREATE TABLE IF NOT EXISTS cab_owners (
    id SERIAL PRIMARY KEY,
    shop_id INTEGER NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
    
    -- Business info
    business_name VARCHAR(255) NOT NULL,
    email VARCHAR(255),
    phone VARCHAR(32),
    whatsapp_phone VARCHAR(32),
    
    -- Status
    active BOOLEAN NOT NULL DEFAULT TRUE,
    
    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- One cab owner per shop
    CONSTRAINT uq_cab_owner_shop UNIQUE (shop_id)
);

CREATE INDEX IF NOT EXISTS idx_cab_owners_shop ON cab_owners(shop_id);

COMMENT ON TABLE cab_owners IS 
    'Shops that have enabled cab services. One record per shop.';

-- ============================================================================
-- PART B: Create cab_drivers table
-- ============================================================================

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'cab_driver_status') THEN
        CREATE TYPE cab_driver_status AS ENUM ('ACTIVE', 'INACTIVE');
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS cab_drivers (
    id SERIAL PRIMARY KEY,
    cab_owner_id INTEGER NOT NULL REFERENCES cab_owners(id) ON DELETE CASCADE,
    
    -- Driver info
    name VARCHAR(255) NOT NULL,
    phone VARCHAR(32) NOT NULL,
    whatsapp_phone VARCHAR(32),
    
    -- Status
    status cab_driver_status NOT NULL DEFAULT 'ACTIVE',
    
    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_cab_drivers_owner ON cab_drivers(cab_owner_id);
CREATE INDEX IF NOT EXISTS idx_cab_drivers_status ON cab_drivers(cab_owner_id, status);

COMMENT ON TABLE cab_drivers IS 
    'Drivers associated with a cab owner. Owner can assign drivers to bookings.';

-- ============================================================================
-- PART C: Add cab_owner_id to cab_pricing_rules (optional migration)
-- Link pricing rules to cab_owners instead of directly to shops
-- ============================================================================

-- Add cab_owner_id column if not exists
ALTER TABLE cab_pricing_rules ADD COLUMN IF NOT EXISTS cab_owner_id INTEGER REFERENCES cab_owners(id) ON DELETE CASCADE;

-- Create index for cab_owner lookups
CREATE INDEX IF NOT EXISTS idx_cab_pricing_rules_owner ON cab_pricing_rules(cab_owner_id);

-- ============================================================================
-- PART D: Add driver assignment to cab_bookings
-- ============================================================================

ALTER TABLE cab_bookings ADD COLUMN IF NOT EXISTS assigned_driver_id INTEGER REFERENCES cab_drivers(id) ON DELETE SET NULL;
ALTER TABLE cab_bookings ADD COLUMN IF NOT EXISTS assigned_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_cab_bookings_driver ON cab_bookings(assigned_driver_id) WHERE assigned_driver_id IS NOT NULL;

COMMENT ON COLUMN cab_bookings.assigned_driver_id IS 'Driver assigned to this ride';
COMMENT ON COLUMN cab_bookings.assigned_at IS 'Timestamp when driver was assigned';

-- ============================================================================
-- PART E: Update triggers
-- ============================================================================

-- Trigger for cab_owners
CREATE OR REPLACE FUNCTION update_cab_owners_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_cab_owners_updated_at ON cab_owners;
CREATE TRIGGER trigger_cab_owners_updated_at
    BEFORE UPDATE ON cab_owners
    FOR EACH ROW
    EXECUTE FUNCTION update_cab_owners_updated_at();

-- Trigger for cab_drivers
DROP TRIGGER IF EXISTS trigger_cab_drivers_updated_at ON cab_drivers;
CREATE TRIGGER trigger_cab_drivers_updated_at
    BEFORE UPDATE ON cab_drivers
    FOR EACH ROW
    EXECUTE FUNCTION update_cab_owners_updated_at();
