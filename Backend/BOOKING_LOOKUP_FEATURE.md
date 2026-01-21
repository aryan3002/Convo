# Booking Lookup Feature

## Overview
The booking lookup feature allows customers to check their recent bookings by providing their email address or phone number, without needing to remember their booking ID.

## API Endpoint

### `GET /public/bookings/lookup`

**Query Parameters:**
- `email` (optional): Customer email address
- `phone` (optional): Customer phone number (any format)

**Note:** At least one of `email` or `phone` must be provided.

**Response:**
```json
{
  "matches": [
    {
      "booking_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "status": "CONFIRMED",
      "service_name": "Men's Haircut",
      "stylist_name": "Alex",
      "date_local": "Wednesday, January 22, 2026",
      "start_time_local": "11:00 AM",
      "end_time_local": "11:30 AM",
      "created_at": "2026-01-20T20:00:00+00:00"
    }
  ],
  "message": "Found 1 booking for the provided contact information."
}
```

**Rate Limiting:**
- 20 requests per 10 minutes per IP address
- Returns 429 status code if limit exceeded

**Security:**
- Requires `X-API-Key` header
- Returns minimal booking information only (no PII beyond what's necessary)
- Maximum 5 most recent bookings returned

## ChatGPT GPT Instructions Update

Add the following section to your Custom GPT's instructions:

```markdown
## Checking Existing Bookings

When a customer wants to check their booking(s):

1. Ask for either their email address OR phone number
   - "To look up your booking, I'll need either your email address or phone number."

2. Use the `lookupBookings` action with the provided contact information

3. Handle the results appropriately:
   - **No bookings found:** 
     - "I couldn't find any bookings with that information. Could you double-check your email/phone? Or would you like to create a new booking?"
   
   - **One booking found:**
     - Display the booking details clearly
     - Offer to show the full details using the booking_id: "Would you like to see the complete details or make any changes?"
   
   - **Multiple bookings found:**
     - List all bookings with dates and services
     - Ask which one they'd like to know more about
     - Example: "I found 3 bookings for you:
       1. Men's Haircut with Alex on Wednesday, January 22 at 11:00 AM
       2. Beard Trim with Jamie on Friday, January 24 at 2:00 PM
       3. Haircut & Beard Combo with Alex on Monday, January 27 at 10:00 AM
       
       Which one would you like to check?"

4. If rate limit is hit (429 error):
   - "I'm currently experiencing high demand. Please try again in a few minutes."

**Important:** Never ask for a booking ID first. Always start with email or phone, which is easier for customers to remember.
```

## Test Commands

### Setup
```bash
# API key for authentication
API_KEY="convo-chatgpt-booking-key-Ax7mN9pQ2rS4tU6vW8xY0z"

# Base URL (development with ngrok)
BASE_URL="https://entomological-herminia-cyanitic.ngrok-free.dev"

# Or for local testing
BASE_URL="http://localhost:8000"
```

### 1. Lookup by Email
```bash
curl -X GET "${BASE_URL}/public/bookings/lookup?email=john.smith@example.com" \
  -H "X-API-Key: ${API_KEY}" \
  -H "Content-Type: application/json" | jq
```

### 2. Lookup by Phone
```bash
curl -X GET "${BASE_URL}/public/bookings/lookup?phone=+1-555-123-4567" \
  -H "X-API-Key: ${API_KEY}" \
  -H "Content-Type: application/json" | jq
```

### 3. Lookup by Both (either matches)
```bash
curl -X GET "${BASE_URL}/public/bookings/lookup?email=john.smith@example.com&phone=+1-555-123-4567" \
  -H "X-API-Key: ${API_KEY}" \
  -H "Content-Type: application/json" | jq
```

### 4. Test Error Cases

**Missing both email and phone:**
```bash
curl -X GET "${BASE_URL}/public/bookings/lookup" \
  -H "X-API-Key: ${API_KEY}" \
  -H "Content-Type: application/json" | jq
```

**Expected Response (400):**
```json
{
  "detail": "Must provide either email or phone to lookup bookings."
}
```

### 5. Test Rate Limiting
Run this command 21+ times quickly to trigger rate limit:
```bash
for i in {1..25}; do
  echo "Request $i:"
  curl -X GET "${BASE_URL}/public/bookings/lookup?email=test@example.com" \
    -H "X-API-Key: ${API_KEY}" \
    -H "Content-Type: application/json" \
    -w "\nHTTP Status: %{http_code}\n" \
    -s | head -n 3
  echo "---"
done
```

**Expected:** First 20 requests succeed (200), requests 21+ return 429.

### 6. Test with Real Data

First, create a booking (see CHATGPT_ACTIONS_SETUP.md for full flow), then look it up:

```bash
# After creating a booking with email john.smith@example.com
curl -X GET "${BASE_URL}/public/bookings/lookup?email=john.smith@example.com" \
  -H "X-API-Key: ${API_KEY}" \
  -H "Content-Type: application/json" | jq
```

## Implementation Details

### Rate Limiting
- **Simple in-memory implementation** using `dict[ip, list[datetime]]`
- Stores request timestamps per IP address
- Automatically cleans up old entries (> 10 minutes)
- Resets on server restart (acceptable for demo/dev)

**For Production:**
- Use Redis with sliding window algorithm
- Consider per-user rate limits in addition to per-IP
- Add distributed rate limiting for multi-instance deployments

### Security Considerations
- ✅ Requires API key authentication
- ✅ Returns minimal information only (no full PII)
- ✅ Rate limited to prevent abuse
- ✅ Uses parameterized queries (SQL injection safe)
- ✅ Normalizes email/phone input

**Not Implemented (Demo-level):**
- Email verification before showing bookings
- Phone verification via SMS
- CAPTCHA for repeated failures
- Audit logging of lookup requests

### Data Privacy
The endpoint returns only essential booking information:
- booking_id
- status
- service_name
- stylist_name
- date_local, start_time_local, end_time_local
- created_at

**Excluded PII:**
- customer_name (already known by requester)
- full customer_email (already provided by requester)
- full customer_phone (already provided by requester)
- price information (not essential for lookup)

## Database Impact

**Query Pattern:**
```sql
SELECT bookings.*, services.name, stylists.name
FROM bookings
JOIN services ON bookings.service_id = services.id
JOIN stylists ON bookings.stylist_id = stylists.id
WHERE (bookings.customer_email = ? OR bookings.customer_phone = ?)
ORDER BY bookings.created_at DESC
LIMIT 5
```

**Indexes Recommended:**
```sql
-- If not already indexed
CREATE INDEX idx_bookings_customer_email ON bookings(customer_email);
CREATE INDEX idx_bookings_customer_phone ON bookings(customer_phone);
CREATE INDEX idx_bookings_created_at ON bookings(created_at DESC);
```

## Monitoring

**Key Metrics to Track:**
- Lookup request rate per minute
- Rate limit hit rate (429 responses)
- Average number of bookings returned per lookup
- Response time percentiles (p50, p95, p99)
- Error rate (400, 404, 500)

**Alerts:**
- Rate limit hit rate > 10% (may indicate abuse or legitimate high demand)
- Error rate > 5%
- p95 response time > 500ms

## Future Enhancements

1. **Email Verification:**
   - Send verification code to email before showing bookings
   - Store verification tokens with expiration

2. **SMS Verification:**
   - Send OTP to phone number
   - Integrate with Twilio or similar

3. **Customer Portal:**
   - Allow customers to manage all their bookings
   - Update contact information
   - Cancel/reschedule bookings

4. **Search Filters:**
   - Filter by date range
   - Filter by status (CONFIRMED, CANCELLED, etc.)
   - Filter by service type

5. **Booking History:**
   - Show all past bookings (not just recent 5)
   - Export booking history as PDF/CSV
