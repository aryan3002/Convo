-- Migration 013: Normalize Cab Services Data Model
-- Purpose: Ensure data consistency between shops, shop_members, and cab_owners

-- ============================================================================
-- PART A: Ensure shops.category is properly typed
-- ============================================================================

-- Add category if it doesn't exist (it should already exist from Phase 1)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'shops' AND column_name = 'category'
    ) THEN
        ALTER TABLE shops ADD COLUMN category VARCHAR(50) DEFAULT NULL;
    END IF;
END $$;

-- Add index for category lookups
CREATE INDEX IF NOT EXISTS idx_shops_category ON shops(category);

COMMENT ON COLUMN shops.category IS 'Business type: salon, cab, barbershop, etc.';

-- ============================================================================
-- PART B: Backfill shop_members for existing cab_owners
-- ============================================================================

-- This query finds cab_owners that have a shop but no corresponding shop_member
-- and creates the OWNER record. It uses the first user who created the cab_owner
-- (approximated by the shop creator from audit_logs or the cab_owner itself).

-- First, let's see if we have any orphaned cab_owners
-- (cab_owners without corresponding shop_members entries)

-- Create a backfill for any shop that has a cab_owner but no shop_member
-- We'll use a dummy user_id that should be replaced manually if needed
INSERT INTO shop_members (shop_id, user_id, role, created_at)
SELECT DISTINCT
    co.shop_id,
    COALESCE(
        -- Try to get user_id from audit_logs (shop.created action)
        (SELECT al.actor_user_id FROM audit_logs al 
         WHERE al.shop_id = co.shop_id AND al.action = 'shop.created' 
         LIMIT 1),
        -- Fall back to a placeholder that indicates manual review needed
        'BACKFILL_NEEDS_REVIEW_' || co.shop_id::text
    ) as user_id,
    'OWNER',
    co.created_at
FROM cab_owners co
WHERE NOT EXISTS (
    SELECT 1 FROM shop_members sm 
    WHERE sm.shop_id = co.shop_id
)
ON CONFLICT (shop_id, user_id) DO NOTHING;

-- ============================================================================
-- PART C: Ensure shops with category='cab' have cab_owners records
-- ============================================================================

-- This is the reverse check: shops marked as 'cab' should have cab_owners config
-- We don't auto-create cab_owners here as that requires business info,
-- but we can log which shops need setup

-- Create a view to identify inconsistencies (for debugging)
CREATE OR REPLACE VIEW v_cab_data_consistency AS
SELECT 
    s.id as shop_id,
    s.name,
    s.category,
    sm.user_id as owner_user_id,
    sm.role as member_role,
    co.id as cab_owner_id,
    co.business_name as cab_business_name,
    CASE 
        WHEN s.category = 'cab' AND co.id IS NULL THEN 'MISSING_CAB_OWNER'
        WHEN co.id IS NOT NULL AND sm.user_id IS NULL THEN 'MISSING_SHOP_MEMBER'
        WHEN s.category = 'cab' AND co.id IS NOT NULL AND sm.user_id IS NOT NULL THEN 'OK'
        WHEN s.category != 'cab' OR s.category IS NULL THEN 'NOT_CAB'
        ELSE 'UNKNOWN'
    END as status
FROM shops s
LEFT JOIN shop_members sm ON sm.shop_id = s.id AND sm.role = 'OWNER'
LEFT JOIN cab_owners co ON co.shop_id = s.id;

COMMENT ON VIEW v_cab_data_consistency IS 
'Debug view showing cab data model consistency. Status values:
- OK: Shop has both shop_member OWNER and cab_owner config
- MISSING_CAB_OWNER: Cab shop without cab_owners record (needs setup)
- MISSING_SHOP_MEMBER: Has cab_owner but no shop_member OWNER
- NOT_CAB: Not a cab business
- UNKNOWN: Unexpected state';

-- ============================================================================
-- PART D: Add helpful indexes for cab queries
-- ============================================================================

-- Compound index for cab owner lookups
CREATE INDEX IF NOT EXISTS idx_cab_owners_shop_active ON cab_owners(shop_id, active);

-- Index for finding active cab businesses
CREATE INDEX IF NOT EXISTS idx_shops_category_cab ON shops(id) WHERE category = 'cab';

-- ============================================================================
-- VERIFICATION QUERY (run manually after migration)
-- ============================================================================

-- SELECT * FROM v_cab_data_consistency WHERE status != 'NOT_CAB' AND status != 'OK';

