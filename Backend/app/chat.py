"""
AI Chat module using GPT-4o-mini for conversational appointment booking.
"""
import json
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from openai import AsyncOpenAI
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .core.config import get_settings
from .customer_memory import get_customer_context, normalize_email, normalize_phone
from .models import Service, Stylist, StylistSpecialty

settings = get_settings()


def get_local_now() -> datetime:
    """Get the current datetime in the configured timezone (Arizona)."""
    tz = ZoneInfo(settings.chat_timezone)
    return datetime.now(tz)


def get_local_today() -> date:
    """Get today's date in the configured timezone (Arizona)."""
    return get_local_now().date()


class ChatMessage(BaseModel):
    role: str  # "user" | "assistant" | "system"
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    context: dict | None = None  # Optional context like selected service, date, etc.


class ChatResponse(BaseModel):
    reply: str
    action: dict | None = None  # Actions for frontend to execute
    data: dict | None = None  # Tool results (services, slots, hold, confirm)
    chips: list[str] | None = None  # Dynamic chips for user to tap (e.g., ["Yes", "No"])


CHAT_PROMPT = """You are a friendly booking assistant for Bishops Tempe hair salon in Tempe, Arizona.

SERVICES: {services}
STYLISTS: {stylists}

NOW: {today} at {current_time} (Arizona/MST)
WORKING HOURS: {working_hours} ({working_days})
CURRENT STAGE: {stage}
SELECTED SERVICE: {selected_service}
SELECTED DATE: {selected_date}
CHANNEL: {channel}

DATE RULES:
- Today: {today_date}, Tomorrow: {tomorrow_date}, Current year: {current_year}
- If user says a month BEFORE current month (e.g. "January" in December), use NEXT YEAR ({next_year})
- Always format dates as YYYY-MM-DD

CRITICAL RULES:
- Be brief. One sentence only. Never list more than 3 items in text.
- Do NOT list time slots in text. The UI shows them as buttons.
- Never claim a booking is held or confirmed unless the backend tool succeeds.
- INFORMATIONAL QUESTIONS: If user asks about price/cost/hours/etc, answer from SERVICES - DO NOT use select_service.
- Only use select_service when user explicitly wants to BOOK that service, not when asking questions.
- If asked who is best for a service, use stylist specialties from STYLISTS. If none match, say you don't have a specialist listed.
- If user mentions a date, use fetch_availability and say: "Here are a few good options. Tap one to continue."
- If user tries to type a time, ask them to tap a time option.
- Before holding: collect name AND (email OR phone) from user.
- FAST-PATH: If user provides ALL required details (service + date + time + stylist + name + email), skip ahead and immediately call hold_slot without re-asking.
- After a service is selected, ask about preferred style before asking for a date.
- Prefer tool calls; do not invent availability or confirmation.
- UI SELECTIONS:
  - "Service selected: <name>" → always use select_service with that service.
  - "Date selected: YYYY-MM-DD" → use fetch_availability for that date.
  - "Time selected: HH:MM with <stylist>" → ask for missing name/email, then hold_slot.

ACTIONS (add at END of message):
[ACTION: {{"type": "action_type", "params": {{...}}}}]

Actions:
- show_services: {{}}
- select_service: {{"service_id": <id>, "service_name": "<name>"}}
- fetch_availability: {{"service_id": <id>, "date": "YYYY-MM-DD"}}
- hold_slot: {{"service_id": <id>, "stylist_id": <id>, "date": "YYYY-MM-DD", "start_time": "HH:MM", "customer_name": "<name>", "customer_email": "<email>", "customer_phone": "<phone>"}}
- confirm_booking: {{}}
- get_last_preferred_style: {{"service_id": <id>, "customer_email": "<email>"}}
- set_preferred_style: {{"service_id": <id>, "customer_email": "<email>", "preferred_style_text": "<text>", "preferred_style_image_url": "<url>"}}
- apply_same_as_last_time: {{"service_id": <id>, "customer_email": "<email>"}}
- skip_preferred_style: {{}}
- check_promos: {{"trigger_point": "<TRIGGER_POINT>", "email": "<email>", "service_id": <id>, "date": "YYYY-MM-DD"}}

PREFERRED STYLE RULES:
- If user wants to add or update preferred style, use set_preferred_style with service_id + customer_email.
- If user asks for "same as last time", use apply_same_as_last_time.
- If user asks to see the last style, use get_last_preferred_style.
- If customer_email is missing, ask for it and do not call the action yet.

BOOKING FLOW:
1. Ask for BOTH name AND email at start (CAPTURE_EMAIL stage) - do not proceed until you have both
2. User provides name and email → check_promos with AT_CHAT_START and AFTER_EMAIL_CAPTURE, display any eligible promos
3. User picks service → select_service action, check_promos with AFTER_SERVICE_SELECTED, display any eligible promos, ask about preferred style
4. Preferred style handled (set_preferred_style / apply_same_as_last_time / skip_preferred_style) → ask for date
5. User picks date → IMMEDIATELY use fetch_availability action and check_promos with AFTER_SLOT_SHOWN, display any eligible promos, say "Here are the available times for [date]:" (slots appear automatically)
6. User picks time from displayed slots → ask which stylist (Alex=ID 1, Jamie=ID 2) + their name + their email
7. Once you have ALL of: time + stylist + name + email → immediately use hold_slot action with ALL params and check_promos with AFTER_HOLD_CREATED, display any eligible promos
8. After a hold exists, ask the user to confirm; only use confirm_booking when they confirm

PROMOTION RULES:
- Check for promotions using check_promos action at the trigger points listed above
- When check_promos returns a promo, display it to the user with the custom_copy text if available, otherwise generate a brief description
- Promos should be applied automatically to the booking total when eligible

RESPONSE STYLE:
- Be professional and brief (one sentence)
- When fetching availability, say "Here are a few good options. Tap one to continue."
- Never list times, names, or multiple options in plain text
"""

