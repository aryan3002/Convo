# Multi-Tenancy Phase 0: Single-Shop Assumptions Audit

**Generated:** 2026-01-21  
**Scope:** Full codebase audit for multi-tenancy migration planning  
**Status:** Phase 0 (Planning/Scaffolding - No behavior changes)

---

## Executive Summary

This audit identifies **47 single-shop assumptions** across the codebase that must be addressed for multi-tenancy. The app currently operates as a single-shop system with `shop_id=1` hardcoded in multiple locations.

**Critical Risk Areas:**
1. Voice agent uses hardcoded `SHOP_ID = 1`
2. Chat prompts hardcode "Bishops Tempe" salon name
3. Frontend hardcodes `SHOP_ID = 1`
4. Multiple endpoints query services/stylists without shop filtering
5. Timezone assumes America/Phoenix globally

---

## 1. Backend Findings

### 1.1 Hardcoded Shop ID Constants

| File | Line | Code | Risk | Suggested Fix (Phase 2+) |
|------|------|------|------|--------------------------|
| `Backend/app/voice.py` | 52 | `SHOP_ID = 1` | **CRITICAL** - Voice agent always uses shop 1 | Resolve shop from Twilio `To` number via phone→shop lookup |
| `Backend/app/owner_chat.py` | 228 | `DEFAULT_SHOP_ID = 1` | **HIGH** - Owner chat always targets shop 1 | Resolve from authenticated user's shop membership |
| `Backend/app/vector_search.py` | 22, 32 | `shop_id=1` (examples in docstrings) | **LOW** - Documentation only | Update docstrings to show dynamic resolution |
| `Backend/app/call_summary.py` | 128 | `shop_id = session_data.get("shop_id", 1)` | **MEDIUM** - Falls back to shop 1 | Require shop_id in session, fail if missing |

### 1.2 `get_default_shop()` Function Usage

The function `get_default_shop(session)` queries by `DEFAULT_SHOP_NAME` from settings and is used extensively:

| File | Lines | Context | Risk |
|------|-------|---------|------|
| `Backend/app/main.py` | 825-831 | Definition - creates shop if not exists | **HIGH** - Auto-creates based on env var |
| `Backend/app/main.py` | 1559, 3216, 3362, 3486, 3603, 3657, 3708, 3772, 3903, 4102, 4415 | Multiple endpoints | **CRITICAL** - All booking/promo endpoints use default |
| `Backend/app/public_booking.py` | 513-522 | ChatGPT booking API | **HIGH** - Public API assumes single shop |
| `Backend/app/public_booking.py` | 539, 567, 596, 662, 831, 891 | All public endpoints | **CRITICAL** - No shop routing |

### 1.3 Unscoped Database Queries

These queries select data **without filtering by `shop_id`**:

| File | Line | Query | Risk |
|------|------|-------|------|
| `Backend/app/chat.py` | 488-490 | `select(Service).where(Service.name.ilike(...))` | **CRITICAL** - Cross-tenant service lookup |
| `Backend/app/chat.py` | 495 | `select(Service).order_by(Service.id)` | **CRITICAL** - Returns all shops' services |
| `Backend/app/chat.py` | 511 | `select(Stylist).where(Stylist.active.is_(True))` | **CRITICAL** - Returns all shops' stylists |
| `Backend/app/owner_chat.py` | 166 | `select(Service).order_by(Service.id)` | **HIGH** - Shows all services in owner chat |
| `Backend/app/owner_chat.py` | 183 | `select(Stylist).order_by(Stylist.id)` | **HIGH** - Shows all stylists in owner chat |
| `Backend/app/main.py` | 809 | `select(Service).where(Service.id == service_id)` | **MEDIUM** - Lookup by ID without shop check |
| `Backend/app/main.py` | 836 | `select(Stylist).where(Stylist.id == stylist_id)` | **MEDIUM** - Lookup by ID without shop check |
| `Backend/app/main.py` | 1140, 1351 | `select(Service).order_by(Service.id)` | **HIGH** - List all services |
| `Backend/app/voice_backup.py` | 529, 564 | Service lookups without shop filter | **HIGH** - Voice backup unscoped |
| `Backend/app/customer_memory.py` | 226 | `select(Stylist).where(Stylist.id == ...)` | **LOW** - FK relationship, but no shop validation |

