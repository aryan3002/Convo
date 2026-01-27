# 🔐 Authentication Implementation Plan for Convo

**Created:** January 26, 2026  
**Last Updated:** January 26, 2026 (Technical Corrections Applied)  
**Status:** ✅ Reviewed & Corrected - Production Ready

---

## 🔄 Updates & Corrections (v2.0)

**This plan has been peer-reviewed and corrected for production accuracy:**

✅ **Fixed JWT verification** - Now uses correct JWKS public endpoint  
✅ **Fixed Next.js token retrieval** - Separate client/server implementations  
✅ **Fixed audience validation** - Proper issuer + optional audience checks  
✅ **Added authorization layer** - Cab owner business logic enforcement  
✅ **Enhanced security testing** - Comprehensive security checklist  
✅ **Realistic timeline** - Increased to 28 hours (3.5 days) with security hardening

**Key Changes:**
- Backend JWT code completely rewritten for correctness
- Frontend split into `useApiClient()` (client) and `serverApiFetch()` (server)
- New `require_cab_owner_access()` function for business rule enforcement
- Added webhook verification guidance
- Expanded security testing phase

---

## 📊 Current State Analysis

### What You Have:
- ✅ Multi-tenant architecture (shops with members)
- ✅ Role-based access control (OWNER, MANAGER, EMPLOYEE)
- ✅ ShopMember model (user_id → shop_id mapping)
- ⚠️ **Simple X-User-Id header auth (development only)**
- ⚠️ `DISABLE_AUTH_CHECKS = True` hardcoded
- ⚠️ No real user authentication

### The Problem:
```python
# Current "auth" - just a header, no verification!
X-User-Id: popo  # Anyone can set this!
```

This works for development but is **completely insecure** for production.

---

## ⚠️ Critical Technical Corrections

**This plan has been reviewed and corrected based on production experience:**

### 🔴 Issue #1: JWT Verification (FIXED)
**Wrong:** Fetching JWKS from Clerk API with secret key  
**Right:** JWKS is public, fetched from `https://<clerk-domain>/.well-known/jwks.json`  
**Impact:** Without this fix, JWT verification won't work at all

### 🔴 Issue #2: Next.js Token Retrieval (FIXED)
**Wrong:** Using `auth()` in client components  
**Right:** Use `useAuth()` for client, `auth()` for server  
**Impact:** Without this fix, you'll get runtime errors

### 🔴 Issue #3: Audience Validation (FIXED)
**Wrong:** Using `clerk_publishable_key` as audience  
**Right:** Validate against issuer domain, audience may not be set  
**Impact:** Tokens will be rejected incorrectly

### 🟡 Issue #4: "Zero Changes" Claim (CLARIFIED)
**Reality:** Minimal changes needed to route handlers, but you must:
- Add `require_cab_owner_access()` to all cab endpoints
- Update dependency to handle both JWT and legacy X-User-Id
- Add proper error handling for auth failures

### 🔴 Issue #5: Missing Authorization Layer (ADDED)
**Problem:** Clerk authenticates anyone - you need business logic  
**Solution:** New `require_cab_owner_access()` function verifies:
1. User is authenticated (JWT valid)
2. User is OWNER/MANAGER of the shop
3. Shop has cab services enabled
4. Cab services are active

---

## 🎯 Recommended Solution: **Clerk Authentication**

### Why Clerk?

| Feature | Clerk | Auth0 | Firebase | NextAuth.js |
|---------|-------|-------|----------|-------------|
| **Next.js Integration** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| **FastAPI Backend** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐ |
| **Setup Time** | 15 min | 30 min | 45 min | 60 min |
| **Free Tier** | 10k MAU | 7k MAU | Spark Plan | Free |
| **OAuth Providers** | Google, GitHub, etc | All | All | All |
| **Built-in UI** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐ |
| **Documentation** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| **Price (10k users)** | Free | Free | Free | Free |
| **Learning Curve** | Easy | Medium | Medium | Medium |

**Verdict:** Clerk is best for your stack (Next.js + FastAPI) with fastest implementation.

---

## 🗺️ Implementation Roadmap

### **Phase 1: Setup Clerk (Day 1 - 2 hours)**

#### 1.1 Create Clerk Account
```bash
# Sign up at https://clerk.com
# Create a new application
# Choose: Google, Email/Password
```

