# RouterGPT API Documentation

## Overview

RouterGPT is a discovery and delegation layer that enables ChatGPT Custom GPTs to find nearby businesses and hand off to shop-specific booking agents.

**Base URL**: `https://your-domain.com` (or `http://localhost:8000` for development)

**Version**: Phase 3 - Location-Based Discovery

---

## Authentication

Currently, RouterGPT endpoints are **public** and do not require authentication. Rate limiting is enforced per IP address.

For production, consider:
- API key authentication for Custom GPT integrations
- OAuth 2.0 for user-specific operations
- JWT tokens for session management

---

## Rate Limits

| Endpoint | Rate Limit | Window |
|----------|------------|--------|
| `POST /router/search-by-location` | 20 requests | 60 seconds |
| `POST /router/delegate` | 10 requests | 60 seconds |

### Rate Limit Headers

All responses include rate limit information:

```http
X-RateLimit-Limit: 20
X-RateLimit-Remaining: 15
X-RateLimit-Reset: 1735862400
```

### Rate Limit Exceeded Response

**Status**: `429 Too Many Requests`

```json
{
  "error": "Rate limit exceeded",
  "message": "Too many requests. Limit: 20 per 60s",
  "retry_after": 45,
  "reset_time": "2024-01-22T18:30:00Z",
  "limit": 20,
  "window_seconds": 60
}
```

---

## Endpoints

### 1. Search Businesses by Location

Find nearby businesses based on geographic coordinates.

**Endpoint**: `POST /router/search-by-location`

**Rate Limit**: 20 requests per minute

#### Request Body

```json
{
  "latitude": 33.4255,
  "longitude": -111.9400,
  "radius_miles": 5.0,
  "category": "barbershop",
  "query": "men's haircut"
}
```

**Parameters**:

| Field | Type | Required | Constraints | Description |
|-------|------|----------|-------------|-------------|
| `latitude` | float | Yes | -90 to 90 | Latitude coordinate |
| `longitude` | float | Yes | -180 to 180 | Longitude coordinate |
| `radius_miles` | float | No (default: 5.0) | 0 to 50 | Search radius in miles |
| `category` | string | No | - | Filter by category (e.g., "barbershop", "salon") |
| `query` | string | No | - | Additional text search filter |

#### Success Response

**Status**: `200 OK`

```json
{
  "query": "Businesses within 5.0 miles in category 'barbershop'",
  "latitude": 33.4255,
  "longitude": -111.94,
  "radius_miles": 5.0,
  "results": [
    {
      "business_id": 15,
      "slug": "bishops-barbershop-tempe",
      "name": "Bishop's Barbershop Tempe",
      "category": "barbershop",
      "address": "123 Mill Avenue, Tempe, AZ 85281",
      "timezone": "America/Phoenix",
      "primary_phone": "+1-480-555-0101",
      "distance_miles": 0.25,
      "confidence": 0.95
    },
    {
      "business_id": 18,
      "slug": "mesa-cuts",
      "name": "Mesa Cuts",
      "category": "barbershop",
      "address": "555 Main Street, Mesa, AZ 85201",
      "timezone": "America/Phoenix",
      "primary_phone": "+1-480-555-0105",
      "distance_miles": 3.7,
      "confidence": 0.26
    }
  ],
  "total_count": 2
}
```

#### Error Responses

**422 Unprocessable Entity** - Invalid input

```json
{
  "detail": [
    {
      "type": "less_than_equal",
      "loc": ["body", "latitude"],
      "msg": "Input should be less than or equal to 90",
      "input": 999.0
    }
  ]
}
```

#### Example Usage

```bash
curl -X POST https://your-domain.com/router/search-by-location \
  -H "Content-Type: application/json" \
  -d '{
    "latitude": 33.4255,
    "longitude": -111.94,
    "radius_miles": 10,
    "category": "barbershop"
  }'
```

---

### 2. Delegate to Shop

Hand off a customer to a specific shop's booking agent with context.

**Endpoint**: `POST /router/delegate`

**Rate Limit**: 10 requests per minute

#### Request Body

```json
{
  "shop_slug": "bishops-barbershop-tempe",
  "customer_context": {
    "intent": "haircut",
    "location": {
      "lat": 33.4255,
      "lon": -111.94
    },
    "preferences": {
      "stylist": "Marcus",
      "time_preference": "morning"
    }
  }
}
```

**Parameters**:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `shop_slug` | string | Yes | URL-safe shop identifier |
| `customer_context` | object | No | Context to pass to shop agent |
| `customer_context.intent` | string | No | Customer's stated intent (e.g., "haircut") |
| `customer_context.location` | object | No | Customer's location coordinates |
| `customer_context.preferences` | object | No | Any additional preferences |

#### Success Response

**Status**: `200 OK`

```json
{
  "success": true,
  "shop_slug": "bishops-barbershop-tempe",
  "shop_name": "Bishop's Barbershop Tempe",
  "session_id": "52fe2139-bc0a-4dc1-bf1d-2f0a4453801b",
  "initial_message": "Welcome to Bishop's Barbershop Tempe! I understand you're looking for haircut. We offer Men's Haircut, Beard Trim, Hot Towel Shave and more. What would you like to book today?",
  "available_services": [
    {
      "id": 45,
      "name": "Men's Haircut",
      "duration_minutes": 30,
      "price_cents": 3500,
      "price_display": "$35.00"
    },
    {
      "id": 46,
      "name": "Beard Trim",
      "duration_minutes": 15,
      "price_cents": 2000,
      "price_display": "$20.00"
    }
  ]
}
```

