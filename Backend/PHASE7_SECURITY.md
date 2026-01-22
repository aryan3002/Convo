# Phase 7: Security & Audit Logging

## Overview

Phase 7 adds production-grade security to multi-tenant operations:

- **Authentication**: Identity extraction via `X-User-Id` header (temporary, before Clerk/JWT)
- **Authorization (RBAC)**: Role-based access using `shop_members` table
- **Audit Logging**: Track all security-relevant actions
- **Tenant Enforcement**: Helpers to prevent cross-tenant data access

## Quick Start

### 1. Apply Migration

```bash
# Against test database
psql -d convo_test -f Backend/migrations/005_phase7_audit_logs.sql

# OR using Makefile
export DATABASE_URL="postgresql+asyncpg://localhost:5432/convo_test"
make init-test-db  # Also initializes audit_logs via SQLAlchemy
```

### 2. Run Phase 7 Tests

```bash
export DATABASE_URL="postgresql+asyncpg://localhost:5432/convo_test"
cd Backend
pytest tests/test_phase7_security.py -v
```

---

## Authentication

### Current Implementation (Phase 7)

Identity is extracted from the `X-User-Id` header:

```bash
curl -X POST http://localhost:8000/s/bishops-tempe/owner/chat \
  -H "Content-Type: application/json" \
  -H "X-User-Id: user_abc123" \
  -d '{"messages": [{"role": "user", "content": "Show services"}]}'
```

**Responses:**
- Missing/empty header → `401 Unauthorized`
- User not a shop member → `403 Forbidden`
- User has wrong role → `403 Forbidden`
- User authorized → `200 OK`

### Future: Clerk/JWT Integration

When Clerk is integrated, replace `X-User-Id` header with JWT:

```bash
curl -X POST http://localhost:8000/s/bishops-tempe/owner/chat \
  -H "Authorization: Bearer eyJhbGciOi..." \
  -d '...'
```

The `get_current_user_id()` dependency will be updated to:
1. Extract JWT from `Authorization` header
2. Verify signature with Clerk public key
3. Extract `user_id` from claims

---

## Role-Based Access Control (RBAC)

### Role Matrix

| Role | Owner Chat | Services | Stylists | Customer Chat | Shop Info |
|------|------------|----------|----------|---------------|-----------|
| **OWNER** | ✅ | ✅ | ✅ | N/A | ✅ |
| **MANAGER** | ✅ | ✅ | ✅ | N/A | ✅ |
| **EMPLOYEE** | ❌ | ✅ (view) | ✅ (view) | N/A | ✅ |
| **Public** | ❌ | ✅ (view) | ✅ (view) | ✅ | ✅ |

### Roles

| Role | Description | Typical Permissions |
|------|-------------|---------------------|
| `OWNER` | Shop owner/founder | Full access, billing, delete shop |
| `MANAGER` | Trusted staff | Manage services, schedule, employees |
| `EMPLOYEE` | Regular staff | View-only, update own schedule |

### RBAC Dependencies

```python
from app.auth import (
    get_current_user_id,      # Extract user from X-User-Id header
    require_owner,            # OWNER only
    require_owner_or_manager, # OWNER or MANAGER
    require_any_member,       # OWNER, MANAGER, or EMPLOYEE
)

# Example usage in endpoint
@router.post("/s/{slug}/owner/chat")
async def owner_chat(
    ctx: ShopContext = Depends(get_shop_context_from_slug),
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    # Verify role
    await require_owner_or_manager(ctx, user_id, session)
    
    # User is authorized, proceed
    ...
```

---

## Audit Logging

### Schema

```sql
CREATE TABLE audit_logs (
    id SERIAL PRIMARY KEY,
    shop_id INTEGER REFERENCES shops(id) ON DELETE SET NULL,
    actor_user_id VARCHAR(255) NOT NULL,
    action VARCHAR(100) NOT NULL,
    target_type VARCHAR(50),
    target_id VARCHAR(100),
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_audit_logs_shop_id ON audit_logs(shop_id);
CREATE INDEX idx_audit_logs_actor_user_id ON audit_logs(actor_user_id);
CREATE INDEX idx_audit_logs_created_at ON audit_logs(created_at DESC);
CREATE INDEX idx_audit_logs_action ON audit_logs(action);
```

