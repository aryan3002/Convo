# SMS Confirmation Feature - Testing Guide

## Overview
Automatic SMS confirmations are sent when a booking is confirmed and has a phone number.

## Environment Variables Required

Add these to your `.env` file:

```bash
# Twilio SMS Configuration
TWILIO_ACCOUNT_SID=your_account_sid_here
TWILIO_AUTH_TOKEN=your_auth_token_here  
TWILIO_FROM_NUMBER=+1234567890  # Your Twilio phone number

# Public API base URL (use ngrok for local testing)
PUBLIC_API_BASE=https://your-ngrok-url.ngrok.io
```

## How to Get Twilio Credentials

1. Go to https://console.twilio.com/
2. Sign up or log in
3. Get your Account SID and Auth Token from the dashboard
4. Get a phone number from Phone Numbers → Manage → Buy a number
5. **Important**: Trial accounts can only send to verified phone numbers
   - Go to Phone Numbers → Manage → Verified Caller IDs
   - Add and verify your test phone number

## Testing Locally with ngrok

### 1. Start ngrok
```bash
ngrok http 8000
```

Copy the HTTPS URL (e.g., `https://abc123.ngrok.io`)

### 2. Update .env
```bash
PUBLIC_API_BASE=https://abc123.ngrok.io
```

### 3. Restart Backend
The backend will automatically add the `sms_sent_at_utc` column on startup.

```bash
cd Backend
source ../.venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 4. Test the Flow

#### Option A: Via Voice Call
1. Call your Twilio number
2. Complete the booking flow
3. You should receive an SMS with calendar link

#### Option B: Via API Test
```bash
# Create a hold with phone number
curl -X POST http://localhost:8000/bookings/hold \
  -H "Content-Type: application/json" \
  -d '{
    "service_id": 1,
    "date": "2026-01-10",
    "start_time": "14:00",
    "stylist_id": 1,
    "customer_name": "Test User",
    "customer_phone": "+16235551234",
    "tz_offset_minutes": -420
  }'

# Confirm the booking (use booking_id from response)
curl -X POST http://localhost:8000/bookings/confirm \
  -H "Content-Type: application/json" \
  -d '{
    "booking_id": "your-booking-id-here"
  }'
```

### 5. Verify SMS Sent
Check your phone for an SMS like:
```
✅ Confirmed: Men's Haircut with Ashmit on Jan 10 at 2:00 PM. Add to calendar: https://abc123.ngrok.io/bookings/xxx/invite.ics
```

### 6. Test Calendar Link
1. Tap the link in the SMS
2. The .ics file should download
3. Open it - should add to your calendar app
4. Works with:
   - Google Calendar
   - Apple Calendar
   - Outlook
   - Any iCalendar-compatible app

## How It Works

### Flow
1. Booking is confirmed via `POST /bookings/confirm`
2. System checks if `booking.customer_phone` exists
3. System checks if `booking.sms_sent_at_utc` is null (not sent yet)
4. If both true:
   - Formats booking details (service, stylist, date, time)
   - Generates ICS download URL
   - Sends SMS via Twilio
   - Marks `sms_sent_at_utc` timestamp
5. If SMS fails, it's logged but doesn't break the booking

### SMS Won't Send If
- Missing Twilio credentials
- Phone number already received SMS (prevents duplicates)
- Phone number is invalid format
- Twilio API fails (logged as warning)

### Key Files
- `Backend/app/sms.py` - SMS sender utility
- `Backend/app/main.py` - confirm_booking() function + /bookings/{id}/invite.ics endpoint
- `Backend/app/models.py` - Booking.sms_sent_at_utc field
- `Backend/app/core/config.py` - Twilio settings

## Production Deployment

### Environment Variables
Set these in your production environment:
```bash
TWILIO_ACCOUNT_SID=AC...
TWILIO_AUTH_TOKEN=...
TWILIO_FROM_NUMBER=+1...
PUBLIC_API_BASE=https://yourdomain.com
```

### Database Migration
The column `bookings.sms_sent_at_utc` is added automatically on app startup via `ensure_identity_schema()`.

### Monitoring
Check logs for:
- `SMS sent successfully` - Success
- `Twilio SMS not configured` - Missing credentials
- `Twilio API error` - API failure (check Twilio console)
- `Failed to send SMS confirmation` - Unexpected errors

## Troubleshooting

### SMS not received
1. Check Twilio console logs
2. Verify phone number is E.164 format (+1...)
3. Trial accounts: Is recipient number verified?
4. Check backend logs for errors

### Calendar link doesn't work
1. Verify PUBLIC_API_BASE is correct
2. Test URL directly: `curl https://yoururl.com/bookings/{id}/invite.ics`
3. Check booking status is CONFIRMED

### SMS sent multiple times
- Should not happen - `sms_sent_at_utc` prevents duplicates
- Check if column was created properly
- Check logs for database errors

## API Endpoints

### GET /bookings/{booking_id}/invite.ics
Downloads .ics calendar invite file

**Requirements:**
- Booking must exist
- Booking status must be CONFIRMED or HOLD

**Response:**
- Content-Type: `text/calendar; charset=utf-8`
- Content-Disposition: `attachment; filename="appointment-{id}.ics"`

**Example:**
```bash
curl https://yourdomain.com/bookings/123e4567-e89b-12d3-a456-426614174000/invite.ics
```