VOICE_PROMPT = """You are a friendly voice booking assistant for Bishops Tempe hair salon in Tempe, Arizona.

SERVICES: {services}
STYLISTS: {stylists}

NOW: {today} at {current_time} (Arizona/MST)
WORKING HOURS: {working_hours} ({working_days})
CURRENT STAGE: {stage}
SELECTED SERVICE: {selected_service}
SELECTED DATE: {selected_date}
CHANNEL: voice

DATE RULES:
- Today: {today_date}, Tomorrow: {tomorrow_date}, Current year: {current_year}
- If user says a month BEFORE current month (e.g. "January" in December), use NEXT YEAR ({next_year})
- Always format dates as YYYY-MM-DD

CRITICAL RULES:
- Voice only: NEVER mention UI elements like "tap", "click", "buttons", "chips", or "list below".
- Keep responses short and natural (one sentence).
- Do NOT list more than 3 options in a single response.
- Identity for voice: must collect name + phone before holding. Email is optional.
- Prefer tool calls; do not invent availability or confirmation.

VOICE FLOW:
1. Get name + phone first.
2. Ask for service and date.
3. Ask for time preference; offer 2–3 options max.
4. Hold booking only after service + date + time + stylist + name + phone.
5. After hold, ask for confirmation. Only confirm after explicit "yes/confirm".

RESPONSE STYLE:
- Speak naturally: "I can do 10 AM with Alex or 11:30 with Jamie. Which works?"
- Never say "select from the list" or "tap".
"""

# Backward compatibility alias
SYSTEM_PROMPT = CHAT_PROMPT

ALLOWED_STAGES = {
    "CAPTURE_EMAIL",
    "WELCOME",
    "SELECT_SERVICE",
    "PREFERRED_STYLE",
    "SELECT_DATE",
    "SELECT_SLOT",
    "HOLDING",
    "CONFIRMING",
    "DONE",
}