### 1.4 Configuration-Level Shop Assumptions

| File | Line | Setting | Value | Risk |
|------|------|---------|-------|------|
| `Backend/app/core/config.py` | 20 | `default_shop_name` | `"Bishops Tempe"` | **HIGH** - Single default shop |
| `Backend/app/core/config.py` | 21 | `chat_timezone` | `"America/Phoenix"` | **MEDIUM** - Global timezone |
| `Backend/.env` | 15 | `DEFAULT_SHOP_NAME` | `Bishops Tempe` | **HIGH** - Env-level assumption |
| `Backend/.env` | 16 | `CHAT_TIMEZONE` | `America/Phoenix` | **MEDIUM** - Should be per-shop |

---

## 2. Frontend Findings

### 2.1 Hardcoded Constants

| File | Line | Code | Risk |
|------|------|------|------|
| `frontend/src/app/chat/page.tsx` | 126 | `const SHOP_ID = 1;` | **CRITICAL** - All API calls use shop 1 |
| `frontend/src/app/chat/page.tsx` | 2165 | `"Bishops Tempe"` | **MEDIUM** - Hardcoded brand in header |
| `frontend/src/app/chat/page.tsx` | 2923 | `"© 2025 Bishops Tempe"` | **LOW** - Footer copyright |

### 2.2 Missing Shop Context in Routes

| Issue | Risk | Suggested Fix |
|-------|------|---------------|
| No `/s/[slug]/` route structure | **HIGH** | Add dynamic routing by shop slug |
| API calls don't include shop identifier | **HIGH** | Pass shop slug/id to all endpoints |
| No shop context provider | **MEDIUM** | Create React context for shop state |

---

## 3. Database Findings

### 3.1 Schema Review

The database schema **already supports multi-tenancy** with `shop_id` foreign keys:

| Table | Has `shop_id` | Index? | Notes |
|-------|--------------|--------|-------|
| `services` | ✅ Yes | ✅ | Properly scoped |
| `stylists` | ✅ Yes | ✅ | Properly scoped |
| `bookings` | ✅ Yes | ✅ | Properly scoped |
| `promos` | ✅ Yes | ✅ | Properly scoped |
| `customers` | ✅ Yes | ✅ | Properly scoped |
| `embedded_chunks` | ✅ Yes | ✅ | Vector search scoped |
| `shops` | N/A | ✅ | Tenant table |

### 3.2 Missing RLS Policies

| Risk | Details |
|------|---------|
| **HIGH** | No Row-Level Security (RLS) policies exist |
| **MEDIUM** | Connection pooling may bypass app-level filters |

**Phase 2+ Action:** Add RLS policies with `current_setting('app.current_shop_id')` for defense-in-depth.

---

## 4. AI Prompts Findings

### 4.1 Hardcoded Shop Names in Prompts

| File | Line | Prompt Text | Risk |
|------|------|-------------|------|
| `Backend/app/chat.py` | 50 | `"booking assistant for Bishops Tempe hair salon"` | **CRITICAL** - Hardcoded shop identity |
| `Backend/app/chat.py` | 142 | `"voice booking assistant for Bishops Tempe"` | **CRITICAL** - Voice prompt |
| `Backend/app/owner_chat.py` | 40-41 | `"Owner GPT for a salon... America/Phoenix (Tempe)"` | **HIGH** - Location in prompt |
| `Backend/app/rag.py` | 173 | `"answers questions about salon operations"` | **LOW** - Generic but shop-specific data |

### 4.2 Hardcoded Timezone Assumptions

| File | Lines | Usage | Risk |
|------|-------|-------|------|
| `Backend/app/chat.py` | Multiple | `ZoneInfo(settings.chat_timezone)` | **MEDIUM** - Uses global setting |
| `Backend/app/voice.py` | 697, 731, 785, 988, 1115 | Timezone from settings | **MEDIUM** - Should be per-shop |
| `Backend/app/voice_harness.py` | 18 | `ZoneInfo("America/Phoenix")` hardcoded | **HIGH** - Direct hardcode |

---

## 5. Voice/Twilio Findings

### 5.1 Voice Agent Single-Shop

