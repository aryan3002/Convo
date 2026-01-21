# ADR-0001: Customer Tenancy Model

**Status:** Accepted  
**Date:** 2026-01-21  
**Decision Makers:** Backend Team  
**Context:** Phase 1 Multi-Tenancy Database Foundation

---

## Context

As we prepare the database for multi-tenancy, we must decide how to model customers across shops. This is a critical decision because:

1. Customers book appointments and have preferences (stylist, service)
2. Customer history/stats are used for personalization
3. The same person (email/phone) could book at multiple shops
4. Current model has **no shop_id** on `customers` table

### Current State Analysis

The existing `Customer` model:
```python
class Customer(Base):
    __tablename__ = "customers"
    
    id: int (PK)
    email: str (UNIQUE, indexed)  # Global uniqueness!
    phone: str | None (indexed)
    name: str | None
    preferred_stylist_id: FK -> stylists.id  # Cross-shop risk
    average_spend_cents: int
    no_show_count: int
    created_at, updated_at
```

Related tables:
- `customer_booking_stats`: customer_id (PK) - aggregated stats, no shop_id
- `customer_stylist_preferences`: customer_id + stylist_id - booking counts per stylist
- `customer_service_preferences`: customer_id + service_id - style preferences

### Key Observations

1. **Email is globally unique** - `unique=True` constraint on `customers.email`
2. **No shop_id anywhere** in customer-related tables
3. **preferred_stylist_id** references a stylist, but stylists are shop-scoped
4. **customer_memory.py** lookups by email/phone are global (no shop filter)
5. **Bookings** have customer info denormalized (customer_name, customer_email, customer_phone)

---

## Decision

### Chosen: **Option A - Customers Remain Global, Add Shop Profiles**

We will adopt a **hybrid model**:

1. **`customers` table stays global** - email remains unique across all shops
2. **New `customer_shop_profiles` table** - per-shop preferences and stats
3. **Migrate existing stats/preferences** to be shop-scoped in profiles
4. **Keep `customer_booking_stats` temporarily** - deprecate in Phase 3

### Rationale

| Factor | Option A (Per-Shop) | Option B (Global + Profiles) ✓ |
|--------|---------------------|--------------------------------|
| Email uniqueness | Break unique constraint or allow dups | Keep natural identity |
| Cross-shop repeat customer | Treated as different person | Recognized, shop-specific prefs |
| Migration effort | Add shop_id to customers, massive backfill | Add new profile table, gradual migration |
| Future "login once, book anywhere" | Impossible | Straightforward |
| Code changes | Moderate (add shop filter everywhere) | Lower (new table, existing code works) |

**Why Global Customers?**

1. **Natural identity** - A person's email/phone is globally unique in reality
2. **Cross-shop recognition** - If Convo expands, same user can book at multiple shops
3. **Minimal disruption** - Current code that finds customers by email/phone still works
4. **Future-proof** - Enables "Convo account" where users see all their bookings

---

## Implementation Plan

### Phase 1 (This Phase) - Foundation Only

**DO:**
- Create `customer_shop_profiles` table with:
  - `customer_id` FK
  - `shop_id` FK
  - `preferred_stylist_id` (moved from customers)
  - `total_bookings`, `total_spend_cents`, `last_booking_at`
  - `no_show_count`
  - Composite PK or unique constraint on (customer_id, shop_id)

- Keep `customers` table unchanged (no shop_id added)
- Keep `customer_booking_stats` for now (deprecated, to be removed Phase 3)
- Backfill existing data to `customer_shop_profiles` for shop_id=1

**DO NOT:**
- Change customer lookup code (Phase 2)
- Remove customer_booking_stats (Phase 3)
- Add shop_id to customers table (never needed)

### Phase 2 - Code Migration

- Update `customer_memory.py` to write to `customer_shop_profiles`
- Update stats/preference queries to use shop context
- Deprecate direct access to `customer_booking_stats`

### Phase 3 - Cleanup

- Drop `customer_booking_stats` table after data verified in profiles
- Remove `preferred_stylist_id` from `customers` (now in profiles)
- Remove `average_spend_cents`, `no_show_count` from `customers` (in profiles)

