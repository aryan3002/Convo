# Cab Services Architecture Fix Summary

## Overview

This document summarizes the architectural changes made to fix cab services authorization, routing, and data model issues.

## Changes Made

### 1. Backend Auth Architecture (`/Backend/app/core/request_context.py`)

**New File:** Created a centralized `RequestContext` module that provides:

- `RequestContext` dataclass - Single source of truth for identity
- `resolve_request_context()` - Central function for extracting identity from requests
- `require_shop_access()` - ONE authorization rule for shop access
- Support for multiple auth methods (JWT ready, session ready, X-User-Id transitional)

**Key Benefits:**
- All routes can use the same context resolution
- Easy to add Clerk/JWT auth later
- Audit-ready (tracks auth method, IP, user agent)

### 2. Data Model Normalization (`/Backend/migrations/013_normalize_cab_data.sql`)

**New Migration:** Ensures consistency between:
- `shops` - canonical table for all businesses
- `shop_members` - user-shop membership and roles
- `cab_owners` - cab-specific configuration (NOT identity)

**What it does:**
- Backfills `shop_members` OWNER records for orphaned `cab_owners`
- Creates `v_cab_data_consistency` debug view
- Adds helpful indexes for cab queries

### 3. Fixed CabOwner Model Property Names

**Problem:** The API was using `is_active`, `contact_email`, `contact_phone` but the model had `active`, `email`, `phone`.

**Fixed in:** `/Backend/app/routes_scoped.py`
- All `CabOwner.is_active` → `CabOwner.active`
- All `owner.contact_email` → `owner.email`
- All `owner.contact_phone` → `owner.phone`

### 4. Server-Authoritative Routing (`/s/{slug}/info` endpoint)

**New Endpoint:** `GET /s/{slug}/info`

Returns:
```json
{
  "id": 123,
  "slug": "my-cab-service",
  "name": "My Cab Service",
  "category": "cab",
  "is_cab_service": true,
  "owner_dashboard_path": "/s/my-cab-service/owner/cab"
}
```

**Frontend Change:** Owner dashboard now uses this endpoint to determine routing instead of guessing from category.

### 5. ShopContext Enhanced (`/Backend/app/tenancy/context.py`)

Added to `ShopContext`:
- `category` field - business type from shops table
- `is_cab_service` property - convenience check
- `owner_dashboard_path` property - correct dashboard path

### 6. Auth Debug Endpoint (`/s/{slug}/owner/auth-status`)

**New Endpoint:** Helps diagnose 403 errors by showing:
- What user ID the frontend is sending
- Whether that user has shop access
- What user IDs DO have access
- Hints for fixing auth issues

### 7. Frontend Auth Debug UI (`/s/[slug]/owner/cab/setup/page.tsx`)

When users get 403 errors, the setup page now shows:
- What user ID is being used
- What user IDs should work
- One-click fix buttons to use the correct ID

### 8. Standardized API Responses (`/Backend/app/core/responses.py`)

**New Module:** Provides consistent response formatting:
```python
# Success
{"data": {...}, "status": "success"}

# Error
{"error": {"code": "NOT_FOUND", "message": "..."}, "status": "error"}
```

Includes `ErrorCodes` class with standard error codes.

## How Authorization Works Now

### Single Rule for Shop Access

```
A user can access a shop IF:
  - They have a record in shop_members for that shop_id
  - AND their role matches the required role (OWNER, MANAGER, EMPLOYEE)
```

### Flow for Cab Dashboard

1. User visits `/s/{slug}/owner`
2. Frontend calls `GET /s/{slug}/info` (public, no auth)
3. Backend returns `is_cab_service: true, owner_dashboard_path: "/s/{slug}/owner/cab"`
4. Frontend redirects to cab dashboard
5. Cab dashboard calls `GET /s/{slug}/owner/cab/owner` with X-User-Id header
6. Backend:
   - Extracts user_id from X-User-Id header
   - Looks up shop_members for (shop_id, user_id)
   - Verifies role is OWNER or MANAGER
   - Returns cab owner config or 403

### Troubleshooting 403 Errors

1. Visit `/s/{slug}/owner/auth-status` to see:
   - What user ID is being sent
   - What user IDs have access
   - What's wrong

2. Fix options:
   - Use the correct user ID in localStorage
   - Run `fix_qaz_membership.py` to add missing membership
   - Use the SQL migration to backfill memberships

## Files Changed

### Backend
- `app/core/__init__.py` - Added exports
- `app/core/request_context.py` - NEW: Centralized auth context
- `app/core/responses.py` - NEW: Standardized responses
- `app/auth.py` - Updated to export new context helpers
- `app/routes_scoped.py` - Fixed model properties, added endpoints
- `app/tenancy/context.py` - Added category to ShopContext
- `migrations/013_normalize_cab_data.sql` - NEW: Data normalization

### Frontend
- `src/lib/api.ts` - Added ShopInfo type, getShopInfo function, updated docs
- `src/app/s/[slug]/owner/page.tsx` - Use server-authoritative routing
- `src/app/s/[slug]/owner/cab/setup/page.tsx` - Auth debug UI

## Future Work

1. **Integrate Clerk JWT:** Replace X-User-Id with proper JWT verification
2. **Session Support:** Add server-side sessions for web clients
3. **Migrate Hooks:** Convert raw fetch calls to use apiFetch
4. **Remove X-User-Id:** Once Clerk is integrated, remove header support
