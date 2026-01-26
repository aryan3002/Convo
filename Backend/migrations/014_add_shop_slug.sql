-- ============================================================================
-- Migration 014: Add Slug Column to Shops
-- Purpose: Add unique slug identifier for URL routing
-- ============================================================================

-- Add slug column if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'shops' AND column_name = 'slug'
    ) THEN
        -- Add slug column as nullable first
        ALTER TABLE shops ADD COLUMN slug VARCHAR(100);
        
        -- Backfill slugs from existing shop names
        -- Convert name to lowercase, replace spaces with hyphens
        UPDATE shops 
        SET slug = LOWER(REGEXP_REPLACE(name, '[^a-zA-Z0-9]+', '-', 'g'))
        WHERE slug IS NULL;
        
        -- Remove leading/trailing hyphens
        UPDATE shops 
        SET slug = TRIM(BOTH '-' FROM slug)
        WHERE slug IS NOT NULL;
        
        -- Make slug NOT NULL now that it's populated
        ALTER TABLE shops ALTER COLUMN slug SET NOT NULL;
        
        -- Add unique constraint
        ALTER TABLE shops ADD CONSTRAINT shops_slug_unique UNIQUE (slug);
        
        -- Add index for faster slug lookups
        CREATE INDEX IF NOT EXISTS idx_shops_slug ON shops(slug);
        
        RAISE NOTICE 'Added slug column to shops table and backfilled existing records';
    ELSE
        RAISE NOTICE 'Slug column already exists on shops table';
    END IF;
END $$;

COMMENT ON COLUMN shops.slug IS 'URL-friendly unique identifier for shop routing (e.g., /s/{slug}/...)';

-- ============================================================================
-- Verification Query (run manually after migration)
-- ============================================================================

-- SELECT id, name, slug, category FROM shops ORDER BY id;
