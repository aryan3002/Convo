# WhatsApp Cab Booking Setup Guide

Complete setup instructions for enabling WhatsApp-based cab bookings via Twilio.

## Phase 1: Twilio Setup (5-10 minutes)

### 1. Access Twilio WhatsApp Sandbox

1. Go to https://console.twilio.com
2. Navigate to **Messaging** → **Try it out** → **Send a WhatsApp message**
3. You'll see your sandbox number (e.g., `+1 415 523 8886`)
4. Note the **join code** (e.g., "join peaceful-mountain")

### 2. Connect Your Phone

1. Save the Twilio sandbox number in your phone contacts
2. Send the join code via WhatsApp to that number
3. Example: Send "join peaceful-mountain" to +1 415 523 8886
4. Wait for confirmation: "You are all set!"

### 3. Get API Credentials

1. In Twilio Console, go to **Account** → **Account Info**
2. Copy your **Account SID** (starts with "AC...")
3. Copy your **Auth Token** (click to reveal)
4. Copy your **WhatsApp Sandbox Number** from the sandbox page

## Phase 2: Backend Configuration (2 minutes)

### 1. Update Environment Variables

Edit `Backend/.env` and add:

```bash
# Twilio WhatsApp Configuration
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_auth_token_here
TWILIO_WHATSAPP_NUMBER=whatsapp:+14155238886
```

**Important**: 
- Replace `ACxxx...` with your actual Account SID
- Replace `your_auth_token_here` with your actual Auth Token
- Replace `+14155238886` with your sandbox number (keep the `whatsapp:` prefix)

### 2. Restart Backend Server

```bash
cd Backend
uvicorn app.main:app --host 0.0.0.0 --port 8002 --reload
```

Check logs for: `✅ Twilio client initialized successfully`

If you see `⚠️ Twilio credentials not configured`, double-check your `.env` file.

## Phase 3: Webhook Setup with ngrok (5 minutes)

### 1. Install ngrok (if not already installed)

```bash
# macOS
brew install ngrok

# Or download from https://ngrok.com/download
```

### 2. Start ngrok Tunnel

Open a new terminal and run:

```bash
ngrok http 8002
```

You'll see output like:
```
Forwarding  https://abc123.ngrok.io -> http://localhost:8002
```

**Copy the HTTPS URL** (e.g., `https://abc123.ngrok.io`)

### 3. Configure Twilio Webhook

1. Go to Twilio Console → **Messaging** → **Settings** → **WhatsApp Sandbox Settings**
2. Find the **"When a message comes in"** field
3. Enter your webhook URL in this format:
   ```
   https://abc123.ngrok.io/s/YOUR_SHOP_SLUG/webhook/whatsapp
   ```
   
   **Example**:
   - If your shop slug is `popo`: `https://abc123.ngrok.io/s/popo/webhook/whatsapp`
   - If your shop slug is `acme-cabs`: `https://abc123.ngrok.io/s/acme-cabs/webhook/whatsapp`

4. Set **HTTP Method** to `POST`
5. Click **Save**

## Phase 4: Testing (10 minutes)

### Test 1: Help Command

Send this message to your Twilio WhatsApp sandbox number:

```
HELP
```

**Expected Response**: You should receive a welcome message with booking instructions.

### Test 2: Structured Booking Request

Send this message:

```
From: 123 Main St Phoenix AZ
To: Sky Harbor Airport Phoenix AZ
Time: Tomorrow 3pm
Passengers: 2
Type: Sedan
```

**Expected Flow**:
1. ✅ You receive a price quote with distance, time, and fare
2. ✅ Backend creates a PENDING booking automatically
3. ✅ You receive a booking confirmation with reference number

### Test 3: Natural Language Request

Send this message:

```
I need a ride from downtown Phoenix to the airport tomorrow at 5pm for 3 people
```

**Expected**: Same flow as Test 2 (price quote → auto-booking → confirmation)

### Test 4: Check Dashboard

1. Open your cab owner dashboard: `http://localhost:3000/s/YOUR_SHOP_SLUG/owner/cab`
2. Click the **"Pending Requests"** tab
3. You should see the WhatsApp bookings with:
   - Channel: WhatsApp icon 💬
   - Customer phone number
   - Pickup/dropoff locations
   - Estimated fare

### Test 5: Accept Booking & Assign Driver

1. In the dashboard, click **"Accept"** on a WhatsApp booking
2. Add a driver if you haven't already (use the **"Drivers"** tab)
3. Assign the driver to the booking
4. **Future**: Customer will receive WhatsApp notification (Phase 5)

## Troubleshooting

### Issue: "Twilio credentials not configured"

