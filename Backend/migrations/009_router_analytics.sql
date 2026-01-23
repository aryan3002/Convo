-- Migration: 009_router_analytics.sql
-- Purpose: Create analytics tracking table for RouterGPT metrics
-- Phase: 3 - RouterGPT Integration (Analytics)
-- Created: 2024

-- ============================================================
-- TABLE: router_analytics
-- ============================================================
-- Tracks RouterGPT usage patterns and metrics for analysis

CREATE TABLE IF NOT EXISTS router_analytics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Event identification
    event_type VARCHAR(50) NOT NULL,  -- 'search', 'delegate', 'booking_complete'
    session_id UUID,  -- Links events in the same customer journey
    
    -- Location search data
    search_latitude DECIMAL(10, 7),
    search_longitude DECIMAL(10, 7),
    search_radius_miles DECIMAL(5, 2),
    search_category VARCHAR(50),
    search_results_count INTEGER,
    
    -- Delegation data
    shop_id INTEGER REFERENCES shops(id) ON DELETE SET NULL,
    shop_slug VARCHAR(100),
    delegation_intent VARCHAR(200),  -- Customer's stated intent
    
    -- Booking completion data
    booking_id INTEGER,  -- From bookings table (if applicable)
    customer_email VARCHAR(255),
    service_id INTEGER,
    
    -- Distance tracking
    customer_to_shop_miles DECIMAL(6, 2),  -- Distance from search location to booked shop
    
    -- Metadata
    ip_address VARCHAR(45),  -- For rate limiting analysis
    user_agent TEXT,
    referrer TEXT,
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Success tracking
    success BOOLEAN DEFAULT TRUE
);

-- ============================================================
-- INDEXES
-- ============================================================

-- Query by event type
CREATE INDEX IF NOT EXISTS idx_router_analytics_event_type 
ON router_analytics (event_type);

-- Query by session to track full journeys
CREATE INDEX IF NOT EXISTS idx_router_analytics_session 
ON router_analytics (session_id);

-- Query by shop to see which shops are most discovered
CREATE INDEX IF NOT EXISTS idx_router_analytics_shop 
ON router_analytics (shop_id);

-- Query by timestamp for time-series analysis
CREATE INDEX IF NOT EXISTS idx_router_analytics_created_at 
ON router_analytics (created_at DESC);

-- Query by success for conversion tracking
CREATE INDEX IF NOT EXISTS idx_router_analytics_success 
ON router_analytics (success);

-- ============================================================
-- VIEWS FOR COMMON ANALYTICS QUERIES
-- ============================================================

-- View 1: RouterGPT Usage Summary
CREATE OR REPLACE VIEW router_usage_summary AS
SELECT
    DATE(created_at) as date,
    event_type,
    COUNT(*) as event_count,
    COUNT(DISTINCT session_id) as unique_sessions,
    COUNT(DISTINCT shop_id) as unique_shops,
    AVG(customer_to_shop_miles) as avg_distance_miles
FROM router_analytics
WHERE created_at >= NOW() - INTERVAL '30 days'
GROUP BY DATE(created_at), event_type
ORDER BY date DESC, event_type;

-- View 2: Shop Discovery Leaderboard
CREATE OR REPLACE VIEW router_shop_discovery AS
SELECT
    s.id as shop_id,
    s.slug,
    s.name,
    s.category,
    s.address,
    COUNT(DISTINCT ra.session_id) as times_discovered,
    COUNT(CASE WHEN ra.event_type = 'delegate' THEN 1 END) as times_selected,
    COUNT(CASE WHEN ra.event_type = 'booking_complete' THEN 1 END) as bookings_completed,
    AVG(ra.customer_to_shop_miles) as avg_customer_distance,
    MAX(ra.created_at) as last_discovered
FROM shops s
LEFT JOIN router_analytics ra ON ra.shop_id = s.id
WHERE ra.created_at >= NOW() - INTERVAL '30 days' OR ra.created_at IS NULL
GROUP BY s.id, s.slug, s.name, s.category, s.address
ORDER BY times_discovered DESC NULLS LAST;

