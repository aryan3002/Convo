"""
Clean Voice Agent Implementation - Phase 1 State Machine

Stages:
1. GET_IDENTITY   - Collect name + phone (no email)
2. GET_SERVICE    - Fuzzy match service
3. GET_DATE       - Parse today/tomorrow/day-of-week/explicit
4. GET_TIME_AND_STYLIST - Get time preference + optional stylist
5. HOLD_SLOT      - Show max 3 options, hold selected slot
6. CONFIRM        - Confirm booking
7. DONE           - Booking complete

Key Design Principles:
- Deterministic state machine (no LLM for flow control)
- Natural voice prompts (no UI language)
- Robust extraction helpers with fallbacks
- Max 3 slot options at once
- Actually writes confirmed bookings to DB
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, time, timedelta, timezone
from difflib import SequenceMatcher
from enum import Enum
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Request
from starlette.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from twilio.request_validator import RequestValidator
from twilio.twiml.voice_response import Gather, VoiceResponse

from .core.config import get_settings
from .core.db import AsyncSessionLocal
from .models import Service, Stylist

# ────────────────────────────────────────────────────────────────
# Configuration
# ────────────────────────────────────────────────────────────────

settings = get_settings()
logger = logging.getLogger(__name__)
router = APIRouter()

SHOP_ID = 1  # Single-shop assumption for now
SESSION_TTL_MINUTES = 30
MAX_NO_INPUT_RETRIES = 3


class Stage(str, Enum):
    GET_IDENTITY = "GET_IDENTITY"
    GET_SERVICE = "GET_SERVICE"
    GET_DATE = "GET_DATE"
    GET_TIME_AND_STYLIST = "GET_TIME_AND_STYLIST"
    HOLD_SLOT = "HOLD_SLOT"
    CONFIRM = "CONFIRM"
    DONE = "DONE"


# In-memory session store keyed by Twilio CallSid
CALL_SESSIONS: dict[str, dict[str, Any]] = {}


# ────────────────────────────────────────────────────────────────
# TwiML Builders
# ────────────────────────────────────────────────────────────────


def build_gather(prompt: str, timeout: int = 5) -> VoiceResponse:
    """Build a Gather TwiML that speaks a prompt and collects speech."""
    response = VoiceResponse()
    gather = Gather(
        input="speech",
        action="/twilio/gather",
        method="POST",
        timeout=timeout,
        speech_timeout="auto",
        language="en-US",
    )
    gather.say(prompt, voice="Polly.Joanna")
    response.append(gather)
    # Fallback if no input
    response.say("I didn't catch that. Let me transfer you to someone who can help.")
    response.hangup()
    return response


def build_say_hangup(message: str) -> VoiceResponse:
    """Say something and hang up."""
    response = VoiceResponse()
    response.say(message, voice="Polly.Joanna")
    response.hangup()
    return response


# ────────────────────────────────────────────────────────────────
# Security
# ────────────────────────────────────────────────────────────────


def verify_twilio_signature(request: Request, form: dict) -> bool:
    """Verify request is from Twilio. Skip if verification disabled or no token."""
    # Check if signature verification is enabled
    if not getattr(settings, 'twilio_verify_signature', False):
        return True
    
    token = settings.twilio_auth_token
    if not token:
        logger.warning("No Twilio auth token set, skipping signature verification")
        return True
    
    validator = RequestValidator(token)
    # Reconstruct the full URL Twilio used
    forwarded_proto = request.headers.get("x-forwarded-proto", "http")
    host = request.headers.get("x-forwarded-host") or request.headers.get("host", "localhost")
    url = f"{forwarded_proto}://{host}{request.url.path}"
    signature = request.headers.get("X-Twilio-Signature", "")
    
    return validator.validate(url, form, signature)


# ────────────────────────────────────────────────────────────────
# Session Management
# ────────────────────────────────────────────────────────────────


def prune_sessions() -> None:
    """Remove sessions older than TTL."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=SESSION_TTL_MINUTES)
    expired = [sid for sid, s in CALL_SESSIONS.items() if s.get("updated_at", datetime.min.replace(tzinfo=timezone.utc)) < cutoff]
    for sid in expired:
        del CALL_SESSIONS[sid]


def get_session(call_sid: str) -> dict[str, Any]:
    """Get or create a session for a call."""
    prune_sessions()
    if call_sid not in CALL_SESSIONS:
        CALL_SESSIONS[call_sid] = {
            "stage": Stage.GET_IDENTITY,
            "customer_name": None,
            "customer_phone": None,
            "pending_phone": None,  # Phone waiting for confirmation
            "service_id": None,
            "service_name": None,
            "date": None,  # YYYY-MM-DD
            "preferred_time_minutes": None,  # Minutes from midnight
            "stylist_id": None,
            "stylist_name": None,
            "available_slots": [],
            "displayed_slots": [],  # The 3 options shown to user
            "held_booking_id": None,
            "held_slot": None,
            "no_input_count": 0,
            "updated_at": datetime.now(timezone.utc),
        }
    return CALL_SESSIONS[call_sid]


