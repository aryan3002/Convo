# ChatGPT Actions Setup Guide

This guide walks you through setting up and testing the ConvoAI ChatGPT Custom GPT integration for customer booking.

## Overview

The integration allows customers to book appointments directly through ChatGPT by mentioning @ConvoAI (or your custom GPT name). The system uses a **quote → confirm** flow to prevent hallucinated bookings.

### Flow Summary
1. Customer asks ChatGPT to book an appointment
2. ChatGPT calls `/public/availability` to find open slots
3. ChatGPT calls `/public/booking/quote` to create a quote
4. Customer reviews the quote details
5. ChatGPT calls `/public/booking/confirm` to finalize the booking

---

## Prerequisites

- Python 3.11+ with the backend dependencies installed
- PostgreSQL database (Neon or local)
- ngrok account (free tier works) for development
- OpenAI ChatGPT Plus account (for Custom GPT creation)

---

## Step 1: Start the Backend Server

### Development (Local + ngrok)

```bash
# Navigate to backend directory
cd /Users/aryantripathi/Convo-main/Backend

# Activate virtual environment
source .venv/bin/activate

# Start the server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The server should start at `http://localhost:8000`.

### Verify Server is Running

```bash
curl http://localhost:8000/health
# Should return: {"status": "healthy"}
```

---

## Step 2: Set Up ngrok Tunnel

ngrok creates a public HTTPS URL that tunnels to your local server.

### Install ngrok (if not installed)

```bash
# macOS with Homebrew
brew install ngrok

# Or download from https://ngrok.com/download
```

### Start ngrok Tunnel

```bash
# Start tunnel to port 8000
ngrok http 8000
```

You'll see output like:
```
Forwarding    https://abc123xyz.ngrok-free.dev -> http://localhost:8000
```

**Copy the HTTPS URL** (e.g., `https://abc123xyz.ngrok-free.dev`) - you'll need this for ChatGPT.

### Important ngrok Notes

- Free tier URLs change each time you restart ngrok
- Consider ngrok paid plan for stable URLs in production
- Add ngrok URL to `ALLOWED_ORIGINS` in `.env` if needed

---

## Step 3: Test the API with curl

Before configuring ChatGPT, verify the API works through the ngrok tunnel.

### Set Variables

```bash
# Replace with your actual values
NGROK_URL="https://your-ngrok-url.ngrok-free.dev"
API_KEY="convo-chatgpt-booking-key-Ax7mN9pQ2rS4tU6vW8xY0z"
```

### Test Business Info

```bash
curl -X GET "${NGROK_URL}/public/business" \
  -H "X-API-Key: ${API_KEY}" \
  -H "Content-Type: application/json"
```

Expected response:
```json
{
  "business_name": "Bishops Tempe",
  "timezone": "America/Phoenix",
  "working_hours_start": "09:00",
  "working_hours_end": "17:00",
  "working_days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
}
```

### Test Services List

```bash
curl -X GET "${NGROK_URL}/public/services" \
  -H "X-API-Key: ${API_KEY}"
```

### Test Stylists List

```bash
curl -X GET "${NGROK_URL}/public/stylists" \
  -H "X-API-Key: ${API_KEY}"
```

### Test Availability

```bash
# Replace date with a future date
curl -X GET "${NGROK_URL}/public/availability?service_id=1&date=2025-01-27" \
  -H "X-API-Key: ${API_KEY}"
```

### Test Quote Creation

```bash
curl -X POST "${NGROK_URL}/public/booking/quote" \
  -H "X-API-Key: ${API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "service_id": 1,
    "stylist_id": 1,
    "date": "2025-01-27",
    "start_time": "11:00",
    "customer_name": "Test User",
    "customer_email": "test@example.com"
  }'
```

Save the `quote_token` from the response.

### Test Booking Confirmation

```bash
# Replace with actual quote_token from previous response
curl -X POST "${NGROK_URL}/public/booking/confirm" \
  -H "X-API-Key: ${API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "quote_token": "YOUR_QUOTE_TOKEN_HERE"
  }'
```

---

## Step 4: Configure ChatGPT Custom GPT

### 4.1 Create the Custom GPT

