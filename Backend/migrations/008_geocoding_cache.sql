-- Migration: 008_geocoding_cache.sql
-- Purpose: Create geocoding cache table for RouterGPT performance
-- Phase: 3 - RouterGPT Integration (Optimization)
-- Created: 2024

-- ============================================================
-- TABLE: geocoding_cache
-- ============================================================
-- Caches geocoding API results to:
--   1. Reduce external API calls (Nominatim has rate limits)
--   2. Speed up repeated lookups for same addresses
--   3. Reduce latency for location-based features
--
-- TTL: 90 days (addresses rarely change)

CREATE TABLE IF NOT EXISTS geocoding_cache (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- The normalized address string (lowercase, trimmed)
    address_normalized VARCHAR(500) NOT NULL,
    
    -- Original address as provided
    address_original VARCHAR(500) NOT NULL,
    
    -- Geocoded coordinates
    latitude DECIMAL(10, 7) NOT NULL,
    longitude DECIMAL(10, 7) NOT NULL,
    
    -- Provider that returned this result
    provider VARCHAR(50) DEFAULT 'nominatim',
    
    -- Confidence/quality score (0-1)
    confidence DECIMAL(3, 2) DEFAULT 1.0,
    
    -- Full response from geocoding API (for debugging)
    raw_response JSONB,
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_used_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Cache control
    expires_at TIMESTAMPTZ DEFAULT (NOW() + INTERVAL '90 days')
);

-- ============================================================
-- INDEXES
-- ============================================================

-- Primary lookup index (by normalized address)
CREATE UNIQUE INDEX IF NOT EXISTS idx_geocoding_cache_address 
ON geocoding_cache (address_normalized);

-- Expiration cleanup index
CREATE INDEX IF NOT EXISTS idx_geocoding_cache_expires 
ON geocoding_cache (expires_at);

-- Provider analysis index (optional)
CREATE INDEX IF NOT EXISTS idx_geocoding_cache_provider 
ON geocoding_cache (provider);

-- ============================================================
-- COMMENTS
-- ============================================================

COMMENT ON TABLE geocoding_cache IS 
'Caches geocoding API results to reduce external calls and improve latency. TTL: 90 days.';

COMMENT ON COLUMN geocoding_cache.address_normalized IS 
'Normalized address (lowercase, trimmed, standardized) for consistent lookups';

COMMENT ON COLUMN geocoding_cache.expires_at IS 
'Cache entries expire after 90 days and can be cleaned up by a scheduled job';

COMMENT ON COLUMN geocoding_cache.last_used_at IS 
'Updated on each cache hit for LRU-style cache analysis';

-- ============================================================
-- CLEANUP FUNCTION (optional)
-- ============================================================
-- Can be called by a cron job to clean expired entries

CREATE OR REPLACE FUNCTION cleanup_expired_geocoding_cache()
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM geocoding_cache
    WHERE expires_at < NOW();
    
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION cleanup_expired_geocoding_cache IS 
'Removes expired geocoding cache entries. Returns count of deleted rows.';
