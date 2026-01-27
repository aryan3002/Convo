# 🚀 Quick Start: Clerk JWT Authentication for Convo

**Time to test:** 5-10 minutes

---

## ✅ What's Already Done

- [x] Clerk account created
- [x] API keys in .env files
- [x] Frontend Clerk integration
- [x] Backend JWT verification
- [x] Security tests ready

---

## 🎯 Next Steps to Test

### Step 1: Start the Backend (if not running)

```bash
cd /Users/aryantripathi/Convo-main/Backend
source venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8002
```

### Step 2: Start the Frontend (if not running)

```bash
cd /Users/aryantripathi/Convo-main/frontend
npm run dev
```

### Step 3: Test Sign-Up Flow

1. Open http://localhost:3000/sign-up
2. Click "Sign up with Google" (or use email)
3. Complete authentication
4. Should redirect to http://localhost:3000/onboarding
5. Create a shop:
   - Name: "My Test Shop"
   - Slug: "my-test-shop"
   - Phone: "+15551234567"
   - Timezone: "America/New_York"
6. Click "Create Shop"
7. Should redirect to http://localhost:3000/s/my-test-shop/owner

### Step 4: Test API with JWT Token

Get JWT from browser:
```javascript
// Open DevTools Console (F12)
// Run:
const token = await window.__clerk.session.getToken();
console.log('Bearer ' + token);
```

Test with curl:
```bash
# Copy token from above
TOKEN="eyJhbGciOiJSUzI1NiIsImtpZCI6Imtlcn..." 

# Test protected endpoint
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8002/s/my-test-shop/owner/chat
```

### Step 5: Run Security Tests

```bash
cd Backend
pip install httpx  # One-time only
python scripts/security_test.py
```

Expected output:
```
✅ Missing Token: Correctly rejected request without token
✅ Malformed Token: Correctly rejected malformed token
✅ Invalid Issuer: Correctly rejected invalid issuer
✅ Expired Token: Correctly rejected expired token
✅ Legacy X-User-Id Header: Legacy header works (dev mode enabled)
✅ Invalid Bearer Format: Invalid bearer format handled
✅ JWKS Caching: JWKS caching working
✅ Tenant Isolation: Tenant isolation enforced
✅ Cab Owner Authorization: Cab owner check enforced

SECURITY TEST SUMMARY
Passed: 9/9 (100%)
Failed: 0/0
✅ All tests passed!
```

---

## 🔍 Verify Implementation

### Check Backend JWT Verification

```bash
# Check clerk_auth.py exists
ls -la Backend/app/clerk_auth.py

# Check auth.py has JWT support
grep -n "verify_clerk_token\|require_cab_owner_access" Backend/app/auth.py
```

### Check Frontend Integration

```bash
# Check middleware
ls -la frontend/src/middleware.ts

# Check sign-in/up pages
ls -la frontend/src/app/sign-in/[[...sign-in]]/page.tsx
ls -la frontend/src/app/sign-up/[[...sign-up]]/page.tsx

# Check API client
ls -la frontend/src/lib/clerk-api.ts
```

### Check Configuration

```bash
# Backend Clerk config
grep "CLERK_" Backend/.env

# Frontend Clerk config
grep "CLERK_" frontend/.env.local
```

---

## 🆘 Troubleshooting

### Issue: "CLERK_FRONTEND_API not set"

**Error message:**
```
ValueError: CLERK_FRONTEND_API environment variable is not set
```

**Fix:**
```bash
# Edit Backend/.env
CLERK_FRONTEND_API=wanted-mammae-42.clerk.accounts.dev
```

### Issue: "Invalid issuer" or JWT verification fails

**Error message:**
```
HTTPException: Invalid token
```

**Causes & Fixes:**
1. Check CLERK_FRONTEND_API is correct (must match your Clerk domain)
2. Check token is fresh (not expired)
3. Check clock skew (server/client time out of sync)

**Debug:**
```javascript
// In browser console
const claims = await window.__clerk.session.getToken();
// Paste at https://jwt.io to inspect claims
```

### Issue: "Clerk sign-in page not loading"

**Fix:**
```bash
# Make sure all packages installed
npm install @clerk/nextjs
npm install

# Clear cache and rebuild
rm -rf .next
npm run dev
```