ALLOWED_ACTIONS = {
    "CAPTURE_EMAIL": {"show_services", "select_service", "fetch_availability", "hold_slot", "confirm_booking", "show_slots", "get_last_preferred_style", "set_preferred_style", "apply_same_as_last_time", "skip_preferred_style", "check_promos"},
    "WELCOME": {"show_services", "select_service", "fetch_availability", "hold_slot", "confirm_booking", "show_slots", "get_last_preferred_style", "set_preferred_style", "apply_same_as_last_time", "skip_preferred_style", "check_promos"},
    "SELECT_SERVICE": {"show_services", "select_service", "fetch_availability", "hold_slot", "confirm_booking", "show_slots", "get_last_preferred_style", "set_preferred_style", "apply_same_as_last_time", "skip_preferred_style", "check_promos"},
    "PREFERRED_STYLE": {"show_services", "select_service", "get_last_preferred_style", "set_preferred_style", "apply_same_as_last_time", "skip_preferred_style", "check_promos"},
    "SELECT_DATE": {"fetch_availability", "hold_slot", "confirm_booking", "show_slots", "get_last_preferred_style", "set_preferred_style", "apply_same_as_last_time", "skip_preferred_style", "check_promos"},
    "SELECT_SLOT": {"hold_slot", "confirm_booking", "show_slots", "get_last_preferred_style", "set_preferred_style", "apply_same_as_last_time", "skip_preferred_style", "check_promos"},
    "HOLDING": {"confirm_booking", "hold_slot", "get_last_preferred_style", "set_preferred_style", "apply_same_as_last_time", "skip_preferred_style", "check_promos"},
    "CONFIRMING": {"confirm_booking", "get_last_preferred_style", "set_preferred_style", "apply_same_as_last_time", "skip_preferred_style", "check_promos"},
    "DONE": {"show_services", "select_service", "fetch_availability", "hold_slot", "confirm_booking", "show_slots", "get_last_preferred_style", "set_preferred_style", "apply_same_as_last_time", "skip_preferred_style", "check_promos"},
}

STAGE_PROMPTS = {
    "CAPTURE_EMAIL": "Hi! What's your name and best email to get started?",
    "WELCOME": "Welcome! What service would you like to book?",
    "SELECT_SERVICE": "Which service would you like? Please tap a service.",
    "PREFERRED_STYLE": "Do you have a preferred style for this service?",
    "SELECT_DATE": "Pick a date below to see times.",
    "SELECT_SLOT": "Here are a few good options. Tap one to continue.",
    "HOLDING": "One moment while I reserve that.",
    "CONFIRMING": "Tap confirm to finalize your booking.",
    "DONE": "You are all set. Anything else I can help with?",
}
VOICE_STAGE_PROMPTS = {
    "WELCOME": "Thanks for calling. What service would you like to book?",
    "SELECT_SERVICE": "Which service would you like?",
    "PREFERRED_STYLE": "Do you have a preferred style?",
    "SELECT_DATE": "What day works for you?",
    "SELECT_SLOT": "I have a few options. Which time works best?",
    "HOLDING": "One moment while I reserve that.",
    "CONFIRMING": "Should I confirm the booking?",
    "DONE": "You are all set. Anything else I can help with?",
}

def parse_action_from_response(response: str) -> tuple[str, dict | None, list[str] | None]:
    """Extract action JSON and chips from response text."""
    import re
    
    action = None
    chips = None
    clean_response = response
    
    # Look for [CHIPS: [...]] pattern
    chips_pattern = r'\[CHIPS:\s*(\[[^\]]*\])\]'
    chips_match = re.search(chips_pattern, response, re.DOTALL)
    if chips_match:
        try:
            chips = json.loads(chips_match.group(1))
            clean_response = clean_response[:chips_match.start()] + clean_response[chips_match.end():]
            clean_response = clean_response.strip()
        except json.JSONDecodeError:
            pass
    
    # Look for [ACTION: {...}] pattern - use greedy match for nested braces
    action_pattern = r'\[ACTION:\s*(\{[^[\]]*\})\]'
    match = re.search(action_pattern, clean_response, re.DOTALL)
    
    if not match:
        # Try alternative pattern with nested braces
        action_pattern = r'\[ACTION:\s*(\{.*\})\]'
        match = re.search(action_pattern, clean_response, re.DOTALL)
    
    if match:
        try:
            raw_action = json.loads(match.group(1))
            
            # Normalize action format - if params are at root level, wrap them
            if "type" in raw_action:
                action_type = raw_action["type"]
                # Check if params are missing but other keys exist (flat format)
                if "params" not in raw_action:
                    params = {k: v for k, v in raw_action.items() if k != "type"}
                    action = {"type": action_type, "params": params}
                else:
                    action = raw_action
            
            clean_response = clean_response[:match.start()].strip()
        except json.JSONDecodeError:
            # If JSON parsing fails, just strip the action text anyway
            clean_response = re.sub(r'\[ACTION:.*?\]\]?', '', clean_response, flags=re.DOTALL).strip()
    
    return clean_response, action, chips