**Solution**: 
1. Check that `TWILIO_ACCOUNT_SID` and `TWILIO_AUTH_TOKEN` are in your `.env` file
2. Restart the backend server
3. Check logs for initialization message

### Issue: No response to WhatsApp messages

**Solutions**:
1. Verify ngrok is running and forwarding to port 8002
2. Check webhook URL in Twilio matches your ngrok URL + shop slug
3. Check backend logs for incoming webhook requests
4. Ensure you "joined" the sandbox by sending the join code first

### Issue: "Shop not found" error

**Solution**: 
- Verify the shop slug in your webhook URL matches an existing shop
- Test with: `curl http://localhost:8002/shops/YOUR_SLUG`

### Issue: "Unable to calculate route"

**Solutions**:
1. Ensure addresses include city and state (e.g., "Phoenix, AZ")
2. Check if `GOOGLE_MAPS_API_KEY` is set in `.env` (uses mock service without it)
3. Try more specific addresses: "123 Main St, Phoenix, AZ 85001"

### Issue: Parse error - couldn't understand request

**Solution**: Use the structured format:
```
From: [pickup address]
To: [dropoff address]
Time: [when you need it]
Passengers: [number]
```

## Message Format Reference

### Structured Format (Recommended)

```
From: 123 Main Street, Phoenix, AZ
To: Phoenix Sky Harbor Airport, Phoenix, AZ
Time: Tomorrow 3pm
Passengers: 2
Type: Sedan
```

**Fields**:
- `From:` - Required - Full pickup address
- `To:` - Required - Full dropoff address
- `Time:` - Optional - Defaults to 1 hour from now
- `Passengers:` - Optional - Defaults to 1
- `Type:` - Optional - Sedan/SUV/Van - Defaults to Sedan

### Time Format Examples

- `Tomorrow 3pm`
- `Today at 5:30pm`
- `3:00pm`
- `14:00` (24-hour format)

### Natural Language (Basic Support)

```
I need a cab from Main St Phoenix to Airport tomorrow at 3pm for 2 people
```

Parser looks for:
- `from X to Y` pattern
- Time: `at 3pm`, `tomorrow 3pm`
- Passengers: `2 people`, `for 3`, `3 passengers`
- Vehicle: `suv`, `van` (defaults to sedan)

## Next Steps (Phase 5)

### 1. Two-Way Confirmation Flow

Currently bookings are created automatically. Add conversation state to:
1. Send price quote
2. Wait for customer to reply "YES"
3. Only then create booking

**Implementation**: Use Redis or database table to store conversation state.

### 2. Status Notifications

Send WhatsApp messages when:
- Booking accepted by owner
- Driver assigned
- Driver en route
- Trip completed

**Implementation**: Hook into existing owner actions (accept, assign, complete).

### 3. Production WhatsApp Business API

Twilio sandbox limitations:
- ❌ Expires after 24 hours of inactivity
- ❌ Requires customers to "join" first
- ❌ Shared sandbox with other developers

For production:
1. Apply for WhatsApp Business API access through Twilio
2. Get a dedicated phone number
3. Update webhook to production domain (no ngrok)

### 4. Enhanced Parsing with GPT

For better natural language understanding:
- Use OpenAI function calling to extract booking details
- Handle complex requests: "Pick me up at my office (123 Main St) and take me to the airport via Starbucks"
- Support multi-stop rides

## Testing Checklist

- [ ] Help command responds with instructions
- [ ] Structured booking creates quote + booking
- [ ] Natural language booking works
- [ ] Booking appears in dashboard with WhatsApp channel
- [ ] Can accept/reject bookings from dashboard
- [ ] Can assign drivers to WhatsApp bookings
- [ ] Invalid addresses show friendly error
- [ ] Missing fields show helpful guidance
- [ ] Backend logs show webhook requests

## Quick Reference: URLs

- **Webhook URL Format**: `https://YOUR_NGROK_URL/s/YOUR_SHOP_SLUG/webhook/whatsapp`
- **Dashboard**: `http://localhost:3000/s/YOUR_SHOP_SLUG/owner/cab`
- **Twilio Console**: https://console.twilio.com
- **Twilio WhatsApp Sandbox**: https://console.twilio.com/us1/develop/sms/try-it-out/whatsapp-learn
- **ngrok Dashboard**: http://127.0.0.1:4040 (when ngrok is running)

## Support

If you encounter issues:
1. Check backend logs: `tail -f Backend/logs/app.log`
2. Check ngrok dashboard: http://127.0.0.1:4040
3. Test webhook directly: `curl -X POST https://YOUR_NGROK_URL/s/YOUR_SLUG/webhook/whatsapp -d "From=whatsapp:+1234567890&Body=HELP"`