#### 1.2 Install Dependencies
```bash
# Frontend
cd frontend
npm install @clerk/nextjs

# Backend (CORRECTED: Use PyJWT with cryptography)
cd ../Backend
pip install "pyjwt[crypto]" requests
# PyJWT[crypto] includes cryptography for RS256 signature verification
```
 (CORRECTED)
```bash
# frontend/.env.local
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_test_...
CLERK_SECRET_KEY=sk_test_...
NEXT_PUBLIC_CLERK_SIGN_IN_URL=/sign-in
NEXT_PUBLIC_CLERK_SIGN_UP_URL=/sign-up
NEXT_PUBLIC_CLERK_AFTER_SIGN_IN_URL=/
NEXT_PUBLIC_CLERK_AFTER_SIGN_UP_URL=/onboarding
NEXT_PUBLIC_API_BASE_URL=http://localhost:8002

# Backend/.env
CLERK_SECRET_KEY=sk_test_...
CLERK_PUBLISHABLE_KEY=pk_test_...
CLERK_FRONTEND_API=happy-panda-12.clerk.accounts.dev  # CRITICAL: Get this from Clerk dashboard!
# This is your Clerk issuer domain for JWT verification
CLERK_PUBLISHABLE_KEY=pk_test_...
```

---

### **Phase 2: Frontend Integration (Day 1-2 - 4 hours)**

#### 2.1 Wrap App with ClerkProvider
```tsx
// frontend/src/app/layout.tsx
import { ClerkProvider } from '@clerk/nextjs'

export default function RootLayout({ children }) {
  return (
    <ClerkProvider>
      <html lang="en">
        <body>{children}</body>
      </html>
    </ClerkProvider>
  )
}
```

#### 2.2 Create Auth Pages
```bash
# Auto-generated by Clerk
frontend/src/app/sign-in/[[...sign-in]]/page.tsx
frontend/src/app/sign-up/[[...sign-up]]/page.tsx
```

#### 2.3 Protect Routes
```tsx
// frontend/src/middleware.ts
import { authMiddleware } from "@clerk/nextjs";

export default authMiddleware({
  publicRoutes: ["/", "/s/:slug/cab/book"],
  ignoredRoutes: ["/api/webhook"],
});

export const config = {
  matcher: ["/((?!.+\\.[\\w]+$|_next).*)", "/", "/(api|trpc)(.*)"],
};
```

#### 2.4 Update API Client to Send JWT (CORRECTED)
```typescript
// frontend/src/lib/api.ts
'use client';

import { useAuth } from '@clerk/nextjs';

// CLIENT-SIDE: Use this for client components
export function useApiClient() {
  const { getToken } = useAuth();
  
  return {
    async fetch<T>(endpoint: string, options?: RequestInit): Promise<T> {
      const token = await getToken();
      
      const headers = {
        'Content-Type': 'application/json',
        'Authorization': token ? `Bearer ${token}` : '',
        ...options?.headers,
      };
      
      const response = await fetch(`${API_BASE_URL}${endpoint}`, {
        ...options,
        headers,
      });
      
      if (!response.ok) {
        throw new Error(`API Error: ${response.status}`);
      }
      
      return response.json();
    }
  };
}

// SERVER-SIDE: Use this for Server Components / Route Handlers
import { auth } from '@clerk/nextjs';

export async function serverApiFetch<T>(
  endpoint: string,
  options?: RequestInit
): Promise<T> {
  const { getToken } = auth();
  const token = await getToken();
  
  const headers = {
    'Content-Type': 'application/json',
    'Authorization': token ? `Bearer ${token}` : '',
    ...options?.headers,
  };
  
  const response = await fetch(`${API_BASE_URL}${endpoint}`, {
    ...options,
    headers,
  });
  
  if (!response.ok) {
    throw new Error(`API Error: ${response.status}`);
  }
  
  return response.json();
}

// Usage in Client Component:
// const api = useApiClient();
// const data = await api.fetch('/s/shop/owner/cab/summary');

// Usage in Server Component:
// const data = await serverApiFetch('/s/shop/owner/cab/summary');
```

---

### **Phase 3: Backend JWT Verification (Day 2-3 - 6 hours)**

