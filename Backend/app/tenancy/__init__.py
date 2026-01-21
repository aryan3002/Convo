"""
Multi-tenancy package for Convo.

This package provides tenant isolation primitives for the multi-tenant architecture.

Modules:
    context: ShopContext resolution and database tenant setting
    config: Tenancy configuration constants (for legacy compatibility)
    queries: Tenant-scoped query helpers

PHASE 3 STATUS:
    - ShopContext resolution implemented (slug, phone, API key)
    - FastAPI dependencies ready for route injection
    - Tenant-scoped query helpers for all tenant tables
    - require_shop_context for strict enforcement (no fallback)
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

from .queries import (
    # Composable helpers
    scoped_select,
    tenant_filter,
    require_owned,
    # Service queries
    get_service_by_id,
    list_services,
    find_service_by_name,
    get_services_by_ids,
    # Stylist queries
    get_stylist_by_id,
    list_stylists,
    list_active_stylists,
    find_stylist_by_name,
    get_stylists_by_ids,
    list_stylists_with_pin,
    # Promo queries
    get_promo_by_id,
    list_promos,
    # Booking queries
    get_booking_by_id,
    list_bookings_in_range,
    # Customer profile queries
    get_or_create_customer_shop_profile,
)

__all__ = [
    # Context
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
    # Query helpers
    "scoped_select",
    "tenant_filter",
    "require_owned",
    "get_service_by_id",
    "list_services",
    "find_service_by_name",
    "get_services_by_ids",
    "get_stylist_by_id",
    "list_stylists",
    "list_active_stylists",
    "find_stylist_by_name",
    "get_stylists_by_ids",
    "list_stylists_with_pin",
    "get_promo_by_id",
    "list_promos",
    "get_booking_by_id",
    "list_bookings_in_range",
    "get_or_create_customer_shop_profile",
]

