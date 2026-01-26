-- Migration: Add COMPLETED status to cab_booking_status enum
-- Date: 2026-01-26
-- Description: Add COMPLETED status for finished cab rides to enable revenue tracking

-- Add COMPLETED to the cab_booking_status enum type
ALTER TYPE cab_booking_status ADD VALUE IF NOT EXISTS 'COMPLETED';

-- Add index on status for faster filtering (if not already exists)
CREATE INDEX IF NOT EXISTS idx_cab_bookings_status ON cab_bookings(status);

-- Add index on created_at for date range queries in analytics
CREATE INDEX IF NOT EXISTS idx_cab_bookings_created_at ON cab_bookings(created_at);

-- Add composite index for common analytics queries
CREATE INDEX IF NOT EXISTS idx_cab_bookings_shop_status_created 
ON cab_bookings(shop_id, status, created_at);
