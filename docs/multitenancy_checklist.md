# Multi-Tenancy Implementation Checklist

> **Updated:** Phase 1 Complete (2026-01-21)  
> This checklist tracks what needs to be done in each phase.  
> Check boxes as items are completed during implementation.

---

## Database Checklist

### Schema Changes
- [x] Add `shop_id` column to all tenant-scoped tables *(Phase 1)*
- [x] Create index on `shop_id` for each table *(Phase 1)*
- [x] Add foreign key constraint to `shops` table *(Phase 1)*
- [x] Set `NOT NULL` constraint on `shop_id` (with default for migration) *(Phase 1)*

### Row-Level Security (RLS)
- [ ] Enable RLS on `services` table
- [ ] Enable RLS on `stylists` table  
- [ ] Enable RLS on `bookings` table
- [ ] Enable RLS on `customers` table
- [ ] Enable RLS on `promos` table
- [ ] Enable RLS on `chat_messages` table (if exists)
- [ ] Create policy: `shop_isolation_policy` for each table
- [ ] Test RLS with multiple shop contexts

### Shops Table
- [x] Create `shops` table with: `id`, `slug`, `name`, `timezone`, `phone_number` *(Phase 1)*
- [x] Add unique constraint on `slug` *(Phase 1)*
- [x] Add unique constraint on `phone_number` (for Twilio routing) *(Phase 1)*
- [x] Seed initial shop data (migrate existing to shop_id=1) *(Phase 1)*

### Vector Search
- [x] Add `shop_id` to `embedded_chunks` table *(Already existed - Migration 001)*
- [x] Update pgvector indexes to include `shop_id` filter *(Already existed)*
- [ ] Test vector search scoping

---

## API Checklist

### Shop-Scoped Routes
- [ ] Add `/s/{slug}` prefix pattern for public routes
- [ ] Update `/api/services` → `/api/s/{slug}/services`
- [ ] Update `/api/stylists` → `/api/s/{slug}/stylists`
- [ ] Update `/api/bookings` → `/api/s/{slug}/bookings`
- [ ] Update `/api/availability` → `/api/s/{slug}/availability`
- [ ] Keep `/api/promos` (requires shop context from auth/slug)

### Shop Context Resolution
- [ ] Implement `resolve_shop_from_slug()` in tenancy/context.py
- [ ] Implement `resolve_shop_from_twilio_to()` for voice/SMS
- [ ] Implement `resolve_shop_from_api_key()` for M2M auth
- [ ] Create FastAPI dependency: `get_shop_context()`
- [ ] Add ShopContext to all route handlers

### Query Scoping
- [ ] voice.py: Remove `SHOP_ID = 1`, use ShopContext
- [ ] chat.py: Add shop_id filter to all queries
- [ ] owner_chat.py: Remove `DEFAULT_SHOP_ID`, use auth context
- [ ] sms.py: Add shop resolution from To number
- [ ] rag.py: Scope vector search to shop
- [ ] customer_memory.py: Scope to shop_id + customer

### Authentication/Authorization
- [ ] Add `shop_id` claim to JWT tokens
- [ ] Validate shop access in auth middleware
- [ ] Owner routes: verify owner has access to shop
- [ ] Employee routes: verify employee belongs to shop

---

## Frontend Checklist

### URL Structure
- [ ] Migrate from `/chat` to `/s/[slug]/chat`
- [ ] Migrate from `/employee` to `/s/[slug]/employee`
- [ ] Update Next.js routing for `[slug]` dynamic segment
- [ ] Handle shop slug in all API calls

### Shop Context
- [ ] Remove hardcoded `SHOP_ID = 1` in page.tsx
- [ ] Create shop context provider
- [ ] Fetch shop data from `/registry/resolve?slug=...`
- [ ] Pass shop_id to all API calls

### Branding/Theming
- [ ] Load shop profile (name, logo, colors) dynamically
- [ ] Display shop name in header/title
- [ ] Support per-shop favicon (Phase 3+)

### Public Booking Widget
- [ ] Update widget to accept shop slug
- [ ] Embed code includes shop identifier
- [ ] Widget fetches shop-specific services/stylists

---

## AI Prompts Checklist

### Dynamic Shop Injection
- [ ] chat.py: Replace "Bishops Tempe" with `{shop_name}`
- [ ] chat.py: Replace static services with `{shop_services}`
- [ ] voice.py: Inject shop name into greeting
- [ ] voice.py: Inject shop-specific instructions