**Response Fields**:

| Field | Type | Description |
|-------|------|-------------|
| `success` | boolean | Always `true` on success |
| `shop_slug` | string | Shop identifier for routing |
| `shop_name` | string | Display name of the shop |
| `session_id` | string (UUID) | Unique session ID for tracking |
| `initial_message` | string | Greeting message to show customer |
| `available_services` | array | List of services offered |

#### Error Responses

**404 Not Found** - Shop doesn't exist

```json
{
  "detail": "Shop not found: invalid-shop-slug"
}
```

#### Next Steps After Delegation

After delegation, route subsequent customer messages to:

```
POST /s/{shop_slug}/chat
```

Include the `session_id` in requests to maintain context:

```json
{
  "messages": [
    {
      "role": "user",
      "content": "I'd like to book a haircut with Marcus tomorrow at 2pm"
    }
  ],
  "router_session_id": "52fe2139-bc0a-4dc1-bf1d-2f0a4453801b",
  "router_intent": "haircut",
  "customer_location": {
    "lat": 33.4255,
    "lon": -111.94
  }
}
```

#### Example Usage

```bash
curl -X POST https://your-domain.com/router/delegate \
  -H "Content-Type: application/json" \
  -d '{
    "shop_slug": "bishops-barbershop-tempe",
    "customer_context": {
      "intent": "haircut",
      "location": {"lat": 33.4255, "lon": -111.94}
    }
  }'
```

---

### 3. Shop Chat Endpoint

Continue the conversation with a shop's booking agent.

**Endpoint**: `POST /s/{shop_slug}/chat`

**Rate Limit**: None (handled by shop-specific rate limiting)

#### Request Body

```json
{
  "messages": [
    {
      "role": "user",
      "content": "I'd like to book a men's haircut tomorrow at 2pm"
    }
  ],
  "router_session_id": "52fe2139-bc0a-4dc1-bf1d-2f0a4453801b",
  "router_intent": "haircut",
  "customer_location": {
    "lat": 33.4255,
    "lon": -111.94
  }
}
```

**Parameters**:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `messages` | array | Yes | Conversation history |
| `messages[].role` | string | Yes | "user" or "assistant" |
| `messages[].content` | string | Yes | Message content |
| `router_session_id` | string (UUID) | No | Session ID from delegation |
| `router_intent` | string | No | Customer's intent |
| `customer_location` | object | No | Customer's coordinates |

#### Success Response

**Status**: `200 OK`

```json
{
  "reply": "Great! I can help you book a men's haircut. Which stylist would you prefer? We have Marcus, Tony, and Derek available.",
  "action": null,
  "data": null,
  "chips": ["Marcus", "Tony", "Derek", "No preference"],
  "shop_slug": "bishops-barbershop-tempe",
  "shop_name": "Bishop's Barbershop Tempe"
}
```

---

## Error Codes

| Status Code | Meaning | Common Causes |
|-------------|---------|---------------|
| 400 | Bad Request | Invalid JSON, malformed request |
| 404 | Not Found | Shop doesn't exist |
| 422 | Unprocessable Entity | Validation errors (coordinates out of range, etc.) |
| 429 | Too Many Requests | Rate limit exceeded |
| 500 | Internal Server Error | Server-side error |

---

## Best Practices

### 1. Location Detection

Always obtain user permission before accessing location. Use ChatGPT's built-in location detection when possible.

### 2. Error Handling

```python
try:
    response = await http_client.post(
        "/router/search-by-location",
        json={"latitude": lat, "longitude": lon, "radius_miles": 5}
    )
    response.raise_for_status()
except httpx.HTTPStatusError as e:
    if e.response.status_code == 429:
        retry_after = e.response.headers.get("Retry-After")
        # Wait and retry
    elif e.response.status_code == 422:
        # Invalid input - show error to user
```

### 3. Session Management

Always store and pass the `session_id` from delegation through subsequent chat requests to maintain analytics tracking.

### 4. Distance Display

Display distances in a user-friendly format:

```python
def format_distance(miles):
    if miles < 0.1:
        return "< 0.1 mi"
    elif miles < 1:
        return f"{miles:.1f} mi"
    else:
        return f"{miles:.0f} mi"
```

### 5. Confidence Scores

Use confidence scores to highlight best matches:

```python
if result['confidence'] > 0.8:
    recommendation = "Highly recommended"
elif result['confidence'] > 0.5:
    recommendation = "Good match"
else:
    recommendation = "Available nearby"
```

---

## Analytics & Monitoring

RouterGPT automatically tracks:

- **Search Events**: Coordinates, radius, results count
- **Delegation Events**: Shop selected, customer intent, distance
- **Booking Completions**: Final conversion tracking

View analytics via SQL queries:

```sql
-- Daily usage summary
SELECT * FROM router_usage_summary
WHERE date >= CURRENT_DATE - INTERVAL '7 days'
ORDER BY date DESC;

-- Shop discovery leaderboard
SELECT * FROM router_shop_discovery
ORDER BY times_discovered DESC
LIMIT 20;

-- Conversion funnel
SELECT * FROM router_conversion_funnel
ORDER BY date DESC
LIMIT 30;
```

---

## Support

For technical support or questions:
- **GitHub Issues**: [github.com/your-repo/issues](https://github.com)
- **Email**: support@convo.ai
- **Documentation**: [docs.convo.ai](https://docs.convo.ai)