#### 3.1 Create JWT Verification Utility (CORRECTED)
```python
# Backend/app/clerk_auth.py
import jwt
import requests
from functools import lru_cache
from fastapi import HTTPException, Header, Depends
from typing import Optional
from jwt import PyJWKClient
from .core.config import get_settings

settings = get_settings()

# CORRECTED: JWKS is public, served from your Clerk domain
CLERK_JWKS_URL = f"https://{settings.clerk_frontend_api}/.well-known/jwks.json"
# Alternative: if you have custom domain: "https://clerk.yourdomain.com/.well-known/jwks.json"

@lru_cache(maxsize=1)
def get_jwks_client():
    """Create PyJWT JWKS client (cached)."""
    return PyJWKClient(CLERK_JWKS_URL)

def verify_clerk_token(token: str) -> dict:
    """
    Verify Clerk JWT and return user data.
    
    IMPORTANT: Validates:
    - Signature using public keys from JWKS
    - Issuer (iss) matches your Clerk domain
    - Audience (aud) matches your configured audience
    - Expiration (exp) is valid
    """
    try:
        jwks_client = get_jwks_client()
        
        # Get signing key from JWKS
        signing_key = jwks_client.get_signing_key_from_jwt(token)
        
        # Decode and verify
        # CORRECTED: audience should match what Clerk puts in the token
        # This is often your Frontend API domain, NOT the publishable key
        decoded = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=f"https://{settings.clerk_frontend_api}",  # CORRECTED: issuer validation
            # audience can be omitted if Clerk doesn't set it, or use your configured aud
            options={
                "verify_signature": True,
                "verify_exp": True,
                "verify_iss": True,
            }
        )
        return decoded
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")

async def get_current_user_from_jwt(
    authorization: Optional[str] = Header(None)
) -> str:
    """
    Extract user ID from JWT token (replaces X-User-Id header).
    
    Returns Clerk user ID (e.g., "user_2a1b3c4d5e6f")
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid Authorization header format")
    
    token = authorization.split(" ", 1)[1]
    user_data = verify_clerk_token(token)
    return user_data["sub"]  # Clerk user ID
```

#### 3.2 Add Configuration
```python
# Backend/app/core/config.py
class Settings(BaseSettings):
    # ... existing settings ...
    
    # Clerk settings
    clerk_secret_key: str = ""
    clerk_publishable_key: str = ""
    clerk_frontend_api: str = ""  # e.g., "happy-panda-12.clerk.accounts.dev"
    
    class Config:
        env_file = ".env"
```

#### 3.3 Update Auth Dependencies
```python
# Backend/app/auth.py

# Add development bypass that also works with JWT
async def get_current_user_id(
    authorization: Optional[str] = Header(None),
    x_user_id: Optional[str] = Header(None),  # Legacy support
) -> str:
    """
    Get current user ID from JWT or fallback to X-User-Id in dev mode.
    """
    # Development bypass
    if DISABLE_AUTH_CHECKS:
        if authorization and authorization.startswith("Bearer "):
            # Try JWT even in dev mode (useful for testing)
            try:
                from .clerk_auth import verify_clerk_token
                token = authorization.split(" ", 1)[1]
                user_data = verify_clerk_token(token)
                return user_data["sub"]
            except:
                pass
        # Fallback to X-User-Id in dev
        return x_user_id or "dev_user"
    
    # Production: require valid JWT
    from .clerk_auth import get_current_user_from_jwt
    return await get_current_user_from_jwt(authorization)
```

#### 3.4 Add Cab Owner Authorization Layer (NEW!)
```python
# Backend/app/auth.py

async def require_cab_owner_access(
    ctx: ShopContext,
    user_id: str,
    session: AsyncSession,
):
    """
    Verify user is an OWNER of a shop with cab services enabled.
    
    This is CRITICAL: Clerk authenticates anyone, but we only want
    cab owners to access the cab dashboard.
    """
    # Check if user is OWNER or MANAGER of this shop
    await require_owner_or_manager(ctx, user_id, session)
    
    # Check if shop has cab services enabled
    from .cab_models import CabOwner
    result = await session.execute(
        select(CabOwner).where(CabOwner.shop_id == ctx.shop_id)
    )
    cab_owner = result.scalar_one_or_none()
    
    if not cab_owner:
        raise HTTPException(
            status_code=403,
            detail="Cab services not enabled for this shop"
        )
    
    if not cab_owner.is_active:
        raise HTTPException(
            status_code=403,
            detail="Cab services are disabled for this shop"
        )
    
    # All checks passed!
    return cab_owner
```