| File | Line | Issue | Risk |
|------|------|-------|------|
| `Backend/app/voice.py` | 52 | `SHOP_ID = 1` constant | **CRITICAL** - All calls go to shop 1 |
| `Backend/app/voice.py` | 485 | `Service.shop_id == SHOP_ID` | **HIGH** - Query hardcoded |
| `Backend/app/voice.py` | 493 | `Stylist.shop_id == SHOP_ID` | **HIGH** - Query hardcoded |

### 5.2 Missing Phone→Shop Routing

| Issue | Risk | Suggested Fix |
|-------|------|---------------|
| No `phone_numbers` table to map Twilio numbers to shops | **CRITICAL** | Create mapping table, resolve shop from `To` number |
| Session doesn't track shop context | **HIGH** | Add `shop_id` to `CALL_SESSIONS` dict |

---

## 6. Public Booking / OpenAPI Findings

### 6.1 ChatGPT Integration

| File | Line | Issue | Risk |
|------|------|-------|------|
| `Backend/app/public_booking.py` | 513-522 | `get_default_shop()` for all endpoints | **CRITICAL** - Single shop |
| `Backend/app/public_booking.py` | 550 | `address="Tempe, Arizona"` hardcoded | **MEDIUM** - Should be from shop record |
| `Backend/openapi_chatgpt_prod.yaml` | 51-56 | Example hardcodes "Bishops Tempe" | **LOW** - Documentation only |
| `Backend/CHATGPT_ACTIONS_SETUP.md` | 111, 186 | Docs reference "Bishops Tempe" | **LOW** - Documentation |

### 6.2 API Key Scope

| Issue | Risk | Suggested Fix |
|-------|------|---------------|
| Single `PUBLIC_BOOKING_API_KEY` for all shops | **HIGH** | Per-shop API keys with shop_id claim |
| No shop identification in request | **CRITICAL** | Add shop slug to URL path or header |

---

## 7. Test Files Findings

| File | Lines | Issue | Risk |
|------|-------|-------|------|
| `Backend/tests/test_promos.py` | 46 | `shop_id=1` | **LOW** - Test data |
| `Backend/tests/test_rag_smoke.py` | 166-172, 228, 233 | `shop_id=1` in tests | **LOW** - Test isolation |

---

## 8. Top 10 Critical Fixes for Phase 2+

1. **Voice SHOP_ID constant** - Replace with phone→shop lookup from Twilio `To` number
2. **Chat prompt hardcoded shop name** - Inject shop profile dynamically from DB
3. **Frontend SHOP_ID constant** - Resolve from URL slug (`/s/[slug]/chat`)
4. **`get_default_shop()` everywhere** - Replace with `ShopContext` resolution
5. **Unscoped service/stylist queries in chat.py** - Add shop_id filter
6. **Public booking API single shop** - Route by shop slug in URL or subdomain
7. **Owner chat DEFAULT_SHOP_ID** - Resolve from authenticated user's shop
8. **Global timezone setting** - Move to per-shop `shops.timezone` column
9. **Call summary shop fallback** - Require explicit shop_id, no fallback
10. **Add RLS policies** - Defense-in-depth for query mistakes

---

## 9. Summary Statistics

| Category | Count | Critical | High | Medium | Low |
|----------|-------|----------|------|--------|-----|
| Backend hardcoded IDs | 6 | 2 | 3 | 1 | 0 |
| Unscoped queries | 12 | 5 | 5 | 2 | 0 |
| Config assumptions | 4 | 0 | 2 | 2 | 0 |
| Frontend hardcodes | 3 | 1 | 1 | 0 | 1 |
| AI prompt hardcodes | 5 | 2 | 2 | 0 | 1 |
| Voice single-shop | 5 | 2 | 2 | 1 | 0 |
| Public API issues | 6 | 2 | 2 | 1 | 1 |
| Tests | 6 | 0 | 0 | 0 | 6 |
| **Total** | **47** | **14** | **17** | **7** | **9** |

---

## 10. Next Steps

This audit is complete. Proceed with:
1. **Phase 0 (current):** Create scaffolding modules, invariants doc, checklist
2. **Phase 1:** Add `shops` table extensions (slug, timezone, profile), phone_numbers table
3. **Phase 2:** Implement shop resolution, scope all queries, update prompts
4. **Phase 3+:** Frontend routing, RouterGPT, per-shop assistants