def update_session(call_sid: str, **kwargs) -> None:
    """Update session fields."""
    session = get_session(call_sid)
    session.update(kwargs)
    session["updated_at"] = datetime.now(timezone.utc)


# ────────────────────────────────────────────────────────────────
# Extraction Helpers
# ────────────────────────────────────────────────────────────────


def normalize_phone(raw: str) -> str | None:
    """Normalize phone to 10-digit format."""
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) == 10:
        return digits
    return None


def extract_phone_from_speech(text: str) -> str | None:
    """Extract phone number from speech, handling spoken digits."""
    if not text:
        return None
    
    # Try to find digits directly
    digits = "".join(re.findall(r"\d", text))
    
    # Also try to convert spoken numbers
    word_map = {
        "zero": "0", "oh": "0", "o": "0",
        "one": "1", "won": "1",
        "two": "2", "to": "2", "too": "2",
        "three": "3",
        "four": "4", "for": "4",
        "five": "5",
        "six": "6",
        "seven": "7",
        "eight": "8", "ate": "8",
        "nine": "9",
    }
    
    words = text.lower().split()
    for word in words:
        # Clean punctuation
        cleaned = re.sub(r"[^\w]", "", word)
        if cleaned in word_map:
            digits += word_map[cleaned]
    
    return normalize_phone(digits)


def format_phone_for_voice(phone: str) -> str:
    """Format phone number for voice readout (digit by digit)."""
    if len(phone) == 10:
        return f"{phone[0]} {phone[1]} {phone[2]}, {phone[3]} {phone[4]} {phone[5]}, {phone[6]} {phone[7]} {phone[8]} {phone[9]}"
    return " ".join(phone)


def extract_name_from_speech(text: str) -> str | None:
    """Extract name from speech."""
    if not text:
        return None
    
    lowered = text.lower()
    
    # Try common patterns with more variations
    patterns = [
        r"(?:my name is|i'm|i am|this is|it's|call me|name's)\s+([a-zA-Z]+(?:\s+[a-zA-Z]+)?)",
        r"(?:^|\s)([a-zA-Z]{2,}(?:\s+[a-zA-Z]{2,})?)(?:\s|$)",  # Name-like words (2+ chars)
    ]
    
    for pattern in patterns:
        matches = re.finditer(pattern, lowered)
        for match in matches:
            name = match.group(1).strip()
            
            # Filter out common filler words and non-names
            skip_words = {
                "and", "the", "my", "phone", "number", "is", "at", "or", "for", "with", "to", "in", "on", "yes", "yeah", "no", "ok", "okay",
                "book", "booking", "appointment", "haircut", "trim", "cut", "service", "today", "tomorrow", "monday", "tuesday", "wednesday",
                "thursday", "friday", "saturday", "sunday", "morning", "afternoon", "evening", "time", "available", "stylist", "anyone"
            }
            
            words = []
            for w in name.split():
                if w not in skip_words and len(w) >= 2 and w.isalpha():
                    words.append(w.title())
            
            if words and len(words) <= 3:
                potential_name = " ".join(words)
                # Additional validation: avoid common non-name patterns
                if not re.match(r"^(do|go|me|we|he|she|it|they|am|are|is|was|were|have|has|had|will|would|could|should|can|may|might)$", potential_name.lower()):
                    return potential_name
    
    return None


def extract_date_from_speech(text: str, tz: ZoneInfo) -> str | None:
    """Extract date from speech, returning YYYY-MM-DD format."""
    if not text:
        return None
    
    lowered = text.lower()
    now = datetime.now(tz)
    
    # Today/tomorrow
    if "today" in lowered:
        return now.strftime("%Y-%m-%d")
    if "tomorrow" in lowered:
        return (now + timedelta(days=1)).strftime("%Y-%m-%d")
    
    # Day of week
    days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    for i, day in enumerate(days):
        if day in lowered:
            current_dow = now.weekday()
            days_ahead = (i - current_dow) % 7
            if days_ahead == 0:  # Same day means next week
                days_ahead = 7
            return (now + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
    
    # Explicit date patterns: "March 15", "March 15th", "3/15", "15th of March"
    months = {
        "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
        "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12
    }
    
    # "March 15" or "March 15th"
    for month_name, month_num in months.items():
        match = re.search(rf"{month_name}\s+(\d{{1,2}})(?:st|nd|rd|th)?", lowered)
        if match:
            day = int(match.group(1))
            year = now.year
            try:
                target = datetime(year, month_num, day, tzinfo=tz)
                if target.date() < now.date():
                    target = datetime(year + 1, month_num, day, tzinfo=tz)
                return target.strftime("%Y-%m-%d")
            except ValueError:
                pass
    
    # "15th of March"
    match = re.search(r"(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?([a-zA-Z]+)", lowered)
    if match:
        day = int(match.group(1))
        month_name = match.group(2).lower()
        if month_name in months:
            month_num = months[month_name]
            year = now.year
            try:
                target = datetime(year, month_num, day, tzinfo=tz)
                if target.date() < now.date():
                    target = datetime(year + 1, month_num, day, tzinfo=tz)
                return target.strftime("%Y-%m-%d")
            except ValueError:
                pass
    
    return None


def extract_time_from_speech(text: str) -> int | None:
    """Extract time preference as minutes from midnight."""
    if not text:
        return None
    
    lowered = text.lower()
    
    # General time of day
    if "morning" in lowered:
        return 10 * 60  # 10 AM
    if "noon" in lowered or "midday" in lowered:
        return 12 * 60
    if "afternoon" in lowered:
        return 14 * 60  # 2 PM
    if "evening" in lowered:
        return 17 * 60  # 5 PM
    
    # "3pm", "3 pm", "3:30pm"
    match = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?)", lowered)
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2) or 0)
        period = match.group(3)
        
        if "p" in period and hour != 12:
            hour += 12
        elif "a" in period and hour == 12:
            hour = 0
        
        return hour * 60 + minute
    
    # "3 o'clock"
    match = re.search(r"(\d{1,2})\s*o'?clock", lowered)
    if match:
        hour = int(match.group(1))
        # Assume PM for business hours
        if 1 <= hour <= 7:
            hour += 12
        return hour * 60
    
    return None


