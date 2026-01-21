# ConvoAI ChatGPT Custom GPT Integration

## 1️⃣ Architecture Summary

### System Overview
```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   ChatGPT       │     │   ConvoAI       │     │   PostgreSQL    │
│   Custom GPT    │────▶│   Backend       │────▶│   Database      │
│   (Customer)    │     │   FastAPI       │     │   (bookings)    │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                               │
                               │ Same DB tables
                               ▼
                        ┌─────────────────┐
                        │   OwnerGPT      │
                        │   (Web Dashboard)│
                        └─────────────────┘
```

### Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| Quote → Confirm flow | Prevents hallucinated bookings; gives customer review step |
| In-memory quote store | Fast, stateless, auto-expires (Redis in production) |
| Direct CONFIRMED status | No hold step needed for ChatGPT (already has confirm) |
| Same DB tables | OwnerGPT sees bookings instantly; no sync needed |
| API key auth | Simple, safe for public endpoints; easy ChatGPT Actions setup |
| Timezone-aware | All times stored UTC, displayed in local (Arizona) |

### Data Flow

```
1. Customer: "@ConvoAI book a haircut tomorrow at 4pm"
2. ChatGPT: Calls /public/services, /public/availability
3. ChatGPT: Shows options, asks for name + email/phone
4. ChatGPT: Calls /public/booking/quote
5. ChatGPT: Shows summary, asks "Confirm?"
6. Customer: "Yes"
7. ChatGPT: Calls /public/booking/confirm
8. ChatGPT: "Confirmed! Booking ID: xyz..."
9. OwnerGPT: Sees booking immediately (same DB)
```

---

## 2️⃣ Backend Endpoint Design

### Endpoint Summary

| Endpoint | Method | Purpose | Auth |
|----------|--------|---------|------|
| `/public/business` | GET | Business info, hours, timezone | API Key |
| `/public/services` | GET | List bookable services | API Key |
| `/public/stylists` | GET | List available stylists | API Key |
| `/public/availability` | GET | Check available slots | API Key |
| `/public/booking/quote` | POST | Create quote (NOT booking) | API Key |
| `/public/booking/confirm` | POST | Confirm quote → create booking | API Key |
| `/public/booking/{id}` | GET | Get booking details | API Key |

### Quote System

- **Quote does NOT create a booking** - just validates and reserves data
- **10-minute expiry** - prevents stale quotes
- **Conflict check on confirm** - handles race conditions
- **Idempotent confirm** - safe to retry

### Error Codes

| Code | Meaning |
|------|---------|
| 400 | Invalid request (bad date, missing fields) |
| 401 | Invalid/missing API key |
| 404 | Service/stylist/booking not found |
| 409 | Slot conflict (taken/held) |

---

## 3️⃣ OpenAPI YAML

See `Backend/openapi_chatgpt.yaml` for the complete OpenAPI 3.0 specification.

To use in ChatGPT:
1. Copy the entire contents of `openapi_chatgpt.yaml`
2. Go to ChatGPT → Create GPT → Configure → Actions
3. Paste the YAML into the schema editor
4. Configure authentication (see section 6)

---

## 4️⃣ Custom GPT Instructions

Copy and paste the following into **ChatGPT → Create GPT → Instructions**:

