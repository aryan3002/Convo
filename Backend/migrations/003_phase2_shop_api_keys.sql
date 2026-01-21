-- Phase 2 Migration: Shop API Keys
-- This migration adds the shop_api_keys table for API key-based shop resolution.
-- Enables ChatGPT plugins and other integrations to authenticate to specific shops.

-- Create the shop_api_keys table
CREATE TABLE IF NOT EXISTS shop_api_keys (
    id SERIAL PRIMARY KEY,
    shop_id INTEGER NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    api_key_hash VARCHAR(64) NOT NULL UNIQUE,  -- SHA-256 hex
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    revoked_at TIMESTAMPTZ,
    
    CONSTRAINT uq_shop_api_key_name UNIQUE (shop_id, name)
);

-- Index for fast lookup by API key hash
CREATE INDEX IF NOT EXISTS idx_shop_api_keys_hash ON shop_api_keys(api_key_hash);

-- Index for listing keys by shop
CREATE INDEX IF NOT EXISTS idx_shop_api_keys_shop ON shop_api_keys(shop_id);

-- Record this migration
INSERT INTO schema_migrations (version, name) 
VALUES ('003', 'phase2_shop_api_keys')
ON CONFLICT (version) DO NOTHING;

-- Note: To generate an API key for a shop:
-- 1. Generate a secure random key: openssl rand -hex 32
-- 2. Hash it: echo -n "YOUR_KEY" | sha256sum
-- 3. Insert: INSERT INTO shop_api_keys (shop_id, name, api_key_hash) VALUES (1, 'ChatGPT Plugin', 'HASHED_KEY');
-- 4. Give the original key to the client (it cannot be recovered from the hash)
