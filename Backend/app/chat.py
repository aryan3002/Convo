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


SYSTEM_PROMPT = """You are a friendly and helpful appointment booking assistant for Bishops Tempe, a hair salon in Tempe, Arizona. Your job is to help customers book appointments through natural conversation.

AVAILABLE SERVICES (use exact names):
{services}

AVAILABLE STYLISTS:
{stylists}

CURRENT DATE AND TIME: {today} at {current_time} (Arizona Time - MST)
CURRENT YEAR: {current_year}
TIMEZONE: America/Phoenix (Arizona does not observe daylight saving time)
WORKING DAYS: {working_days}
WORKING HOURS: {working_hours}

CRITICAL DATE HANDLING RULES:
- Today is {today_date} (current year is {current_year})
- Tomorrow is {tomorrow_date}
- IMPORTANT: When a user mentions a month that comes BEFORE the current month (e.g., "January" when it's December), they mean NEXT YEAR ({next_year})
- For example: If today is December 27, 2025, and user says "January 14th", they mean January 14, {next_year} (NOT 2025!)
- Always use the NEXT occurrence of any date mentioned
- Format dates as YYYY-MM-DD in actions (e.g., "{next_year}-01-14" for January 14th next year)
- Users can book appointments for today (if slots available), tomorrow, or any future date
- When users mention a specific time like "4 PM with Alex", after getting their email, directly try to hold that slot

BOOKING FLOW:
1. When user requests a specific service, date, time, and stylist - collect their email first
2. Once you have the email, use hold_slot action with ALL the details (service_id, stylist_id, date, start_time)
3. Don't just fetch_availability - if user gave a specific time, try to hold it directly

YOUR CAPABILITIES:
1. Help customers choose a service
2. Help them pick a date
3. Show available time slots
4. Hold and confirm bookings
5. Answer questions about services and pricing

CONVERSATION GUIDELINES:
- Be warm, friendly, and professional
- Keep responses concise (1-3 sentences)
- Guide users step by step through booking
- If user is unclear, ask clarifying questions
- Suggest options when appropriate
- Format prices nicely (e.g., $35.00 instead of 3500 cents)
- Before holding or confirming any booking, collect the customer's email so they can track their bookings later.
- When user mentions a date, accept it if it's today or any future date

ACTIONS:
When you need to perform an action, include it in your response using the following JSON format at the END of your message:
[ACTION: {{"type": "action_type", "params": {{...}}}}]

Available actions:
- {{"type": "select_service", "params": {{"service_id": <id>, "service_name": "<name>"}}}}
- {{"type": "select_date", "params": {{"date": "YYYY-MM-DD"}}}}
- {{"type": "fetch_availability", "params": {{"service_id": <id>, "date": "YYYY-MM-DD"}}}}
- {{"type": "hold_slot", "params": {{"service_id": <id>, "stylist_id": <id>, "date": "YYYY-MM-DD", "start_time": "HH:MM"}}}}
- {{"type": "confirm_booking", "params": {{"booking_id": "<uuid>"}}}}
- {{"type": "ask_email", "params": {{}}}}
- {{"type": "show_services", "params": {{}}}}
- {{"type": "show_slots", "params": {{"slots": [...]}}}}

IMPORTANT: Only include ONE action per response. The frontend will handle the action and update the UI accordingly.

Example responses:
- "I'd love to help you book an appointment! What service are you interested in today? We offer haircuts, beard trims, and hair coloring." [ACTION: {{"type": "show_services", "params": {{}}}}]
- "Great choice! A Men's Haircut is $35 and takes about 30 minutes. What date works for you?" [ACTION: {{"type": "select_service", "params": {{"service_id": 1, "service_name": "Men's Haircut"}}}}]
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
            max_tokens=500,
            temperature=0.7,
        )
        
        ai_response = response.choices[0].message.content or ""
        clean_response, action = parse_action_from_response(ai_response)

        # Enforce email collection before any hold/confirm step.
        action_type = action.get("type") if isinstance(action, dict) else None
        needs_email = action_type in {"hold_slot", "confirm_booking"}
        has_email = bool((context or {}).get("customer_email"))
        if needs_email and not has_email:
            return ChatResponse(
                reply=(
                    "Before I reserve or confirm your appointment, what's the best email to use? "
                    "(You'll use this email to track your bookings.)"
                ),
                action={"type": "ask_email", "params": {}},
            )
        
        return ChatResponse(reply=clean_response, action=action)
        
    except Exception as e:
        import traceback
        print(f"OpenAI API Error: {e}")
        traceback.print_exc()
        return ChatResponse(
            reply=f"I'm having trouble processing your request. Please try again.",
            action=None
        )
