-- Migration: 007_phase3_location_indexes.sql
-- Purpose: Add indexes for location-based queries (RouterGPT optimization)
-- Phase: 3 - RouterGPT Integration
-- Created: 2024

-- ============================================================
-- INDEX 1: Composite index for location + category queries
-- ============================================================
-- This index optimizes the common query pattern:
--   SELECT * FROM shops 
--   WHERE latitude IS NOT NULL 
--     AND longitude IS NOT NULL
--     AND (category = 'barbershop' OR category IS NULL)
--   ORDER BY distance
--
-- The NULLS NOT DISTINCT ensures we can use the index even when
-- filtering for shops with coordinates.

CREATE INDEX IF NOT EXISTS idx_shops_location_category 
ON shops (latitude, longitude, category)
WHERE latitude IS NOT NULL AND longitude IS NOT NULL;

-- ============================================================
-- INDEX 2: Bounding box optimization index
-- ============================================================
-- For initial bounding box filtering before distance calculation.
-- Queries first filter by lat/lon ranges, then calculate exact distances.
-- This allows PostgreSQL to use index range scans.

CREATE INDEX IF NOT EXISTS idx_shops_lat 
ON shops (latitude)
WHERE latitude IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_shops_lon 
ON shops (longitude)
WHERE longitude IS NOT NULL;

-- ============================================================
-- INDEX 3: Slug lookup optimization
-- ============================================================
-- Used by /router/delegate and /s/{slug}/chat endpoints
-- Already likely exists but ensure it's there

CREATE INDEX IF NOT EXISTS idx_shops_slug 
ON shops (slug)
WHERE slug IS NOT NULL;

-- ============================================================
-- INDEX 4: Active shops filter
-- ============================================================
-- RouterGPT should only return active shops
-- If there's an 'active' or 'status' column, index it

-- Uncomment if shops table has an 'active' column:
-- CREATE INDEX IF NOT EXISTS idx_shops_active_location
-- ON shops (latitude, longitude)
-- WHERE active = true AND latitude IS NOT NULL AND longitude IS NOT NULL;

-- ============================================================
-- ANALYZE to update statistics
-- ============================================================
-- Run ANALYZE after creating indexes to help the query planner

ANALYZE shops;

-- ============================================================
-- COMMENT on indexes for documentation
-- ============================================================

COMMENT ON INDEX idx_shops_location_category IS 
'Composite index for location-based queries with optional category filter. Used by RouterGPT search.';

COMMENT ON INDEX idx_shops_lat IS 
'Latitude index for bounding box filtering in location search.';

COMMENT ON INDEX idx_shops_lon IS 
'Longitude index for bounding box filtering in location search.';

COMMENT ON INDEX idx_shops_slug IS 
'Slug lookup index for shop delegation and chat endpoints.';
