"""
AI Chat module using GPT-4o-mini for conversational appointment booking.
"""
import json
import re
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from openai import AsyncOpenAI
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .core.config import get_settings
from .models import Service, Stylist

settings = get_settings()


class ChatMessage(BaseModel):
    role: str  # "user" | "assistant" | "system"
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    context: dict | None = None  # Optional context like selected service, date, etc.


class ChatResponse(BaseModel):
    reply: str
    action: dict | None = None  # Legacy single action for current frontend
    assistant_text: str
    actions: list[dict] = []
    next_state: str
    chips: list[str] | None = None


class AIAction(BaseModel):
    type: str
    params: dict = Field(default_factory=dict)


class AIResponsePayload(BaseModel):
    assistant_text: str
    actions: list[AIAction] = []
    next_state: str
    chips: list[str] | None = None


SYSTEM_PROMPT = """You are a friendly and helpful appointment booking assistant for Bishops Tempe, a hair salon. Your job is to help customers book appointments through natural conversation.

AVAILABLE SERVICES (use exact names):
{services}

AVAILABLE STYLISTS:
{stylists}

TODAY'S DATE (Arizona): {today}
TIMEZONE: {timezone}
WORKING DAYS: {working_days}
WORKING HOURS (default): {working_hours}

YOUR CAPABILITIES:
1. Help customers choose a service
2. Help them pick a date
3. Show available time slots
4. Hold and confirm bookings
5. Answer questions about services and pricing

STATE MACHINE:
- START: greet and ask for service
- NEED_SERVICE: ask for service
- NEED_DATE: ask for a date (YYYY-MM-DD)
- NEED_TIME: ask for time preference (morning/afternoon/evening)
- SHOWING_SLOTS: ask the user to pick a time slot
- HOLDING: ask to confirm the held slot
- CONFIRMED: confirm and offer further help

CONVERSATION GUIDELINES:
- Be warm, friendly, and professional
- Keep responses concise (1-3 sentences)
- Guide users step by step through booking
- If user is unclear, ask clarifying questions
- Suggest options when appropriate
- Format prices nicely (e.g., $35.00 instead of 3500 cents)
- Do not guess the day-of-week; if needed, ask for the exact date.
- Never say you "held" or "confirmed" a booking unless you include the corresponding action.
- Do not invent availability or times. Always request availability via action.
- Ask only one question at a time.

ACTIONS:
Return JSON ONLY with the following fields:
- assistant_text: string
- actions: array of objects {type, params}
- next_state: one of START, NEED_SERVICE, NEED_DATE, NEED_TIME, SHOWING_SLOTS, HOLDING, CONFIRMED
- chips: optional array of short suggestion strings

Available action types:
- SELECT_SERVICE (service_id, service_name)
- SET_DATE (date: YYYY-MM-DD)
- FETCH_AVAILABILITY (service_id, date)
- HOLD_SLOT (service_id, stylist_id, date, start_time)
- CONFIRM_BOOKING (booking_id)
- SHOW_SERVICES
- SHOW_SLOTS

IMPORTANT: Use at most ONE action per response. If asking a question, keep actions empty.
Return ONLY valid JSON and nothing else.
"""


def _extract_action_json(response: str) -> tuple[str, dict | None]:
    """Extract action JSON from response text, allowing nested braces."""
    action = None
    clean_response = response
    marker = "[ACTION:"
    marker_index = response.find(marker)

    if marker_index == -1:
        return clean_response, None

    brace_start = response.find("{", marker_index)
    if brace_start == -1:
        return clean_response, None

    depth = 0
    brace_end = None
    for idx in range(brace_start, len(response)):
        ch = response[idx]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                brace_end = idx + 1
                break

    if brace_end is None:
        return clean_response, None

    action_str = response[brace_start:brace_end]
    try:
        action = json.loads(action_str)
        clean_response = response[:marker_index].strip()
    except json.JSONDecodeError:
        pass

    return clean_response, action


def _working_days_text(days: list[int]) -> str:
    names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    open_days = [names[i] for i in days if 0 <= i <= 6]
    closed_days = [names[i] for i in range(7) if i not in days]
    open_text = ", ".join(open_days) if open_days else "None"
    if closed_days:
        return f"{open_text} (closed {', '.join(closed_days)})"
    return open_text