def is_affirmative(text: str) -> bool:
    """Check if speech is affirmative."""
    if not text:
        return False
    lowered = text.lower()
    affirmatives = ["yes", "yeah", "yep", "correct", "right", "that's right", "exactly", "sure", "ok", "okay", "confirm", "do it", "book it", "sounds good", "perfect"]
    return any(a in lowered for a in affirmatives)


def is_negative(text: str) -> bool:
    """Check if speech is negative."""
    if not text:
        return False
    lowered = text.lower()
    negatives = ["no", "nope", "wrong", "incorrect", "not right", "that's wrong", "cancel", "never mind"]
    return any(n in lowered for n in negatives)


def is_goodbye(text: str) -> bool:
    """Check if user wants to end the call."""
    if not text:
        return False
    lowered = text.lower()
    goodbyes = ["goodbye", "bye", "hang up", "end call", "that's all", "nevermind", "never mind"]
    return any(g in lowered for g in goodbyes)


# ────────────────────────────────────────────────────────────────
# Fuzzy Matching for Services and Stylists
# ────────────────────────────────────────────────────────────────


async def get_all_services(session: AsyncSession) -> list[Service]:
    """Get all services for the shop."""
    result = await session.execute(
        select(Service).where(Service.shop_id == SHOP_ID)
    )
    return list(result.scalars().all())


async def get_all_stylists(session: AsyncSession) -> list[Stylist]:
    """Get all active stylists for the shop."""
    result = await session.execute(
        select(Stylist).where(Stylist.shop_id == SHOP_ID, Stylist.active == True)
    )
    return list(result.scalars().all())


def fuzzy_match_service(text: str, services: list[Service]) -> Service | None:
    """Fuzzy match a service from speech with strict gender matching."""
    if not text or not services:
        return None
    
    lowered = text.lower()
    # Normalize apostrophes and contractions for better matching
    normalized = lowered.replace("'", "").replace("'", "").replace("-", " ")
    
    # Extract key characteristics from speech - be very specific about gender
    has_women = bool(re.search(r"\bwom[ae]n'?s?\b|\bfemale\b|\blad(?:y|ies)\b", normalized))
    has_men = bool(re.search(r"\bm[ae]n'?s?\b|\bmale\b|\bgentlem[ae]n\b", normalized))
    has_haircut = bool(re.search(r"\bhaircut\b|\bhair\s+cut\b", normalized))
    has_trim = "trim" in normalized
    has_color = bool(re.search(r"\bcolou?r\b", normalized))
    has_beard = "beard" in normalized
    
    logger.info(f"Service matching: '{text}' | women={has_women}, men={has_men}, haircut={has_haircut}")
    
    best_match = None
    best_score = 0.0
    
    for service in services:
        service_lower = service.name.lower()
        service_normalized = service_lower.replace("'", "").replace("'", "").replace("-", " ")
        
        # Check service characteristics
        service_has_women = bool(re.search(r"\bwom[ae]n'?s?\b", service_normalized))
        service_has_men = bool(re.search(r"\bm[ae]n'?s?\b", service_normalized))
        service_has_haircut = "haircut" in service_normalized
        service_has_trim = "trim" in service_normalized
        service_has_color = "color" in service_normalized or "colour" in service_normalized
        service_has_beard = "beard" in service_normalized
        
        # Check if this is a gender-specific service
        service_is_gendered = service_has_women or service_has_men
        
        # STRICT RULE: If speech specifies gender AND service is gendered, they MUST match
        if service_is_gendered:
            if has_women and not service_has_women:
                logger.debug(f"Skipping '{service.name}' - speech has women, service doesn't")
                continue
            if has_men and not service_has_men:
                logger.debug(f"Skipping '{service.name}' - speech has men, service doesn't")
                continue
            
            # STRICT RULE: Gender-specific services must match the gender in speech
            if service_has_women and has_men:
                logger.debug(f"Skipping '{service.name}' - service is women's but speech says men")
                continue
            if service_has_men and has_women:
                logger.debug(f"Skipping '{service.name}' - service is men's but speech says women")
                continue
        
        # For gendered services, enforce service type matching
        if service_is_gendered:
            if has_haircut and not service_has_haircut and not service_has_trim:
                continue
            if has_color and not service_has_color:
                continue
            if has_trim and service_has_haircut and not service_has_trim:
                continue
            if has_beard and not service_has_beard:
                continue
        
        # Calculate match score
        score = 0.0
        
        # SIMPLE EXACT MATCH (highest priority) - case insensitive
        if service_normalized == normalized or service_lower == lowered:
            logger.info(f"EXACT MATCH: '{service.name}' with score 1000")
            return service
        
        # SIMPLE SUBSTRING MATCH - if service name is in speech or vice versa
        if service_normalized in normalized or normalized in service_normalized:
            score += 200
            logger.info(f"SUBSTRING MATCH: '{service.name}' with score {score}")
        
        # High priority for exact gender + service type match
        if has_women and service_has_women:
            score += 100
        if has_men and service_has_men:
            score += 100
        if has_haircut and service_has_haircut:
            score += 50
        if has_trim and service_has_trim:
            score += 50
        if has_color and service_has_color:
            score += 50
        if has_beard and service_has_beard:
            score += 50
        
        # Exact word matching
        speech_words = set(normalized.split())
        service_words = set(service_normalized.split())
        common = speech_words.intersection(service_words)
        meaningful = [w for w in common if len(w) > 2 and w not in ["the", "and", "for", "with", "is", "are"]]
        
        # Boost score significantly if any word matches
        if meaningful:
            score += len(meaningful) * 30
            logger.debug(f"Word matches for '{service.name}': {meaningful}, score: {score}")
        
        # For non-gendered services, be more lenient with partial matches
        if not service_is_gendered:
            # Check if any significant part of the service name appears in speech
            service_parts = [w for w in service_words if len(w) > 3]
            for part in service_parts:
                if part in normalized:
                    score += 40
                    logger.debug(f"Partial match '{part}' in '{service.name}', score: {score}")
        
        if score > best_score and score >= 30:  # Lower threshold for better matching
            best_score = score
            best_match = service
            logger.info(f"Potential match: '{service.name}' with score {score}")
    
    if best_match:
        logger.info(f"Selected service: '{best_match.name}' with score {best_score}")
    else:
        logger.warning(f"No service match found for: '{text}'")
    
    return best_match


