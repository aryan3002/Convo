# RouterGPT Production Deployment Checklist

Complete checklist for deploying RouterGPT to production.

---

## Pre-Deployment Checklist

### ✅ Database Preparation

- [ ] **Backup current database**
  ```bash
  pg_dump $DATABASE_URL > backup_$(date +%Y%m%d_%H%M%S).sql
  ```

- [ ] **Run all migrations in order**
  ```bash
  psql $DATABASE_URL -f migrations/006_phase3_shop_location.sql
  psql $DATABASE_URL -f migrations/007_phase3_location_indexes.sql
  psql $DATABASE_URL -f migrations/008_geocoding_cache.sql
  psql $DATABASE_URL -f migrations/009_router_analytics.sql
  ```

- [ ] **Verify migrations succeeded**
  ```sql
  -- Check shops table has location fields
  \d shops
  
  -- Check new tables exist
  \dt geocoding_cache
  \dt router_analytics
  
  -- Check indexes were created
  \di idx_shops_location_category
  \di idx_shops_lat
  \di idx_shops_lon
  ```

- [ ] **Geocode existing shops**
  ```bash
  # Dry run first
  python scripts/geocode_existing_shops.py --dry-run
  
  # Review output, then run for real
  python scripts/geocode_existing_shops.py
  ```

- [ ] **Remove test data**
  ```sql
  DELETE FROM shops 
  WHERE slug IN (
    'bishops-barbershop-tempe',
    'tempe-hair-salon',
    'phoenix-beauty-studio',
    'scottsdale-styles',
    'mesa-cuts'
  );
  ```

- [ ] **Verify analytics views work**
  ```sql
  SELECT * FROM router_usage_summary LIMIT 5;
  SELECT * FROM router_shop_discovery LIMIT 10;
  SELECT * FROM router_conversion_funnel LIMIT 5;
  ```

---

### ✅ Code Quality & Testing

- [ ] **All unit tests pass**
  ```bash
  pytest tests/
  ```

- [ ] **API integration tests pass**
  ```bash
  python scripts/test_routergpt_api.py -v
  ```

- [ ] **Manual E2E testing completed** (see E2E_TESTING_GUIDE.md)
  - [ ] Location search returns results
  - [ ] Delegation creates session
  - [ ] Chat endpoint works with router context
  - [ ] Custom GPT can complete full booking flow

- [ ] **Error scenarios tested**
  - [ ] Invalid coordinates return 422
  - [ ] Nonexistent shop returns 404
  - [ ] Rate limits work correctly
  - [ ] Empty search areas return gracefully

- [ ] **Performance tested**
  - [ ] Location search < 500ms
  - [ ] Delegation < 200ms
  - [ ] Chat response < 5s (with OpenAI)

---

### ✅ Configuration

- [ ] **Environment variables set**
  ```env
  # Production database
  DATABASE_URL=postgresql+asyncpg://...
  
  # OpenAI API key
  OPENAI_API_KEY=sk-...
  
  # Optional: Google Maps API key (recommended)
  GOOGLE_MAPS_API_KEY=...
  
  # Production domain
  PUBLIC_API_BASE=https://api.yourdomain.com
  ALLOWED_ORIGINS=https://yourdomain.com,https://chat.openai.com
  
  # Email (if using)
  RESEND_API_KEY=...
  RESEND_FROM=noreply@yourdomain.com
  ```

- [ ] **Rate limiting configured**
  - [ ] `/router/search-by-location`: 20/min per IP
  - [ ] `/router/delegate`: 10/min per IP
  - [ ] Consider Redis-based rate limiting for multi-server deployments

- [ ] **CORS origins updated**
  - [ ] Production frontend domain
  - [ ] ChatGPT domain (chat.openai.com)

- [ ] **SSL/TLS certificates installed**
  - [ ] HTTPS enabled
  - [ ] Certificate valid and not expiring soon

---

### ✅ API Documentation

- [ ] **OpenAPI schema updated**
  - [ ] Production URL in `openapi_chatgpt_prod.yaml`
  - [ ] All endpoints documented
  - [ ] Rate limits documented
  - [ ] Example requests/responses included

- [ ] **Schema validated**
  ```bash
  # Validate YAML syntax
  python -c "import yaml; yaml.safe_load(open('openapi_chatgpt_prod.yaml'))"
  
  # Optional: Use Swagger Editor
  # https://editor.swagger.io/
  ```

- [ ] **API documentation published**
  - [ ] docs/router-gpt-api.md accessible
  - [ ] Versioning strategy defined
  - [ ] Changelog maintained

---

### ✅ Custom GPT Configuration

- [ ] **Production Custom GPT created**
  - [ ] Name: "RouterGPT" or your branded name
  - [ ] Description updated
  - [ ] Instructions from CUSTOM_GPT_INSTRUCTIONS.md
  - [ ] Actions using openapi_chatgpt_prod.yaml
  - [ ] Privacy policy linked

