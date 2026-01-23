-- Phase 3: Add location coordinates for RouterGPT location-based search
-- This migration adds latitude/longitude columns to the shops table
-- to enable geographic search for nearby businesses.

-- Add latitude column (DOUBLE PRECISION for accurate coordinates)
ALTER TABLE shops ADD COLUMN IF NOT EXISTS latitude DOUBLE PRECISION;

-- Add longitude column
ALTER TABLE shops ADD COLUMN IF NOT EXISTS longitude DOUBLE PRECISION;

-- Create index on latitude for efficient range queries
CREATE INDEX IF NOT EXISTS idx_shops_latitude ON shops(latitude) WHERE latitude IS NOT NULL;

-- Create index on longitude for efficient range queries
CREATE INDEX IF NOT EXISTS idx_shops_longitude ON shops(longitude) WHERE longitude IS NOT NULL;

-- Create composite index for location-based queries
-- This index is used when filtering by both lat and lon (bounding box queries)
CREATE INDEX IF NOT EXISTS idx_shops_location ON shops(latitude, longitude) 
    WHERE latitude IS NOT NULL AND longitude IS NOT NULL;

-- Update existing shops with known coordinates (example: Bishops Tempe)
-- Tempe, AZ coordinates: approximately 33.4255° N, 111.9400° W
UPDATE shops 
SET latitude = 33.4255, longitude = -111.9400, updated_at = NOW()
WHERE slug = 'bishops-tempe' AND latitude IS NULL;

-- Add comment explaining the columns
COMMENT ON COLUMN shops.latitude IS 'Latitude coordinate for location-based search (WGS84)';
COMMENT ON COLUMN shops.longitude IS 'Longitude coordinate for location-based search (WGS84)';