def fuzzy_match_stylist(text: str, stylists: list[Stylist]) -> Stylist | None:
    """Fuzzy match a stylist from speech."""
    if not text or not stylists:
        return None
    
    lowered = text.lower()
    speech_words = lowered.split()
    best_match = None
    best_score = 0.0
    
    for stylist in stylists:
        stylist_lower = stylist.name.lower()
        stylist_words = stylist_lower.split()
        
        # Exact full name match (highest priority)
        if stylist_lower == lowered:
            return stylist
        
        # Full name appears in speech
        if stylist_lower in lowered:
            return stylist
        
        # Exact first or last name match in speech words
        for stylist_word in stylist_words:
            if stylist_word in speech_words:
                # Prioritize longer name matches
                if len(stylist_word) >= 4:  # Longer names are more specific
                    return stylist
                elif len(stylist_word) >= 3 and not best_match:
                    best_match = stylist
                    best_score = 0.8  # High score for exact word match
        
        # Fuzzy match only if no exact word matches found
        if best_score < 0.7:
            ratio = SequenceMatcher(None, lowered, stylist_lower).ratio()
            if ratio > best_score and ratio > 0.7:
                best_score = ratio
                best_match = stylist
    
    return best_match


# ────────────────────────────────────────────────────────────────
# Slot Selection Helpers
# ────────────────────────────────────────────────────────────────


def parse_option_number(text: str) -> int | None:
    """Parse option selection (1, 2, 3, first, second, third)."""
    if not text:
        return None
    
    lowered = text.lower()
    
    if re.search(r"\b(first|one|option one|1)\b", lowered):
        return 0
    if re.search(r"\b(second|two|option two|2)\b", lowered):
        return 1
    if re.search(r"\b(third|three|option three|3)\b", lowered):
        return 2
    
    return None


def select_best_slots(slots: list[dict], preferred_minutes: int | None, max_count: int = 3) -> list[dict]:
    """Select up to max_count slots closest to preferred time."""
    if not slots:
        return []
    
    if preferred_minutes is None:
        # Return first available slots
        return slots[:max_count]
    
    # Sort by distance from preferred time (in local timezone)
    tz = ZoneInfo(settings.chat_timezone)
    
    def time_distance(slot: dict) -> int:
        start = slot.get("start_time", "")
        local_minutes = None
        
        if isinstance(start, str) and "T" in start:
            try:
                from datetime import datetime as dt
                utc_dt = dt.fromisoformat(start.replace("Z", "+00:00"))
                local_dt = utc_dt.astimezone(tz)
                local_minutes = local_dt.hour * 60 + local_dt.minute
            except Exception:
                pass
        elif hasattr(start, 'astimezone'):
            local_dt = start.astimezone(tz)
            local_minutes = local_dt.hour * 60 + local_dt.minute
        elif hasattr(start, 'hour'):
            local_minutes = start.hour * 60 + start.minute
        
        if local_minutes is not None:
            return abs(local_minutes - preferred_minutes)
        return 9999
    
    sorted_slots = sorted(slots, key=time_distance)
    return sorted_slots[:max_count]


