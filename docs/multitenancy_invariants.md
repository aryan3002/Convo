# Multi-Tenancy Invariants

**Version:** 1.0  
**Created:** 2026-01-21  
**Status:** Phase 0 (Non-negotiable rules defined, not yet enforced)

---

## Overview

This document defines the **non-negotiable rules** for multi-tenancy in Convo. These invariants must be maintained across all code changes once multi-tenancy is fully implemented.

We are adopting **Option A: Shared Database with Tenant Isolation by `shop_id`**.

---

## 1. Data Isolation Invariants

### INV-1: Every tenant-owned row MUST have `shop_id`

```
All tables containing tenant-specific data MUST include:
- shop_id INTEGER NOT NULL REFERENCES shops(id) ON DELETE CASCADE
- Index on shop_id (composite indexes preferred)
```

**Tenant-owned tables:**
- `services`
- `stylists`
- `bookings`
- `customers`
- `promos`
- `promo_impressions`
- `embedded_chunks`
- `call_transcripts` (future)
- `stylist_specialties`
- `preferred_styles`

**Exception:** The `shops` table itself is the tenant registry.

### INV-2: Every tenant-owned query MUST filter by `shop_id`

```sql
-- CORRECT
SELECT * FROM services WHERE shop_id = :shop_id AND ...

-- INCORRECT (NEVER DO THIS)
SELECT * FROM services WHERE name = :name  -- Missing shop_id!
```

**Enforcement:**
- Application-level: All repository functions require `shop_id` parameter
- Database-level: Row-Level Security (RLS) policies as defense-in-depth
- CI-level: Lint script scans for unscoped queries

### INV-3: Shop context MUST be resolved server-side from trusted inputs

**Trusted resolution sources (in order of preference):**

| Source | Use Case | Example |
|--------|----------|---------|
| URL slug | Web app routes | `/s/bishops-tempe/chat` → shop_id=1 |
| Auth token claim | Authenticated APIs | JWT `shop_id` claim from owner login |
| Twilio `To` number | Voice calls | `+16234048440` → shop_id=1 via `phone_numbers` table |
| API key lookup | ChatGPT/external | API key → shop_id mapping |
| Subdomain | Future | `bishops-tempe.convo.ai` → shop_id=1 |

**NEVER trust:**
- Client-provided `shop_id` in request body
- Query parameters like `?shop_id=1`
- Headers that can be spoofed (unless signed/verified)

### INV-4: Cross-tenant access is FORBIDDEN

```
A request with ShopContext(shop_id=1) MUST NOT:
- Read data from shop_id=2
- Write data to shop_id=2
- See that shop_id=2 exists (information leak)
```

**Exception:** Super-admin/platform operations (Phase 6+).

---

## 2. Frontend Invariants

### INV-5: Frontend MUST NOT hardcode shop identifiers

```typescript
// FORBIDDEN
const SHOP_ID = 1;

// REQUIRED (Phase 2+)
const shopSlug = useParams().slug;  // From URL /s/[slug]/...
const { shopId } = useShopContext();  // From React context
```

### INV-6: Frontend routes MUST include shop context

**Target URL structure:**
```
/s/[slug]/chat      - Customer chat
/s/[slug]/book      - Public booking
/o/[slug]/dashboard - Owner dashboard
/o/[slug]/settings  - Owner settings
```

**Current (temporary):** Root routes (`/chat`, `/owner`) will continue working for shop_id=1 during migration.

---

## 3. Backend Invariants

### INV-7: ShopContext MUST be established before any tenant operation

```python
# Every endpoint that accesses tenant data:
async def endpoint(
    request: Request,
    ctx: ShopContext = Depends(get_shop_context),  # Resolved from URL/auth
    session: AsyncSession = Depends(get_session),
):
    # ctx.shop_id is now guaranteed
    services = await get_services(session, shop_id=ctx.shop_id)
```

### INV-8: AI prompts MUST inject shop profile dynamically

```python
# FORBIDDEN
prompt = "You are a booking assistant for Bishops Tempe..."

# REQUIRED
shop = await get_shop(session, ctx.shop_id)
prompt = f"You are a booking assistant for {shop.name} in {shop.address}..."
```

