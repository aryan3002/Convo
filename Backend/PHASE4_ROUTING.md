# Phase 4: Entry Points & Routing

## Status: ✅ COMPLETE

This document describes the Phase 4 implementation for multi-tenant entry points and routing.

## Goals Achieved

| Goal | Status |
|------|--------|
| URL-based shop routing is live | ✅ `/s/{slug}/...` routes |
| Voice routing is final | ✅ Strict Twilio To resolution |
| Legacy fallback removed from real entrypoints | ✅ No silent shop_id=1 defaults |
| Frontend routing hooks | ✅ `shop_slug` in responses |

## New Routes (Phase 4)

### Slug-Scoped Routes (`/s/{slug}/...`)

All new routes use strict shop resolution from URL slug. Invalid slugs return 404.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/s/{slug}/chat` | POST | Multi-tenant chat endpoint |
| `/s/{slug}/owner/chat` | POST | Multi-tenant owner chat |
| `/s/{slug}/services` | GET | List services for shop |
| `/s/{slug}/stylists` | GET | List active stylists |
| `/s/{slug}/info` | GET | Shop info (name, slug, timezone) |

### Example Usage

```bash
# Chat with Bishops Tempe shop
curl -X POST "http://localhost:8000/s/bishops-tempe/chat" \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "I want to book a haircut"}]}'

# Get shop info
curl "http://localhost:8000/s/bishops-tempe/info"

# List services
curl "http://localhost:8000/s/bishops-tempe/services"
```

### Response Format

All scoped routes include shop context in responses:

```json
{
  "reply": "I can help you book an appointment...",
  "action": null,
  "data": null,
  "shop_slug": "bishops-tempe",
  "shop_name": "Bishops Tempe"
}
```

## Deprecated Routes

The following routes are **deprecated** and will be removed in Phase 5:

| Endpoint | Replacement |
|----------|-------------|
| `POST /chat` | `POST /s/{slug}/chat` |
| `POST /owner/chat` | `POST /s/{slug}/owner/chat` |

These routes still work but:
- Log deprecation warnings
- Default to shop_id=1 via legacy fallback
- Are marked `deprecated=True` in OpenAPI schema

## Voice Routing Changes

### Strict Twilio To Resolution

The `/twilio/voice` endpoint now uses **strict** shop resolution:

1. Extracts `To` number from Twilio webhook
2. Looks up shop by registered phone number in `shop_phone_numbers` table (preferred) or `shops.phone_number` (fallback)
3. **No fallback** - returns error TwiML if shop not found

### Error Handling

If Twilio To number is not registered:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Say>Sorry, this phone number is not configured for bookings. 
       Please contact the salon directly. Goodbye.</Say>
  <Hangup/>
</Response>
```

### Setup Required

To enable voice for a shop, register the Twilio number in the database.

**Option A: Use `shop_phone_numbers` table (recommended for multiple numbers)**:

```sql
-- Insert into shop_phone_numbers (supports multiple numbers per shop)
-- Note: phone_number has a UNIQUE constraint across all shops
INSERT INTO shop_phone_numbers (shop_id, phone_number, label, is_primary)
SELECT id, '+14801234567', 'booking', true
FROM shops
WHERE slug = 'bishops-tempe';
```

**Schema reference:**
- `shop_id`: Foreign key to shops table
- `phone_number`: VARCHAR(20), UNIQUE across all shops
- `label`: Optional label like 'main', 'booking', 'support'
- `is_primary`: BOOLEAN, marks the primary number for the shop

**Option B: Use `shops.phone_number` column (simple single-number setup)**:

```sql
-- Set the primary phone directly on the shop
UPDATE shops 
SET phone_number = '+14801234567' 
WHERE slug = 'bishops-tempe';
```

**Resolution Order**: The system checks `shop_phone_numbers` first, then falls back to `shops.phone_number`. Use Option A for multi-number routing (e.g., separate booking vs support lines).

## File Changes

### New Files

- `app/routes_scoped.py` - Slug-scoped router with strict resolution
- `tests/test_phase4_routing.py` - Phase 4 tests

### Modified Files

| File | Changes |
|------|---------|
| `app/main.py` | Added scoped router, deprecated legacy routes |
| `app/voice.py` | Strict Twilio To resolution, removed LEGACY_DEFAULT_SHOP_ID fallback |
| `app/voice_backup.py` | Added deprecation warning (to be deleted in Phase 5) |

## Testing

```bash
# Run Phase 4 tests
pytest tests/test_phase4_routing.py -v

# Test slug resolution
curl -I "http://localhost:8000/s/invalid-shop/info"
# Expected: 404 Not Found

curl "http://localhost:8000/s/bishops-tempe/info"
# Expected: 200 OK with shop context
```

## Migration Guide

### For Frontend Developers

1. Update API base URLs to include shop slug:
   ```javascript
   // Old
   const response = await fetch('/chat', { ... });
   
   // New (Phase 4)
   const response = await fetch(`/s/${shopSlug}/chat`, { ... });
   ```

2. Use `shop_slug` from responses for building URLs:
   ```javascript
   const data = await response.json();
   const bookingUrl = `/s/${data.shop_slug}/booking`;
   ```

### For Backend/API Consumers

1. Stop using `/chat` and `/owner/chat` endpoints
2. Determine shop slug from URL or configuration
3. Use `/s/{slug}/...` endpoints

## Verification Checklist

- [x] `python3 -c "from app.main import app"` succeeds
- [x] Scoped routes appear in `app.routes`
- [x] Legacy routes marked deprecated
- [x] Voice.py has no LEGACY_DEFAULT_SHOP_ID references
- [x] Tests pass: `pytest tests/test_phase4_routing.py -v`

## Next Steps (Phase 5)

1. Remove deprecated `/chat` and `/owner/chat` routes
2. Delete `voice_backup.py` 
3. Remove `get_default_shop()` helper from main.py
4. Update frontend to use slug-scoped routes exclusively
5. Add shop onboarding flow with automatic slug generation
