-- ============================================================================
-- Migration 011: Add owner action fields to cab_bookings
-- Purpose: Track who confirmed/rejected bookings and price overrides
-- ============================================================================

-- Add fields for tracking who performed actions
ALTER TABLE cab_bookings ADD COLUMN IF NOT EXISTS confirmed_by VARCHAR(255);
ALTER TABLE cab_bookings ADD COLUMN IF NOT EXISTS rejected_by VARCHAR(255);
ALTER TABLE cab_bookings ADD COLUMN IF NOT EXISTS rejection_reason TEXT;

-- Add fields for price override tracking
ALTER TABLE cab_bookings ADD COLUMN IF NOT EXISTS original_price DECIMAL(10, 2);
ALTER TABLE cab_bookings ADD COLUMN IF NOT EXISTS price_override DECIMAL(10, 2);

-- Comments
COMMENT ON COLUMN cab_bookings.confirmed_by IS 'User ID who confirmed the booking';
COMMENT ON COLUMN cab_bookings.rejected_by IS 'User ID who rejected the booking';
COMMENT ON COLUMN cab_bookings.rejection_reason IS 'Reason given for rejecting the booking';
COMMENT ON COLUMN cab_bookings.original_price IS 'Original calculated price before owner override';
COMMENT ON COLUMN cab_bookings.price_override IS 'Owner-set price override (when not null, replaces calculated price)';