def format_slot_for_voice(slot: dict, option_num: int) -> str:
    """Format a slot for voice announcement."""
    start = slot.get("start_time", "")
    stylist_name = slot.get("stylist_name", "a stylist")
    
    # Convert to local timezone
    tz = ZoneInfo(settings.chat_timezone)
    local_hour = None
    local_minute = None
    
    if isinstance(start, str) and "T" in start:
        try:
            from datetime import datetime as dt
            utc_dt = dt.fromisoformat(start.replace("Z", "+00:00"))
            local_dt = utc_dt.astimezone(tz)
            local_hour = local_dt.hour
            local_minute = local_dt.minute
        except Exception:
            pass
    elif hasattr(start, 'astimezone'):
        local_dt = start.astimezone(tz)
        local_hour = local_dt.hour
        local_minute = local_dt.minute
    elif hasattr(start, 'hour'):
        local_hour = start.hour
        local_minute = start.minute
    
    if local_hour is not None:
        # Convert to 12-hour format
        period = "AM" if local_hour < 12 else "PM"
        display_hour = local_hour % 12
        if display_hour == 0:
            display_hour = 12
        
        if local_minute == 0:
            time_str = f"{display_hour} {period}"
        else:
            time_str = f"{display_hour}:{local_minute:02d} {period}"
        
        return f"Option {option_num}: {time_str} with {stylist_name}"
    
    return f"Option {option_num}: available with {stylist_name}"


def format_slots_for_voice(slots: list[dict]) -> str:
    """Format multiple slots for voice announcement."""
    if not slots:
        return "I couldn't find any available times for that day."
    
    lines = [format_slot_for_voice(slot, i + 1) for i, slot in enumerate(slots)]
    return "Here are your options. " + ". ".join(lines) + ". Which would you like?"


# ────────────────────────────────────────────────────────────────
# Booking Integration
# ────────────────────────────────────────────────────────────────


def get_local_tz_offset_minutes() -> int:
    """Get timezone offset in minutes."""
    tz = ZoneInfo(settings.chat_timezone)
    now = datetime.now(tz)
    offset = now.utcoffset()
    if offset:
        return int(offset.total_seconds() / 60)
    return 0


async def fetch_availability(session: AsyncSession, service_id: int, date: str, stylist_id: int | None = None) -> list[dict]:
    """Fetch available slots for a service on a date."""
    from .main import get_availability
    
    # get_availability uses query params, not a model
    slots = await get_availability(
        service_id=service_id,
        date=date,
        tz_offset_minutes=get_local_tz_offset_minutes(),
        secondary_service_id=None,
        session=session,
    )
    
    # Filter by stylist if specified
    if stylist_id and slots:
        slots = [s for s in slots if s.get("stylist_id") == stylist_id]
    
    return slots


async def create_hold(
    session: AsyncSession,
    service_id: int,
    date: str,
    start_time: str,
    stylist_id: int,
    customer_name: str,
    customer_phone: str,
) -> dict:
    """Create a hold on a slot."""
    from .main import HoldRequest, create_hold as main_create_hold
    
    payload = HoldRequest(
        service_id=service_id,
        date=date,
        start_time=start_time,
        stylist_id=stylist_id,
        customer_name=customer_name,
        customer_phone=customer_phone,
        tz_offset_minutes=get_local_tz_offset_minutes(),
    )
    
    result = await main_create_hold(payload, session)
    return result.model_dump()


async def confirm_booking(session: AsyncSession, booking_id: uuid.UUID) -> dict:
    """Confirm a held booking."""
    from .main import ConfirmRequest, confirm_booking as main_confirm_booking
    
    payload = ConfirmRequest(booking_id=booking_id)
    result = await main_confirm_booking(payload, session)
    return result.model_dump()


# ────────────────────────────────────────────────────────────────
# State Machine Handlers
# ────────────────────────────────────────────────────────────────