### Issue: "Backend 502 Bad Gateway from JWKS endpoint"

**Cause:** Clerk's JWKS endpoint is unreachable

**Fixes:**
1. Check internet connection
2. Check firewall allows *.clerk.accounts.dev
3. Check Clerk status page
4. In dev mode, set `DISABLE_AUTH_CHECKS=true` temporarily

---

## 📊 What Each Component Does

### Frontend Components

**`middleware.ts`** - Protects routes
- Requires auth on `/s/*` routes
- Allows public access to `/sign-in`, `/sign-up`, `/`
- Redirects unauthenticated users to `/sign-in`

**`clerk-api.ts`** - Sends JWT tokens
- `useApiClient()` - For client components
- `serverApiFetch()` - For server components
- Automatically includes `Authorization: Bearer {token}` header

**Sign-in/Sign-up pages** - Clerk pre-built UI
- Beautiful OAuth interface
- Email/password support
- Automatic form validation

**Onboarding page** - Shop creation
- Uses Clerk's `useUser()` hook
- Creates shop in backend
- Adds user as OWNER

### Backend Components

**`clerk_auth.py`** - Verifies JWTs
- Fetches public keys from Clerk
- Verifies RS256 signature
- Validates issuer and expiration
- Caches keys for performance

**Updated `auth.py`** - Handles both JWT and legacy auth
- Supports `Authorization: Bearer {token}` header
- Falls back to `X-User-Id` in dev mode
- Added `require_cab_owner_access()` for business logic

**Updated `config.py`** - Clerk settings
- Reads CLERK_SECRET_KEY from environment
- Reads CLERK_FRONTEND_API (JWKS endpoint)
- Passes to clerk_auth module

---

## 🎓 How It Works (End-to-End)

### 1. User Signs Up

```
User clicks "Sign up with Google"
         ↓
Clerk handles OAuth with Google
         ↓
Google returns auth code
         ↓
Clerk validates code, creates user session
         ↓
Browser redirected to /onboarding with session
         ↓
Frontend calls useUser() to get Clerk user ID
         ↓
User creates shop (owner_user_id = Clerk ID)
```

### 2. API Request with JWT

```
Browser has Clerk session token
         ↓
Client component calls useApiClient()
         ↓
useAuth() hook gets JWT token
         ↓
Request sent: Authorization: Bearer {JWT}
         ↓
Backend receives request
         ↓
Extracts token from Authorization header
         ↓
Calls verify_clerk_token(token)
         ↓
Fetches public key from Clerk's JWKS endpoint
         ↓
Verifies RS256 signature
         ↓
Validates issuer: https://wanted-mammae-42.clerk.accounts.dev
         ↓
Validates expiration
         ↓
Extracts user_id from 'sub' claim
         ↓
Checks user is OWNER of shop
         ↓
Check shop has cab services enabled
         ↓
Request allowed, returns data
```

---

## 🧪 Testing Checklist

- [ ] Can sign up with Google
- [ ] Can sign in after sign-up
- [ ] Can create shop on onboarding page
- [ ] Can access owner dashboard
- [ ] Cab owner authorization works
- [ ] Tenant isolation enforced (can't access other shops)
- [ ] Security tests pass
- [ ] Missing token returns 401
- [ ] Invalid token returns 401
- [ ] Legacy X-User-Id works (dev mode)

---

## 🔐 Security Notes

### For Development

- `DISABLE_AUTH_CHECKS=true` allows testing without real Clerk account
- Legacy `X-User-Id` header works for testing
- OK to share test environment

### For Production

- Change `DISABLE_AUTH_CHECKS=false` before deploying
- Use Clerk production keys (not test keys)
- Enable HTTPS
- Monitor Clerk dashboard for security events
- Consider adding MFA

---

## 📞 Support

If you encounter issues:

1. Check `CLERK_AUTH_IMPLEMENTATION.md` for detailed docs
2. Run `Backend/scripts/security_test.py`
3. Check browser console for errors (DevTools F12)
4. Check backend logs (uvicorn output)
5. Visit https://clerk.com/docs for Clerk docs

---

## ✨ You're All Set!

The complete authentication system is now ready to test. Sign up with Google, create a shop, and explore the authenticated dashboard.

**Next:** Test the full flow and then consider production deployment configuration.