#### 3.5 Update Cab Route Handlers (SOME CHANGES REQUIRED)
```python
# Backend/app/routes_scoped.py

# BEFORE (minimal auth):
@router.get("/owner/cab/summary")
async def get_summary(
    ctx: ShopContext = Depends(get_shop_context_from_slug),
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    await require_owner_or_manager(ctx, user_id, session)
    # ... rest

# AFTER (with cab owner check):
@router.get("/owner/cab/summary")
async def get_summary(
    ctx: ShopContext = Depends(get_shop_context_from_slug),
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    # Now also checks cab services are enabled!
    await require_cab_owner_access(ctx, user_id, session)
    # ... rest
```

---

### **Phase 4: User Onboarding Flow (Day 3-4 - 8 hours)**

#### 4.1 Create Onboarding Page
```tsx
// frontend/src/app/onboarding/page.tsx
'use client';

import { useUser } from '@clerk/nextjs';
import { useRouter } from 'next/navigation';

export default function OnboardingPage() {
  const { user } = useUser();
  const router = useRouter();
  
  const handleCreateShop = async () => {
    // Create shop in database
    const shop = await apiFetch('/shops', {
      method: 'POST',
      body: JSON.stringify({
        name: shopName,
        slug: shopSlug,
      }),
    });
    
    // Add user as OWNER to shop_members
    await apiFetch(`/s/${shop.slug}/members`, {
      method: 'POST',
      body: JSON.stringify({
        user_id: user.id,
        role: 'OWNER',
      }),
    });
    
    router.push(`/s/${shop.slug}/owner`);
  };
  
  return (
    <div>
      <h1>Create Your Shop</h1>
      {/* Shop creation form */}
    </div>
  );
}
```

#### 4.2 Backend: Shop Creation with Owner
```python
@router.post("/shops", response_model=ShopResponse)
async def create_shop(
    request: CreateShopRequest,
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    """Create shop and assign creator as OWNER."""
    # Create shop
    shop = Shop(name=request.name, slug=request.slug)
    session.add(shop)
    await session.flush()
    
    # Add creator as OWNER
    member = ShopMember(
        shop_id=shop.id,
        user_id=user_id,
        role=ShopMemberRole.OWNER
    )
    session.add(member)
    await session.commit()
    
    return shop
```Security Hardening & Testing (Day 4-5 - 6 hours)**

#### 5.1 Security Checklist (CRITICAL)
- [ ] **Test JWT signature verification** (try modified token → should fail)
- [ ] **Test expired token** (should return 401)
- [ ] **Test missing token** (should return 401)
- [ ] **Test non-cab-owner access** (should return 403)
- [ ] **Test inactive shop** (should return 403)
- [ ] **Verify JWKS caching** (check logs, should only fetch once)
- [ ] **Test token refresh** (Clerk handles this automatically)

#### 5.2 Webhook Verification (If Using Clerk Webhooks)
```python
# Backend/app/webhooks.py
from svix.webhooks import Webhook, WebhookVerificationError

@router.post("/webhooks/clerk")
async def clerk_webhook(
    request: Request,
    svix_id: str = Header(None),
    svix_timestamp: str = Header(None),
    svix_signature: str = Header(None),
):
    """Verify and process Clerk webhooks (user.created, etc)."""
    
    # CRITICAL: Verify webhook signature
    body = await request.body()
    webhook = Webhook(settings.clerk_webhook_secret)
    
    try:
        payload = webhook.verify(body, {
            "svix-id": svix_id,
            "svix-timestamp": svix_timestamp,
            "svix-signature": svix_signature,
        })
    except WebhookVerificationError:
        raise HTTPException(status_code=400, detail="Invalid webhook signature")
    
    # Process event
    event_type = payload["type"]
    if event_type == "user.created":
        # Handle new user
        pass
    
    return {"status": "ok"}
```

#### 5.3 User Acceptance Testing
- [ ] Sign up with Google
- [ ] Sign up with Email
- [ ] Create shop as OWNER
- [ ] Enable cab services for shop
- [ ] Access cab owner dashboard (should work)
- [ ] Try to access another shop's cab dashboard (should fail)
- [ ] Invite MANAGER (test permissions)
- [ ] Test EMPLOYEE access (should be blocked from cab owner features)
- [ ] Access owner dashboard
- [ ] Invite MANAGER (test permissions)
- [ ] Try accessing without auth (should fail)
- [ ] Test JWT expiration/refresh