- [ ] **Custom GPT tested end-to-end**
  - [ ] Location search works
  - [ ] Business selection works
  - [ ] Delegation to shop works
  - [ ] Booking completion works

- [ ] **Custom GPT published**
  - [ ] Listed in GPT Store (if desired)
  - [ ] Shared with team/testers
  - [ ] Usage instructions documented

---

### ✅ Monitoring & Logging

- [ ] **Logging configured**
  - [ ] All [ROUTER] logs present
  - [ ] [BOOKING] completion logs work
  - [ ] [ANALYTICS] tracking confirmed
  - [ ] Error logs include stack traces

- [ ] **Log aggregation setup** (optional but recommended)
  - [ ] Sentry / Datadog / CloudWatch configured
  - [ ] Error alerts enabled
  - [ ] Performance monitoring enabled

- [ ] **Analytics tracking verified**
  ```sql
  -- Check recent events
  SELECT event_type, COUNT(*) 
  FROM router_analytics 
  WHERE created_at > NOW() - INTERVAL '1 hour'
  GROUP BY event_type;
  ```

- [ ] **Health check endpoint working**
  ```bash
  curl https://api.yourdomain.com/health
  # Expected: {"ok":true}
  ```

---

### ✅ Performance Optimization

- [ ] **Database indexes verified**
  ```sql
  SELECT * FROM pg_indexes 
  WHERE tablename = 'shops' 
  AND indexname LIKE 'idx_shops_%';
  ```

- [ ] **Query performance acceptable**
  ```sql
  EXPLAIN ANALYZE
  SELECT * FROM shops
  WHERE latitude IS NOT NULL 
    AND longitude IS NOT NULL
    AND category = 'barbershop'
  ORDER BY latitude, longitude;
  ```

- [ ] **Geocoding cache working**
  ```sql
  -- Should have cached entries
  SELECT COUNT(*), provider 
  FROM geocoding_cache 
  GROUP BY provider;
  ```

- [ ] **Rate limiting tested**
  - [ ] Exceeding limits returns 429
  - [ ] Retry-After header present
  - [ ] Rate limit headers on all responses

---

### ✅ Security

- [ ] **Secrets not in code**
  - [ ] .env file in .gitignore
  - [ ] No API keys in repository
  - [ ] Environment variables used

- [ ] **Input validation working**
  - [ ] Coordinates validated (-90 to 90, -180 to 180)
  - [ ] Radius validated (0 to 50 miles)
  - [ ] SQL injection protected (using SQLAlchemy)

- [ ] **HTTPS enforced**
  - [ ] HTTP redirects to HTTPS
  - [ ] HSTS header set
  - [ ] Secure cookies (if using sessions)

- [ ] **API authentication considered** (for future)
  - [ ] Document whether public or authenticated
  - [ ] Plan for API key management if needed

---

### ✅ Data Privacy & Compliance

- [ ] **Privacy policy updated**
  - [ ] Location data collection disclosed
  - [ ] Data retention policy documented
  - [ ] User consent mechanism (if required)

- [ ] **GDPR compliance** (if serving EU)
  - [ ] Data deletion procedures
  - [ ] Data export capabilities
  - [ ] Cookie consent banner

- [ ] **Data retention configured**
  - [ ] Analytics older than X days deleted
  - [ ] Geocoding cache expires after 90 days
  - [ ] Cleanup jobs scheduled

---

## Deployment Steps

### Step 1: Final Testing

```bash
# Run all tests one more time
cd Backend
python scripts/test_routergpt_api.py -v

# Verify test data removed
psql $DATABASE_URL -c "SELECT slug FROM shops WHERE slug LIKE '%tempe%' OR slug LIKE '%test%';"
```

### Step 2: Deploy Code

```bash
# Pull latest code on production server
git pull origin main

# Install/update dependencies
pip install -r requirements.txt

# Restart application server
systemctl restart uvicorn  # or your process manager
# OR
pm2 restart convo-backend
```

### Step 3: Smoke Test Production

```bash
# Test health endpoint
curl https://api.yourdomain.com/health

# Test location search
curl -X POST https://api.yourdomain.com/router/search-by-location \
  -H "Content-Type: application/json" \
  -d '{"latitude": 33.4255, "longitude": -111.94, "radius_miles": 10}'

# Test delegation to a real shop
curl -X POST https://api.yourdomain.com/router/delegate \
  -H "Content-Type: application/json" \
  -d '{"shop_slug": "your-real-shop-slug"}'
```

### Step 4: Update Custom GPT

1. Go to ChatGPT → Your Custom GPT → Edit
2. Update Actions → Import new OpenAPI schema
3. Verify production URL
4. Test full flow

