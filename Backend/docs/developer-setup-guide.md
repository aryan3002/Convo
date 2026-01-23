# RouterGPT Developer Setup Guide

Complete guide for setting up RouterGPT in your local development environment.

---

## Prerequisites

- **Python 3.12+**
- **PostgreSQL 14+** with pgvector extension (Neon database recommended)
- **Git**
- **Node.js 18+** (for frontend, optional)
- **OpenAI API Key** (for chat functionality)
- **Ngrok** (for Custom GPT testing)

---

## Part 1: Backend Setup

### 1.1 Clone Repository

```bash
git clone https://github.com/your-org/convo.git
cd convo/Backend
```

### 1.2 Create Virtual Environment

```bash
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

### 1.3 Install Dependencies

```bash
pip install -r requirements.txt
```

### 1.4 Configure Environment Variables

Create `.env` file in `Backend/` directory:

```bash
cp .env.example .env
```

Edit `.env` with your values:

```env
# Database Connection
DATABASE_URL=postgresql+asyncpg://user:password@host:5432/database

# OpenAI API Key
OPENAI_API_KEY=sk-...

# Optional: Google Maps Geocoding (recommended for production)
GOOGLE_MAPS_API_KEY=

# Server Configuration
ALLOWED_ORIGINS=http://localhost:3000,http://localhost:8000
PUBLIC_API_BASE=http://localhost:8000

# Optional: Email (Resend)
RESEND_API_KEY=
RESEND_FROM=onboarding@yourdomain.com

# Optional: Twilio (for voice/SMS)
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_FROM_NUMBER=
```

### 1.5 Run Database Migrations

```bash
# Run all migrations in order
psql $DATABASE_URL -f migrations/001_add_pgvector_chunks.sql
psql $DATABASE_URL -f migrations/002_phase1_multitenancy.sql
psql $DATABASE_URL -f migrations/003_phase2_shop_api_keys.sql
psql $DATABASE_URL -f migrations/004_phase6_shop_members.sql
psql $DATABASE_URL -f migrations/005_phase7_audit_logs.sql
psql $DATABASE_URL -f migrations/006_phase3_shop_location.sql
psql $DATABASE_URL -f migrations/007_phase3_location_indexes.sql
psql $DATABASE_URL -f migrations/008_geocoding_cache.sql
psql $DATABASE_URL -f migrations/009_router_analytics.sql
```

**Or use the migration script:**

```bash
./scripts/run_migrations.sh
```

### 1.6 Verify Database Schema

```bash
psql $DATABASE_URL -c "\dt"  # List tables
psql $DATABASE_URL -c "\d shops"  # Verify shops table has latitude/longitude
```

Expected tables:
- `shops` (with latitude, longitude columns)
- `geocoding_cache`
- `router_analytics`
- `services`, `stylists`, `bookings`, etc.

---

## Part 2: Seed Test Data

### 2.1 Seed Test Shops with Locations

```bash
cd Backend
python3 scripts/seed_test_shops_with_locations.py
```

This creates 5 test shops in Phoenix metro area with:
- Geographic coordinates
- 3-5 services each
- 2-3 stylists each

**Expected Output:**

```
✅ Created Bishop's Barbershop Tempe (33.4255, -111.94)
✅ Created Tempe Hair Salon (33.4356, -111.9543)
✅ Created Phoenix Beauty Studio (33.4484, -112.074)
✅ Created Scottsdale Styles (33.5092, -111.899)
✅ Created Mesa Cuts (33.4152, -111.8315)
```

### 2.2 Geocode Existing Shops (Optional)

If you have existing shops without coordinates:

```bash
# Dry run to preview
python3 scripts/geocode_existing_shops.py --dry-run

# Actually geocode
python3 scripts/geocode_existing_shops.py
```

**Note**: Nominatim has a 1 request/second rate limit. For bulk geocoding, consider getting a Google Maps API key.

---

## Part 3: Start Development Server

### 3.1 Start Backend Server

```bash
cd Backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**Server should start at**: http://localhost:8000

### 3.2 Verify Server is Running

```bash
curl http://localhost:8000/health
# Expected: {"ok":true}
```

### 3.3 Test RouterGPT Endpoints

```bash
# Test location search
curl -X POST http://localhost:8000/router/search-by-location \
  -H "Content-Type: application/json" \
  -d '{"latitude": 33.4255, "longitude": -111.94, "radius_miles": 10}'

# Test delegation
curl -X POST http://localhost:8000/router/delegate \
  -H "Content-Type: application/json" \
  -d '{"shop_slug": "bishops-barbershop-tempe"}'
```

---

## Part 4: Run API Tests

### 4.1 Run Complete Test Suite

```bash
cd Backend
python3 scripts/test_routergpt_api.py -v
```

**Expected**: 13/14 tests pass (1 warning for empty messages is acceptable)

### 4.2 Run Specific Tests

```bash
# Test location search only
python3 scripts/test_routergpt_api.py --test location-search

# Test delegation only
python3 scripts/test_routergpt_api.py --test delegation

# Test error handling
python3 scripts/test_routergpt_api.py --test errors
```

---

## Part 5: Configure Custom GPT (Optional)

### 5.1 Start Ngrok Tunnel

```bash
ngrok http 8000
```

Copy the HTTPS URL (e.g., `https://abc123.ngrok.io`)

### 5.2 Update OpenAPI Schema

Edit `Backend/openapi_chatgpt_dev_ngrok.yaml`:

```yaml
servers:
  - url: https://YOUR-NGROK-ID.ngrok.io
    description: Development server (ngrok)
```