-- View 3: Conversion Funnel
CREATE OR REPLACE VIEW router_conversion_funnel AS
WITH funnel_data AS (
    SELECT
        DATE(created_at) as date,
        COUNT(DISTINCT CASE WHEN event_type = 'search' THEN session_id END) as searches,
        COUNT(DISTINCT CASE WHEN event_type = 'delegate' THEN session_id END) as delegations,
        COUNT(DISTINCT CASE WHEN event_type = 'booking_complete' THEN session_id END) as bookings
    FROM router_analytics
    WHERE created_at >= NOW() - INTERVAL '30 days'
    GROUP BY DATE(created_at)
)
SELECT
    date,
    searches,
    delegations,
    bookings,
    CASE WHEN searches > 0 THEN ROUND((delegations::DECIMAL / searches * 100), 2) ELSE 0 END as search_to_delegate_pct,
    CASE WHEN delegations > 0 THEN ROUND((bookings::DECIMAL / delegations * 100), 2) ELSE 0 END as delegate_to_booking_pct,
    CASE WHEN searches > 0 THEN ROUND((bookings::DECIMAL / searches * 100), 2) ELSE 0 END as search_to_booking_pct
FROM funnel_data
ORDER BY date DESC;

-- View 4: Popular Search Locations
CREATE OR REPLACE VIEW router_popular_locations AS
SELECT
    ROUND(search_latitude::NUMERIC, 2) as lat_rounded,
    ROUND(search_longitude::NUMERIC, 2) as lon_rounded,
    search_category,
    COUNT(*) as search_count,
    COUNT(DISTINCT session_id) as unique_sessions,
    AVG(search_results_count) as avg_results,
    MAX(created_at) as last_search
FROM router_analytics
WHERE event_type = 'search'
  AND search_latitude IS NOT NULL
  AND created_at >= NOW() - INTERVAL '30 days'
GROUP BY 
    ROUND(search_latitude::NUMERIC, 2),
    ROUND(search_longitude::NUMERIC, 2),
    search_category
HAVING COUNT(*) >= 5  -- Only show locations with 5+ searches
ORDER BY search_count DESC
LIMIT 50;

-- ============================================================
-- HELPER FUNCTIONS
-- ============================================================

-- Function to calculate RouterGPT booking rate
CREATE OR REPLACE FUNCTION get_routergpt_booking_rate(days INTEGER DEFAULT 30)
RETURNS TABLE (
    total_bookings BIGINT,
    routergpt_bookings BIGINT,
    routergpt_percentage DECIMAL
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        COUNT(*)::BIGINT as total_bookings,
        COUNT(CASE WHEN ra.session_id IS NOT NULL THEN 1 END)::BIGINT as routergpt_bookings,
        CASE 
            WHEN COUNT(*) > 0 THEN 
                ROUND((COUNT(CASE WHEN ra.session_id IS NOT NULL THEN 1 END)::DECIMAL / COUNT(*) * 100), 2)
            ELSE 0
        END as routergpt_percentage
    FROM bookings b
    LEFT JOIN router_analytics ra 
        ON ra.booking_id = b.id 
        AND ra.event_type = 'booking_complete'
    WHERE b.created_at >= NOW() - (days || ' days')::INTERVAL;
END;
$$ LANGUAGE plpgsql;

-- ============================================================
-- COMMENTS
-- ============================================================

COMMENT ON TABLE router_analytics IS 
'Tracks RouterGPT usage patterns: searches, delegations, and booking completions for analytics';

COMMENT ON VIEW router_usage_summary IS 
'Daily summary of RouterGPT activity by event type';

COMMENT ON VIEW router_shop_discovery IS 
'Leaderboard showing which shops are most frequently discovered and selected';

COMMENT ON VIEW router_conversion_funnel IS 
'Conversion rates through the RouterGPT funnel: search → delegate → booking';

COMMENT ON VIEW router_popular_locations IS 
'Most frequently searched locations (rounded to 0.01 degree precision)';

COMMENT ON FUNCTION get_routergpt_booking_rate IS 
'Calculate percentage of bookings that came through RouterGPT vs direct booking';