BOOKING_STATES = {
    "START",
    "NEED_SERVICE",
    "NEED_DATE",
    "NEED_TIME",
    "SHOWING_SLOTS",
    "HOLDING",
    "CONFIRMED",
}


ACTION_TYPE_MAP = {
    "SELECT_SERVICE": "select_service",
    "SET_DATE": "select_date",
    "FETCH_AVAILABILITY": "fetch_availability",
    "HOLD_SLOT": "hold_slot",
    "CONFIRM_BOOKING": "confirm_booking",
    "SHOW_SERVICES": "show_services",
    "SHOW_SLOTS": "show_slots",
}


def _normalize_state(state: str | None) -> str:
    if not state:
        return "START"
    upper = state.strip().upper()
    return upper if upper in BOOKING_STATES else "START"


def _infer_state(context: dict | None) -> str:
    if not context:
        return "START"
    context_state = _normalize_state(context.get("booking_state"))
    if context_state != "START":
        return context_state
    if context.get("confirmed"):
        return "CONFIRMED"
    if context.get("booking_id") and context.get("held_slot"):
        return "HOLDING"
    if context.get("available_slots"):
        return "SHOWING_SLOTS"
    if context.get("selected_service") and context.get("selected_date"):
        return "NEED_TIME"
    if context.get("selected_service"):
        return "NEED_DATE"
    return "NEED_SERVICE"


def _derive_next_state(current_state: str, action_type: str | None, llm_state: str | None) -> str:
    if action_type == "select_service":
        return "NEED_DATE"
    if action_type == "select_date":
        return "NEED_TIME"
    if action_type in {"fetch_availability", "show_slots"}:
        return "SHOWING_SLOTS"
    if action_type == "hold_slot":
        return "HOLDING"
    if action_type == "confirm_booking":
        return "CONFIRMED"
    if action_type == "show_services":
        return "NEED_SERVICE"
    if llm_state:
        return _normalize_state(llm_state)
    return current_state


def _normalize_action(action: AIAction | None) -> dict | None:
    if not action:
        return None
    action_type = ACTION_TYPE_MAP.get(action.type.strip().upper(), action.type.strip().lower())
    return {"type": action_type, "params": action.params or {}}


def _action_has_required_params(action: AIAction) -> bool:
    action_type = action.type.strip().upper()
    params = action.params or {}
    required = {
        "SELECT_SERVICE": ["service_id"],
        "SET_DATE": ["date"],
        "FETCH_AVAILABILITY": ["service_id", "date"],
        "HOLD_SLOT": ["service_id", "stylist_id", "date", "start_time"],
        "CONFIRM_BOOKING": ["booking_id"],
    }.get(action_type)
    if not required:
        return True
    return all(params.get(key) for key in required)


def _build_fallback(state: str) -> AIResponsePayload:
    if state in {"START", "NEED_SERVICE"}:
        return AIResponsePayload(
            assistant_text="What service would you like to book?",
            actions=[AIAction(type="SHOW_SERVICES", params={})],
            next_state="NEED_SERVICE",
            chips=None,
        )
    if state == "NEED_DATE":
        return AIResponsePayload(
            assistant_text="What day works best for you? Please share a date (YYYY-MM-DD).",
            actions=[],
            next_state="NEED_DATE",
            chips=None,
        )
    if state == "NEED_TIME":
        return AIResponsePayload(
            assistant_text="Any time preference? Morning, afternoon, or evening?",
            actions=[],
            next_state="NEED_TIME",
            chips=None,
        )
    if state == "SHOWING_SLOTS":
        return AIResponsePayload(
            assistant_text="Here are the available times. Tap one to hold it.",
            actions=[AIAction(type="SHOW_SLOTS", params={})],
            next_state="SHOWING_SLOTS",
            chips=None,
        )
    if state == "HOLDING":
        return AIResponsePayload(
            assistant_text="Would you like me to confirm this booking?",
            actions=[],
            next_state="HOLDING",
            chips=None,
        )
    if state == "CONFIRMED":
        return AIResponsePayload(
            assistant_text="You're all set. Anything else I can help with?",
            actions=[],
            next_state="CONFIRMED",
            chips=None,
        )
    return AIResponsePayload(
        assistant_text="How can I help you book an appointment?",
        actions=[],
        next_state="START",
        chips=None,
    )