def normalize_stage(value: Any) -> str:
    if not value:
        return "CAPTURE_EMAIL"
    text = str(value).strip().upper()
    return text if text in ALLOWED_STAGES else "CAPTURE_EMAIL"


def _get_ordinal_suffix(day: int) -> str:
    """Get ordinal suffix for day number (1st, 2nd, 3rd, 4th, etc.)."""
    if 10 <= day % 100 <= 20:
        return "th"
    else:
        return {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")


def shorten_reply(text: str) -> str:
    cleaned = " ".join(text.split())
    if not cleaned:
        return ""
    first_line = cleaned.split("\n", 1)[0]
    sentence = re.split(r"(?<=[.!?])\s", first_line)[0]
    if len(sentence) > 160:
        sentence = sentence[:157].rstrip() + "..."
    return sentence


def format_cents(value: int) -> str:
    return f"${value / 100:.2f}"


def extract_phone_from_messages(messages: list[ChatMessage]) -> str:
    """Extract phone number from messages."""
    for msg in reversed(messages):
        if msg.role != "user":
            continue
        # Match phone patterns: (123) 456-7890, 123-456-7890, 1234567890, +1...
        match = re.search(r"(\+?1?[-.\s]?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4})", msg.content)
        if match:
            return match.group(0).strip()
    return ""


def extract_email_from_messages(messages: list[ChatMessage]) -> str:
    for msg in reversed(messages):
        if msg.role != "user":
            continue
        match = re.search(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", msg.content, re.IGNORECASE)
        if match:
            return match.group(0).strip().lower()
    return ""


def extract_name_from_messages(messages: list[ChatMessage]) -> str:
    """Extract customer name from messages - look for names in context or user messages."""
    for msg in reversed(messages):
        if msg.role != "user":
            continue
        # Look for patterns like "I'm John" or "my name is Sarah" or just "John Smith"
        name_patterns = [
            r"(?:my name is|i'?m|call me|it'?s)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)",
            r"^([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s*(?:,|and|@)",  # Name at start followed by comma/and/@
        ]
        for pattern in name_patterns:
            match = re.search(pattern, msg.content, re.IGNORECASE)
            if match:
                return match.group(1).strip()
    return ""


def extract_service_name_from_text(text: str, services_list: list[str]) -> str | None:
    """Extract service name from user text by fuzzy matching."""
    if not text or not services_list:
        return None
    lowered = text.lower()
    for service_name in services_list:
        if service_name.lower() in lowered:
            return service_name
    return None


def extract_day_only_from_text(text: str) -> int | None:
    """Extract just the day number from text (e.g., '22nd' -> 22) for confirmation."""
    if not text:
        return None
    lowered = text.lower()
    
    # Look for standalone day numbers like "22nd", "20th", "5th" without month context
    # Use word boundaries to avoid matching dates like "16th January"
    match = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\b", lowered)
    if match:
        day = int(match.group(1))
        # Only return if it's a valid day (1-31) and there's no month in the text
        if 1 <= day <= 31:
            # Check if there's a month name nearby (avoid false positives)
            months_pattern = r"(january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)"
            if not re.search(months_pattern, lowered):
                return day
    return None


def extract_date_from_text(text: str, tz: ZoneInfo) -> str | None:
    """Extract date from text, returning YYYY-MM-DD format."""
    if not text:
        return None
    lowered = text.lower()
    now = datetime.now(tz)
    
    # Today/tomorrow
    if "today" in lowered:
        return now.strftime("%Y-%m-%d")
    if "tomorrow" in lowered:
        return (now + timedelta(days=1)).strftime("%Y-%m-%d")
    
    # Day of week (whole word match to avoid false positives like "friday" in "16th January")
    days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    for i, day in enumerate(days):
        if re.search(rf"\b{day}\b", lowered):
            current_dow = now.weekday()
            days_ahead = (i - current_dow) % 7
            if days_ahead == 0:
                days_ahead = 7
            return (now + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
    
    # Explicit date patterns: "March 15", "15th", "16th January", etc.
    months = {
        "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
        "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12
    }
    
    # "16th January" or "January 16th" patterns (match day before checking month-day patterns)
    for month_name, month_num in months.items():
        # Try "16th January" pattern first (number before month)
        match = re.search(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?{month_name}\b", lowered)
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
        
        # Try "January 16th" pattern (month before number)
        match = re.search(rf"\b{month_name}\s+(\d{{1,2}})(?:st|nd|rd|th)?\b", lowered)
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
    
    # YYYY-MM-DD format
    match = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", text)
    if match:
        try:
            year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3))
            target = datetime(year, month, day, tzinfo=tz)
            return target.strftime("%Y-%m-%d")
        except ValueError:
            pass
    
    return None


def extract_time_from_text(text: str) -> str | None:
    """Extract time from text, returning HH:MM format (24-hour)."""
    if not text:
        return None
    lowered = text.lower()
    
    # "3pm", "3 pm", "3:30pm", "4:00 pm"
    match = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?)", lowered)
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2) or 0)
        period = match.group(3)
        
        if "p" in period and hour != 12:
            hour += 12
        elif "a" in period and hour == 12:
            hour = 0
        
        return f"{hour:02d}:{minute:02d}"
    
    # "3 o'clock"
    match = re.search(r"(\d{1,2})\s*o'?clock", lowered)
    if match:
        hour = int(match.group(1))
        if 1 <= hour <= 7:
            hour += 12
        return f"{hour:02d}:00"
    
    return None


