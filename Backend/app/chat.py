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
from .customer_memory import get_customer_context
from .models import Service, Stylist

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


SYSTEM_PROMPT = """You are a friendly booking assistant for Bishops Tempe hair salon in Tempe, Arizona.

SERVICES: {services}
STYLISTS: {stylists}

NOW: {today} at {current_time} (Arizona/MST)
WORKING HOURS: {working_hours} ({working_days})
CURRENT STAGE: {stage}
SELECTED SERVICE: {selected_service}
SELECTED DATE: {selected_date}

DATE RULES:
- Today: {today_date}, Tomorrow: {tomorrow_date}, Current year: {current_year}
- If user says a month BEFORE current month (e.g. "January" in December), use NEXT YEAR ({next_year})
- Always format dates as YYYY-MM-DD

CRITICAL RULES:
- Be brief. One sentence only. Never list more than 3 items in text.
- Do NOT list time slots in text. The UI shows them as buttons.
- Never claim a booking is held or confirmed unless the backend tool succeeds.
- If user mentions a date, use fetch_availability and say: "Here are a few good options. Tap one to continue."
- If user tries to type a time, ask them to tap a time option.
- Before holding: collect BOTH name AND email from user.
- Follow the CURRENT STAGE and do not skip steps.
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
- hold_slot: {{"service_id": <id>, "stylist_id": <id>, "date": "YYYY-MM-DD", "start_time": "HH:MM", "customer_name": "<name>", "customer_email": "<email>"}}
- confirm_booking: {{}}

BOOKING FLOW:
1. User picks service → select_service action, ask for date
2. User picks date → IMMEDIATELY use fetch_availability action and say "Here are the available times for [date]:" (slots appear automatically)
3. User picks time from displayed slots → ask which stylist (Alex=ID 1, Jamie=ID 2) + their name + their email
4. Once you have ALL of: time + stylist + name + email → immediately use hold_slot action with ALL params
5. After a hold exists, ask the user to confirm; only use confirm_booking when they confirm

RESPONSE STYLE:
- Be professional and brief (one sentence)
- When fetching availability, say "Here are a few good options. Tap one to continue."
- Never list times, names, or multiple options in plain text
"""

ALLOWED_STAGES = {
    "WELCOME",
    "SELECT_SERVICE",
    "SELECT_DATE",
    "SELECT_SLOT",
    "HOLDING",
    "CONFIRMING",
    "DONE",
}

ALLOWED_ACTIONS = {
    "WELCOME": {"show_services", "select_service", "fetch_availability", "hold_slot", "confirm_booking", "show_slots"},
    "SELECT_SERVICE": {"show_services", "select_service", "fetch_availability", "hold_slot", "confirm_booking", "show_slots"},
    "SELECT_DATE": {"fetch_availability", "hold_slot", "confirm_booking", "show_slots"},
    "SELECT_SLOT": {"hold_slot", "confirm_booking", "show_slots"},
    "HOLDING": {"confirm_booking", "hold_slot"},
    "CONFIRMING": {"confirm_booking"},
    "DONE": {"show_services", "select_service", "fetch_availability", "hold_slot", "confirm_booking", "show_slots"},
}

STAGE_PROMPTS = {
    "WELCOME": "Welcome! What service would you like to book?",
    "SELECT_SERVICE": "Which service would you like? Please tap a service.",
    "SELECT_DATE": "Pick a date below to see times.",
    "SELECT_SLOT": "Here are a few good options. Tap one to continue.",
    "HOLDING": "One moment while I reserve that.",
    "CONFIRMING": "Tap confirm to finalize your booking.",
    "DONE": "You are all set. Anything else I can help with?",
}


def parse_action_from_response(response: str) -> tuple[str, dict | None]:
    """Extract action JSON from response text."""
    import re
    
    action = None
    clean_response = response
    
    # Look for [ACTION: {...}] pattern - use greedy match for nested braces
    action_pattern = r'\[ACTION:\s*(\{[^[\]]*\})\]'
    match = re.search(action_pattern, response, re.DOTALL)
    
    if not match:
        # Try alternative pattern with nested braces
        action_pattern = r'\[ACTION:\s*(\{.*\})\]'
        match = re.search(action_pattern, response, re.DOTALL)
    
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
            
            clean_response = response[:match.start()].strip()
        except json.JSONDecodeError:
            # If JSON parsing fails, just strip the action text anyway
            clean_response = re.sub(r'\[ACTION:.*?\]\]?', '', response, flags=re.DOTALL).strip()
    
    return clean_response, action


