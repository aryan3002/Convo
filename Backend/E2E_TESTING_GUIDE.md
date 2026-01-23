# RouterGPT End-to-End Testing Guide

This document provides step-by-step instructions for testing the RouterGPT location-based business discovery and delegation system with ChatGPT Custom GPTs.

## Prerequisites

1. **Backend Running**: The FastAPI server must be running
2. **Database Seeded**: Test shops must be in the database
3. **Ngrok Tunnel**: For ChatGPT integration testing
4. **OpenAI Account**: With Custom GPT creation access

---

## Part 1: Local Setup

### 1.1 Start the Backend Server

```bash
cd Backend
source venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 1.2 Seed Test Data

Run the seeding script to create test shops with coordinates:

```bash
cd Backend
python scripts/seed_test_shops_with_locations.py
```

Expected output:
```
✅ Created Bishop's Barbershop Tempe (33.4255, -111.94)
✅ Created Tempe Hair Salon (33.4356, -111.9543)
✅ Created Phoenix Beauty Studio (33.4484, -112.074)
✅ Created Scottsdale Styles (33.5092, -111.899)
✅ Created Mesa Cuts (33.4152, -111.8315)
```

### 1.3 Run API Tests

Verify the API is working before testing with ChatGPT:

```bash
cd Backend
python scripts/test_routergpt_api.py -v
```

All tests should pass before proceeding.

---

## Part 2: ChatGPT Custom GPT Testing

### 2.1 Set Up Ngrok Tunnel

```bash
ngrok http 8000
```

Note the HTTPS URL (e.g., `https://abc123.ngrok.io`)

### 2.2 Update OpenAPI Schema

Edit `Backend/openapi_chatgpt_dev_ngrok.yaml` and update the server URL:

```yaml
servers:
  - url: https://YOUR-NGROK-ID.ngrok.io
    description: Development server (ngrok)
```

### 2.3 Create/Update Custom GPT