def extract_stylist_from_text(text: str) -> tuple[int | None, str | None]:
    """Extract stylist from text, returning (stylist_id, stylist_name)."""
    if not text:
        return None, None
    lowered = text.lower()
    
    # Known stylists mapping
    stylists = {
        "alex": (1, "Alex"),
        "jamie": (2, "Jamie"),
        "sanskar": (3, "Sanskar"),
    }
    
    for name, (stylist_id, display_name) in stylists.items():
        if name in lowered:
            return stylist_id, display_name
    
    return None, None


async def find_service_by_name(session: AsyncSession, shop_id: int, name: str) -> Service | None:
    """Find a service by name, scoped to shop_id."""
    if not name:
        return None
    result = await session.execute(
        select(Service).where(
            Service.shop_id == shop_id,
            Service.name.ilike(f"%{name.strip()}%")
        ).order_by(Service.id)
    )
    return result.scalar_one_or_none()


async def get_services_context(session: AsyncSession, shop_id: int) -> str:
    """Get formatted services list for the system prompt, scoped to shop_id."""
    result = await session.execute(
        select(Service).where(Service.shop_id == shop_id).order_by(Service.id)
    )
    services = result.scalars().all()
    
    if not services:
        return "No services available"
    
    lines = []
    for svc in services:
        price = svc.price_cents / 100
        lines.append(f"- ID {svc.id}: {svc.name} (${price:.2f}, {svc.duration_minutes} min)")
    return "\n".join(lines)


async def get_stylists_context(session: AsyncSession, shop_id: int) -> str:
    """Get formatted stylists list for the system prompt, scoped to shop_id."""
    result = await session.execute(
        select(Stylist).where(
            Stylist.shop_id == shop_id,
            Stylist.active.is_(True)
        ).order_by(Stylist.id)
    )
    stylists = result.scalars().all()
    
    if not stylists:
        return "No stylists available"
    
    specialties_result = await session.execute(select(StylistSpecialty))
    specialties: dict[int, list[str]] = {}
    for specialty in specialties_result.scalars().all():
        specialties.setdefault(specialty.stylist_id, []).append(specialty.tag)

    lines = []
    for stylist in stylists:
        tags = ", ".join(sorted(specialties.get(stylist.id, []))) or "none"
        lines.append(f"- ID {stylist.id}: {stylist.name} (specialties: {tags})")
    return "\n".join(lines)