### Actions Logged

| Action | Trigger | Target Type |
|--------|---------|-------------|
| `shop.created` | POST /shops | shop |
| `owner.chat` | POST /s/{slug}/owner/chat | shop |

**Future actions (not yet implemented):**
- `booking.created`, `booking.confirmed`, `booking.cancelled`
- `service.created`, `service.updated`, `service.deleted`
- `member.added`, `member.role_changed`, `member.removed`

### Example Audit Log Entry

```json
{
  "id": 42,
  "shop_id": 5,
  "actor_user_id": "user_abc123",
  "action": "shop.created",
  "target_type": "shop",
  "target_id": "5",
  "metadata": {
    "slug": "awesome-cuts",
    "name": "Awesome Cuts",
    "category": "barbershop",
    "timezone": "America/New_York"
  },
  "created_at": "2026-01-21T10:30:00Z"
}
```

### PII Policy

**IMPORTANT**: Audit logs MUST NOT contain PII (personally identifiable information) in the `metadata` field unless absolutely required for compliance.

**DO NOT log:**
- Phone numbers
- Email addresses
- Customer names
- Payment details

**OK to log:**
- Shop slugs, names, IDs
- Service names, IDs
- User IDs (from auth provider)
- Action types and timestamps

### Querying Audit Logs

```sql
-- Recent activity for a shop
SELECT * FROM audit_logs 
WHERE shop_id = 5 
ORDER BY created_at DESC 
LIMIT 50;

-- All actions by a user
SELECT * FROM audit_logs 
WHERE actor_user_id = 'user_abc123'
ORDER BY created_at DESC;

-- All shop creations in last 24 hours
SELECT * FROM audit_logs 
WHERE action = 'shop.created' 
  AND created_at > NOW() - INTERVAL '24 hours';
```

---

## Tenant Enforcement

### Helper: `assert_shop_scoped_row`

Use before updating/deleting any tenant-scoped row:

```python
from app.auth import assert_shop_scoped_row

# When updating a booking
booking = await get_booking(session, booking_id)
assert_shop_scoped_row(booking.shop_id, ctx.shop_id)
# Now safe to update
```

If shop IDs don't match, raises `403 Forbidden`.

### Rule: Always Use Context

When creating records for tenant tables, **always** set `shop_id` from context, never from request:

```python
# ❌ WRONG - shop_id from request
new_service = Service(
    shop_id=request.shop_id,  # NEVER DO THIS
    name=request.name,
)

# ✅ CORRECT - shop_id from context
new_service = Service(
    shop_id=ctx.shop_id,  # Always from ShopContext
    name=request.name,
)
```

---

## Protected vs Public Endpoints

### Protected Endpoints (require auth)

| Endpoint | Required Role | Header |
|----------|---------------|--------|
| `POST /s/{slug}/owner/chat` | OWNER, MANAGER | `X-User-Id` |

### Public Endpoints (no auth required)

| Endpoint | Description |
|----------|-------------|
| `POST /shops` | Create new shop (onboarding) |
| `GET /shops/{slug}` | Get shop info (registry) |
| `POST /s/{slug}/chat` | Customer chat |
| `GET /s/{slug}/services` | List services |
| `GET /s/{slug}/stylists` | List stylists |
| `GET /s/{slug}/info` | Shop info |

---

## Testing

### Run All Phase 7 Tests

```bash
export DATABASE_URL="postgresql+asyncpg://localhost:5432/convo_test"
cd Backend
pytest tests/test_phase7_security.py -v
```

### Expected Test Coverage

1. **Authentication Tests**
   - Missing X-User-Id → 401
   - Empty X-User-Id → 401
   - Whitespace X-User-Id → 401