1. Go to [ChatGPT](https://chat.openai.com) → My GPTs → Create a GPT
2. Configure the GPT:
   - **Name**: RouterGPT (Dev)
   - **Description**: Find and book appointments at local businesses
   - **Instructions**: Copy from `Backend/CUSTOM_GPT_INSTRUCTIONS.md`
   - **Actions**: Import the updated OpenAPI schema

### 2.4 Test Conversation Flows

#### Flow 1: Location Search → Delegation → Booking

**User Prompt:**
> "I'm in Tempe, Arizona looking for a haircut near Mill Avenue"

**Expected Behavior:**
1. GPT calls `searchBusinessesByLocation` with Tempe coordinates
2. GPT presents list of nearby businesses
3. GPT asks user to select one

**User Prompt:**
> "Let's go with Bishop's Barbershop"

**Expected Behavior:**
1. GPT calls `delegateToShop` with slug "bishops-tempe"
2. GPT receives session_id and available services
3. GPT presents services and asks for preference

**User Prompt:**
> "I'd like a classic haircut with Mike"

**Expected Behavior:**
1. GPT calls `chatWithShop` with booking context
2. GPT helps complete the booking

#### Flow 2: Category-Specific Search

**User Prompt:**
> "Find a barbershop within 5 miles of Scottsdale"

**Expected Behavior:**
1. GPT calls `searchBusinessesByLocation` with:
   - category: "barbershop"
   - radius_miles: 5
   - Scottsdale coordinates
2. Returns filtered results

#### Flow 3: No Results Handling

**User Prompt:**
> "I need a haircut in New York City"

**Expected Behavior:**
1. GPT calls `searchBusinessesByLocation` with NYC coordinates
2. GPT receives empty results
3. GPT gracefully informs user no businesses available in that area

---

## Part 3: Test Scenarios Checklist

### Location Search Tests

| Test | Input | Expected Result | ✓ |
|------|-------|-----------------|---|
| Basic search | Tempe coords, 10mi | 2-5 results | ☐ |
| Category filter | barbershop | Only barbershops | ☐ |
| Small radius | 1 mile | Fewer results | ☐ |
| No results | NYC coords | Empty array | ☐ |
| Distance sorting | Any coords | Sorted by distance | ☐ |

### Delegation Tests

| Test | Input | Expected Result | ✓ |
|------|-------|-----------------|---|
| Valid shop | bishops-tempe | Session created | ☐ |
| With context | intent + location | Context preserved | ☐ |
| Invalid shop | nonexistent-slug | 404 error | ☐ |

### Chat Tests

| Test | Input | Expected Result | ✓ |
|------|-------|-----------------|---|
| With session | valid session_id | Context aware | ☐ |
| First message | "book haircut" | Services offered | ☐ |
| Follow-up | time preference | Availability shown | ☐ |

### Error Handling Tests

| Test | Input | Expected Result | ✓ |
|------|-------|-----------------|---|
| Invalid coords | lat: 999 | 422 validation error | ☐ |
| Missing fields | no longitude | 422 validation error | ☐ |
| Negative radius | radius: -5 | 422 validation error | ☐ |

---

## Part 4: Debugging Tips

### Check Server Logs

Watch the uvicorn output for API calls:

```
INFO: POST /router/search-by-location - 200
INFO: POST /router/delegate - 200
INFO: POST /s/bishops-tempe/chat - 200
```

### Verify Geocoding

Test that coordinates are correct:

```python
# In Python shell
from app.geocoding import calculate_distance

# Tempe to Phoenix should be ~10-12 miles
dist = calculate_distance(33.4255, -111.9400, 33.4484, -112.0740)
print(f"Distance: {dist:.2f} miles")  # Should be ~10.5 miles
```

### Check Database

Verify shop locations:

```sql
SELECT slug, name, latitude, longitude, category 
FROM shops 
WHERE latitude IS NOT NULL
ORDER BY name;
```

### Test Individual Endpoints

```bash
# Location search
curl -X POST http://localhost:8000/router/search-by-location \
  -H "Content-Type: application/json" \
  -d '{"latitude": 33.4255, "longitude": -111.94, "radius_miles": 10}'

# Delegation
curl -X POST http://localhost:8000/router/delegate \
  -H "Content-Type: application/json" \
  -d '{"shop_slug": "bishops-tempe"}'

# Chat
curl -X POST http://localhost:8000/s/bishops-tempe/chat \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "What services do you offer?"}]}'
```

---

## Part 5: Common Issues & Solutions

### Issue: No shops returned in location search

**Cause**: Shops don't have coordinates

**Solution**:
```bash
python scripts/geocode_existing_shops.py --dry-run
python scripts/geocode_existing_shops.py
```

### Issue: ChatGPT not calling the API

**Cause**: OpenAPI schema issues or ngrok tunnel down

**Solution**:
1. Verify ngrok is running
2. Re-import the OpenAPI schema
3. Check the schema validates at editor.swagger.io

### Issue: 500 errors on chat endpoint

**Cause**: OpenAI API timeout or missing API key

**Solution**:
1. Check `OPENAI_API_KEY` is set in `.env`
2. Verify the key is valid
3. Check OpenAI status page

### Issue: Wrong distances calculated

**Cause**: Using wrong coordinate format (lat/lon swapped)

**Solution**:
Verify coordinates are in correct order:
- Latitude: -90 to 90 (e.g., 33.4255 for Tempe)
- Longitude: -180 to 180 (e.g., -111.94 for Tempe)

---

## Part 6: Performance Benchmarks

### Expected Response Times

| Endpoint | Target | Acceptable |
|----------|--------|------------|
| `/router/search-by-location` | < 100ms | < 500ms |
| `/router/delegate` | < 50ms | < 200ms |
| `/s/{slug}/chat` | < 3s | < 10s |

### Load Testing

Use the test script to measure response times:

```bash
python scripts/test_routergpt_api.py -v --test location-search
```

---

## Part 7: Production Checklist

Before going to production:

- [ ] Remove test data (`test-owner-routergpt` shops)
- [ ] Update OpenAPI schema with production URL
- [ ] Enable rate limiting on router endpoints
- [ ] Add monitoring/alerting for API errors
- [ ] Review security of location data
- [ ] Document API versioning strategy