**Shop profile includes:**
- `name` - Business name
- `timezone` - IANA timezone string
- `address` - Location string
- `phone` - Contact phone
- `working_hours_start/end` - Operating hours
- `working_days` - Days open (bitmask or list)
- `brand_voice` - Optional prompt customization

---

## 4. Voice/Twilio Invariants

### INV-9: Voice calls MUST resolve shop from `To` phone number

```python
# Twilio webhook provides: To=+16234048440
shop_id = await resolve_shop_from_phone(session, request.form["To"])
if not shop_id:
    # Return generic "number not configured" response
```

**Requires:** `phone_numbers` table mapping Twilio numbers to shops.

### INV-10: Call sessions MUST track shop context

```python
CALL_SESSIONS[call_sid] = {
    "shop_id": shop_id,  # REQUIRED - set at call start
    "stage": Stage.GET_IDENTITY,
    ...
}
```

---

## 5. RouterGPT Invariants (Phase 4+)

### INV-11: RouterGPT only routes; per-shop assistants execute

```
User: "Book me a haircut at the Phoenix location"
                ↓
         [RouterGPT]
    - Understands request
    - Searches shop registry
    - Returns: shop_slug="bishops-tempe"
                ↓
         [Handoff to per-shop assistant]
    - ShopContext(shop_id=1) established
    - Booking flow executes with shop isolation
```

**RouterGPT MUST NOT:**
- Access tenant data directly
- Execute bookings
- See cross-tenant information

### INV-12: Shop search returns only public metadata

```python
# RouterGPT shop search returns:
{
    "slug": "bishops-tempe",
    "name": "Bishops Tempe",
    "city": "Tempe",
    "state": "AZ",
    "services_summary": "Haircuts, Beard Trims, ...",
}
# NOT internal IDs, prices, or customer data
```

---

## 6. Definition of Done

### Phase 1: Schema & Foundation
- [ ] `shops` table extended with: `slug`, `timezone`, `address`, `phone`, `brand_voice`
- [ ] `phone_numbers` table created: `phone_number` → `shop_id` mapping
- [ ] Unique index on `shops.slug`
- [ ] Migration scripts tested on staging
- [ ] No runtime behavior changes yet

### Phase 2: Query Scoping & Context Resolution
- [ ] `ShopContext` dataclass enforced on all tenant endpoints
- [ ] All 12 unscoped queries from audit fixed
- [ ] `get_default_shop()` replaced with proper resolution
- [ ] Frontend routes migrated to `/s/[slug]/...`
- [ ] AI prompts dynamically inject shop profile
- [ ] Voice agent resolves shop from `To` number
- [ ] Lint script passes with 0 warnings
- [ ] E2E tests verify tenant isolation

### Phase 3: External Integrations
- [ ] ChatGPT public API routes by shop slug
- [ ] Per-shop API keys implemented
- [ ] Webhook signatures validated

### Phase 4: RouterGPT
- [ ] RouterGPT searches shop registry
- [ ] Handoff protocol to per-shop assistants defined
- [ ] Cross-tenant access blocked at API level

### Phase 5: RLS & Security Hardening
- [ ] RLS policies on all tenant tables
- [ ] Audit logging for cross-tenant access attempts
- [ ] Penetration testing completed

### Phase 6: Admin & Platform
- [ ] Super-admin can view/manage all shops
- [ ] Shop onboarding flow
- [ ] Billing integration per shop

---

## 7. Verification Checklist

Before any PR is merged, verify:

```markdown
- [ ] No new hardcoded shop_id values introduced
- [ ] All new queries include shop_id filter
- [ ] New endpoints establish ShopContext
- [ ] New AI prompts use dynamic shop profile
- [ ] Lint script (`scripts/check_tenant_scoping.py`) passes
- [ ] No cross-tenant test failures
```

---

## 8. Glossary

| Term | Definition |
|------|------------|
| **Tenant** | A shop/business using the Convo platform |
| **ShopContext** | Runtime object containing resolved `shop_id`, `slug`, and resolution `source` |
| **Resolution** | Process of determining `shop_id` from trusted input |
| **RLS** | Row-Level Security - database-level tenant isolation |
| **RouterGPT** | AI layer that routes users to correct shop assistant |
| **Slug** | URL-safe unique identifier for shop (e.g., `bishops-tempe`) |
