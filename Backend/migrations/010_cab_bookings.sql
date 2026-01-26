-- ============================================================================
-- Migration 010: Cab Services Vertical
-- Purpose: Add tables for cab booking feature (airport + intercity pre-booking)
-- 
-- TABLES CREATED:
--   - cab_pricing_rules: Per-shop pricing configuration for cab services
--   - cab_bookings: Customer cab booking requests with pricing snapshots
--
-- IMPORTANT: This migration is idempotent - safe to run multiple times.
-- ============================================================================

-- ============================================================================
-- PART A: Create cab_pricing_rules table
-- ============================================================================

CREATE TABLE IF NOT EXISTS cab_pricing_rules (
    id SERIAL PRIMARY KEY,
    shop_id INTEGER NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
    
    -- Pricing parameters
    per_mile_rate DECIMAL(10, 2) NOT NULL DEFAULT 4.00,
    rounding_step DECIMAL(10, 2) NOT NULL DEFAULT 5.00,
    minimum_fare DECIMAL(10, 2) NOT NULL DEFAULT 0.00,
    currency VARCHAR(3) NOT NULL DEFAULT 'USD',
    
    -- Vehicle-specific pricing (JSON for flexibility)
    -- Format: {"SEDAN_4": 1.0, "SUV": 1.3, "VAN": 1.5} (multipliers)
    vehicle_multipliers JSONB DEFAULT '{"SEDAN_4": 1.0, "SUV": 1.3, "VAN": 1.5}'::jsonb,
    
    -- Status
    active BOOLEAN NOT NULL DEFAULT TRUE,
    
    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- One active pricing rule per shop
    CONSTRAINT uq_cab_pricing_rule_shop UNIQUE (shop_id)
);

CREATE INDEX IF NOT EXISTS idx_cab_pricing_rules_shop ON cab_pricing_rules(shop_id);

COMMENT ON TABLE cab_pricing_rules IS 
    'Cab service pricing configuration per shop. Each shop has one active pricing rule.';

-- ============================================================================
-- PART B: Create cab_bookings table
-- ============================================================================

-- Create enum for cab booking status
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'cab_booking_status') THEN
        CREATE TYPE cab_booking_status AS ENUM ('PENDING', 'CONFIRMED', 'REJECTED', 'CANCELLED');
    END IF;
END $$;

-- Create enum for vehicle type
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'cab_vehicle_type') THEN
        CREATE TYPE cab_vehicle_type AS ENUM ('SEDAN_4', 'SUV', 'VAN');
    END IF;
END $$;

-- Create enum for booking channel
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'cab_booking_channel') THEN
        CREATE TYPE cab_booking_channel AS ENUM ('web', 'whatsapp', 'phone', 'chatgpt');
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS cab_bookings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Tenant relationship (shop owns the cab service)
    shop_id INTEGER NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
    
    -- Booking channel
    channel cab_booking_channel NOT NULL DEFAULT 'web',
    
    -- Trip details
    pickup_text TEXT NOT NULL,
    drop_text TEXT NOT NULL,
    pickup_time TIMESTAMPTZ NOT NULL,
    vehicle_type cab_vehicle_type NOT NULL DEFAULT 'SEDAN_4',
    
    -- Optional trip info
    flight_number VARCHAR(20),
    passengers INTEGER,
    luggage INTEGER,
    
    -- Customer info (optional, for guest bookings)
    customer_name VARCHAR(255),
    customer_email VARCHAR(255),
    customer_phone VARCHAR(32),
    
    -- Route metrics (from Google Maps)
    distance_miles DECIMAL(10, 2),
    duration_minutes INTEGER,
    
    -- Pricing snapshot (captured at booking time for audit)
    per_mile_rate_snapshot DECIMAL(10, 2) NOT NULL,
    rounding_step_snapshot DECIMAL(10, 2) NOT NULL,
    minimum_fare_snapshot DECIMAL(10, 2) NOT NULL,
    vehicle_multiplier_snapshot DECIMAL(10, 2) NOT NULL DEFAULT 1.0,
    
    -- Calculated prices
    raw_price DECIMAL(10, 2),
    final_price DECIMAL(10, 2),
    
    -- Pricing lock (true after owner confirms)
    pricing_locked BOOLEAN NOT NULL DEFAULT FALSE,
    
    -- Status
    status cab_booking_status NOT NULL DEFAULT 'PENDING',
    
    -- Notes (owner can add)
    notes TEXT,
    
    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    confirmed_at TIMESTAMPTZ,
    rejected_at TIMESTAMPTZ
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_cab_bookings_shop_status ON cab_bookings(shop_id, status);
CREATE INDEX IF NOT EXISTS idx_cab_bookings_shop_pickup_time ON cab_bookings(shop_id, pickup_time);
CREATE INDEX IF NOT EXISTS idx_cab_bookings_status ON cab_bookings(status);
CREATE INDEX IF NOT EXISTS idx_cab_bookings_customer_email ON cab_bookings(customer_email) WHERE customer_email IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_cab_bookings_customer_phone ON cab_bookings(customer_phone) WHERE customer_phone IS NOT NULL;

COMMENT ON TABLE cab_bookings IS 
    'Cab booking requests with full pricing snapshot for audit trail. Status flow: PENDING -> CONFIRMED/REJECTED.';

COMMENT ON COLUMN cab_bookings.pricing_locked IS 
    'When true, price cannot be modified. Set to true on CONFIRM.';

COMMENT ON COLUMN cab_bookings.per_mile_rate_snapshot IS 
    'Per-mile rate captured at booking time (from cab_pricing_rules).';

-- ============================================================================
-- PART C: Seed default pricing rule for shop_id=1 (pilot)
-- ============================================================================

-- Insert default pricing rule for the pilot shop (shop_id=1)
-- This is idempotent - will not duplicate if already exists
INSERT INTO cab_pricing_rules (shop_id, per_mile_rate, rounding_step, minimum_fare, currency, active)
VALUES (1, 4.00, 5.00, 0.00, 'USD', TRUE)
ON CONFLICT (shop_id) DO NOTHING;

-- ============================================================================
-- PART D: Add trigger for updated_at
-- ============================================================================

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_cab_bookings_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Drop trigger if exists, then create
DROP TRIGGER IF EXISTS trigger_cab_bookings_updated_at ON cab_bookings;
CREATE TRIGGER trigger_cab_bookings_updated_at
    BEFORE UPDATE ON cab_bookings
    FOR EACH ROW
    EXECUTE FUNCTION update_cab_bookings_updated_at();

-- Same for pricing rules
DROP TRIGGER IF EXISTS trigger_cab_pricing_rules_updated_at ON cab_pricing_rules;
CREATE TRIGGER trigger_cab_pricing_rules_updated_at
    BEFORE UPDATE ON cab_pricing_rules
    FOR EACH ROW
    EXECUTE FUNCTION update_cab_bookings_updated_at();
