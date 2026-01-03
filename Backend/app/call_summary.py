"""
Call Summary Generator - Internal owner feature for voice call tracking.

Uses GPT-4o-mini for factual extraction and summarization.
No creative writing, no speculation, no conversational tone.
"""

import logging
import re
from datetime import datetime, timezone

from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from .core.config import get_settings
from .models import CallSummary, CallSummaryStatus

settings = get_settings()
logger = logging.getLogger(__name__)

# Strict system prompt for factual extraction only
SUMMARY_SYSTEM_PROMPT = """You are an assistant that generates concise internal call summaries for salon owners.

Input:
- A full transcript of a phone call between a customer and a booking assistant.

Your task:
- Produce a clear, factual summary for internal staff.
- Do NOT include conversational filler.
- Do NOT speculate.
- Do NOT restate the transcript.
- Extract only relevant booking and customer details.

Output format (strict):

Customer Name: [name or "Not provided"]
Phone Number: [phone or "Not provided"]
Service Requested: [service or "Not provided"]
Preferred Stylist: [stylist or "Not provided"]
Date: [date or "Not provided"]
Time: [time or "Not provided"]
Booking Status: [Confirmed / Not confirmed / Follow-up needed]
Key Notes: [1–2 short bullet points max, or "None"]

If information is missing, write "Not provided"."""


async def generate_call_summary(
    call_sid: str,
    customer_phone: str,
    transcript: str,
    session_data: dict,
    db: AsyncSession,
) -> CallSummary | None:
    """
    Generate a call summary using GPT-4o-mini and store it in the database.
    
    Args:
        call_sid: Twilio call SID
        customer_phone: Customer's phone number
        transcript: Full conversation transcript
        session_data: Voice session data with extracted info
        db: Database session
    
    Returns:
        CallSummary object if successful, None otherwise
    """
    if not settings.openai_api_key:
        logger.warning("No OpenAI API key, skipping call summary generation")
        return None
    
    if not transcript or len(transcript.strip()) < 20:
        logger.info(f"Transcript too short for call {call_sid}, skipping summary")
        return None
    
    try:
        client = AsyncOpenAI(api_key=settings.openai_api_key)
        
        # Generate summary using GPT-4o-mini
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
                {"role": "user", "content": f"Call transcript:\n\n{transcript}"},
            ],
            max_tokens=300,
            temperature=0.1,  # Low temperature for factual extraction
        )
        
        summary_text = response.choices[0].message.content or ""
        logger.info(f"Generated summary for call {call_sid}")
        
        # Parse the structured output
        parsed = parse_summary_output(summary_text)
        
        # Determine booking status from session data or parsed output
        booking_status = determine_booking_status(session_data, parsed)
        
        # Create CallSummary record
        call_summary = CallSummary(
            call_sid=call_sid,
            customer_name=parsed.get("customer_name") or session_data.get("customer_name"),
            customer_phone=customer_phone,
            service=parsed.get("service") or session_data.get("service_name"),
            stylist=parsed.get("stylist") or session_data.get("stylist_name"),
            appointment_date=parsed.get("date") or session_data.get("date"),
            appointment_time=parsed.get("time"),
            booking_status=booking_status,
            key_notes=parsed.get("key_notes"),
            transcript=transcript,
        )
        
        db.add(call_summary)
        await db.commit()
        await db.refresh(call_summary)
        
        logger.info(f"Saved call summary {call_summary.id} for call {call_sid}")
        return call_summary
        
    except Exception as e:
        logger.exception(f"Failed to generate call summary for {call_sid}: {e}")
        return None


def parse_summary_output(text: str) -> dict:
    """
    Parse the structured GPT output into a dictionary.
    Handles variations in formatting.
    """
    result = {
        "customer_name": None,
        "phone": None,
        "service": None,
        "stylist": None,
        "date": None,
        "time": None,
        "booking_status": None,
        "key_notes": None,
    }
    
    if not text:
        return result
    
    lines = text.strip().split("\n")
    current_key = None
    key_notes_lines = []
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # Match "Key: Value" pattern
        match = re.match(r"^([^:]+):\s*(.*)$", line)
        if match:
            key_raw = match.group(1).lower().strip()
            value = match.group(2).strip()
            
            # Skip "Not provided" values
            if value.lower() in ("not provided", "none", "n/a", ""):
                continue
            
            if "customer name" in key_raw or key_raw == "name":
                result["customer_name"] = value
                current_key = None
            elif "phone" in key_raw:
                result["phone"] = value
                current_key = None
            elif "service" in key_raw:
                result["service"] = value
                current_key = None
            elif "stylist" in key_raw:
                result["stylist"] = value
                current_key = None
            elif "date" in key_raw:
                result["date"] = value
                current_key = None
            elif "time" in key_raw:
                result["time"] = value
                current_key = None
            elif "status" in key_raw:
                result["booking_status"] = value.lower()
                current_key = None
            elif "key notes" in key_raw or "notes" in key_raw:
                if value and value.lower() not in ("none", "n/a"):
                    key_notes_lines.append(value)
                current_key = "key_notes"
        elif current_key == "key_notes" and line.startswith("-"):
            # Continuation of key notes (bullet points)
            key_notes_lines.append(line)
    
    if key_notes_lines:
        result["key_notes"] = "\n".join(key_notes_lines)
    
    return result


def determine_booking_status(session_data: dict, parsed: dict) -> CallSummaryStatus:
    """
    Determine the booking status from session data and parsed output.
    Priority: session data (ground truth) > parsed GPT output
    """
    # Check if booking was confirmed in session
    if session_data.get("held_booking_id") and session_data.get("stage") == "DONE":
        return CallSummaryStatus.CONFIRMED
    
    # Check parsed status
    parsed_status = (parsed.get("booking_status") or "").lower()
    if "confirm" in parsed_status:
        return CallSummaryStatus.CONFIRMED
    elif "follow" in parsed_status:
        return CallSummaryStatus.FOLLOW_UP
    
    # Default to not confirmed
    return CallSummaryStatus.NOT_CONFIRMED


def format_transcript(turns: list[tuple[str, str]]) -> str:
    """
    Format conversation turns into a readable transcript.
    
    Args:
        turns: List of (speaker, message) tuples where speaker is "Agent" or "Customer"
    
    Returns:
        Formatted transcript string
    """
    lines = []
    for speaker, message in turns:
        lines.append(f"{speaker}: {message}")
    return "\n".join(lines)