async def handle_get_identity(call_sid: str, speech: str) -> VoiceResponse:
    """Stage 1: Collect name and phone number."""
    session = get_session(call_sid)
    
    # Check for goodbye
    if is_goodbye(speech):
        return build_say_hangup("No problem. Call us back anytime. Goodbye!")
    
    # Handle phone confirmation FIRST (before extracting new data)
    if session["pending_phone"]:
        if is_affirmative(speech):
            # Phone confirmed, move forward
            update_session(call_sid, customer_phone=session["pending_phone"], pending_phone=None)
            session = get_session(call_sid)
            # Don't extract name from "yes"
            if session["customer_name"]:
                # We have both, move to next stage
                update_session(call_sid, stage=Stage.GET_SERVICE)
                return build_gather(f"Great, {session['customer_name']}! What service would you like to book today?")
            else:
                return build_gather("And what's your name?")
        elif is_negative(speech):
            # Phone rejected, ask again
            update_session(call_sid, pending_phone=None)
            return build_gather("Okay, please tell me your phone number again.")
        else:
            # Check if they're providing a new phone number
            new_phone = extract_phone_from_speech(speech)
            if new_phone and new_phone != session["pending_phone"]:
                update_session(call_sid, pending_phone=new_phone)
                formatted = format_phone_for_voice(new_phone)
                return build_gather(f"I heard {formatted}. Is that correct?")
            else:
                # Ask for confirmation again
                formatted = format_phone_for_voice(session["pending_phone"])
                return build_gather(f"I heard {formatted}. Is that correct?")
    
    # Extract name if we don't have it
    if not session["customer_name"]:
        name = extract_name_from_speech(speech)
        if name:
            update_session(call_sid, customer_name=name)
            session = get_session(call_sid)
    
    # Extract phone if we don't have it
    if not session["customer_phone"] and not session["pending_phone"]:
        phone = extract_phone_from_speech(speech)
        if phone:
            # Store pending phone for confirmation
            update_session(call_sid, pending_phone=phone)
            session = get_session(call_sid)
    
    # If we have a pending phone, ask for confirmation
    if session["pending_phone"]:
        formatted = format_phone_for_voice(session["pending_phone"])
        return build_gather(f"I heard {formatted}. Is that correct?")
    
    # Build next prompt based on what we have
    if not session["customer_name"] and not session["customer_phone"]:
        return build_gather("I didn't catch that. What's your name and phone number?")
    
    if not session["customer_phone"]:
        name = session["customer_name"]
        return build_gather(f"Thanks {name}! What's a good phone number for your booking?")
    
    if not session["customer_name"]:
        return build_gather("And what's your name?")
    
    # We have both, move to next stage
    update_session(call_sid, stage=Stage.GET_SERVICE)
    name = session["customer_name"]
    return build_gather(f"Great, {name}! What service would you like to book today?")


async def handle_get_service(call_sid: str, speech: str) -> VoiceResponse:
    """Stage 2: Get the service they want."""
    session = get_session(call_sid)
    
    if is_goodbye(speech):
        return build_say_hangup("No problem. Call us back anytime. Goodbye!")
    
    async with AsyncSessionLocal() as db:
        services = await get_all_services(db)
    
    matched = fuzzy_match_service(speech, services)
    
    if matched:
        update_session(
            call_sid,
            service_id=matched.id,
            service_name=matched.name,
            stage=Stage.GET_DATE
        )
        # Confirm the service so customer can correct if wrong
        return build_gather(f"Perfect! I've got you down for a {matched.name}. What day works for you?")
    
    # List available services with better categorization
    service_names = [s.name for s in services[:6]]  # Max 6 for voice
    if len(service_names) > 1:
        service_list = ", ".join(service_names[:-1]) + f", or {service_names[-1]}"
    else:
        service_list = service_names[0] if service_names else "various services"
    return build_gather(f"I didn't quite catch that. We offer {service_list}. Which service would you like?")


async def handle_get_date(call_sid: str, speech: str) -> VoiceResponse:
    """Stage 3: Get the appointment date."""
    session = get_session(call_sid)
    
    if is_goodbye(speech):
        return build_say_hangup("No problem. Call us back anytime. Goodbye!")
    
    # Check if user wants to correct the service
    if any(word in speech.lower() for word in ["change", "wrong", "different service", "not that", "actually"]):
        async with AsyncSessionLocal() as db:
            services = await get_all_services(db)
        
        matched = fuzzy_match_service(speech, services)
        if matched:
            update_session(
                call_sid,
                service_id=matched.id,
                service_name=matched.name
            )
            return build_gather(f"No problem! I've updated it to {matched.name}. What day works for you?")
        else:
            # Reset to service selection
            update_session(call_sid, stage=Stage.GET_SERVICE, service_id=None, service_name=None)
            service_names = [s.name for s in services[:6]]
            if len(service_names) > 1:
                service_list = ", ".join(service_names[:-1]) + f", or {service_names[-1]}"
            else:
                service_list = service_names[0] if service_names else "various services"
            return build_gather(f"Let me help you choose the right service. We offer {service_list}. Which one would you like?")
    
    tz = ZoneInfo(settings.chat_timezone)
    date = extract_date_from_speech(speech, tz)
    
    if date:
        update_session(call_sid, date=date, stage=Stage.GET_TIME_AND_STYLIST)
        return build_gather("Got it! Do you have a preferred time or stylist? Or I can show you what's available.")
    
    # Remind them what service they selected
    service_name = session.get("service_name", "your service")
    return build_gather(f"I didn't catch the date for your {service_name}. You can say today, tomorrow, or a specific day like Monday or March 15th.")