---

## Schema Design

### New Table: `customer_shop_profiles`

```sql
CREATE TABLE customer_shop_profiles (
    id SERIAL PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    shop_id INTEGER NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
    
    -- Moved from customers table (shop-specific)
    preferred_stylist_id INTEGER REFERENCES stylists(id) ON DELETE SET NULL,
    
    -- Moved from customer_booking_stats (shop-specific)
    total_bookings INTEGER NOT NULL DEFAULT 0,
    total_spend_cents INTEGER NOT NULL DEFAULT 0,
    last_booking_at TIMESTAMPTZ,
    no_show_count INTEGER NOT NULL DEFAULT 0,
    
    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    CONSTRAINT uq_customer_shop_profile UNIQUE (customer_id, shop_id)
);

CREATE INDEX idx_customer_shop_profiles_shop ON customer_shop_profiles(shop_id);
CREATE INDEX idx_customer_shop_profiles_customer ON customer_shop_profiles(customer_id);
```

### Migration Strategy

```sql
-- Step 1: Create table (Phase 1)
-- Step 2: Backfill for existing shop_id=1
INSERT INTO customer_shop_profiles (customer_id, shop_id, preferred_stylist_id, 
    total_bookings, total_spend_cents, last_booking_at, no_show_count)
SELECT 
    c.id,
    1 AS shop_id,
    c.preferred_stylist_id,
    COALESCE(s.total_bookings, 0),
    COALESCE(s.total_spend_cents, 0),
    s.last_booking_at,
    c.no_show_count
FROM customers c
LEFT JOIN customer_booking_stats s ON s.customer_id = c.id
ON CONFLICT (customer_id, shop_id) DO NOTHING;
```

---

## Impacts

### Tables Affected
- `customers` - NO CHANGE (stays global)
- `customer_booking_stats` - DEPRECATED (keep for now, remove Phase 3)
- `customer_stylist_preferences` - Keep as-is (stylist already shop-scoped via FK)
- `customer_service_preferences` - Keep as-is (service already shop-scoped via FK)

### Code Paths Affected (Phase 2)
- `customer_memory.py` - Write to profiles, read from profiles for shop context
- `chat.py` - Use shop-scoped customer context
- `voice.py` - Use shop-scoped customer context
- Booking confirmation flows - Update correct shop profile

### No Impact (Phase 1)
- All existing queries continue to work
- `get_customer_by_email/phone` still returns global customer
- Stats still aggregated in `customer_booking_stats` (until Phase 2 code changes)

---

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Orphaned profile rows | ON DELETE CASCADE on both FKs |
| Preferred stylist cross-shop | FK to stylists validates shop match at insert |
| Duplicate stats during transition | Phase 2 code writes to both, Phase 3 removes old |
| Query performance | Indexes on (shop_id), (customer_id), unique on (customer_id, shop_id) |

---

## Alternatives Considered

### Option A: Per-Shop Customers (Rejected)

Add `shop_id` to `customers` table, make email unique per shop.

**Pros:**
- Simpler model conceptually
- All customer data isolated per shop

**Cons:**
- Breaks current unique constraint on email
- Same person is different customer at each shop (bad UX long-term)
- Requires massive code changes to add shop_id filter everywhere
- No path to "Convo account" feature

### Option C: Fully Normalize Everything (Rejected)

Create separate tables for every shop-specific attribute.

**Pros:**
- Maximum flexibility

**Cons:**
- Over-engineering for current scale
- Many joins for simple queries
- Phase 1 scope explosion

---

## Decision Outcome

**Accept Option B (Global Customers + Shop Profiles)**

This gives us:
1. ✅ Clean tenant isolation for shop-specific data
2. ✅ Minimal disruption to existing code paths
3. ✅ Future-proof for cross-shop customer recognition
4. ✅ Incremental migration (Phase 1 adds table, Phase 2 uses it, Phase 3 cleans up)

---

*Last Updated: 2026-01-21 - Phase 1 Planning*