### 5.3 Create Custom GPT

1. Go to [ChatGPT](https://chat.openai.com) → My GPTs → Create
2. Configure GPT:
   - **Name**: RouterGPT (Dev)
   - **Description**: Find and book at local businesses
   - **Instructions**: Copy from `Backend/CUSTOM_GPT_INSTRUCTIONS.md`
   - **Actions**: Import `openapi_chatgpt_dev_ngrok.yaml`

### 5.4 Test Custom GPT

In ChatGPT, try:

> "I'm in Tempe, Arizona looking for a haircut near Mill Avenue"

Expected behavior:
1. GPT calls `searchBusinessesByLocation`
2. Lists nearby shops
3. Asks which one to select

---

## Part 6: Troubleshooting

### Issue: ImportError: No module named 'app'

**Solution**: Make sure you're running from the `Backend/` directory:

```bash
cd Backend
uvicorn app.main:app --reload
```

### Issue: Database connection failed

**Solution**: Check your `DATABASE_URL` format:

```env
# Correct format for asyncpg
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/dbname

# For psql command, use:
postgresql://user:pass@host:5432/dbname?sslmode=require
```

### Issue: No shops returned in location search

**Solution**: Verify shops have coordinates:

```sql
SELECT slug, name, latitude, longitude 
FROM shops 
WHERE latitude IS NOT NULL
LIMIT 10;
```

If empty, run the seed script or geocode existing shops.

### Issue: Rate limit errors during testing

**Solution**: Clear rate limits:

```python
# In Python shell
from app.rate_limiter import clear_rate_limits
clear_rate_limits()
```

### Issue: OpenAI API errors

**Solution**: Verify your API key:

```bash
# Test OpenAI key
curl https://api.openai.com/v1/models \
  -H "Authorization: Bearer $OPENAI_API_KEY"
```

### Issue: Geocoding fails

**Solution**: 
1. Check internet connection (Nominatim requires external API access)
2. Respect 1 second rate limit between requests
3. Consider getting Google Maps API key for production

---

## Part 7: Development Workflow

### 7.1 Daily Development

```bash
# 1. Activate virtual environment
cd Backend
source .venv/bin/activate

# 2. Pull latest changes
git pull

# 3. Run migrations (if any new ones)
./scripts/run_migrations.sh

# 4. Start server
uvicorn app.main:app --reload
```

### 7.2 Testing Changes

```bash
# Run full test suite
python3 scripts/test_routergpt_api.py -v

# Test specific endpoints manually
curl -X POST http://localhost:8000/router/search-by-location \
  -H "Content-Type: application/json" \
  -d '{"latitude": 33.4255, "longitude": -111.94, "radius_miles": 5}'
```

### 7.3 Database Inspection

```bash
# Connect to database
psql $DATABASE_URL

# Useful queries
\dt                          # List tables
\d shops                     # Describe shops table
SELECT * FROM shops LIMIT 5; # View shop data

# Check geocoding cache
SELECT COUNT(*) FROM geocoding_cache;
SELECT * FROM geocoding_cache LIMIT 5;

# View analytics
SELECT * FROM router_usage_summary;
SELECT * FROM router_shop_discovery LIMIT 10;
```

---

## Part 8: Common Development Tasks

### Add a New Shop Manually

```sql
INSERT INTO shops (name, slug, address, category, latitude, longitude, timezone)
VALUES (
  'My Test Shop',
  'my-test-shop',
  '123 Main St, Phoenix, AZ 85001',
  'salon',
  33.4484,
  -112.0740,
  'America/Phoenix'
);
```

### Clear Test Data

```bash
# Remove all test shops
psql $DATABASE_URL -c "DELETE FROM shops WHERE slug LIKE 'bishops-barbershop-tempe%' OR slug LIKE 'tempe-hair-salon%'"

# Clear analytics
psql $DATABASE_URL -c "TRUNCATE router_analytics;"

# Clear geocoding cache
psql $DATABASE_URL -c "TRUNCATE geocoding_cache;"
```

### View Recent API Requests

```sql
-- Recent searches
SELECT 
  created_at,
  search_latitude,
  search_longitude,
  search_radius_miles,
  search_results_count
FROM router_analytics
WHERE event_type = 'search'
ORDER BY created_at DESC
LIMIT 10;

-- Recent delegations
SELECT 
  created_at,
  shop_slug,
  delegation_intent,
  customer_to_shop_miles
FROM router_analytics
WHERE event_type = 'delegate'
ORDER BY created_at DESC
LIMIT 10;
```

---

## Part 9: Performance Optimization

### Check Index Usage

```sql
SELECT 
  schemaname,
  tablename,
  indexname,
  idx_scan,
  idx_tup_read
FROM pg_stat_user_indexes
WHERE tablename = 'shops'
ORDER BY idx_scan DESC;
```

### Analyze Query Performance

```sql
EXPLAIN ANALYZE
SELECT * FROM shops
WHERE latitude IS NOT NULL 
  AND longitude IS NOT NULL
  AND category = 'barbershop';
```

---

## Next Steps

✅ Backend running with test data  
✅ API tests passing  
✅ Database properly configured  

**Now you can**:
- Develop new features
- Test Custom GPT integration
- Deploy to staging/production

See:
- [E2E Testing Guide](../E2E_TESTING_GUIDE.md) - Full ChatGPT integration testing
- [Router API Docs](../docs/router-gpt-api.md) - Complete API reference
- [Deployment Checklist](../docs/deployment-checklist.md) - Production deployment steps
