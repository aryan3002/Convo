# Frontend Onboarding Flow

This document describes the new multi-tenant owner onboarding flow for the Convo frontend.

## Overview

The frontend now supports shop-scoped owner dashboards with proper authentication:

| Route | Purpose |
|-------|---------|
| `/onboarding` | New shop creation form |
| `/s/[slug]/owner` | Shop-scoped owner dashboard |
| `/owner-landing` | Landing page with shop selector |
| `/owner` | Legacy demo dashboard (not shop-scoped) |

## Quick Start

### 1. Start the Backend

```bash
cd Backend
source venv/bin/activate  # or create one: python -m venv venv
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 2. Start the Frontend

```bash
cd frontend
npm install
npm run dev
```

### 3. Create Your First Shop

1. Open http://localhost:3000/onboarding
2. Enter your Owner ID (e.g., `owner-abc-123`)
3. Enter Shop Name (e.g., `Classic Cuts Barbershop`)
4. Optionally fill in phone, timezone, address, category
5. Click **Create Shop**
6. You'll be redirected to `/s/classic-cuts-barbershop/owner`

### 4. Access Your Shop Dashboard

Once created, access your shop at:
```
http://localhost:3000/s/{your-shop-slug}/owner
```

## Architecture

### API Helper Library

Located at `frontend/src/lib/api.ts`, provides:

```typescript
// Configuration
getApiBase(): string

// Shop endpoints
createShop(payload: CreateShopPayload): Promise<Shop>
getShopBySlug(slug: string): Promise<Shop>

// Shop-scoped endpoints
getServices(slug: string): Promise<Service[]>
getStylists(slug: string): Promise<Stylist[]>
ownerChat(slug: string, messages: OwnerMessage[], userId: string): Promise<OwnerChatResponse>

// Error handling
isApiError(err: unknown): err is ApiError
getErrorMessage(err: unknown): string

// Storage
getStoredUserId(): string | null
setStoredUserId(userId: string): void
clearStoredUserId(): void
```

### Environment Variables

Set in `.env.local`:

```bash
NEXT_PUBLIC_API_BASE=http://localhost:8000
```

If not set, defaults to `http://localhost:8000`.

## Routes

### `/onboarding`

**File:** `src/app/onboarding/page.tsx`

Shop creation form with:
- Owner ID (required) - unique identifier for the owner
- Shop Name (required) - creates URL slug automatically
- Phone (optional)
- Timezone (optional) - defaults to America/Los_Angeles
- Address (optional)
- Category (optional) - barbershop, salon, spa, etc.

On success:
1. Stores owner_user_id in localStorage
2. Redirects to `/s/{slug}/owner`

Handles errors:
- 409 Conflict: Shop name already exists
- 422 Validation: Invalid input fields

### `/s/[slug]/owner`

**File:** `src/app/s/[slug]/owner/page.tsx`

Shop-scoped owner dashboard with:
- Shop info display
- AI chat interface (via `/s/{slug}/owner/chat`)
- Services list (via `/s/{slug}/services`)
- Stylists list (via `/s/{slug}/stylists`)
- Auth error handling (401/403)

Requires:
- Valid shop slug in URL
- Owner ID stored in localStorage (prompts if missing)

### `/owner-landing`

**File:** `src/app/owner-landing/page.tsx`

Landing page with:
- Create new shop button → `/onboarding`
- Shop slug input → `/s/{slug}/owner`
- Feature highlights

### `/owner` (Legacy)

**File:** `src/app/owner/page.tsx`

Original demo dashboard (3200+ lines). Not shop-scoped - uses global endpoints. Kept for reference/demo purposes.

## Authentication Flow

1. **Onboarding:** User enters Owner ID, stored in localStorage
2. **Dashboard Access:** Owner ID read from localStorage
3. **API Calls:** Owner ID sent as `X-User-Id` header
4. **Error Handling:**
   - 401: Session expired, re-prompt for Owner ID
   - 403: Not shop owner, show permission error
5. **Logout:** Clears localStorage, redirects to `/onboarding`

## UI Components Used

The onboarding flow reuses existing UI patterns:

| Component | Usage |
|-----------|-------|
| `glass-card` | Main card containers |
| `input-glass` | Form inputs |
| `btn-neon` | Primary action buttons |
| `glass` | Secondary elements |
| Framer Motion | Animations |
| Lucide icons | Icons throughout |

### Color Palette

```css
--neon-blue: #00d4ff
--neon-purple: #a855f7
--neon-pink: #ec4899
--neon-mint: #34d399
--background: #0a0e1a
--card: #0f1629
```

## Error States

The dashboard handles these scenarios gracefully:

1. **Shop Not Found (404)**
   - Shows error card with "Shop Not Found"
   - Links to create shop or go to landing

2. **Unauthorized (401)**
   - Shows banner prompting for Owner ID
   - Clears stale session data

3. **Forbidden (403)**
   - Shows "Permission Denied" message
   - Explains user is not the shop owner

4. **Conflict (409)**
   - Shows "Shop name already exists"
   - User can try different name

## Testing the Flow

### Manual Testing

1. **Happy Path:**
   ```
   /onboarding → fill form → submit → /s/{slug}/owner
   ```

2. **Duplicate Shop:**
   ```
   /onboarding → same name → see error → change name → success
   ```

3. **Invalid Shop Slug:**
   ```
   /s/nonexistent-shop/owner → see "Shop Not Found" → redirect options
   ```

4. **Missing Owner ID:**
   ```
   Clear localStorage → /s/{slug}/owner → see login prompt
   ```

### API Verification

```bash
# Create shop
curl -X POST http://localhost:8000/shops \
  -H "Content-Type: application/json" \
  -d '{"owner_user_id": "test-owner", "name": "Test Shop"}'

# Get shop
curl http://localhost:8000/shops/test-shop

# Get services (shop-scoped)
curl http://localhost:8000/s/test-shop/services

# Owner chat (requires auth)
curl -X POST http://localhost:8000/s/test-shop/owner/chat \
  -H "Content-Type: application/json" \
  -H "X-User-Id: test-owner" \
  -d '{"messages": [{"role": "user", "content": "Show my services"}]}'
```

## File Structure

```
frontend/src/
├── lib/
│   └── api.ts                    # API helpers
├── app/
│   ├── onboarding/
│   │   └── page.tsx              # Onboarding form
│   ├── owner-landing/
│   │   └── page.tsx              # Landing page
│   ├── owner/
│   │   └── page.tsx              # Legacy dashboard
│   └── s/
│       └── [slug]/
│           └── owner/
│               └── page.tsx      # Shop-scoped dashboard
└── components/
    └── ui/
        ├── button.tsx
        ├── card.tsx
        └── input.tsx
```

## Related Backend Docs

- [MULTI_TENANT_SETUP.md](../Backend/MULTI_TENANT_SETUP.md) - Phase 4-7 backend setup
- [Backend README](../Backend/README.md) - General backend docs

## Troubleshooting

### "Failed to fetch" errors

1. Check backend is running: `curl http://localhost:8000/health`
2. Check CORS: Backend should allow `http://localhost:3000`
3. Check env var: `NEXT_PUBLIC_API_BASE` should match backend URL

### Shop creation fails silently

1. Open browser DevTools → Network tab
2. Check the POST /shops response
3. Look for validation errors in response body

### Dashboard shows "Shop Not Found"

1. Verify shop exists: `curl http://localhost:8000/shops/{slug}`
2. Check slug spelling in URL
3. Shop may have been deleted

### Chat returns 403

1. Verify Owner ID matches the shop creator
2. Check `X-User-Id` header is being sent
3. Clear localStorage and re-authenticate
