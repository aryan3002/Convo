"""
AI Chat module using GPT-4o-mini for conversational appointment booking.
"""
import json
from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from openai import AsyncOpenAI
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .core.config import get_settings
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


SYSTEM_PROMPT = """You are a friendly booking assistant for Bishops Tempe hair salon in Tempe, Arizona.

SERVICES: {services}
STYLISTS: {stylists}

NOW: {today} at {current_time} (Arizona/MST)
WORKING HOURS: {working_hours} ({working_days})

DATE RULES:
- Today: {today_date}, Tomorrow: {tomorrow_date}, Current year: {current_year}
- If user says a month BEFORE current month (e.g. "January" in December), use NEXT YEAR ({next_year})
- Always format dates as YYYY-MM-DD

CRITICAL RULES:
- NEVER make up or list time slots yourself - the system displays them automatically
- When user mentions a date, IMMEDIATELY use fetch_availability - the UI shows slots automatically
- Slots are every 30 minutes (10:00, 10:30, 11:00, etc.) 
- If user picks a time that doesn't exist (like 9:30 or 2:30), tell them to pick from the displayed slots
- NEVER say "let me check", "I'll check", "one moment", "checking" - just include the action and say "Here are the available times:"
- Before holding: collect BOTH name AND email from user

ACTIONS (add at END of message):
[ACTION: {{"type": "action_type", "params": {{...}}}}]

Actions:
- select_service: {{"service_id": <id>, "service_name": "<name>"}}
- fetch_availability: {{"service_id": <id>, "date": "YYYY-MM-DD"}}
- hold_slot: {{"service_id": <id>, "stylist_id": <id>, "date": "YYYY-MM-DD", "start_time": "HH:MM", "customer_name": "<name>", "customer_email": "<email>"}}
- confirm_booking: {{}}

BOOKING FLOW:
1. User picks service → select_service action, ask for date
2. User picks date → IMMEDIATELY use fetch_availability action and say "Here are the available times for [date]:" (slots appear automatically)
3. User picks time from displayed slots → ask which stylist (Alex=ID 1, Jamie=ID 2) + their name + their email
4. Once you have ALL of: time + stylist + name + email → immediately use hold_slot action with ALL params
5. After hold succeeds → use confirm_booking action to finalize

RESPONSE STYLE:
- Be friendly and brief
- When fetching availability, just say "Here are the available times for [date]:" and include the action - slots show automatically
- NEVER announce you're checking or looking - just do it
- Don't list times yourself - they appear automatically in the chat
"""


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
        working_hours=working_hours_text
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
    
    # Build messages for OpenAI
    openai_messages = [{"role": "system", "content": system_prompt}]
    for msg in messages:
        openai_messages.append({"role": msg.role, "content": msg.content})
    
    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=openai_messages,
            max_tokens=1000,
            temperature=0.7,
        )
        
        ai_response = response.choices[0].message.content or ""
        clean_response, action = parse_action_from_response(ai_response)
        
        return ChatResponse(reply=clean_response, action=action)
        
    except Exception as e:
        import traceback
        print(f"OpenAI API Error: {e}")
        traceback.print_exc()
        return ChatResponse(
            reply=f"I'm having trouble processing your request. Please try again.",
            action=None
        )
