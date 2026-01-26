#!/usr/bin/env python3
"""
Test WhatsApp webhook locally without Twilio.

Simulates incoming WhatsApp messages to test the booking flow.
"""

import requests
import json

WEBHOOK_URL = "http://localhost:8002/s/popo/webhook/whatsapp"

# Test messages
test_messages = [
    {
        "name": "Natural Language - AI Parsing",
        "message": "I need a ride from downtown Phoenix to the airport tomorrow at 3pm for 2 people"
    },
    {
        "name": "Structured Format",
        "message": """From: 123 Main St, Phoenix, AZ
To: Sky Harbor Airport, Phoenix, AZ
Time: Tomorrow 5pm
Passengers: 3
Type: SUV"""
    },
    {
        "name": "Simple Request",
        "message": "Book me a cab from Central Ave Phoenix to Tempe Marketplace"
    },
]

def test_whatsapp_booking(message_text, test_name):
    """Send a test message to the webhook."""
    print(f"\n{'='*60}")
    print(f"TEST: {test_name}")
    print(f"{'='*60}")
    print(f"Message: {message_text}\n")
    
    # Simulate Twilio webhook POST data
    data = {
        "From": "whatsapp:+12067902033",
        "Body": message_text,
        "MessageSid": "TEST123456"
    }
    
    try:
        response = requests.post(WEBHOOK_URL, data=data, timeout=30)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        
        if response.status_code == 200:
            print("✅ SUCCESS")
        else:
            print("❌ FAILED")
            
    except Exception as e:
        print(f"❌ ERROR: {e}")

if __name__ == "__main__":
    print("🚖 Testing WhatsApp Cab Booking Webhook")
    print("="*60)
    
    for test in test_messages:
        test_whatsapp_booking(test["message"], test["name"])
        input("\nPress Enter to continue to next test...")
    
    print("\n✅ All tests completed!")
    print("\nCheck your dashboard at: http://localhost:3000/s/popo/owner/cab")