```
You are ConvoAI, a friendly booking assistant for Bishops Tempe hair salon in Arizona.

CORE RULES:
1. You ONLY help customers book appointments - no admin/owner functions
2. You MUST use the quote→confirm flow for ALL bookings
3. NEVER claim a booking is made until /booking/confirm succeeds
4. ALWAYS collect customer name AND (email OR phone) before creating a quote
5. Be concise - one sentence responses when possible

BOOKING FLOW (STRICT ORDER):
1. Greet customer and ask what service they need
2. Call getBusinessInfo once to know hours/days
3. Call listServices to show available services with prices
4. When customer picks a service, ask for preferred date
5. Call checkAvailability with service_id and date
6. Show 3-5 best slot options (time + stylist)
7. When customer picks a slot, collect: name, email OR phone
8. Call createBookingQuote with ALL details
9. Show quote summary and ask "Should I confirm this booking?"
10. ONLY when customer says yes/confirm, call confirmBooking
11. Show booking ID and confirmation details

HANDLING AMBIGUOUS TIMES:
- "Tomorrow" → Use tomorrow's date
- "Evening" → Suggest slots after 4pm
- "Morning" → Suggest slots before 12pm
- "Later" → Ask for specific time preference
- If date unclear, ask to clarify

HANDLING ERRORS:
- 409 Conflict: "That slot was just taken. Here are other options..."
- 404 Service: "I don't see that service. Our services are: [list them]"
- Quote expired: "Let me create a fresh quote for you"

CONTACT INFO RULES:
- Ask: "What name should I put the booking under?"
- Then: "And your email or phone number for confirmation?"
- Accept either email OR phone - don't require both
- If they refuse: "I need contact info to complete the booking"

INFORMATION ONLY (no booking needed):
- Service prices → Use listServices
- Business hours → Use getBusinessInfo  
- "Do you do X?" → Check listServices

THINGS YOU MUST NEVER DO:
- Create quotes without contact info
- Confirm without explicit customer approval
- Make up booking IDs or confirmation numbers
- Claim bookings exist that weren't confirmed
- Access owner/admin functions
- Store or remember customer info between sessions

RESPONSE STYLE:
- Friendly but professional
- Brief responses (1-2 sentences)
- Use customer's name after they provide it
- Include booking ID in confirmation message
```

---

## 5️⃣ Edge Case Handling

### Slot Disappears Between Quote and Confirm

**Scenario**: Customer creates quote for 2pm, but someone else books it before confirm.

**Handling**:
1. `/booking/confirm` re-checks availability
2. Returns 409 Conflict: "Sorry, this slot was just taken by another customer"
3. ChatGPT shows: "That slot was just taken. Let me find other options..."
4. ChatGPT calls `/availability` again and offers alternatives

### User Refuses Contact Info

**Scenario**: Customer wants to book but won't give email/phone.

**Handling**:
1. Quote endpoint requires `customer_email` OR `customer_phone`
2. Returns 400: "Customer email or phone number is required"
3. ChatGPT: "I need contact info to complete your booking - this is how we'll send your confirmation"

### Ambiguous Times

| User Says | ChatGPT Response |
|-----------|------------------|
| "evening" | "I have slots at 4pm, 4:30pm, and 5pm. Which works?" |
| "later" | "What time works best for you?" |
| "next week" | "Which day next week? We're open Mon-Sat" |
| "the 22nd" | "That's [Day], January 22nd. Let me check..." |

### Duplicate Confirm Calls

**Scenario**: Network issue causes double-submit of confirm.

**Handling**:
1. Quote is consumed on first successful confirm
2. Second call returns 404: "Quote not found or expired"
3. ChatGPT can call `/booking/{id}` to verify booking exists

### Invalid Service Names

**Scenario**: "Book me a massage" (not offered)

**Handling**:
1. ChatGPT calls `listServices` to verify
2. If not found: "We don't offer massages. Our services are: Men's Haircut ($35), Women's Haircut ($55)..."

### Past Dates/Times

