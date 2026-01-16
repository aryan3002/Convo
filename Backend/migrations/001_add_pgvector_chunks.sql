-- ============================================================================
-- Migration: Add pgvector extension and embedded_chunks table
-- Purpose: Enable semantic search over call transcripts, summaries, booking notes
-- 
-- DESIGN CHOICES:
-- 1. Embedding Model: OpenAI text-embedding-3-small (1536 dimensions)
--    - Best balance of cost, performance, and quality for search use cases
--    - ~5x cheaper than ada-002 with better quality
--    - If you need higher quality, switch to text-embedding-3-large (3072 dims)
--
-- 2. Vector Index: HNSW instead of IVFFlat
--    - HNSW: Better recall without training, faster queries, slightly more RAM
--    - IVFFlat: Requires training (lists parameter), worse recall on small data
--    - For moderate scale (thousands of chunks), HNSW is the clear winner
--
-- 3. Uniqueness: Composite (shop_id, source_type, source_id, chunk_index)
--    - Prevents duplicate ingestion of same chunk
--    - Allows re-ingestion if source changes (delete old, insert new)
--    - content_hash is for change detection, not uniqueness constraint
--
-- 4. Multi-tenancy: Every query MUST filter by shop_id first
--    - Composite index on (shop_id, source_type) for filtered scans
--    - HNSW index still useful after shop_id filter narrows results
-- ============================================================================

-- Enable pgvector extension (requires superuser or extension already installed on Neon)
CREATE EXTENSION IF NOT EXISTS vector;

-- Enum for source types (extensible)
-- Using TEXT instead of ENUM for easier future additions without migrations
-- Validates at application layer

-- Main embedded chunks table
CREATE TABLE IF NOT EXISTS embedded_chunks (
    -- Primary key
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Multi-tenancy: REQUIRED for all queries
    shop_id INTEGER NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
    
    -- Source identification
    source_type TEXT NOT NULL CHECK (source_type IN ('call_transcript', 'call_summary', 'booking_note')),
    source_id UUID NOT NULL,  -- The ID of the source record (call_summary.id, booking.id, etc.)
    
    -- Optional foreign keys for filtering (nullable for flexibility)
    booking_id UUID REFERENCES bookings(id) ON DELETE SET NULL,
    call_id UUID,  -- References call_summaries.id (nullable, not all chunks have calls)
    customer_id INTEGER REFERENCES customers(id) ON DELETE SET NULL,
    stylist_id INTEGER REFERENCES stylists(id) ON DELETE SET NULL,
    
    -- Chunk metadata
    chunk_index INTEGER NOT NULL DEFAULT 0,  -- 0-indexed position within source
    content TEXT NOT NULL,  -- The actual text chunk
    content_hash TEXT NOT NULL,  -- SHA256 of normalized content for change detection
    token_count INTEGER,  -- Approximate token count (useful for context windows)
    
    -- The embedding vector (1536 dims for text-embedding-3-small)
    embedding vector(1536) NOT NULL,
    
    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- Prevent duplicate chunk ingestion
    CONSTRAINT uq_chunk_identity UNIQUE (shop_id, source_type, source_id, chunk_index)
);

-- ============================================================================
-- INDEXES
-- ============================================================================

-- 1. Shop + created_at: For time-based queries within a shop
CREATE INDEX IF NOT EXISTS idx_chunks_shop_created 
    ON embedded_chunks(shop_id, created_at DESC);

-- 2. Shop + source_type: For filtered vector searches
CREATE INDEX IF NOT EXISTS idx_chunks_shop_source_type 
    ON embedded_chunks(shop_id, source_type);

-- 3. Shop + customer: For customer-specific searches
CREATE INDEX IF NOT EXISTS idx_chunks_shop_customer 
    ON embedded_chunks(shop_id, customer_id) 
    WHERE customer_id IS NOT NULL;

-- 4. Shop + stylist: For stylist-specific searches
CREATE INDEX IF NOT EXISTS idx_chunks_shop_stylist 
    ON embedded_chunks(shop_id, stylist_id) 
    WHERE stylist_id IS NOT NULL;

-- 5. Content hash: For idempotent upserts (check if content changed)
CREATE INDEX IF NOT EXISTS idx_chunks_content_hash 
    ON embedded_chunks(shop_id, content_hash);

-- 6. HNSW Vector Index: For fast approximate nearest neighbor search
-- Parameters:
--   m = 16: Number of connections per layer (default, good balance)
--   ef_construction = 64: Build-time quality (higher = better recall, slower build)
-- 
-- Using cosine distance (<=>) which is standard for normalized embeddings
-- OpenAI embeddings are already normalized, so cosine = dot product
CREATE INDEX IF NOT EXISTS idx_chunks_embedding_hnsw 
    ON embedded_chunks 
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- ============================================================================
-- HELPER FUNCTION: Semantic search with shop isolation
-- ============================================================================

-- Function to perform semantic search with mandatory shop_id filtering
-- Returns chunks ordered by similarity (lower distance = more similar)
CREATE OR REPLACE FUNCTION search_chunks(
    p_shop_id INTEGER,
    p_query_embedding vector(1536),
    p_limit INTEGER DEFAULT 10,
    p_source_types TEXT[] DEFAULT NULL,
    p_customer_id INTEGER DEFAULT NULL,
    p_stylist_id INTEGER DEFAULT NULL,
    p_min_created_at TIMESTAMPTZ DEFAULT NULL
)
RETURNS TABLE (
    id UUID,
    source_type TEXT,
    source_id UUID,
    chunk_index INTEGER,
    content TEXT,
    customer_id INTEGER,
    stylist_id INTEGER,
    created_at TIMESTAMPTZ,
    similarity FLOAT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        ec.id,
        ec.source_type,
        ec.source_id,
        ec.chunk_index,
        ec.content,
        ec.customer_id,
        ec.stylist_id,
        ec.created_at,
        1 - (ec.embedding <=> p_query_embedding) AS similarity
    FROM embedded_chunks ec
    WHERE ec.shop_id = p_shop_id
        AND (p_source_types IS NULL OR ec.source_type = ANY(p_source_types))
        AND (p_customer_id IS NULL OR ec.customer_id = p_customer_id)
        AND (p_stylist_id IS NULL OR ec.stylist_id = p_stylist_id)
        AND (p_min_created_at IS NULL OR ec.created_at >= p_min_created_at)
    ORDER BY ec.embedding <=> p_query_embedding
    LIMIT p_limit;
END;
$$ LANGUAGE plpgsql STABLE;

-- ============================================================================
-- COMMENTS for documentation
-- ============================================================================

COMMENT ON TABLE embedded_chunks IS 
    'Stores embedded text chunks for semantic search. All queries must filter by shop_id.';

COMMENT ON COLUMN embedded_chunks.source_type IS 
    'Type of source: call_transcript, call_summary, or booking_note';

COMMENT ON COLUMN embedded_chunks.embedding IS 
    'Vector embedding from OpenAI text-embedding-3-small (1536 dimensions)';

COMMENT ON FUNCTION search_chunks IS 
    'Semantic search with mandatory shop_id isolation. Returns chunks ordered by similarity.';