def _render_assistant_text(
    payload_text: str,
    current_state: str,
    action: dict | None,
    context: dict | None,
) -> str:
    action_type = action["type"] if action else None
    params = action.get("params", {}) if action else {}

    if action_type == "show_services":
        return "What service would you like to book?"
    if action_type == "select_service":
        service_name = params.get("service_name") or "that service"
        return f"Great choice. What date works best for your {service_name}?"
    if action_type == "select_date":
        return "Got it. Any time preference? Morning, afternoon, or evening?"
    if action_type == "fetch_availability":
        date_val = params.get("date")
        if date_val:
            return f"Checking availability for {date_val}."
        return "Checking availability for that date."
    if action_type == "show_slots":
        return "Here are the available times. Tap one to hold it."
    if action_type == "hold_slot":
        return "Got it — holding that time. Tap Confirm to finalize."
    if action_type == "confirm_booking":
        return "Confirming your booking now."

    if current_state in {"START", "NEED_SERVICE", "NEED_DATE", "NEED_TIME", "SHOWING_SLOTS", "HOLDING"}:
        return _build_fallback(current_state).assistant_text

    return payload_text or _build_fallback(current_state).assistant_text


def _default_chips_for_state(state: str) -> list[str] | None:
    if state == "NEED_DATE":
        return ["Today", "Tomorrow", "Pick a date below"]
    if state == "NEED_TIME":
        return ["Morning", "Afternoon", "Evening"]
    return None


def _log_chat_event(event: dict) -> None:
    path = getattr(settings, "chat_log_path", None)
    if not path:
        return
    try:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=True) + "\n")
    except Exception:
        pass


async def fetch_services(session: AsyncSession) -> list[Service]:
    result = await session.execute(select(Service).order_by(Service.id))
    return result.scalars().all()


def format_services_context(services: list[Service]) -> str:
    if not services:
        return "No services available"
    lines = []
    for svc in services:
        price = svc.price_cents / 100
        lines.append(f"- ID {svc.id}: {svc.name} (${price:.2f}, {svc.duration_minutes} min)")
    return "\n".join(lines)


async def fetch_stylists(session: AsyncSession) -> list[Stylist]:
    result = await session.execute(
        select(Stylist).where(Stylist.active.is_(True)).order_by(Stylist.id)
    )
    return result.scalars().all()


def format_stylists_context(stylists: list[Stylist]) -> str:
    if not stylists:
        return "No stylists available"
    lines = []
    for stylist in stylists:
        if stylist.work_start and stylist.work_end:
            hours = f"{stylist.work_start.strftime('%H:%M')}-{stylist.work_end.strftime('%H:%M')}"
            lines.append(f"- ID {stylist.id}: {stylist.name} ({hours})")
        else:
            lines.append(f"- ID {stylist.id}: {stylist.name}")
    return "\n".join(lines)


MONTH_ALIASES = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}

WEEKDAY_ALIASES = {
    "mon": 0,
    "monday": 0,
    "tue": 1,
    "tues": 1,
    "tuesday": 1,
    "wed": 2,
    "wednesday": 2,
    "thu": 3,
    "thur": 3,
    "thurs": 3,
    "thursday": 3,
    "fri": 4,
    "friday": 4,
    "sat": 5,
    "saturday": 5,
    "sun": 6,
    "sunday": 6,
}

BOOKING_KEYWORDS = {
    "book",
    "schedule",
    "appointment",
    "reserve",
    "hold",
    "confirm",
    "availability",
    "available",
    "slot",
    "time",
}

PRICE_KEYWORDS = {"price", "prices", "cost", "costs", "how much", "charge", "rate", "rates"}
HOURS_KEYWORDS = {"hours", "open", "close", "closing", "opening", "when are you open"}
CONFIRM_KEYWORDS = {"confirm", "confirmed", "yes", "book it", "finalize", "done"}


