"""
Owner GPT module for managing services via structured actions.
Includes semantic search over call transcripts and booking notes.
"""
import json
import re
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from openai import AsyncOpenAI
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .core.config import get_settings
from .models import Service, ServiceRule, Stylist, StylistSpecialty
from .vector_search import get_context_for_query, search_similar_chunks
from .tenancy import LEGACY_DEFAULT_SHOP_ID

settings = get_settings()

SUPPORTED_RULES = {"weekends_only", "weekdays_only", "weekday_evenings", "none"}


class OwnerChatMessage(BaseModel):
    role: str  # "user" | "assistant" | "system"
    content: str


class OwnerChatRequest(BaseModel):
    messages: list[OwnerChatMessage]


class OwnerChatResponse(BaseModel):
    reply: str
    action: dict | None = None
    data: dict | None = None


SYSTEM_PROMPT = """You are Owner GPT for a salon. You manage services and stylists using structured actions.
Assume the timezone is America/Phoenix (Tempe). Do not ask for timezone; use this by default.

RULES:
- Output ONE action at the end of the message using [ACTION: {{...}}] for any create, update, remove, or list request.
- For booking/schedule questions, always use list_schedule instead of guessing.
- For moving bookings, use reschedule_booking with from_time and to_time.
- If required fields are missing, ask ONE short clarifying question.
- Never invent data or confirm DB changes without an action.
- When outputting an action, DO NOT include a confirmation message - the system will automatically confirm the action.
- Supported availability_rule values: weekends_only, weekdays_only, weekday_evenings, none.
- If the user says add/create/new service, use create_service (never update_service_price).
- Use 24h time (HH:MM) and ISO dates (YYYY-MM-DD).
- Today is {today} in {timezone}.
- If the user gives a time range like "from 12pm-9pm", map it to work_start/work_end or time off.
- For customer history or preferences, use get_customer_profile or list_customers_by_stylist.
- Promotions require structured fields. Ask one short clarification at a time if anything is missing.
- For questions about past calls, customer feedback, or conversations, use search_calls to find relevant transcripts.

SERVICES:
{services}

STYLISTS:
{stylists}

{call_context}

PROMO TYPES:
- FIRST_USER_PROMO
- DAILY_PROMO
- SEASONAL_PROMO
- SERVICE_COMBO_PROMO (requires service_id and trigger points after service selection)

PROMO TRIGGER POINTS:
- AT_CHAT_START
- AFTER_EMAIL_CAPTURE
- AFTER_SERVICE_SELECTED
- AFTER_SLOT_SHOWN
- AFTER_HOLD_CREATED

DISCOUNT TYPES:
- PERCENT
- FIXED
- FREE_ADDON
- BUNDLE

Actions:
- list_services: {{}}
- list_promos: {{}}
- list_schedule: {{"date": "YYYY-MM-DD", "tz_offset_minutes": <int>}}
- reschedule_booking: {{"date": "YYYY-MM-DD", "from_stylist_name": "<name>", "to_stylist_name": "<name>", "from_time": "HH:MM", "to_time": "HH:MM", "tz_offset_minutes": <int>}}
- create_service: {{"name": "<name>", "duration_minutes": <int>, "price_cents": <int>, "availability_rule": "<rule>"}}
- update_service_price: {{"service_id": <id>, "service_name": "<name>", "price_cents": <int>}}
- update_service_duration: {{"service_id": <id>, "service_name": "<name>", "duration_minutes": <int>}}
- remove_service: {{"service_id": <id>, "service_name": "<name>"}}
- set_service_rule: {{"service_id": <id>, "service_name": "<name>", "availability_rule": "<rule>"}}
- list_stylists: {{}}
- create_stylist: {{"name": "<name>", "work_start": "HH:MM", "work_end": "HH:MM"}}
- remove_stylist: {{"stylist_id": <id>, "stylist_name": "<name>"}}
- update_stylist_hours: {{"stylist_id": <id>, "stylist_name": "<name>", "work_start": "HH:MM", "work_end": "HH:MM"}}
- update_stylist_specialties: {{"stylist_id": <id>, "stylist_name": "<name>", "tags": ["color","balayage"]}}
- add_time_off: {{"stylist_id": <id>, "stylist_name": "<name>", "date": "YYYY-MM-DD", "start_time": "HH:MM", "end_time": "HH:MM"}}
- remove_time_off: {{"stylist_name": "<name>", "date": "YYYY-MM-DD"}}  (start_time/end_time optional; removes all time off for that date if not specified)
- get_customer_profile: {{"email": "name@example.com"}}
- list_customers_by_stylist: {{"stylist_name": "<name>"}}
- search_calls: {{"query": "<natural language question about calls>"}}  (searches call transcripts and summaries semantically)
- create_promo: {{"type": "<PROMO_TYPE>", "trigger_point": "<TRIGGER_POINT>", "discount_type": "<DISCOUNT_TYPE>", "discount_value": <int>, "service_id": <id|null>, "constraints_json": {{"min_spend_cents": 2000, "valid_days_of_week":[0,1,2], "usage_limit_per_customer": 1}}, "custom_copy": "<optional>", "start_at": "YYYY-MM-DD", "end_at": "YYYY-MM-DD", "active": true, "priority": 0}}
- update_promo: {{"promo_id": <id>, "trigger_point": "<TRIGGER_POINT>", "active": false}}
- delete_promo: {{"promo_id": <id>}}

Examples:
User: "Create Keratin Treatment: 90 minutes, $200"
Reply: "Got it. I'll create Keratin Treatment." [ACTION: {{"type":"create_service","params":{{"name":"Keratin Treatment","duration_minutes":90,"price_cents":20000,"availability_rule":"none"}}}}]
User: "Alex is off next Tuesday 2–6pm"
Reply: "Got it. I'll add that time off." [ACTION: {{"type":"add_time_off","params":{{"stylist_name":"Alex","date":"YYYY-MM-DD","start_time":"14:00","end_time":"18:00"}}}}]
User: "Add time off for Alex on December 30 from 11am to 2pm"
Reply: "Got it. I'll add that time off." [ACTION: {{"type":"add_time_off","params":{{"stylist_name":"Alex","date":"2025-12-30","start_time":"11:00","end_time":"14:00"}}}}]
User: "Remove time off for Alex on Tuesday"
Reply: "Got it. I'll remove all time off for Alex on Tuesday." [ACTION: {{"type":"remove_time_off","params":{{"stylist_name":"Alex","date":"YYYY-MM-DD"}}}}]
User: "Remove time off for Alex on Tuesday from 2–6pm"
Reply: "Got it. I'll remove that time off." [ACTION: {{"type":"remove_time_off","params":{{"stylist_name":"Alex","date":"YYYY-MM-DD","start_time":"14:00","end_time":"18:00"}}}}]
User: "Add a new stylist named John"
Reply: "Got it. I'll add John as a new stylist." [ACTION: {{"type":"create_stylist","params":{{"name":"John","work_start":"09:00","work_end":"17:00"}}}}]
User: "Remove John as a stylist"
Reply: "Got it. I'll remove John." [ACTION: {{"type":"remove_stylist","params":{{"stylist_name":"John"}}}}]
User: "Show me Aryan's booking history (aryan@email.com)"
Reply: "Here is Aryan's booking history." [ACTION: {{"type":"get_customer_profile","params":{{"email":"aryan@email.com"}}}}]
User: "Which customers prefer Alex?"
Reply: "Here are customers who prefer Alex." [ACTION: {{"type":"list_customers_by_stylist","params":{{"stylist_name":"Alex"}}}}]
User: "Add a daily promo for 10% off after email capture"
Reply: "Got it. I'll add that promotion." [ACTION: {{"type":"create_promo","params":{{"type":"DAILY_PROMO","trigger_point":"AFTER_EMAIL_CAPTURE","discount_type":"PERCENT","discount_value":10,"active":true,"priority":0}}}}]
"""


