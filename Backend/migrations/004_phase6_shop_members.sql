-- Migration 004: Phase 6 - Shop Members Table
-- Purpose: Multi-user access control and ownership tracking

CREATE TABLE IF NOT EXISTS shop_members (
    id SERIAL PRIMARY KEY,
    shop_id INTEGER NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
    user_id VARCHAR(255) NOT NULL,  -- Auth provider user ID (e.g., Clerk, Auth0, Firebase)
    role VARCHAR(20) NOT NULL DEFAULT 'EMPLOYEE',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    
    CONSTRAINT uq_shop_member UNIQUE (shop_id, user_id)
);

-- Indexes for query performance
CREATE INDEX IF NOT EXISTS idx_shop_members_shop_id ON shop_members(shop_id);
CREATE INDEX IF NOT EXISTS idx_shop_members_user_id ON shop_members(user_id);

-- Comments for documentation
COMMENT ON TABLE shop_members IS 'Multi-user access control for shops (Phase 6)';
COMMENT ON COLUMN shop_members.user_id IS 'External auth provider user identifier';
COMMENT ON COLUMN shop_members.role IS 'OWNER | MANAGER | EMPLOYEE';