async def handle_get_time_and_stylist(call_sid: str, speech: str) -> VoiceResponse:
    """Stage 4: Get time preference and optional stylist."""
    session = get_session(call_sid)
    
    if is_goodbye(speech):
        return build_say_hangup("No problem. Call us back anytime. Goodbye!")
    
    # Extract time preference
    time_minutes = extract_time_from_speech(speech)
    if time_minutes is not None:
        update_session(call_sid, preferred_time_minutes=time_minutes)
        session = get_session(call_sid)
    
    # Extract stylist preference
    async with AsyncSessionLocal() as db:
        stylists = await get_all_stylists(db)
    
    matched_stylist = fuzzy_match_stylist(speech, stylists)
    if matched_stylist:
        update_session(
            call_sid,
            stylist_id=matched_stylist.id,
            stylist_name=matched_stylist.name
        )
        session = get_session(call_sid)
    
    # Check for "any" or "whoever" or just wants availability
    wants_any = any(w in speech.lower() for w in ["any", "anyone", "whoever", "available", "what's available", "show me"])
    
    # Fetch availability
    async with AsyncSessionLocal() as db:
        slots = await fetch_availability(
            db,
            session["service_id"],
            session["date"],
            session.get("stylist_id")
        )
    
    if not slots:
        update_session(call_sid, stage=Stage.GET_DATE)
        return build_gather("Sorry, I couldn't find any availability for that day. Would you like to try a different date?")
    
    # Select best slots
    displayed = select_best_slots(slots, session.get("preferred_time_minutes"), max_count=3)
    update_session(
        call_sid,
        available_slots=slots,
        displayed_slots=displayed,
        stage=Stage.HOLD_SLOT
    )
    
    return build_gather(format_slots_for_voice(displayed))


async def handle_hold_slot(call_sid: str, speech: str) -> VoiceResponse:
    """Stage 5: User selects a slot, we hold it."""
    session = get_session(call_sid)
    
    if is_goodbye(speech):
        return build_say_hangup("No problem. Call us back anytime. Goodbye!")
    
    displayed = session.get("displayed_slots", [])
    
    # Parse option selection
    option_idx = parse_option_number(speech)
    
    selected_slot = None
    
    if option_idx is not None and option_idx < len(displayed):
        selected_slot = displayed[option_idx]
    else:
        # Try to match by time or stylist name
        time_minutes = extract_time_from_speech(speech)
        if time_minutes is not None:
            # Find closest match
            for slot in displayed:
                start = slot.get("start_time", "")
                if isinstance(start, str) and "T" in start:
                    time_part = start.split("T")[1][:5]
                    hour, minute = map(int, time_part.split(":"))
                    slot_minutes = hour * 60 + minute
                    if abs(slot_minutes - time_minutes) < 30:  # Within 30 min
                        selected_slot = slot
                        break
    
    if not selected_slot:
        return build_gather("I didn't catch which option. Please say first, second, or third, or the time you'd like.")
    
    # Extract slot details
    start_time = selected_slot.get("start_time", "")
    stylist_id = selected_slot.get("stylist_id")
    stylist_name = selected_slot.get("stylist_name", "your stylist")
    
    # Convert UTC time to local time for the hold request
    tz = ZoneInfo(settings.chat_timezone)
    time_24 = None
    local_hour = None
    
    if isinstance(start_time, str) and "T" in start_time:
        # Parse ISO format UTC time
        try:
            from datetime import datetime as dt
            utc_dt = dt.fromisoformat(start_time.replace("Z", "+00:00"))
            local_dt = utc_dt.astimezone(tz)
            time_24 = f"{local_dt.hour:02d}:{local_dt.minute:02d}"
            local_hour = local_dt.hour
        except Exception as e:
            logger.error(f"Failed to parse start_time: {start_time}, error: {e}")
    elif hasattr(start_time, 'astimezone'):
        # It's a datetime object with timezone
        local_dt = start_time.astimezone(tz)
        time_24 = f"{local_dt.hour:02d}:{local_dt.minute:02d}"
        local_hour = local_dt.hour
    elif hasattr(start_time, 'hour'):
        # It's a datetime object without timezone (assume UTC)
        time_24 = f"{start_time.hour:02d}:{start_time.minute:02d}"
        local_hour = start_time.hour
    
    if not time_24:
        logger.error(f"Could not parse start_time: {start_time}, type: {type(start_time)}")
        return build_gather("Sorry, there was an issue with that time. Please try again.")
    
    # Create hold
    try:
        async with AsyncSessionLocal() as db:
            hold_result = await create_hold(
                db,
                session["service_id"],
                session["date"],
                time_24,
                stylist_id,
                session["customer_name"],
                session["customer_phone"],
            )
        
        booking_id = hold_result.get("booking_id")
        update_session(
            call_sid,
            held_booking_id=str(booking_id) if booking_id else None,
            held_slot=selected_slot,
            stage=Stage.CONFIRM
        )
        
        # Format time for voice
        hour, minute = map(int, time_24.split(":"))
        period = "AM" if hour < 12 else "PM"
        display_hour = hour % 12 or 12
        if minute == 0:
            time_voice = f"{display_hour} {period}"
        else:
            time_voice = f"{display_hour}:{minute:02d} {period}"
        
        return build_gather(
            f"I've reserved {time_voice} with {stylist_name} for you. "
            f"This hold lasts 5 minutes. Should I confirm this booking?"
        )
        
    except Exception as e:
        logger.exception(f"Failed to hold slot: {e}")
        return build_gather("Sorry, I couldn't reserve that slot. It may have just been taken. Would you like to try another time?")