### Step 5: Monitor Logs

```bash
# Watch logs for errors
tail -f /var/log/uvicorn/error.log

# Check for [ROUTER] and [ANALYTICS] logs
tail -f /var/log/uvicorn/access.log | grep ROUTER
```

---

## Post-Deployment Verification

### ✅ Functional Testing (15 minutes)

- [ ] **Location search works**
  - Try 3-4 different locations
  - Try with and without category filter
  - Verify distances are accurate

- [ ] **Delegation works**
  - Delegate to 2-3 different shops
  - Verify session IDs generated
  - Check initial messages correct

- [ ] **Chat flow works**
  - Complete at least 1 full booking
  - Verify router context passed
  - Check booking saved to database

- [ ] **Custom GPT works end-to-end**
  - Search → Select → Book flow
  - Multiple shops
  - Different intents

### ✅ Performance Monitoring (24 hours)

- [ ] **Response times acceptable**
  ```sql
  -- Add query timing if needed
  SELECT 
    event_type,
    AVG(EXTRACT(EPOCH FROM (created_at - LAG(created_at) OVER (PARTITION BY session_id ORDER BY created_at)))) as avg_time_between_events
  FROM router_analytics
  WHERE created_at > NOW() - INTERVAL '24 hours'
  GROUP BY event_type;
  ```

- [ ] **No errors in logs**
  - Check error rate
  - Review any 500 errors
  - Investigate slow queries

- [ ] **Rate limiting working**
  - No excessive 429 errors
  - Legitimate users not blocked
  - Abuse prevented

### ✅ Analytics Review (1 week)

- [ ] **Usage patterns normal**
  ```sql
  SELECT * FROM router_usage_summary
  WHERE date >= CURRENT_DATE - 7
  ORDER BY date DESC;
  ```

- [ ] **Conversion funnel healthy**
  ```sql
  SELECT * FROM router_conversion_funnel
  WHERE date >= CURRENT_DATE - 7
  ORDER BY date DESC;
  ```

- [ ] **Popular shops identified**
  ```sql
  SELECT * FROM router_shop_discovery
  WHERE times_discovered > 0
  ORDER BY times_discovered DESC
  LIMIT 20;
  ```

---

## Rollback Plan

If critical issues discovered:

### Option 1: Code Rollback

```bash
# Revert to previous version
git revert HEAD
git push

# Restart server
systemctl restart uvicorn
```

### Option 2: Database Rollback

```bash
# Restore from backup
psql $DATABASE_URL < backup_20240122_120000.sql

# Remove new tables if needed
psql $DATABASE_URL -c "DROP TABLE IF EXISTS router_analytics CASCADE;"
psql $DATABASE_URL -c "DROP TABLE IF EXISTS geocoding_cache CASCADE;"

# Remove indexes
psql $DATABASE_URL -c "DROP INDEX IF EXISTS idx_shops_location_category;"
```

### Option 3: Feature Toggle

```env
# Disable RouterGPT temporarily
ENABLE_ROUTER_GPT=false
```

---

## Ongoing Maintenance

### Daily

- [ ] Check error logs
- [ ] Monitor response times
- [ ] Review rate limit hits

### Weekly

- [ ] Review analytics
  ```sql
  SELECT * FROM router_usage_summary WHERE date >= CURRENT_DATE - 7;
  SELECT * FROM router_conversion_funnel WHERE date >= CURRENT_DATE - 7;
  ```

- [ ] Clean up expired geocoding cache
  ```sql
  SELECT cleanup_expired_geocoding_cache();
  ```

- [ ] Check disk space
  ```bash
  df -h
  ```

### Monthly

- [ ] Review and optimize slow queries
- [ ] Archive old analytics data
- [ ] Update documentation
- [ ] Review and update rate limits if needed

---

## Success Metrics

After 1 month in production, evaluate:

| Metric | Target | Actual |
|--------|--------|--------|
| RouterGPT usage rate | > 10% of bookings | ___ |
| Search to booking conversion | > 25% | ___ |
| Average response time | < 500ms | ___ |
| Error rate | < 1% | ___ |
| Custom GPT user satisfaction | > 4.0/5.0 | ___ |

---

## Support Contacts

- **Database Issues**: DBA Team
- **API Errors**: Backend Team
- **Custom GPT Issues**: OpenAI Support
- **Geocoding Issues**: Google Maps Support

---

## Additional Resources

- [RouterGPT API Documentation](./router-gpt-api.md)
- [Developer Setup Guide](./developer-setup-guide.md)
- [E2E Testing Guide](../E2E_TESTING_GUIDE.md)
- [OpenAI Custom GPT Docs](https://platform.openai.com/docs/actions)

---

**Deployment Date**: _____________

**Deployed By**: _____________

**Sign-off**: _____________