def _normalize_text(text: str) -> str:
    cleaned = text.lower()
    cleaned = cleaned.replace("’", "'")
    cleaned = cleaned.replace("`", "'")
    cleaned = re.sub(r"[^a-z0-9\s]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _tokenize(text: str) -> set[str]:
    return set(_normalize_text(text).split())


def _service_by_id(services: list[Service], service_id: int | None) -> Service | None:
    if not service_id:
        return None
    for svc in services:
        if svc.id == service_id:
            return svc
    return None


def _service_by_token(services: list[Service], token: str) -> Service | None:
    for svc in services:
        if token in _tokenize(svc.name):
            return svc
    return None


def _extract_service_from_context(context: dict | None, services: list[Service]) -> Service | None:
    if not context:
        return None

    for key in ("selected_service_id", "service_id"):
        raw = context.get(key)
        if raw is not None:
            try:
                return _service_by_id(services, int(raw))
            except (TypeError, ValueError):
                pass

    selected = context.get("selected_service")
    if isinstance(selected, str) and selected.strip():
        match = re.search(r"ID:\s*(\d+)", selected)
        if match:
            return _service_by_id(services, int(match.group(1)))
        selected_name = selected.split("(ID:", 1)[0].strip()
        if selected_name:
            for svc in services:
                if _normalize_text(svc.name) == _normalize_text(selected_name):
                    return svc

    return None


def _match_service_from_message(message: str, services: list[Service]) -> Service | None:
    tokens = _tokenize(message)
    if not tokens:
        return None

    matches: list[Service] = []
    for svc in services:
        svc_tokens = _tokenize(svc.name)
        if svc_tokens and svc_tokens.issubset(tokens):
            matches.append(svc)
    if len(matches) == 1:
        return matches[0]

    if "beard" in tokens:
        return _service_by_token(services, "beard")
    if "color" in tokens or "colour" in tokens:
        return _service_by_token(services, "color")

    if "haircut" in tokens or "cut" in tokens:
        male_tokens = {"men", "man", "mens"}
        female_tokens = {"women", "woman", "womens", "ladies", "lady"}
        if tokens & male_tokens:
            return _service_by_token(services, "men")
        if tokens & female_tokens:
            return _service_by_token(services, "women")

    return None


def _contains_ambiguous_haircut(message: str, services: list[Service]) -> bool:
    tokens = _tokenize(message)
    if "haircut" not in tokens and "cut" not in tokens:
        return False
    has_men = "men" in tokens or "man" in tokens or "mens" in tokens
    has_women = "women" in tokens or "woman" in tokens or "womens" in tokens
    if has_men or has_women:
        return False
    haircut_services = [svc for svc in services if "haircut" in _tokenize(svc.name)]
    return len(haircut_services) > 1


def _parse_date_from_message(message: str, tzinfo: ZoneInfo) -> date | None:
    text = message.lower().replace("’", "'")
    today = datetime.now(tzinfo).date()

    if "today" in text:
        return today
    if "tomorrow" in text:
        return today + timedelta(days=1)

    iso_match = re.search(r"\b(20\d{2})[-/](\d{1,2})[-/](\d{1,2})\b", text)
    if iso_match:
        year, month, day = map(int, iso_match.groups())
        try:
            return date(year, month, day)
        except ValueError:
            return None

    mdy_match = re.search(r"\b(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\b", text)
    if mdy_match:
        month = int(mdy_match.group(1))
        day = int(mdy_match.group(2))
        year_raw = mdy_match.group(3)
        if year_raw:
            year = int(year_raw)
            if year < 100:
                year += 2000
        else:
            year = today.year
            try:
                candidate = date(year, month, day)
            except ValueError:
                return None
            if candidate < today:
                year += 1
        try:
            return date(year, month, day)
        except ValueError:
            return None

    month_pattern = r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t|tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
    month_day = re.search(
        rf"\b{month_pattern}\s+(\d{{1,2}})(?:st|nd|rd|th)?(?:[,\s]+(\d{{4}}))?\b",
        text,
    )
    if month_day:
        month = MONTH_ALIASES[month_day.group(1)]
        day = int(month_day.group(2))
        year_raw = month_day.group(3)
        year = int(year_raw) if year_raw else today.year
        if not year_raw:
            try:
                candidate = date(year, month, day)
            except ValueError:
                return None
            if candidate < today:
                year += 1
        try:
            return date(year, month, day)
        except ValueError:
            return None

    day_month = re.search(
        rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+{month_pattern}(?:[,\s]+(\d{{4}}))?\b",
        text,
    )
    if day_month:
        day = int(day_month.group(1))
        month = MONTH_ALIASES[day_month.group(2)]
        year_raw = day_month.group(3)
        year = int(year_raw) if year_raw else today.year
        if not year_raw:
            try:
                candidate = date(year, month, day)
            except ValueError:
                return None
            if candidate < today:
                year += 1
        try:
            return date(year, month, day)
        except ValueError:
            return None

    weekday_match = re.search(
        r"\b(?:next|this)?\s*(mon(?:day)?|tue(?:s|sday)?|wed(?:nesday)?|thu(?:rs|rsday)?|fri(?:day)?|sat(?:urday)?|sun(?:day)?)\b",
        text,
    )
    if weekday_match:
        weekday_key = weekday_match.group(0).strip().split()[-1]
        target = WEEKDAY_ALIASES.get(weekday_key)
        if target is not None:
            days_ahead = (target - today.weekday() + 7) % 7
            if days_ahead == 0:
                days_ahead = 7
            return today + timedelta(days=days_ahead)

    return None


def _parse_time_from_message(message: str) -> str | None:
    text = message.lower().replace("’", "'")

    if "noon" in text:
        return "12:00"
    if "midnight" in text:
        return "00:00"

    clock_match = re.search(r"\b(\d{1,2}):(\d{2})\s*(am|pm)?\b", text)
    if clock_match:
        hour = int(clock_match.group(1))
        minute = int(clock_match.group(2))
        ampm = clock_match.group(3)
        if ampm:
            if ampm == "pm" and hour != 12:
                hour += 12
            if ampm == "am" and hour == 12:
                hour = 0
        if hour > 23 or minute > 59:
            return None
        return f"{hour:02d}:{minute:02d}"

    hour_match = re.search(r"\b(\d{1,2})\s*(am|pm)\b", text)
    if hour_match:
        hour = int(hour_match.group(1))
        ampm = hour_match.group(2)
        if ampm == "pm" and hour != 12:
            hour += 12
        if ampm == "am" and hour == 12:
            hour = 0
        if hour > 23:
            return None
        return f"{hour:02d}:00"

    return None


def _is_booking_intent(message: str, services: list[Service]) -> bool:
    normalized = _normalize_text(message)
    if not normalized:
        return False

    if any(keyword in normalized for keyword in BOOKING_KEYWORDS):
        return True

    service_tokens: set[str] = set()
    for svc in services:
        service_tokens.update(_tokenize(svc.name))
    if service_tokens & _tokenize(message):
        return True

    if _parse_date_from_message(message, ZoneInfo(settings.chat_timezone or "America/Phoenix")):
        return True
    if _parse_time_from_message(message):
        return True

    return False


def _build_price_text(services: list[Service]) -> str:
    if not services:
        return "I do not have service pricing yet."
    parts = []
    for svc in services:
        price = svc.price_cents / 100
        parts.append(f"{svc.name} (${price:.2f})")
    return "Here are our services and prices: " + ", ".join(parts) + "."


def _build_hours_text() -> str:
    working_days = _working_days_text(settings.working_days_list)
    hours = f"{settings.working_hours_start}-{settings.working_hours_end}"
    return f"We are open {working_days}, {hours}."


def _deterministic_payload_from_message(
    message: str,
    current_state: str,
    context: dict | None,
    services: list[Service],
    tzinfo: ZoneInfo,
) -> AIResponsePayload | None:
    normalized = _normalize_text(message)
    if not normalized:
        return None

    if any(keyword in normalized for keyword in PRICE_KEYWORDS):
        return AIResponsePayload(
            assistant_text=f"{_build_price_text(services)} Which service would you like to book?",
            actions=[AIAction(type="SHOW_SERVICES", params={})],
            next_state="NEED_SERVICE",
            chips=None,
        )

    if any(keyword in normalized for keyword in HOURS_KEYWORDS):
        return AIResponsePayload(
            assistant_text=f"{_build_hours_text()} What service can I help you with?",
            actions=[AIAction(type="SHOW_SERVICES", params={})],
            next_state="NEED_SERVICE",
            chips=None,
        )

    if context and context.get("booking_id") and any(keyword in normalized for keyword in CONFIRM_KEYWORDS):
        return AIResponsePayload(
            assistant_text="Confirming your booking now.",
            actions=[AIAction(type="CONFIRM_BOOKING", params={"booking_id": context["booking_id"]})],
            next_state="CONFIRMED",
            chips=None,
        )

    if "service" in normalized or "services" in normalized:
        return AIResponsePayload(
            assistant_text="Here are the services we offer.",
            actions=[AIAction(type="SHOW_SERVICES", params={})],
            next_state="NEED_SERVICE",
            chips=None,
        )

    if _contains_ambiguous_haircut(message, services):
        return AIResponsePayload(
            assistant_text="Do you want a Men's Haircut or a Women's Haircut?",
            actions=[AIAction(type="SHOW_SERVICES", params={})],
            next_state="NEED_SERVICE",
            chips=None,
        )

    matched_service = _match_service_from_message(message, services)
    selected_service = matched_service or _extract_service_from_context(context, services)
    parsed_date = _parse_date_from_message(message, tzinfo)
    parsed_time = _parse_time_from_message(message)

    if matched_service and not parsed_date:
        return AIResponsePayload(
            assistant_text="",
            actions=[
                AIAction(
                    type="SELECT_SERVICE",
                    params={"service_id": matched_service.id, "service_name": matched_service.name},
                )
            ],
            next_state="NEED_DATE",
            chips=None,
        )

    if parsed_date and not selected_service:
        return AIResponsePayload(
            assistant_text="What service would you like to book for that date?",
            actions=[AIAction(type="SHOW_SERVICES", params={})],
            next_state="NEED_SERVICE",
            chips=None,
        )

    if selected_service and parsed_date:
        if parsed_date < datetime.now(tzinfo).date():
            return AIResponsePayload(
                assistant_text="That date has already passed. What day works instead?",
                actions=[],
                next_state="NEED_DATE",
                chips=None,
            )
        if parsed_date.weekday() not in settings.working_days_list:
            return AIResponsePayload(
                assistant_text=f"We are open {_working_days_text(settings.working_days_list)}. What date works instead?",
                actions=[],
                next_state="NEED_DATE",
                chips=None,
            )

        date_str = parsed_date.strftime("%Y-%m-%d")
        pref_text = ""
        if parsed_time:
            pref_text = f" Looking for around {parsed_time}."

        return AIResponsePayload(
            assistant_text=f"Checking availability for {date_str}.{pref_text}",
            actions=[
                AIAction(
                    type="FETCH_AVAILABILITY",
                    params={"service_id": selected_service.id, "date": date_str},
                )
            ],
            next_state="SHOWING_SLOTS",
            chips=None,
        )

    if matched_service:
        return AIResponsePayload(
            assistant_text="",
            actions=[
                AIAction(
                    type="SELECT_SERVICE",
                    params={"service_id": matched_service.id, "service_name": matched_service.name},
                )
            ],
            next_state="NEED_DATE",
            chips=None,
        )

    return None


def _finalize_payload(
    payload: AIResponsePayload,
    current_state: str,
    context: dict | None,
    tzinfo: ZoneInfo,
    source: str,
    messages: list[ChatMessage],
    prefer_payload_text: bool,
) -> ChatResponse:
    if payload.actions and len(payload.actions) > 1:
        payload.actions = payload.actions[:1]

    if payload.actions and not _action_has_required_params(payload.actions[0]):
        payload.actions = []

    if payload.actions and payload.actions[0].type.strip().upper() == "SHOW_SLOTS":
        if not (context and context.get("available_slots")):
            payload.actions = []

    primary_action = payload.actions[0] if payload.actions else None
    legacy_action = _normalize_action(primary_action)
    next_state = _derive_next_state(
        current_state,
        legacy_action["type"] if legacy_action else None,
        payload.next_state,
    )
    raw_text = (payload.assistant_text or "").strip()
    if prefer_payload_text and raw_text:
        assistant_text = raw_text
    elif not prefer_payload_text and not payload.actions and current_state == "START" and raw_text:
        assistant_text = raw_text
    else:
        assistant_text = _render_assistant_text(
            payload.assistant_text,
            current_state,
            legacy_action,
            context,
        )
    chips = payload.chips or _default_chips_for_state(next_state)

    _log_chat_event(
        {
            "timestamp": datetime.now(tzinfo).isoformat(),
            "source": source,
            "state": current_state,
            "next_state": next_state,
            "messages": [m.model_dump() for m in messages],
            "assistant_text": assistant_text,
            "actions": [a.model_dump() for a in payload.actions],
            "legacy_action": legacy_action,
            "context": context or {},
        }
    )

    return ChatResponse(
        reply=assistant_text,
        action=legacy_action,
        assistant_text=assistant_text,
        actions=[_normalize_action(a) for a in payload.actions if _normalize_action(a)],
        next_state=next_state,
        chips=chips,
    )


async def chat_with_ai(
    messages: list[ChatMessage],
    session: AsyncSession,
    context: dict | None = None
) -> ChatResponse:
    """Process chat messages and return AI response with optional actions."""
    
    tz_name = settings.chat_timezone or "America/Phoenix"
    tzinfo = ZoneInfo(tz_name)
    current_state = _infer_state(context)

    services = await fetch_services(session)
    stylists = await fetch_stylists(session)
    services_text = format_services_context(services)
    stylists_text = format_stylists_context(stylists)

    latest_user = ""
    for msg in reversed(messages):
        if msg.role == "user":
            latest_user = msg.content
            break

    deterministic_payload = _deterministic_payload_from_message(
        latest_user,
        current_state,
        context,
        services,
        tzinfo,
    )
    if deterministic_payload:
        return _finalize_payload(
            deterministic_payload,
            current_state,
            context,
            tzinfo,
            "deterministic",
            messages,
            True,
        )

    booking_intent = _is_booking_intent(latest_user, services)
    if booking_intent or current_state != "START":
        fallback_payload = _build_fallback(current_state)
        return _finalize_payload(
            fallback_payload,
            current_state,
            context,
            tzinfo,
            "fallback",
            messages,
            True,
        )

    if not settings.openai_api_key:
        return ChatResponse(
            reply="I'm sorry, but the AI assistant is not configured. Please contact support.",
            action=None,
            assistant_text="I'm sorry, but the AI assistant is not configured. Please contact support.",
            actions=[],
            next_state=current_state,
            chips=None,
        )

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    
    today = datetime.now(tzinfo).strftime("%Y-%m-%d (%A)")
    working_days = _working_days_text(settings.working_days_list)
    working_hours = f"{settings.working_hours_start}-{settings.working_hours_end}"
    
    system_prompt = SYSTEM_PROMPT.format(
        services=services_text,
        stylists=stylists_text,
        today=today,
        timezone=tz_name,
        working_days=working_days,
        working_hours=working_hours,
    )
    
    # Add context information if available
    context_parts = [f"Booking state: {current_state}"]
    if context:
        if context.get("selected_service"):
            context_parts.append(f"Selected service: {context['selected_service']}")
        if context.get("selected_date"):
            context_parts.append(f"Selected date: {context['selected_date']}")
        if context.get("customer_name"):
            context_parts.append(f"Customer name: {context['customer_name']}")
        if context.get("held_slot"):
            context_parts.append(f"Held slot: {context['held_slot']}")
        if context.get("booking_id"):
            context_parts.append(f"Booking ID: {context['booking_id']}")
        if context.get("available_slots"):
            slots_summary = context["available_slots"][:5]
            context_parts.append(f"Available slots shown: {slots_summary}")
        if context.get("tz_offset_minutes") is not None:
            context_parts.append(f"Client tz offset minutes: {context['tz_offset_minutes']}")

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
            temperature=0.2,
            response_format={"type": "json_object"},
        )
        
        ai_response = response.choices[0].message.content or ""
        payload = None
        try:
            payload = AIResponsePayload.model_validate(json.loads(ai_response))
        except Exception:
            clean_response, action = _extract_action_json(ai_response)
            if action:
                payload = AIResponsePayload(
                    assistant_text=clean_response or "How can I help?",
                    actions=[AIAction(type=action.get("type", ""), params=action.get("params", {}))],
                    next_state=current_state,
                    chips=None,
                )

        if not payload:
            payload = _build_fallback(current_state)
        return _finalize_payload(payload, current_state, context, tzinfo, "llm", messages, False)
        
    except Exception as e:
        import traceback
        print(f"OpenAI API Error: {e}")
        traceback.print_exc()
        return ChatResponse(
            reply="I'm having trouble processing your request. Please try again.",
            action=None,
            assistant_text="I'm having trouble processing your request. Please try again.",
            actions=[],
            next_state=current_state,
            chips=None,
        )