def normalize_stage(value: Any) -> str:
    if not value:
        return "WELCOME"
    text = str(value).strip().upper()
    return text if text in ALLOWED_STAGES else "WELCOME"


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


def extract_email_from_messages(messages: list[ChatMessage]) -> str:
    for msg in reversed(messages):
        if msg.role != "user":
            continue
        match = re.search(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", msg.content, re.IGNORECASE)
        if match:
            return match.group(0).strip().lower()
    return ""


async def find_service_by_name(session: AsyncSession, name: str) -> Service | None:
    if not name:
        return None
    result = await session.execute(
        select(Service).where(Service.name.ilike(f"%{name.strip()}%")).order_by(Service.id)
    )
    return result.scalar_one_or_none()


async def get_services_context(session: AsyncSession) -> str:
    """Get formatted services list for the system prompt."""
    result = await session.execute(select(Service).order_by(Service.id))
    services = result.scalars().all()
    
    if not services:
        return "No services available"
    
    lines = []
    for svc in services:
        price = svc.price_cents / 100
        lines.append(f"- ID {svc.id}: {svc.name} (${price:.2f}, {svc.duration_minutes} min)")
    return "\n".join(lines)


async def get_stylists_context(session: AsyncSession) -> str:
    """Get formatted stylists list for the system prompt."""
    result = await session.execute(select(Stylist).where(Stylist.active.is_(True)).order_by(Stylist.id))
    stylists = result.scalars().all()
    
    if not stylists:
        return "No stylists available"
    
    lines = []
    for stylist in stylists:
        lines.append(f"- ID {stylist.id}: {stylist.name}")
    return "\n".join(lines)


async def chat_with_ai(
    messages: list[ChatMessage],
    session: AsyncSession,
    context: dict | None = None
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

    last_user_text = messages[-1].content if messages else ""
    repeat_intent = bool(
        re.search(
            r"\b(same as last time|same as last|as last time|same as before|same again|again|book me as last time|book me same as last time|same as previous|last time)\b",
            last_user_text,
            re.IGNORECASE,
        )
    )
    if repeat_intent and stage in {"WELCOME", "SELECT_SERVICE"} and not selected_service:
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

    # Build system prompt with current context
    services_text = await get_services_context(session)
    stylists_text = await get_stylists_context(session)
    
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

    system_prompt = SYSTEM_PROMPT.format(
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
        clean_response, action = parse_action_from_response(ai_response)

        allowed = ALLOWED_ACTIONS.get(stage, set())
        if action and action.get("type") not in allowed:
            # allow if it's a sensible downstream action
            if action.get("type") in {"hold_slot", "confirm_booking", "fetch_availability", "select_service", "show_slots"}:
                pass
            else:
                action = None

        reply = shorten_reply(clean_response)
        if not reply:
            reply = STAGE_PROMPTS.get(stage, STAGE_PROMPTS["WELCOME"])

        # Guardrail: never list slots or long text
        if action and action.get("type") == "fetch_availability":
            reply = "Here are a few good options. Tap one to continue."
        elif action and action.get("type") == "select_service":
            reply = "Great choice. Pick a date below to see times."
        elif not reply:
            reply = STAGE_PROMPTS.get(stage, STAGE_PROMPTS["WELCOME"])

        time_pattern = re.compile(r"\b\d{1,2}(:\d{2})?\s*(am|pm)\b", re.IGNORECASE)
        count_pattern = re.compile(r"\b\d+\s+(slots|times|options)\b", re.IGNORECASE)
        if stage == "SELECT_SLOT" and (time_pattern.search(reply) or count_pattern.search(reply)):
            reply = STAGE_PROMPTS["SELECT_SLOT"]

        return ChatResponse(reply=reply, action=action)
        
    except Exception as e:
        import traceback
        print(f"OpenAI API Error: {e}")
        traceback.print_exc()
        return ChatResponse(
            reply=f"I'm having trouble processing your request. Please try again.",
            action=None
        )