async def chat_with_ai(
    messages: list[ChatMessage],
    session: AsyncSession,
    context: dict | None = None,
    shop_id: int = 1,  # Phase 3: Required shop_id for tenant isolation
) -> ChatResponse:
    """Process chat messages and return AI response with optional actions."""
    
    if not settings.openai_api_key:
        return ChatResponse(
            reply="I'm sorry, but the AI assistant is not configured. Please contact support.",
            action=None
        )
    
    client = AsyncOpenAI(api_key=settings.openai_api_key)

    stage = normalize_stage(context.get("stage") if context else None)
    selected_service = context.get("selected_service") if context else None

    customer_email = None
    if context and context.get("customer_email"):
        customer_email = str(context.get("customer_email") or "").strip().lower()
    if not customer_email:
        customer_email = extract_email_from_messages(messages)
    
    # Also extract phone from messages
    customer_phone = None
    if context and context.get("customer_phone"):
        customer_phone = str(context.get("customer_phone") or "").strip()
    if not customer_phone:
        customer_phone = extract_phone_from_messages(messages)
    
    customer_name = None
    if context and context.get("customer_name"):
        customer_name = str(context.get("customer_name") or "").strip()
    if not customer_name:
        customer_name = extract_name_from_messages(messages)
    
    # If we have email or phone but no name, try to look up from customer memory
    looked_up_name = None
    if (customer_email or customer_phone) and not customer_name:
        customer_ctx = await get_customer_context(session, customer_email, customer_phone)
        if customer_ctx and customer_ctx.get("name"):
            looked_up_name = customer_ctx.get("name")
            customer_name = looked_up_name

    # During CAPTURE_EMAIL stage, if we have one but not the other, ask for both
    if stage == "CAPTURE_EMAIL":
        has_email = bool(customer_email)
        has_name = bool(customer_name)
        
        # If we looked up name from email/phone, greet them and move on
        if has_email and looked_up_name:
            return ChatResponse(
                reply=f"Welcome back, {looked_up_name}! What service would you like to book?",
                action={"type": "show_services", "params": {}},
            )
        
        if not has_email or not has_name:
            if has_email and not has_name:
                return ChatResponse(
                    reply="Thanks! What's your name?",
                    action=None,
                )
            elif has_name and not has_email:
                return ChatResponse(
                    reply="Nice to meet you! What's your email address?",
                    action=None,
                )
            else:
                # Neither name nor email provided yet
                return ChatResponse(
                    reply="Hi! What's your name and best email to get started?",
                    action=None,
                )

    last_user_text = messages[-1].content if messages else ""
    repeat_intent = bool(
        re.search(
            r"\b(same as last time|same as last|as last time|same as before|same again|again|book me as last time|book me same as last time|same as previous|last time)\b",
            last_user_text,
            re.IGNORECASE,
        )
    )
    if repeat_intent and stage in {"CAPTURE_EMAIL", "WELCOME", "SELECT_SERVICE"} and not selected_service:
        if not customer_email:
            return ChatResponse(
                reply="Sure — what's the email on your last booking?",
                action=None,
            )
        customer_context = await get_customer_context(session, customer_email)
        last_service = customer_context.get("last_service") if customer_context else None
        if last_service:
            service = await find_service_by_name(session, last_service)
            if service:
                return ChatResponse(
                    reply=f"Got it. Booking {service.name} again. Pick a date below to see times.",
                    action={
                        "type": "select_service",
                        "params": {"service_id": service.id, "service_name": service.name},
                    },
                )
    
    # Check for "Yes" confirmation to a date disambiguation question
    if last_user_text and context and context.get("tentative_date"):
        affirmative = re.search(r"\b(yes|yeah|yep|yup|correct|right|sure|ok|okay|confirm|that'?s? right)\b", last_user_text.lower())
        if affirmative:
            tentative_date = context.get("tentative_date")
            service_id = context.get("selected_service_id") or context.get("service_id")
            # User confirmed the date - proceed to fetch availability
            return ChatResponse(
                reply="Here are a few good options. Tap one to continue.",
                action={
                    "type": "fetch_availability",
                    "params": {"date": tentative_date, "service_id": service_id},
                },
                chips=None,  # Clear chips after confirmation
            )
        # Check for negative response
        negative = re.search(r"\b(no|nope|nah|wrong|not right|different|another)\b", last_user_text.lower())
        if negative:
            return ChatResponse(
                reply="No problem. Please provide the full date with month (e.g., January 22).",
                action=None,
                chips=None,
            )
    
    # Check for day-only date input (e.g., "22nd", "5th") - needs confirmation regardless of other context
    if last_user_text:
        tz = ZoneInfo(settings.chat_timezone)
        potential_full_date = extract_date_from_text(last_user_text, tz)
        
        # Only check day-only if we didn't extract a full date
        if not potential_full_date:
            day_only = extract_day_only_from_text(last_user_text)
            if day_only:
                local_now = get_local_now()
                current_month = local_now.month
                current_year = local_now.year
                try:
                    tentative_date = datetime(current_year, current_month, day_only, tzinfo=tz)
                    if tentative_date.date() < local_now.date():
                        if current_month == 12:
                            tentative_date = datetime(current_year + 1, 1, day_only, tzinfo=tz)
                        else:
                            tentative_date = datetime(current_year, current_month + 1, day_only, tzinfo=tz)
                    
                    month_name = tentative_date.strftime("%B")
                    suffix = _get_ordinal_suffix(day_only)
                    formatted_date = tentative_date.strftime("%Y-%m-%d")
                    
                    return ChatResponse(
                        reply=f"Did you mean {day_only}{suffix} {month_name}?",
                        action={
                            "type": "confirm_date",
                            "params": {"tentative_date": formatted_date},
                        },
                        chips=["Yes", "No"],
                    )
                except ValueError:
                    pass
    
    # FAST-PATH: Check if user provided all booking details in current message
    # Extract from last user message if we have name and email already
    if customer_name and customer_email and last_user_text:
        # Get list of services for matching (scoped to shop_id)
        services_result = await session.execute(
            select(Service).where(Service.shop_id == shop_id).order_by(Service.id)
        )
        all_services = services_result.scalars().all()
        service_names = [s.name for s in all_services]
        
        # Extract details from user text
        tz = ZoneInfo(settings.chat_timezone)
        extracted_service_name = extract_service_name_from_text(last_user_text, service_names)
        extracted_date = extract_date_from_text(last_user_text, tz)
        extracted_time = extract_time_from_text(last_user_text)
        extracted_stylist_id, extracted_stylist_name = extract_stylist_from_text(last_user_text)
        
        # If we have all the details, bypass normal flow and hold slot immediately
        if extracted_service_name and extracted_date and extracted_time and extracted_stylist_id:
            service = await find_service_by_name(session, shop_id, extracted_service_name)
            if service:
                return ChatResponse(
                    reply=f"Holding {extracted_time} on {extracted_date} with {extracted_stylist_name}. Tap confirm to finalize.",
                    action={
                        "type": "hold_slot",
                        "params": {
                            "service_id": service.id,
                            "stylist_id": extracted_stylist_id,
                            "date": extracted_date,
                            "start_time": extracted_time,
                            "customer_name": customer_name,
                            "customer_email": customer_email,
                            "customer_phone": "",
                        },
                    },
                )

    # Build system prompt with current context (scoped to shop_id)
    services_text = await get_services_context(session, shop_id)
    stylists_text = await get_stylists_context(session, shop_id)
    
    # Use Arizona timezone for dates
    local_now = get_local_now()
    local_today = get_local_today()
    tomorrow = local_today + timedelta(days=1)
    
    today_formatted = local_today.strftime("%Y-%m-%d (%A, %B %d, %Y)")
    today_date = local_today.strftime("%Y-%m-%d")
    tomorrow_date = tomorrow.strftime("%Y-%m-%d")
    current_time = local_now.strftime("%I:%M %p")
    current_year = local_today.year
    next_year = current_year + 1
    
    # Format working days from settings
    day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    working_day_names = [day_names[i] for i in settings.working_days_list]
    closed_days = [day_names[i] for i in range(7) if i not in settings.working_days_list]
    if working_day_names:
        working_days_text = f"{', '.join(working_day_names)} (closed {', '.join(closed_days)})"
    else:
        working_days_text = 'Monday to Saturday (closed Sunday)'
    
    working_hours_text = f'{settings.working_hours_start} to {settings.working_hours_end}'
    
    selected_date = context.get("selected_date") if context else None
    
    # Determine channel (chat or voice)
    channel = context.get("channel", "chat") if context else "chat"
    
    # Select appropriate prompt based on channel
    base_prompt = VOICE_PROMPT if channel == "voice" else CHAT_PROMPT

    system_prompt = base_prompt.format(
        services=services_text,
        stylists=stylists_text,
        today=today_formatted,
        today_date=today_date,
        tomorrow_date=tomorrow_date,
        current_time=current_time,
        current_year=current_year,
        next_year=next_year,
        working_days=working_days_text,
        working_hours=working_hours_text,
        stage=stage,
        selected_service=selected_service or "None",
        selected_date=selected_date or "None",
        channel=channel,
    )
    
    # Add context information if available
    if context:
        context_parts = []
        if context.get("selected_service"):
            context_parts.append(f"Selected service: {context['selected_service']}")
        if context.get("selected_date"):
            context_parts.append(f"Selected date: {context['selected_date']}")
        if context.get("customer_name"):
            context_parts.append(f"Customer name: {context['customer_name']}")
        if context.get("customer_email"):
            context_parts.append(f"Customer email: {context['customer_email']}")
        if context.get("held_slot"):
            context_parts.append(f"Held slot: {context['held_slot']}")
        if context.get("available_slots"):
            slots_summary = context['available_slots'][:5]  # First 5 slots
            context_parts.append(f"Available slots shown: {slots_summary}")
        if context.get("preferred_style_text") or context.get("preferred_style_image_url"):
            context_parts.append("Preferred style saved for this service.")
        if "has_last_preferred_style" in context:
            context_parts.append(
                f"Has saved style for this service: {bool(context.get('has_last_preferred_style'))}"
            )
        
        if context_parts:
            system_prompt += f"\n\nCURRENT BOOKING CONTEXT:\n" + "\n".join(context_parts)

    if customer_email:
        customer_context = await get_customer_context(session, customer_email)
        if customer_context:
            profile_lines = ["Customer Profile:"]
            if customer_context.get("last_service"):
                profile_lines.append(f"- Last service: {customer_context['last_service']}")
            if customer_context.get("preferred_stylist"):
                profile_lines.append(f"- Preferred stylist: {customer_context['preferred_stylist']}")
            if customer_context.get("average_spend_cents") is not None:
                profile_lines.append(
                    f"- Average spend: {format_cents(int(customer_context['average_spend_cents']))}"
                )
            if customer_context.get("total_bookings") is not None:
                profile_lines.append(
                    f"- Total bookings: {int(customer_context['total_bookings'])}"
                )
            if customer_context.get("last_stylist"):
                profile_lines.append(f"- Last stylist: {customer_context['last_stylist']}")
            system_prompt += "\n\n" + "\n".join(profile_lines)
    
    # Build messages for OpenAI
    openai_messages = [{"role": "system", "content": system_prompt}]
    for msg in messages:
        openai_messages.append({"role": msg.role, "content": msg.content})
    
    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=openai_messages,
            max_tokens=200,
            temperature=0.2,
        )
        
        ai_response = response.choices[0].message.content or ""
        clean_response, action, chips = parse_action_from_response(ai_response)

        allowed = ALLOWED_ACTIONS.get(stage, set())
        if action and action.get("type") not in allowed:
            # allow if it's a sensible downstream action
            if action.get("type") in {"hold_slot", "confirm_booking", "fetch_availability", "select_service", "show_slots"}:
                pass
            else:
                action = None

        reply = shorten_reply(clean_response)
        
        # Use channel-aware stage prompts
        stage_prompts_to_use = VOICE_STAGE_PROMPTS if channel == "voice" else STAGE_PROMPTS
        
        if not reply:
            reply = stage_prompts_to_use.get(stage, stage_prompts_to_use.get("WELCOME", "Welcome!"))

        # Guardrail: never list slots or long text
        if action and action.get("type") == "fetch_availability":
            reply = "Here are a few good options" if channel == "voice" else "Here are a few good options. Tap one to continue."
        elif action and action.get("type") == "select_service":
            reply = "Great choice. What day works for you?" if channel == "voice" else "Great choice. Pick a date below to see times."
        elif not reply:
            reply = stage_prompts_to_use.get(stage, stage_prompts_to_use.get("WELCOME", "Welcome!"))

        time_pattern = re.compile(r"\b\d{1,2}(:\d{2})?\s*(am|pm)\b", re.IGNORECASE)
        count_pattern = re.compile(r"\b\d+\s+(slots|times|options)\b", re.IGNORECASE)
        if stage == "SELECT_SLOT" and (time_pattern.search(reply) or count_pattern.search(reply)):
            reply = stage_prompts_to_use.get("SELECT_SLOT", "Here are a few good options.")

        return ChatResponse(reply=reply, action=action, chips=chips)
        
    except Exception as e:
        import traceback
        print(f"OpenAI API Error: {e}")
        traceback.print_exc()
        return ChatResponse(
            reply=f"I'm having trouble processing your request. Please try again.",
            action=None
        )
