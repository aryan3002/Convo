# Phase 5: RouterGPT - Discovery & Delegation Layer

## Status: ✅ COMPLETE

RouterGPT is a **discovery-only** layer that helps ChatGPT find and route to the appropriate business-specific GPT. It **never books appointments** - it only discovers businesses and prepares handoff packages for delegation.

## Design Principles

| Principle | Description |
|-----------|-------------|
| **Discovery Only** | RouterGPT searches and describes - never creates or modifies data |
| **Multi-Tenant Safe** | Only exposes public shop information; no cross-tenant data leaks |
| **Stateless** | Each request is independent; no session state |
| **Delegation** | Always routes to `/s/{slug}/...` endpoints for actual booking |

## Tools / Endpoints

### Tool 1: `search_businesses`

**Endpoint:** `GET /router/search`

Search for businesses matching user criteria.

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `query` | string | Yes | Search query (name, category, location keywords) |
| `location` | string | No | Location filter (city, state, address text) |
| `category` | string | No | Category filter (e.g., "barbershop", "salon") |
| `limit` | int | No | Max results (default: 10, max: 50) |

**Response:**

```json
{
  "query": "bishops",
  "results": [
    {
      "business_id": 1,
      "slug": "bishops-tempe",
      "name": "Bishops Tempe",
      "category": "barbershop",
      "address": "123 Main St, Tempe, AZ",
      "timezone": "America/Phoenix",
      "primary_phone": "+16234048440",
      "confidence": 0.95
    }
  ],
  "total_count": 1
}
```

**Example:**

```bash
# Search by name
curl "http://localhost:8000/router/search?query=bishops"

# Search with location filter
curl "http://localhost:8000/router/search?query=haircut&location=tempe"

# Search by category
curl "http://localhost:8000/router/search?query=haircut&category=barbershop&limit=5"
```

---

### Tool 2: `get_business_summary`

**Endpoint:** `GET /router/business/{identifier}`

Get detailed information about a specific business.

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `identifier` | string | Business ID (numeric) OR slug |

**Response:**

```json
{
  "business_id": 1,
  "slug": "bishops-tempe",
  "name": "Bishops Tempe",
  "timezone": "America/Phoenix",
  "address": "123 Main St, Tempe, AZ",
  "category": "barbershop",
  "primary_phone": "+16234048440",
  "service_count": 12,
  "stylist_count": 4,
  "capabilities": {
    "supports_chat": true,
    "supports_voice": true,
    "supports_owner_chat": true
  },
  "chat_endpoint": "/s/bishops-tempe/chat",
  "owner_chat_endpoint": "/s/bishops-tempe/owner/chat",
  "services_endpoint": "/s/bishops-tempe/services"
}
```

**Example:**

```bash
# By ID
curl "http://localhost:8000/router/business/1"

# By slug
curl "http://localhost:8000/router/business/bishops-tempe"
```

---

### Tool 3: `handoff_to_business_gpt`

**Endpoint:** `POST /router/handoff`

Generate a handoff package for delegating to a business-specific GPT.

**Request Body:**

```json
{
  "business_id": 1,
  "slug": "bishops-tempe",
  "conversation_context": [
    {"role": "user", "content": "I want to book a haircut for tomorrow"}
  ],
  "user_intent": "book haircut"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `business_id` | int | No* | Business ID |
| `slug` | string | No* | Business slug |
| `conversation_context` | array | No | Previous messages to pass along |
| `user_intent` | string | No | Explicit user intent |

*Must provide either `business_id` OR `slug`.

**Response:**

```json
{
  "business_id": 1,
  "slug": "bishops-tempe",
  "name": "Bishops Tempe",
  "recommended_endpoint": "/s/bishops-tempe/chat",
  "payload_template": {
    "messages": [
      {"role": "user", "content": "I want to book a haircut for tomorrow"}
    ],
    "metadata": {
      "shop_slug": "bishops-tempe",
      "shop_name": "Bishops Tempe",
      "shop_id": 1,
      "timezone": "America/Phoenix",
      "source": "router_gpt_handoff"
    }
  },
  "explanation": "Delegating to Bishops Tempe GPT for: book haircut. Call POST /s/bishops-tempe/chat with the payload template."
}
```

**Example:**

```bash
curl -X POST "http://localhost:8000/router/handoff" \
  -H "Content-Type: application/json" \
  -d '{
    "slug": "bishops-tempe",
    "conversation_context": [
      {"role": "user", "content": "I want to book a haircut"}
    ],
    "user_intent": "book haircut"
  }'
