-- Phase 7: Audit Logging
-- Track all security-relevant actions in the system

-- ============================================================================
-- AUDIT_LOGS TABLE
-- ============================================================================
-- Stores audit trail for security, compliance, and debugging.
-- All shop-scoped actions should log the shop_id for tenant filtering.
-- ============================================================================

CREATE TABLE IF NOT EXISTS audit_logs (
    id SERIAL PRIMARY KEY,
    
    -- Tenant context (nullable for system-level actions)
    shop_id INTEGER REFERENCES shops(id) ON DELETE SET NULL,
    
    -- Who performed the action
    actor_user_id VARCHAR(255) NOT NULL,
    
    -- What action was performed (e.g., 'shop.created', 'owner.chat', 'booking.created')
    action VARCHAR(100) NOT NULL,
    
    -- Target entity type (e.g., 'shop', 'booking', 'service')
    target_type VARCHAR(50),
    
    -- Target entity ID (nullable - some actions have no specific target)
    target_id VARCHAR(100),
    
    -- Additional context (JSON blob, must NOT contain PII unless necessary)
    metadata JSONB,
    
    -- Timestamp with timezone
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================================
-- INDEXES
-- ============================================================================
-- Optimize common query patterns for audit log retrieval

-- Query logs by shop (tenant filtering)
CREATE INDEX IF NOT EXISTS idx_audit_logs_shop_id ON audit_logs(shop_id);

-- Query logs by user (who did what)
CREATE INDEX IF NOT EXISTS idx_audit_logs_actor_user_id ON audit_logs(actor_user_id);

-- Query logs by time range (recent activity, time-based filtering)
CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at ON audit_logs(created_at DESC);

-- Query logs by action type (e.g., find all 'shop.created' events)
CREATE INDEX IF NOT EXISTS idx_audit_logs_action ON audit_logs(action);

-- Composite index for common dashboard queries: shop + time
CREATE INDEX IF NOT EXISTS idx_audit_logs_shop_created 
    ON audit_logs(shop_id, created_at DESC);

-- ============================================================================
-- COMMENTS
-- ============================================================================

COMMENT ON TABLE audit_logs IS 'Security audit trail for all significant actions';
COMMENT ON COLUMN audit_logs.shop_id IS 'Tenant scope (NULL for system-level actions like shop creation)';
COMMENT ON COLUMN audit_logs.actor_user_id IS 'User who performed the action (from auth provider)';
COMMENT ON COLUMN audit_logs.action IS 'Action identifier (e.g., shop.created, owner.chat, booking.created)';
COMMENT ON COLUMN audit_logs.target_type IS 'Type of entity affected (shop, booking, service, etc.)';
COMMENT ON COLUMN audit_logs.target_id IS 'ID of affected entity (string to support various ID types)';
COMMENT ON COLUMN audit_logs.metadata IS 'Additional context (MUST NOT contain PII unless necessary)';