async def handle_confirm(call_sid: str, speech: str) -> VoiceResponse:
    """Stage 6: Confirm the booking."""
    session = get_session(call_sid)
    
    if is_goodbye(speech):
        return build_say_hangup("No problem. Your hold has been released. Call us back anytime. Goodbye!")
    
    if is_negative(speech):
        update_session(call_sid, stage=Stage.HOLD_SLOT)
        return build_gather("No problem. Would you like to choose a different time?")
    
    if is_affirmative(speech):
        booking_id = session.get("held_booking_id")
        if not booking_id:
            return build_gather("I don't have a reservation to confirm. Let's start over. What service would you like?")
        
        try:
            async with AsyncSessionLocal() as db:
                await confirm_booking(db, uuid.UUID(booking_id))
            
            update_session(call_sid, stage=Stage.DONE)
            
            held_slot = session.get("held_slot", {})
            stylist_name = held_slot.get("stylist_name", "your stylist")
            
            return build_say_hangup(
                f"Your booking is confirmed! We'll see you then with {stylist_name}. "
                f"A confirmation will be sent to your phone. Thanks for calling!"
            )
            
        except Exception as e:
            logger.exception(f"Failed to confirm booking: {e}")
            return build_gather("Sorry, I couldn't confirm that booking. Would you like me to try again?")
    
    return build_gather("Should I confirm this booking? Just say yes or no.")


async def handle_done(call_sid: str, speech: str) -> VoiceResponse:
    """Stage 7: Booking complete, anything else?"""
    if is_goodbye(speech) or is_negative(speech):
        return build_say_hangup("Thanks for calling! Have a great day!")
    
    # Reset for another booking
    update_session(
        call_sid,
        stage=Stage.GET_SERVICE,
        service_id=None,
        service_name=None,
        date=None,
        preferred_time_minutes=None,
        stylist_id=None,
        stylist_name=None,
        available_slots=[],
        displayed_slots=[],
        held_booking_id=None,
        held_slot=None,
    )
    return build_gather("Would you like to book another appointment? What service would you like?")


# ────────────────────────────────────────────────────────────────
# Main Route Handlers
# ────────────────────────────────────────────────────────────────


@router.post("/voice")
async def twilio_voice(request: Request) -> Response:
    """Initial call handler - welcome message and start gathering."""
    form = dict(await request.form())
    
    if not verify_twilio_signature(request, form):
        return Response("Forbidden", status_code=403)
    
    call_sid = str(form.get("CallSid", "unknown"))
    logger.info(f"Voice call started: {call_sid}")
    
    # Initialize session
    get_session(call_sid)
    
    twiml = build_gather(
        "Hi, thanks for calling! I can help you book an appointment. "
        "What's your name and phone number?"
    )
    
    return Response(str(twiml), media_type="application/xml")


@router.post("/gather")
async def twilio_gather(request: Request) -> Response:
    """Handle speech input and route through state machine."""
    form = dict(await request.form())
    
    if not verify_twilio_signature(request, form):
        return Response("Forbidden", status_code=403)
    
    call_sid = str(form.get("CallSid", "unknown"))
    speech = str(form.get("SpeechResult", "")).strip()
    
    session = get_session(call_sid)
    logger.info(f"Gather input: call={call_sid}, stage={session['stage']}, speech='{speech}'")
    
    # Handle no input
    if not speech:
        session["no_input_count"] = session.get("no_input_count", 0) + 1
        if session["no_input_count"] >= MAX_NO_INPUT_RETRIES:
            logger.warning(f"Max no-input retries reached: {call_sid}")
            return Response(str(build_say_hangup(
                "I'm having trouble hearing you. Please call back when you have a better connection."
            )), media_type="application/xml")
        
        return Response(str(build_gather(
            "I didn't catch that. Could you please repeat?"
        )), media_type="application/xml")
    
    # Reset no-input counter on successful input
    update_session(call_sid, no_input_count=0)
    
    # Route to appropriate handler based on stage
    stage = session.get("stage", Stage.GET_IDENTITY)
    
    try:
        if stage == Stage.GET_IDENTITY:
            twiml = await handle_get_identity(call_sid, speech)
        elif stage == Stage.GET_SERVICE:
            twiml = await handle_get_service(call_sid, speech)
        elif stage == Stage.GET_DATE:
            twiml = await handle_get_date(call_sid, speech)
        elif stage == Stage.GET_TIME_AND_STYLIST:
            twiml = await handle_get_time_and_stylist(call_sid, speech)
        elif stage == Stage.HOLD_SLOT:
            twiml = await handle_hold_slot(call_sid, speech)
        elif stage == Stage.CONFIRM:
            twiml = await handle_confirm(call_sid, speech)
        elif stage == Stage.DONE:
            twiml = await handle_done(call_sid, speech)
        else:
            logger.error(f"Unknown stage: {stage}")
            twiml = build_gather("I got confused. Let's start over. What's your name?")
            update_session(call_sid, stage=Stage.GET_IDENTITY)
        
        return Response(str(twiml), media_type="application/xml")
        
    except Exception as e:
        logger.exception(f"Error in gather handler: {e}")
        return Response(str(build_gather(
            "Sorry, something went wrong. Let me try that again. What would you like to do?"
        )), media_type="application/xml")