```

---

## RouterGPT Info Endpoint

**Endpoint:** `GET /router/info`

Returns metadata about RouterGPT and its available tools.

```bash
curl "http://localhost:8000/router/info"
```

```json
{
  "name": "RouterGPT",
  "version": "1.0.0",
  "description": "Discovery and delegation layer for multi-tenant booking",
  "capabilities": {
    "books_appointments": false,
    "modifies_data": false,
    "discovery_only": true
  },
  "tools": [
    {
      "name": "search_businesses",
      "endpoint": "GET /router/search",
      "description": "Search for businesses by name, location, or category"
    },
    {
      "name": "get_business_summary",
      "endpoint": "GET /router/business/{id}",
      "description": "Get detailed information about a specific business"
    },
    {
      "name": "handoff_to_business_gpt",
      "endpoint": "POST /router/handoff",
      "description": "Generate handoff package for delegation to business GPT"
    }
  ],
  "delegation_pattern": "/s/{slug}/chat"
}
```

---

## Flow Example

1. **User:** "I want to book a haircut in Tempe"

2. **ChatGPT calls RouterGPT:**
   ```
   GET /router/search?query=haircut&location=tempe
   ```

3. **RouterGPT returns** list of matching businesses with confidence scores

4. **ChatGPT** presents options to user or auto-selects highest confidence

5. **User:** selects "Bishops Tempe"

6. **ChatGPT calls RouterGPT:**
   ```
   POST /router/handoff
   {
     "slug": "bishops-tempe",
     "user_intent": "book haircut"
   }
   ```

7. **RouterGPT returns** handoff package with endpoint + payload template

8. **ChatGPT calls Business GPT:**
   ```
   POST /s/bishops-tempe/chat
   {
     "messages": [{"role": "user", "content": "I want to book a haircut"}]
   }
   ```

9. **Business GPT** handles the actual booking conversation

---

## Safety & Security

### What RouterGPT Does NOT Do

- ❌ Create appointments or bookings
- ❌ Modify any database records
- ❌ Access private customer data
- ❌ Handle payment or PII
- ❌ Authenticate users

### Data Exposed

RouterGPT only exposes **public shop information**:

- Shop name, slug, category
- Business address
- Phone numbers (for contact purposes)
- Service/stylist counts (not details)
- Timezone

### Cross-Tenant Safety

- Each search/handoff is stateless
- No session data stored
- Handoff includes only the target shop's context
- Delegation always goes through `/s/{slug}/...` which enforces tenant isolation

---

## File Changes (Phase 5)

### New Files

| File | Description |
|------|-------------|
| `app/router_gpt.py` | RouterGPT router with all three tools |
| `tests/test_phase5_routergpt.py` | Phase 5 test suite |
| `PHASE5_ROUTERGPT.md` | This documentation |

### Modified Files

| File | Changes |
|------|---------|
| `app/main.py` | Registered `router_gpt_router` |
| `requirements.txt` | Added `pytest-asyncio` |
| `pytest.ini` | Created with `asyncio_mode = auto` |
| `PHASE4_ROUTING.md` | Fixed phone number documentation |

---

## Testing

```bash
# Run Phase 5 tests
pytest tests/test_phase5_routergpt.py -v

# Run all tests
pytest -v

# Quick verification
python3 -c "from app.main import app; print([r.path for r in app.routes if '/router' in r.path])"
```

### Manual Testing

```bash
# Start server
uvicorn app.main:app --reload --port 8000

# Test search
curl "http://localhost:8000/router/search?query=bishops"

# Test business summary
curl "http://localhost:8000/router/business/bishops-tempe"

# Test handoff
curl -X POST "http://localhost:8000/router/handoff" \
  -H "Content-Type: application/json" \
  -d '{"slug": "bishops-tempe", "user_intent": "book haircut"}'

# Check OpenAPI docs
open http://localhost:8000/docs#/router-gpt
```

---

## Future Enhancements (Not in Phase 5)

1. **Geo-based search** - Use PostGIS for actual location-aware search
2. **Search ranking ML** - Train a model on user selection patterns
3. **Business verification** - Verified/featured business badges
4. **Availability preview** - Show next available slot in search results
5. **Rate limiting** - Per-IP/per-key rate limits on search

---

## Verification Checklist

- [x] `python3 -c "from app.main import app"` succeeds
- [x] RouterGPT routes appear in `app.routes`
- [x] `/router/search` returns results for seeded shop
- [x] `/router/business/{id}` returns consistent schema
- [x] `/router/handoff` returns correct `/s/{slug}/chat` endpoint
- [x] Tests pass: `pytest tests/test_phase5_routergpt.py -v`
- [x] No booking/data modification code in `router_gpt.py`
