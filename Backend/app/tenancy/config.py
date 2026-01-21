"""
Tenancy configuration constants.

This module centralizes all multi-tenancy configuration values.

PHASE 0 STATUS:
    - DEFAULT_SHOP_ID defined as single source of truth
    - Not yet used by existing code (to preserve behavior)
    
PHASE 2 TODO:
    - Remove DEFAULT_SHOP_ID after all code uses proper resolution
    - This constant should NOT exist in production multi-tenant setup
"""

# ────────────────────────────────────────────────────────────────
# WARNING: Phase 0/1 Only - Remove in Phase 2
# ────────────────────────────────────────────────────────────────

# The default shop ID used when shop context cannot be determined.
# This exists ONLY to preserve current single-shop behavior during migration.
#
# CRITICAL: Do NOT add new usages of this constant.
# CRITICAL: All new code should use ShopContext resolution.
#
# TODO [Phase 2]: Delete this constant and all references to it.
DEFAULT_SHOP_ID: int = 1

# Default shop name (matches DEFAULT_SHOP_NAME env var)
# Used by get_default_shop() to find/create the default shop.
#
# TODO [Phase 2]: Remove - shops should be explicitly created, not auto-created.
DEFAULT_SHOP_NAME: str = "Bishops Tempe"


# ────────────────────────────────────────────────────────────────
# Future Configuration (Phase 2+)
# ────────────────────────────────────────────────────────────────

# These will be used when multi-tenancy is fully implemented.
# Keeping them commented for planning purposes.

# # Shop resolution configuration
# SHOP_RESOLUTION_ENABLED: bool = False  # Set True in Phase 2
# 
# # URL patterns for shop slug extraction
# SHOP_URL_PATTERNS: list[str] = [
#     r"^/s/(?P<slug>[a-z0-9-]+)/",  # Customer routes
#     r"^/o/(?P<slug>[a-z0-9-]+)/",  # Owner routes
# ]
# 
# # Fallback behavior when shop cannot be resolved
# # Options: "error" (return 400), "default" (use DEFAULT_SHOP_ID)
# SHOP_RESOLUTION_FALLBACK: str = "error"
# 
# # RLS configuration
# RLS_ENABLED: bool = False  # Set True in Phase 5
# RLS_SESSION_VARIABLE: str = "app.current_shop_id"
