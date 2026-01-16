-- Test data for pgvector semantic search
-- Insert multiple call summaries with realistic transcripts

-- Test Call 1: Keratin Treatment Pricing
INSERT INTO call_summaries (
  id, call_sid, customer_phone, customer_name, service, stylist,
  appointment_date, appointment_time, booking_status, key_notes, transcript
) VALUES (
  'a1b2c3d4-e5f6-7890-abcd-ef1234567890'::uuid,
  'test_call_001',
  '555-123-4567',
  'Sarah Johnson',
  'Keratin Treatment',
  'Alex',
  '2025-01-20',
  '14:00',
  'confirmed',
  'Customer interested in keratin treatment pricing. Prefers Monday appointments. Wants to know about product aftercare.',
  'Agent: Hi! Welcome to our salon. How can I help you today?
Customer: Hi, I am interested in learning about your keratin treatment and pricing.
Agent: Great! Our Keratin Treatment is $200 and takes about 90 minutes.
Customer: That sounds good. What days can I schedule it?
Agent: We have availability on Mondays, Wednesdays, and Fridays.
Customer: I prefer Mondays. Can I book for next Monday?
Agent: Absolutely! Let me check our schedule. We have a slot at 2 PM. Would that work?
Customer: Perfect! That works for me. Do I need to do anything special after the treatment?
Agent: Yes, avoid washing your hair for 48 hours and use sulfate-free shampoo for the next 3 weeks.
Customer: Great! That makes sense.
Agent: You are all set for Monday, January 20th at 2 PM for Keratin Treatment.'
);

-- Test Call 2: Balayage Consultation
INSERT INTO call_summaries (
  id, call_sid, customer_phone, customer_name, service, stylist,
  appointment_date, appointment_time, booking_status, key_notes, transcript
) VALUES (
  'b2c3d4e5-f6a7-8901-bcde-f12345678901'::uuid,
  'test_call_002',
  '555-987-6543',
  'Emily Chen',
  'Balayage',
  'Jordan',
  '2025-01-22',
  '10:00',
  'confirmed',
  'Customer wants balayage but concerned about damage. First time customer. Interested in maintenance schedule.',
  'Agent: Good morning! Thank you for calling. How can we assist you today?
Customer: Hi, I have been thinking about getting balayage done. I have never done it before and I am worried about hair damage.
Agent: That is a great question. Our balayage technique is very gentle. We use premium products that minimize damage.
Customer: What is the price and how long does it take?
Agent: Our balayage typically costs between $150 and $300 depending on hair length and thickness. It usually takes 2-3 hours.
Customer: That is reasonable. How often do I need to maintain it?
Agent: Balayage is low maintenance! You only need touch-ups every 3-4 months since it blends naturally as it grows.
Customer: Perfect. Can I book for Wednesday?
Agent: Absolutely! We have Jordan available at 10 AM on Wednesday, January 22nd.
Customer: Great! I will take that appointment.
Agent: Wonderful! See you soon!'
);

-- Test Call 3: Hair Extensions Inquiry
INSERT INTO call_summaries (
  id, call_sid, customer_phone, customer_name, service, stylist,
  appointment_date, appointment_time, booking_status, key_notes, transcript
) VALUES (
  'c3d4e5f6-a7b8-9012-cdef-123456789012'::uuid,
  'test_call_003',
  '555-246-8135',
  'Michael Rodriguez',
  'Hair Extensions',
  'Taylor',
  '2025-01-25',
  '15:00',
  'not_confirmed',
  'Customer interested in hair extensions but pricing too high. Wants to check competitor rates. Follow-up needed.',
  'Agent: Hello! Thanks for calling our salon.
Customer: Hi, I am interested in hair extensions but I want to understand your pricing first.
Agent: Of course! We offer several options. Tape-in extensions are $400, while sew-in extensions are $600.
Customer: Wow, that is quite expensive. Do you offer any discounts?
Agent: We do offer a first-time customer discount of 10% on service fees.
Customer: That helps a bit, but I want to check with other salons first to compare pricing.
Agent: Absolutely, feel free to shop around. We would love to have you. Our extensions also come with a free consultation.
Customer: Okay, I will call you back if I decide to go ahead.
Agent: Sounds great! Feel free to reach out anytime with questions.'
);

-- Test Call 4: Color Correction Emergency
INSERT INTO call_summaries (
  id, call_sid, customer_phone, customer_name, service, stylist,
  appointment_date, appointment_time, booking_status, key_notes, transcript
) VALUES (
  'd4e5f6a7-b8c9-0123-def0-234567890123'::uuid,
  'test_call_004',
  '555-555-1111',
  'Lisa Martinez',
  'Color Correction',
  'Alex',
  '2025-01-16',
  '11:00',
  'confirmed',
  'URGENT: Customer had bad color elsewhere. Needs immediate correction. Same-day appointment scheduled.',
  'Customer: Hi! I have an emergency. I got my hair colored at another salon and it turned out way too orange.
Agent: Oh no! That is frustrating. Can you come in today?
Customer: Yes please! I work nearby and can come right now.
Agent: Perfect! Let me get you with our best colorist. Alex has an opening at 11 AM today.
Customer: Yes, that works! How much will the correction cost?
Agent: Color correction is $150-250 depending on the extent of the work. Alex will assess it when you arrive.
Customer: Okay, I am on my way now!
Agent: Great! We will take good care of you. See you in a few minutes!'
);

-- Test Call 5: Wedding Party Packages
INSERT INTO call_summaries (
  id, call_sid, customer_phone, customer_name, service, stylist,
  appointment_date, appointment_time, booking_status, key_notes, transcript
) VALUES (
  'e5f6a7b8-c9d0-1234-ef01-345678901234'::uuid,
  'test_call_005',
  '555-369-2580',
  'Victoria Thompson',
  'Bridal Party Package',
  'Jordan',
  '2025-06-15',
  '09:00',
  'confirmed',
  'Bride booking for wedding party. 6 people total. Hair and makeup. Deposit required.',
  'Agent: Hello! Welcome to our salon. How can we help?
Customer: Hi! I am planning my wedding and I need hair and makeup services for my bridal party.
Agent: Congratulations! How many people will you need services for?
Customer: There are 6 of us total: me, 3 bridesmaids, and 2 groomsmen who just want hair.
Agent: Perfect! We offer bridal party packages. Bride styling is $150, bridesmaids are $100 each, and groom hair is $50 each.
Customer: What is the timeline like? How long will it take?
Agent: Typically we need about 3-4 hours total. We recommend starting early morning.
Customer: When would be available? I am thinking June 15th.
Agent: That date works! We have availability starting at 9 AM.
Customer: Fantastic! Can I put a deposit down to secure it?
Agent: Of course! We require a 25% deposit to hold your date. That would be $675.'
);

-- Verify inserts
SELECT COUNT(*) as total_test_calls FROM call_summaries WHERE call_sid LIKE 'test_call_%';
SELECT id, customer_name, service, booking_status FROM call_summaries WHERE call_sid LIKE 'test_call_%' ORDER BY created_at DESC;