### Per-Shop Customization
- [ ] Store custom prompt fragments in DB (per shop)
- [ ] Support shop-specific personality/tone
- [ ] Support shop-specific booking rules
- [ ] Support shop-specific hours/timezone

### RAG Knowledge
- [ ] Scope knowledge_chunks by shop_id
- [ ] Support shop-specific FAQ entries
- [ ] Support shop-specific policy documents

---

## Voice/Twilio Checklist

### Phone Number Routing
- [ ] Map Twilio To number → shop_id in resolution
- [ ] Store phone→shop mapping in DB
- [ ] Handle multiple numbers per shop (future)

### Voice Agent
- [ ] Pass shop_id to all voice handler functions
- [ ] Scope service/stylist lookups to shop
- [ ] Log shop_id with all call records
- [ ] Shop-specific voice greeting

### SMS
- [ ] Route inbound SMS by To number
- [ ] Scope customer lookup to shop
- [ ] Scope promo lookups to shop

### Call Summaries
- [ ] Include shop_id in call summary records
- [ ] Scope summary queries to shop

---

## RouterGPT Checklist

> For future multi-model orchestration

### Context Flow
- [ ] ShopContext passed through entire pipeline
- [ ] search → summary → handoff preserves shop_id
- [ ] No cross-tenant data in context windows

### Intent Detection
- [ ] Shop-specific intent patterns
- [ ] Shop-specific entity recognition

### Model Selection
- [ ] Per-shop model preferences (future)
- [ ] Per-shop token limits

---

## Testing Checklist

### Unit Tests
- [ ] Test ShopContext creation and validation
- [ ] Test shop resolution from various sources
- [ ] Test query scoping helpers

### Integration Tests
- [ ] Test API routes with shop context
- [ ] Test voice calls with shop routing
- [ ] Test SMS with shop routing

### Multi-Tenant Tests
- [ ] Create test with 2+ shops
- [ ] Verify data isolation between shops
- [ ] Test that shop A cannot see shop B data
- [ ] Test RLS policies work correctly

### Load Tests
- [ ] Verify performance with multi-tenant queries
- [ ] Test vector search performance with shop filter

---

## Deployment Checklist

### Database Migration
- [ ] Create migration script for schema changes
- [ ] Run migration on staging first
- [ ] Backfill existing data with shop_id=1
- [ ] Enable RLS policies
- [ ] Verify data integrity

### Application Deployment
- [ ] Deploy backend with new tenancy code
- [ ] Verify existing shop still works (shop_id=1)
- [ ] Deploy frontend with slug routing
- [ ] Set up redirect: old URLs → new URLs

### Monitoring
- [ ] Add shop_id to all log entries
- [ ] Create per-shop usage dashboards
- [ ] Alert on cross-tenant query attempts
- [ ] Monitor RLS policy violations

---

## Phase Completion Gates

### Phase 1 Complete When:
- [ ] `shops` table created and seeded
- [ ] ShopContext dependency working in routes
- [ ] All queries include shop_id filter
- [ ] Tests pass for single shop

### Phase 2 Complete When:
- [ ] Frontend uses `/s/[slug]` routing
- [ ] Voice/SMS routes by phone number
- [ ] AI prompts are dynamic per shop
- [ ] Second test shop can be created

### Phase 3 Complete When:
- [ ] Admin UI for shop management
- [ ] Self-service shop onboarding
- [ ] Per-shop billing hooks ready

---

## Quick Reference

### Key Files to Modify
| File | Change Needed |
|------|---------------|
| `voice.py:52` | Remove `SHOP_ID = 1` |
| `owner_chat.py:228` | Remove `DEFAULT_SHOP_ID = 1` |
| `chat.py:50` | Replace "Bishops Tempe" |
| `chat/page.tsx:126` | Remove `const SHOP_ID = 1` |
| `main.py:825` | Update `get_default_shop()` |

### New Files Added (Phase 0)
- `Backend/app/tenancy/__init__.py`
- `Backend/app/tenancy/context.py`
- `Backend/app/tenancy/config.py`
- `Backend/app/registry.py`
- `docs/multitenancy_phase0_audit.md`
- `docs/multitenancy_invariants.md`
- `docs/multitenancy_checklist.md`
- `scripts/check_tenant_scoping.py`

---

*Last updated: Phase 0*  
*Next phase: Phase 1 - Add ShopContext to all routes*
