"""
Multi-tenancy package for Convo.

This package provides tenant isolation primitives for the multi-tenant architecture.

Modules:
    context: ShopContext resolution and database tenant setting
    config: Tenancy configuration constants (for legacy compatibility)
    queries: Tenant-scoped query helpers

PHASE 2 STATUS:
    - ShopContext resolution implemented (slug, phone, API key)
    - FastAPI dependencies ready for route injection
    - Legacy fallback to shop_id=1 for old routes
"""

from .context import (
    ShopContext,
    ShopResolutionSource,
    get_shop_context,
    get_shop_context_or_none,
    require_shop_context,
    get_legacy_default_shop_context,
    resolve_shop_context,
    resolve_shop_from_slug,
    resolve_shop_from_twilio_to,
    resolve_shop_from_api_key,
    extract_slug_from_path,
    hash_api_key,
    set_db_tenant,
    LEGACY_DEFAULT_SHOP_ID,
)

__all__ = [
    "ShopContext",
    "ShopResolutionSource",
    "get_shop_context",
    "get_shop_context_or_none",
    "require_shop_context",
    "get_legacy_default_shop_context",
    "resolve_shop_context",
    "resolve_shop_from_slug",
    "resolve_shop_from_twilio_to",
    "resolve_shop_from_api_key",
    "extract_slug_from_path",
    "hash_api_key",
    "set_db_tenant",
    "LEGACY_DEFAULT_SHOP_ID",
]