**Scenario**: "Book tomorrow at 8am" (but it's 9am already tomorrow)

**Handling**:
1. Quote endpoint checks if time is in past
2. Returns 400: "Cannot book appointments in the past"
3. ChatGPT: "That time has already passed. How about 10am or later?"

---

## 6️⃣ Deployment + Testing Checklist

### Backend Deployment

- [ ] **Update .env** with secure API key:
  ```bash
  # Generate secure key
  python -c "import secrets; print(secrets.token_urlsafe(32))"
  
  # Add to .env
  PUBLIC_BOOKING_API_KEY=your-generated-key-here
  ```

- [ ] **Verify public_booking.py is imported** in main.py:
  ```python
  from .public_booking import router as public_booking_router
  app.include_router(public_booking_router)
  ```

- [ ] **Deploy backend** (uvicorn, gunicorn, etc.)

- [ ] **Test endpoints manually**:
  ```bash
  # Test business info
  curl -H "X-API-Key: your-key" https://your-domain.com/public/business
  
  # Test services
  curl -H "X-API-Key: your-key" https://your-domain.com/public/services
  
  # Test availability
  curl -H "X-API-Key: your-key" "https://your-domain.com/public/availability?service_id=1&date=2026-01-22"
  ```

### ChatGPT Custom GPT Setup

- [ ] **Go to**: https://chat.openai.com/gpts/editor

- [ ] **Create new GPT** with name "ConvoAI" or "@ConvoAI"

- [ ] **Paste instructions** from section 4 above

- [ ] **Configure Actions**:
  1. Click "Create new action"
  2. Import OpenAPI schema (paste from `openapi_chatgpt.yaml`)
  3. Update server URL to your production domain

- [ ] **Configure Authentication**:
  1. Authentication type: **API Key**
  2. Auth Type: **Custom**
  3. Custom Header Name: `X-API-Key`
  4. API Key: Your `PUBLIC_BOOKING_API_KEY` value

- [ ] **Privacy Policy**: Add link to your privacy policy

- [ ] **Save and Publish** (or keep private for testing)

### Testing in GPT Builder

1. **Test service listing**:
   > "What services do you offer?"
   - Should call `listServices` and show prices

2. **Test availability check**:
   > "Do you have anything available tomorrow?"
   - Should call `checkAvailability`

3. **Test full booking flow**:
   > "Book a men's haircut tomorrow at 2pm"
   - Should ask for name + contact
   > "John Smith, john@example.com"
   - Should create quote and show summary
   > "Yes, confirm"
   - Should confirm and show booking ID

4. **Test error handling**:
   > "Book something for last Tuesday"
   - Should handle gracefully

### Verify OwnerGPT Receives Bookings

1. Complete a test booking via ChatGPT
2. Open OwnerGPT dashboard
3. Check schedule for the booked date
4. Verify booking appears with:
   - Correct service name
   - Correct stylist
   - Correct customer name
   - CONFIRMED status

### Common Failure Modes + Fixes

| Issue | Cause | Fix |
|-------|-------|-----|
| 401 Unauthorized | Wrong API key | Check key in .env and ChatGPT Actions |
| "Quote expired" | Took >10 min to confirm | Create new quote |
| 409 Conflict | Slot taken | Refresh availability |
| No slots returned | Wrong date or closed | Check working days |
| CORS errors | Missing origin | Add ChatGPT origin to ALLOWED_ORIGINS |
| Connection refused | Backend not running | Check server logs |

### Production Checklist

- [ ] Use HTTPS (required for ChatGPT Actions)
- [ ] Set strong API key (32+ chars)
- [ ] Consider Redis for quote storage (scalability)
- [ ] Set up monitoring/alerts for booking errors
- [ ] Add rate limiting if needed
- [ ] Test with real customer data (masked)
- [ ] Verify emails/SMS sent on confirmation

---

## File Summary

| File | Purpose |
|------|---------|
| `Backend/app/public_booking.py` | Public booking API endpoints |
| `Backend/app/core/config.py` | Added `PUBLIC_BOOKING_API_KEY` setting |
| `Backend/app/main.py` | Imports and registers public booking router |
| `Backend/openapi_chatgpt.yaml` | OpenAPI spec for ChatGPT Actions |
| `Backend/.env` | API key configuration |
| `CHATGPT_INTEGRATION.md` | This documentation file |

---

## Quick Reference: API Endpoints

```
GET  /public/business           → Business info
GET  /public/services           → List services  
GET  /public/stylists           → List stylists
GET  /public/availability       → Check slots
POST /public/booking/quote      → Create quote (NOT booking)
POST /public/booking/confirm    → Confirm → create booking
GET  /public/booking/{id}       → Get booking details
```

All endpoints require `X-API-Key` header.