def parse_action_from_response(response: str) -> tuple[str, dict | None]:
    action = None
    clean_response = response
    pattern = r"\[ACTION:\s*(\{.*\})\]"
    match = re.search(pattern, response, re.DOTALL)
    if match:
        try:
            raw_action = json.loads(match.group(1))
            if "type" in raw_action:
                if "params" not in raw_action:
                    params = {k: v for k, v in raw_action.items() if k != "type"}
                    action = {"type": raw_action["type"], "params": params}
                else:
                    action = raw_action
            clean_response = response[: match.start()].strip()
        except json.JSONDecodeError:
            clean_response = re.sub(r"\[ACTION:.*\]\]?", "", response, flags=re.DOTALL).strip()
    return clean_response, action


def shorten_reply(text: str) -> str:
    cleaned = " ".join(text.split())
    if not cleaned:
        return ""
    first_line = cleaned.split("\n", 1)[0]
    sentence = re.split(r"(?<=[.!?])\s", first_line)[0]
    if len(sentence) > 160:
        sentence = sentence[:157].rstrip() + "..."
    return sentence


async def get_services_context(session: AsyncSession) -> str:
    result = await session.execute(select(Service).order_by(Service.id))
    services = result.scalars().all()
    if not services:
        return "No services available."

    rules_result = await session.execute(select(ServiceRule))
    rules = {r.service_id: r.rule for r in rules_result.scalars().all()}

    lines = []
    for svc in services:
        price = svc.price_cents / 100
        rule = rules.get(svc.id, "none")
        lines.append(f"- ID {svc.id}: {svc.name} (${price:.2f}, {svc.duration_minutes} min, rule={rule})")
    return "\n".join(lines)