1. Go to [ChatGPT](https://chat.openai.com)
2. Click your profile → **My GPTs** → **Create a GPT**
3. Click **Configure** tab

### 4.2 Set GPT Instructions

In the **Instructions** field, paste:

```
You are ConvoAI, a booking assistant for Bishops Tempe hair salon.

## Your Role
- Help customers book haircuts, beard trims, and styling services
- Check availability and create booking quotes
- Confirm bookings when the customer approves

## Booking Flow (ALWAYS FOLLOW)
1. Ask what service they want (or show options)
2. Ask for their preferred date
3. Call checkAvailability to see open slots
4. Present available times to the customer
5. When they choose, call createBookingQuote with their details
6. ALWAYS show the quote details and ask for confirmation
7. Only call confirmBooking AFTER the customer explicitly confirms

## Important Rules
- NEVER skip the quote step - always create a quote first
- NEVER confirm a booking without customer approval
- Quotes expire in 10 minutes
- Either email OR phone is required for booking
- Business hours: 9 AM - 5 PM, Monday-Saturday
- Timezone: America/Phoenix (Arizona time)

## When Showing Availability
- Show the local time (start_time_local), not UTC
- Group by stylist if multiple stylists available
- Mention the slot_id is available for quick booking

## When Creating Quotes
- You can use slot_id from availability OR date/time/stylist
- Always ask for customer name and contact (email or phone)
- Show the full quote details including price

## Error Handling
- If a slot is taken (409 error), apologize and offer alternatives
- If quote expired (404), ask to start over
- Always be helpful and suggest alternatives
```

### 4.3 Add Actions

1. Click **Create new action**
2. Choose **Import from URL** or paste the OpenAPI spec
3. For development, use the contents of `openapi_chatgpt_dev_ngrok.yaml`
4. Replace `{{NGROK_URL}}` with your actual ngrok URL

**Or manually paste:**

Copy the entire contents of `/Backend/openapi_chatgpt_dev_ngrok.yaml` and replace the `{{NGROK_URL}}` placeholder with your ngrok URL.

### 4.4 Configure Authentication

1. In the Actions section, click **Authentication**
2. Select **API Key**
3. Auth Type: **Custom**
4. Custom Header Name: `X-API-Key`
5. API Key: `convo-chatgpt-booking-key-Ax7mN9pQ2rS4tU6vW8xY0z`

### 4.5 Privacy Policy (Required for Publishing)

If you plan to publish the GPT, you'll need a privacy policy URL. For testing, you can use a placeholder.

### 4.6 Save and Test

1. Click **Save** (or **Update**)
2. Choose visibility (Only me, Anyone with link, or Public)
3. Test with prompts like:
   - "I'd like to book a haircut"
   - "What services do you offer?"
   - "Show me availability for tomorrow"

---

## Step 5: Testing the Integration

### Test Conversation Flow

**User:** "I want to book a men's haircut for tomorrow"

**Expected GPT behavior:**
1. Calls `listServices` to confirm service
2. Calls `checkAvailability` with service_id and tomorrow's date
3. Shows available slots
4. Asks which slot they prefer

**User:** "I'll take the 11 AM slot with Alex"

**Expected GPT behavior:**
1. Asks for name and contact info
2. Calls `createBookingQuote`
3. Shows quote details (price, time, stylist)
4. Asks "Would you like me to confirm this booking?"

**User:** "Yes, please confirm"

**Expected GPT behavior:**
1. Calls `confirmBooking` with quote_token
2. Shows confirmation with booking ID
3. Reminds about appointment details

### Test Error Cases

1. **Past date:** Try booking for yesterday
2. **Closed day:** Try booking for Sunday
3. **No contact info:** Try creating quote without email/phone
4. **Expired quote:** Wait 11 minutes, then try to confirm
5. **Duplicate confirmation:** Confirm same quote twice (should work - idempotent)

---

## Debugging

### Check Server Logs

Watch the uvicorn terminal for request logs and any errors.

### Common Issues

| Issue | Solution |
|-------|----------|
| 401 Unauthorized | Check API key is correct in ChatGPT Actions |
| 502 Bad Gateway | Check ngrok tunnel is running |
| Connection refused | Check backend server is running |
| CORS errors | Add ngrok URL to ALLOWED_ORIGINS in .env |
| Quote expired | Quotes only last 10 minutes - start over |

### ngrok Inspect Tool

Visit `http://127.0.0.1:4040` while ngrok is running to see all requests and responses. This is invaluable for debugging.

### Test API Key Manually

```bash
# Should return 401
curl -X GET "${NGROK_URL}/public/business" \
  -H "X-API-Key: wrong-key"

# Should return 200
curl -X GET "${NGROK_URL}/public/business" \
  -H "X-API-Key: ${API_KEY}"
```

---

## Production Deployment

### Use Production OpenAPI Spec

For production, use `openapi_chatgpt_prod.yaml`:
1. Replace `{{PROD_API_BASE_URL}}` with your production backend URL
2. Update the API key to a production key
3. Ensure HTTPS is properly configured

### Environment Variables

```bash
# Production .env
PUBLIC_BOOKING_API_KEY=your-secure-production-key
PUBLIC_API_BASE=https://api.yourdomain.com
ALLOWED_ORIGINS=https://chat.openai.com,https://yourdomain.com
```

### Security Checklist

- [ ] Use strong, unique API key for production
- [ ] Enable rate limiting
- [ ] Set up monitoring/alerting
- [ ] Review CORS settings
- [ ] Enable request logging
- [ ] Set up SSL certificate

---

## Files Reference

| File | Purpose |
|------|---------|
| `public_booking.py` | API endpoints implementation |
| `openapi_chatgpt_prod.yaml` | Production OpenAPI spec |
| `openapi_chatgpt_dev_ngrok.yaml` | Development OpenAPI spec (ngrok) |
| `CHATGPT_INTEGRATION.md` | Architecture documentation |

---

## Support

For issues with:
- **Backend/API:** Check server logs, verify database connection
- **ChatGPT Actions:** Review the Actions configuration in GPT Builder
- **ngrok:** Visit http://127.0.0.1:4040 for detailed request inspection
