"""
Owner GPT module for managing services via structured actions.
"""
import json
import re
from typing import Any

from openai import AsyncOpenAI
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .core.config import get_settings
from .models import Service, ServiceRule

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


SYSTEM_PROMPT = """You are Owner GPT for a salon. You manage services using structured actions.

RULES:
- Output ONE action at the end of the message using [ACTION: {{...}}].
- If required fields are missing, ask ONE short clarifying question.
- Never invent data or confirm DB changes without an action.
- Supported availability_rule values: weekends_only, weekdays_only, weekday_evenings, none.

SERVICES:
{services}

Actions:
- list_services: {{}}
- create_service: {{"name": "<name>", "duration_minutes": <int>, "price_cents": <int>, "availability_rule": "<rule>"}}
- update_service_price: {{"service_id": <id>, "service_name": "<name>", "price_cents": <int>}}
- update_service_duration: {{"service_id": <id>, "service_name": "<name>", "duration_minutes": <int>}}
- remove_service: {{"service_id": <id>, "service_name": "<name>"}}
- set_service_rule: {{"service_id": <id>, "service_name": "<name>", "availability_rule": "<rule>"}}

Examples:
User: "Add Keratin Treatment: 90 minutes, $200"
Reply: "Got it. I'll add Keratin Treatment." [ACTION: {{"type":"create_service","params":{{"name":"Keratin Treatment","duration_minutes":90,"price_cents":20000,"availability_rule":"none"}}}}]
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


ALLOWED_ACTIONS = {
    "list_services",
    "create_service",
    "update_service_price",
    "update_service_duration",
    "remove_service",
    "set_service_rule",
}


async def owner_chat_with_ai(messages: list[OwnerChatMessage], session: AsyncSession) -> OwnerChatResponse:
    if not settings.openai_api_key:
        return OwnerChatResponse(
            reply="Owner assistant is not configured yet. Please add OPENAI_API_KEY.",
            action=None,
        )

    services_text = await get_services_context(session)
    system_prompt = SYSTEM_PROMPT.format(services=services_text)

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