async def get_stylists_context(session: AsyncSession) -> str:
    result = await session.execute(select(Stylist).order_by(Stylist.id))
    stylists = result.scalars().all()
    if not stylists:
        return "No stylists available."

    specialties_result = await session.execute(select(StylistSpecialty))
    specialties: dict[int, list[str]] = {}
    for specialty in specialties_result.scalars().all():
        specialties.setdefault(specialty.stylist_id, []).append(specialty.tag)

    lines = []
    for stylist in stylists:
        tags = ", ".join(sorted(specialties.get(stylist.id, []))) or "none"
        lines.append(
            f"- ID {stylist.id}: {stylist.name} ({stylist.work_start.strftime('%H:%M')}–{stylist.work_end.strftime('%H:%M')}, specialties={tags})"
        )
    return "\n".join(lines)


ALLOWED_ACTIONS = {
    "list_services",
    "list_promos",
    "list_schedule",
    "reschedule_booking",
    "create_service",
    "update_service_price",
    "update_service_duration",
    "remove_service",
    "set_service_rule",
    "list_stylists",
    "create_stylist",
    "remove_stylist",
    "update_stylist_hours",
    "update_stylist_specialties",
    "add_time_off",
    "remove_time_off",
    "get_customer_profile",
    "list_customers_by_stylist",
    "search_calls",
    "create_promo",
    "update_promo",
    "delete_promo",
}

# PHASE 2: Use LEGACY_DEFAULT_SHOP_ID from tenancy module


async def get_call_context_for_query(user_query: str, session: AsyncSession, shop_id: int = LEGACY_DEFAULT_SHOP_ID) -> str:
    """
    Check if the user query might benefit from call transcript context.
    If so, fetch relevant chunks from the vector store.
    """
    # Keywords that suggest the user wants info from past calls
    call_keywords = [
        "call", "calls", "transcript", "conversation", "said", "mentioned",
        "complaint", "feedback", "customer said", "asked about", "requested",
        "why did", "what did", "how many", "issue", "problem"
    ]
    
    query_lower = user_query.lower()
    needs_context = any(kw in query_lower for kw in call_keywords)
    
    if not needs_context:
        return ""
    
    try:
        context = await get_context_for_query(
            session=session,
            shop_id=shop_id,
            query=user_query,
            max_tokens=1500,  # Leave room for other context
            limit=5,
        )
        if context:
            return f"RELEVANT CALL CONTEXT:\n{context}"
    except Exception as e:
        # Don't fail the chat if vector search fails
        import logging
        logging.getLogger(__name__).warning(f"Failed to fetch call context: {e}")
    
    return ""


async def owner_chat_with_ai(messages: list[OwnerChatMessage], session: AsyncSession) -> OwnerChatResponse:
    if not settings.openai_api_key:
        return OwnerChatResponse(
            reply="Owner assistant is not configured yet. Please add OPENAI_API_KEY.",
            action=None,
        )

    services_text = await get_services_context(session)
    stylists_text = await get_stylists_context(session)
    tz = ZoneInfo(settings.chat_timezone)
    today = datetime.now(tz).strftime("%Y-%m-%d")
    
    # Get relevant call context if the user query suggests it
    last_user_message = ""
    for msg in reversed(messages):
        if msg.role == "user":
            last_user_message = msg.content
            break
    
    call_context = ""
    if last_user_message:
        call_context = await get_call_context_for_query(last_user_message, session)
    
    system_prompt = SYSTEM_PROMPT.format(
        services=services_text,
        stylists=stylists_text,
        call_context=call_context,
        today=today,
        timezone=settings.chat_timezone,
    )

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    openai_messages = [{"role": "system", "content": system_prompt}]
    for msg in messages:
        openai_messages.append({"role": msg.role, "content": msg.content})

    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=openai_messages,
        max_tokens=200,
        temperature=0.2,
    )

    ai_response = response.choices[0].message.content or ""
    clean_response, action = parse_action_from_response(ai_response)
    reply = shorten_reply(clean_response)
    if not reply:
        reply = "What would you like to change?"

    if action and action.get("type") not in ALLOWED_ACTIONS:
        action = None

    params = action.get("params") if action else {}
    if params:
        rule = params.get("availability_rule")
        if rule and rule not in SUPPORTED_RULES:
            action = None
            reply = "That rule isn't supported yet. Use weekends_only, weekdays_only, weekday_evenings, or none."

    return OwnerChatResponse(reply=reply, action=action)