2. **Authorization Tests**
   - Non-member user → 403
   - EMPLOYEE role on owner endpoint → 403
   - OWNER role → 200 (auth passes)
   - MANAGER role → 200 (auth passes)

3. **Audit Logging Tests**
   - POST /shops creates audit log
   - owner/chat creates audit log

4. **Tenant Enforcement Tests**
   - Public endpoints remain public
   - assert_shop_scoped_row works

---

## curl Examples

### 1. Unauthorized (no header)

```bash
curl -X POST http://localhost:8000/s/bishops-tempe/owner/chat \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "Show services"}]}'
```

**Response:**
```json
{
  "detail": "Authentication required. Provide X-User-Id header."
}
```
**Status:** `401 Unauthorized`

---

### 2. Forbidden (not a member)

```bash
curl -X POST http://localhost:8000/s/bishops-tempe/owner/chat \
  -H "Content-Type: application/json" \
  -H "X-User-Id: random_user_not_a_member" \
  -d '{"messages": [{"role": "user", "content": "Show services"}]}'
```

**Response:**
```json
{
  "detail": "Access denied. You are not a member of Bishops Tempe."
}
```
**Status:** `403 Forbidden`

---

### 3. Allowed (OWNER membership)

First, ensure user is an OWNER member:

```sql
INSERT INTO shop_members (shop_id, user_id, role) 
SELECT id, 'my_owner_user', 'OWNER' FROM shops WHERE slug = 'bishops-tempe'
ON CONFLICT (shop_id, user_id) DO NOTHING;
```

Then call:

```bash
curl -X POST http://localhost:8000/s/bishops-tempe/owner/chat \
  -H "Content-Type: application/json" \
  -H "X-User-Id: my_owner_user" \
  -d '{"messages": [{"role": "user", "content": "Show services"}]}'
```

**Response:** `200 OK` with AI response

---

## File Structure

```
Backend/
├── app/
│   ├── auth.py                    # NEW: Auth + RBAC + audit helpers
│   ├── models.py                  # UPDATED: AuditLog model added
│   ├── onboarding.py              # UPDATED: Audit logging on shop.created
│   └── routes_scoped.py           # UPDATED: Owner route protection
├── migrations/
│   └── 005_phase7_audit_logs.sql  # NEW: Audit logs table
└── tests/
    └── test_phase7_security.py    # NEW: Security tests
```

---

## Troubleshooting

### "Authentication required" but I sent X-User-Id

Check header case sensitivity. Use exactly `X-User-Id`:
```bash
-H "X-User-Id: my_user"  # ✅ Correct
-H "x-user-id: my_user"  # ✅ Also works (FastAPI is case-insensitive)
-H "X-USER-ID: my_user"  # ✅ Also works
```

### "Not a member" but I just created the shop

The user ID must exactly match. Check:
```sql
SELECT user_id FROM shop_members WHERE shop_id = (
  SELECT id FROM shops WHERE slug = 'your-slug'
);
```

### Tests fail with "audit_logs does not exist"

Apply the migration:
```bash
psql -d convo_test -f Backend/migrations/005_phase7_audit_logs.sql
```

Or re-initialize:
```bash
make init-test-db
```

### Server fails with "type vector does not exist"

The application uses pgvector for RAG features. For local testing:
1. Install pgvector: `brew install pgvector`
2. Enable it: `psql convo_test -c "CREATE EXTENSION IF NOT EXISTS vector;"`

Or run against the Neon production database which has pgvector enabled.

For Phase 7 tests specifically, pgvector is not required (tests run without starting the full server).

---

## Security Checklist

- [x] All shop-scoped endpoints have resolved ShopContext
- [x] Owner operations require shop membership (OWNER/MANAGER)
- [x] No endpoint accepts raw shop_id from client (slug/context only)
- [x] RouterGPT remains discovery-only (no write operations)
- [x] Audit logs track shop creation and owner chat
- [x] PII excluded from audit metadata
- [x] Public endpoints (onboarding, customer chat) remain public