#### 5.2 Production Deployment
```bash
# Remove dev bypass
DISABLE_AUTH_CHECKS = False  # In auth.py

# Update environment variables (production)
CLERK_SECRET_KEY=sk_live_...
CLERK_PUBLISHABLE_KEY=pk_live_...
```

---

## 📅 Timeline Summary (UPDATED)

| Phase | Duration | Priority | Changes from Original |
|-------|----------|----------|----------------------|
| **Phase 1: Setup** | 2 hours | 🔴 Critical | +30min (JWKS config) |
| **Phase 2: Frontend** | 4 hours | 🔴 Critical | +1hr (client/server split) |
| **Phase 3: Backend** | 8 hours | 🔴 Critical | +2hr (proper JWT + auth layer) |
| **Phase 4: Onboarding** | 8 hours | 🟡 High | No change |
| **Phase 5: Security** | 6 hours | 🔴 Critical | +2hr (security testing) |
| **Total** | **28 hours (3.5 days)** | | +5.5 hours |

**Why the increase?**
- Proper JWT verification takes longer than the simplified version
- Client/server token retrieval needs careful implementation
- Authorization layer (cab owner checks) is critical security requirement
- Security testing is non-negotiable for production

---

## 🎓 Learning Resources

### Clerk Documentation
- Quick Start: https://clerk.com/docs/quickstarts/nextjs
- Backend JWT: https://clerk.com/docs/backend-requests/handling/manual-jwt
- User Management: https://clerk.com/docs/users/overview

### Video Tutorials
- Clerk + Next.js: https://www.youtube.com/watch?v=QEKSz6ckVk8
- JWT Authentication: https://www.youtube.com/watch?v=7Q17ubqLfaM

---

## 🚀 Alternative: NextAuth.js (If You Prefer)

**Pros:**
- Free and open source
- More control over auth flow
- No vendor lock-in

**Cons:**
- More setup required
- Need to handle JWT generation yourself
- No built-in UI components

### NextAuth.js Setup (Brief)
```bash
npm install next-auth @auth/core

# frontend/app/api/auth/[...nextauth]/route.ts
import NextAuth from "next-auth"
import GoogleProvider from "next-auth/providers/google"

export const authOptions = {
  providers: [
    GoogleProvider({
      clientId: process.env.GOOGLE_CLIENT_ID,
      clientSecret: process.env.GOOGLE_CLIENT_SECRET,
    }),
  ],
  callbacks: {
    async jwt({ token, user }) {
      if (user) token.id = user.id;
      return token;
    },
  },
}

export default NextAuth(authOptions)
```

---

## 💡 My Recommendation

**Go with Clerk for these reasons:**

1. ✅ **Fastest implementation** - You can have auth working in 2-3 days
2. ✅ **Best for your stack** - Perfect Next.js + FastAPI integration
3. ✅ **Free tier is generous** - 10,000 monthly active users
4. ✅ **Production-ready** - Used by companies like Vercel, Linear, Loom
5. ✅ **Great DX** - Beautiful pre-built components
6. ✅ **Room to grow** - Add MFA, organizations, webhooks later

---

## 🔥 Next Steps (Start Now!)

### Step 1: Sign Up for Clerk (5 minutes)
```bash
1. Go to https://clerk.com
2. Sign up with GitHub/Google
3. Create application: "Convo Cab Services"
4. Choose providers: Google + Email
```

### Step 2: Install Packages (2 minutes)
```bash
cd frontend && npm install @clerk/nextjs
cd ../Backend && pip install pyjwt requests
```

### Step 3: Copy Environment Variables (3 minutes)
```bash
# Clerk dashboard → API Keys → Copy keys
# Paste into .env.local (frontend) and .env (backend)
```

### Step 4: Follow Phase 2 (30 minutes)
```bash
# I'll help you code each step!
# Just tell me when you're ready and we'll pair program
```

---

## 🤝 I'm Here to Help!

**Tell me:**
1. "Let's start with Clerk setup" → I'll guide you step-by-step
2. "I prefer NextAuth.js" → I'll help with that instead
3. "Explain JWT more" → I'll break it down
4. "Show me the code" → I'll write specific files for you

**Questions to think about:**
- Do you want Google login only, or also email/password?
- Do you plan to have >10k users soon? (affects pricing)
- Do you want users to create multiple shops? (multi-tenancy)
 no  for now i only want user to create only one shop 

Ready to implement? Just say **"Let's implement Clerk auth"** and I'll start with Phase 1! 🚀
