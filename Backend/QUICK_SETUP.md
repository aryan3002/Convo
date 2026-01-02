# SMS Confirmation - Quick Setup

## ✅ What Was Implemented

1. **Twilio SMS sender** (`Backend/app/sms.py`)
   - Async SMS sending with Twilio API
   - E.164 phone formatting
   - Error handling (never crashes booking)

2. **ICS calendar download** (`GET /bookings/{id}/invite.ics`)
   - Direct .ics file download
   - Works with Google/Apple/Outlook calendars
   - Proper content-type headers

3. **SMS hook in confirm_booking** (`Backend/app/main.py`)
   - Sends SMS after booking confirmed
   - Includes service, stylist, date/time, calendar link
   - One-time send (tracked via `sms_sent_at_utc`)

4. **Database column** (`bookings.sms_sent_at_utc`)
   - Auto-migrated on startup
   - Prevents duplicate SMS sends

## 🔧 What You Need to Provide

### 1. Twilio Account
- Go to: https://console.twilio.com/
- Sign up (free trial available)
- Get these values:

### 2. Environment Variables
Add to `Backend/.env`:
```bash
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_auth_token_here
TWILIO_FROM_NUMBER=+12345678900
PUBLIC_API_BASE=https://your-ngrok-url.ngrok.io
```

### 3. For Local Testing with ngrok
```bash
# Terminal 1: Start ngrok
ngrok http 8000

# Copy the HTTPS URL shown (e.g., https://abc123.ngrok.io)
# Update PUBLIC_API_BASE in .env

# Terminal 2: Restart backend
cd Backend
source ../.venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 4. Verify Phone Number (Trial Accounts Only)
- Go to: https://console.twilio.com/us1/develop/phone-numbers/manage/verified
- Click "Add a new number"
- Verify your mobile number
- Trial accounts can only SMS verified numbers

## 🧪 Quick Test

```bash
# 1. Create booking with phone
curl -X POST http://localhost:8000/bookings/hold \
  -H "Content-Type: application/json" \
  -d '{
    "service_id": 1,
    "date": "2026-01-10",
    "start_time": "14:00",
    "stylist_id": 1,
    "customer_name": "Test User",
    "customer_phone": "+YOUR_VERIFIED_NUMBER",
    "tz_offset_minutes": -420
  }'

# 2. Confirm booking (replace BOOKING_ID)
curl -X POST http://localhost:8000/bookings/confirm \
  -H "Content-Type: application/json" \
  -d '{"booking_id": "BOOKING_ID_FROM_STEP_1"}'

# 3. Check your phone for SMS
# 4. Tap the calendar link to test
```

## 📱 Expected SMS Format

```
✅ Confirmed: Men's Haircut with Ashmit on Jan 10 at 2:00 PM. Add to calendar: https://yoururl.com/bookings/xxx/invite.ics
```

## 🎯 Production Ready

- ✅ Works with ngrok for local dev
- ✅ Works with production domains
- ✅ No payment required
- ✅ Non-blocking (booking succeeds even if SMS fails)
- ✅ Prevents duplicate SMS
- ✅ E.164 phone formatting
- ✅ Calendar works on all major platforms

## 📝 Files Changed

- `Backend/app/sms.py` - NEW
- `Backend/app/core/config.py` - Added Twilio settings
- `Backend/app/models.py` - Added sms_sent_at_utc column
- `Backend/app/main.py` - Added ICS endpoint + SMS hook
- `Backend/SMS_TESTING_GUIDE.md` - NEW (detailed guide)

## ⚠️ Important Notes

- Trial Twilio accounts: Only sends to verified numbers
- SMS won't crash booking if Twilio fails (just logs warning)
- SMS only sent once per booking (tracked in DB)
- Calendar link requires PUBLIC_API_BASE to be set correctly
- Voice bookings automatically include phone number

## 🚀 Ready to Test!

Just provide the 3 environment variables above and restart your backend.
