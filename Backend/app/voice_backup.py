import logging
import re
import uuid
import difflib
from datetime import datetime, timedelta, timezone, date
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Request, Response
from twilio.request_validator import RequestValidator
from twilio.twiml.voice_response import Gather, VoiceResponse

from .chat import ChatMessage, ChatRequest, ChatResponse, VOICE_STAGE_PROMPTS
from .core.config import get_settings
from .core.db import AsyncSessionLocal
from .customer_memory import normalize_phone
from .models import Service
from sqlalchemy import select


logger = logging.getLogger(__name__)
router = APIRouter()
settings = get_settings()

CALL_SESSIONS: dict[str, dict] = {}
SESSION_TTL_MINUTES = 120
MAX_NO_INPUT_REPROMPTS = 4


def get_local_tz_offset_minutes() -> int:
    tz = ZoneInfo(settings.chat_timezone)
    local_now = datetime.now(tz)
    offset = local_now.utcoffset()
    if not offset:
        return 0
    return int(offset.total_seconds() / 60)


def prune_sessions(now: datetime | None = None) -> None:
    if not CALL_SESSIONS:
        return
    if now is None:
        now = datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=SESSION_TTL_MINUTES)
    stale = [sid for sid, state in CALL_SESSIONS.items() if state.get("updated_at", now) < cutoff]
    for sid in stale:
        CALL_SESSIONS.pop(sid, None)


def is_affirmative_intent(text: str) -> bool:
    return bool(re.search(r"\b(yes|yeah|yep|correct|that's right|that is right|sure|affirmative)\b", text.lower()))


def is_negative_intent(text: str) -> bool:
    return bool(re.search(r"\b(no|nope|nah|not right|incorrect|negative)\b", text.lower()))


def is_goodbye_intent(text: str) -> bool:
    return bool(re.search(r"\b(bye|goodbye|hang up|cancel|stop|no thanks|that's all)\b", text.lower()))


def format_phone_for_voice(phone: str | None) -> str:
    if not phone:
        return ""
    digits = re.sub(r"\D", "", phone)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) == 10:
        return f"{digits[:3]}-{digits[3:6]}-{digits[6:]}"
    return phone


def verify_twilio_signature(request: Request, form_data: dict) -> bool:
    if not settings.twilio_verify_signature:
        return True
    if not settings.twilio_auth_token:
        logger.warning("TWILIO_VERIFY_SIGNATURE enabled but TWILIO_AUTH_TOKEN is missing.")
        return False
    validator = RequestValidator(settings.twilio_auth_token)
    signature = request.headers.get("X-Twilio-Signature", "")
    return validator.validate(str(request.url), form_data, signature)


def build_gather(prompt: str) -> VoiceResponse:
    response = VoiceResponse()
    action_url = f"{settings.public_api_base.rstrip('/')}/twilio/gather"
    gather = Gather(
        input="speech",
        action=action_url,
        method="POST",
        timeout=10,
        speech_timeout="auto",
    )
    if prompt:
        gather.say(prompt)
    response.append(gather)
    return response


def build_hangup(prompt: str) -> VoiceResponse:
    response = VoiceResponse()
    if prompt:
        response.say(prompt)
    response.hangup()
    return response


def extract_email_from_speech(text: str) -> str | None:
    lowered = text.lower()
    normalized = lowered
    replacements = {
        " at sign ": "@",
        " at ": "@",
        " dot com": ".com",
        " dot net": ".net",
        " dot org": ".org",
        " dot edu": ".edu",
        " dot ": ".",
        " period ": ".",
        " point ": ".",
        " underscore ": "_",
        " dash ": "-",
        " hyphen ": "-",
    }
    for needle, value in replacements.items():
        normalized = normalized.replace(needle, value)
    normalized = re.sub(r"[^\w@.+-]", "", normalized.replace(" ", ""))

    match = re.search(r"[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}", normalized)
    if match:
        return match.group(0)
    return None


def extract_phone_from_speech(text: str) -> str | None:
    if not text:
        return None
    digits = "".join(re.findall(r"\d+", text))
    if not digits:
        word_map = {
            "zero": "0",
            "one": "1",
            "two": "2",
            "three": "3",
            "four": "4",
            "five": "5",
            "six": "6",
            "seven": "7",
            "eight": "8",
            "nine": "9",
        }
        tokens = re.findall(r"[a-zA-Z]+", text.lower())
        for token in tokens:
            if token in word_map:
                digits += word_map[token]
    normalized = normalize_phone(digits or text)
    return normalized or None


def extract_name_from_speech(text: str, prefer_simple: bool = False) -> str | None:
    """Extract name from speech. Prefers pattern matching, falls back to simple extraction."""
    lowered = text.lower()
    
    # Try common name introductions first
    match = re.search(r"\b(my name is|this is|i am|i'm|it's)\s+([a-zA-Z\s-]+?)(?:\s+(?:and|my|the|number|phone|email)|\s*$)", lowered)
    if match:
        name = match.group(2).strip()
        # Filter out numbers spelled as words that might be in the name
        words = [w for w in name.split() if not w in {"zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"}]
        if words:
            return " ".join(word.title() for word in words)
        return name.title()

    if prefer_simple:
        # For simple extraction, be more conservative
        # Try to extract capitalized words or the first few words
        # But skip words that are likely numbers or numbers
        cleaned = re.sub(r"[^a-zA-Z\s-]", "", text).strip()
        words = [word for word in cleaned.split() if len(word) > 1 and word not in {"and", "the", "my", "your", "phone", "number", "email", "digit", "is"}]
        if 1 <= len(words) <= 2:
            return " ".join(word.title() for word in words)
    return None


def extract_time_minutes_from_speech(text: str) -> int | None:
    lowered = re.sub(r"[,\-]", " ", text.lower())
    if "noon" in lowered or "midday" in lowered:
        return 12 * 60
    if "midnight" in lowered:
        return 0
    if "morning" in lowered:
        return 10 * 60
    if "afternoon" in lowered:
        return 15 * 60
    if "evening" in lowered or "tonight" in lowered:
        return 18 * 60

    match = re.search(r"\b(\d{1,2})(?:[:.](\d{2}))?\s*(a\.m\.|am|p\.m\.|pm)\b", lowered)
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2) or 0)
        period = match.group(3)
        if "p" in period and hour != 12:
            hour += 12
        if "a" in period and hour == 12:
            hour = 0
        return hour * 60 + minute

    match = re.search(r"\b([01]?\d|2[0-3])[:.](\d{2})\b", lowered)
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2))
        return hour * 60 + minute

    match = re.search(r"\b(\d{1,2})\s*(o'clock|oclock)\b", lowered)
    if match:
        hour = int(match.group(1)) % 12
        return hour * 60

    return None


def parse_option_index(text: str) -> int | None:
    lowered = text.lower()
    if re.search(r"\b(first|one|option one|option 1|number one|1)\b", lowered):
        return 0
    if re.search(r"\b(second|two|option two|option 2|number two|2)\b", lowered):
        return 1
    if re.search(r"\b(third|three|option three|option 3|number three|3)\b", lowered):
        return 2
    return None


def parse_slot_start(slot: dict) -> datetime | None:
    raw = slot.get("start_time")
    if not raw:
        return None
    if isinstance(raw, datetime):
        dt = raw
    elif isinstance(raw, str):
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def slot_local_minutes(slot: dict) -> int | None:
    dt = parse_slot_start(slot)
    if not dt:
        return None
    local = dt.astimezone(ZoneInfo(settings.chat_timezone))
    return local.hour * 60 + local.minute


def slot_local_time_strings(slot: dict) -> tuple[str | None, str | None]:
    dt = parse_slot_start(slot)
    if not dt:
        return None, None
    local = dt.astimezone(ZoneInfo(settings.chat_timezone))
    return local.strftime("%H:%M"), local.strftime("%I:%M %p").lstrip("0")


def match_slot_from_speech(text: str, slots: list[dict]) -> dict | None:
    preferred_minutes = extract_time_minutes_from_speech(text)
    if preferred_minutes is None:
        return None

    stylist_match = None
    lowered = text.lower()
    for slot in slots:
        name = str(slot.get("stylist_name") or "").lower()
        if name and name in lowered:
            stylist_match = name
            break

    candidates = []
    for slot in slots:
        slot_minutes = slot_local_minutes(slot)
        if slot_minutes is None:
            continue
        stylist_name = str(slot.get("stylist_name") or "").lower()
        if stylist_match and stylist_match != stylist_name:
            continue
        diff = abs(slot_minutes - preferred_minutes)
        candidates.append((diff, slot_minutes, slot))

    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], item[1]))
    diff, _, best = candidates[0]
    if diff > 90:
        return None
    return best


def is_confirm_intent(text: str) -> bool:
    return bool(
        re.search(
            r"\b(confirm|yes|yeah|yep|correct|that's right|that is right|please do|go ahead|book it|sounds good|sure)\b",
            text.lower(),
        )
    )


def update_context_from_response(context: dict, response: ChatResponse) -> dict:
    updated = dict(context or {})
    data = response.data or {}

    if "selected_service_name" in data:
        updated["selected_service"] = data["selected_service_name"]
    if "selected_service_id" in data:
        updated["selected_service_id"] = data["selected_service_id"]
    if "selected_date" in data:
        updated["selected_date"] = data["selected_date"]
    if "slots" in data:
        updated["available_slots"] = data["slots"]
    if "hold" in data:
        updated["held_slot"] = data["hold"]
    if "selected_slot" in data:
        updated["selected_slot"] = data["selected_slot"]
    if "confirmed" in data:
        updated["confirmed"] = data["confirmed"]

    action_type = (response.action or {}).get("type")
    stage_map = {
        "show_services": "SELECT_SERVICE",
        "select_service": "SELECT_DATE",
        "fetch_availability": "SELECT_SLOT",
        "hold_slot": "HOLDING",
        "confirm_booking": "DONE",
    }
    if action_type in stage_map:
        # Prevent moving backwards once service/date are set
        desired_stage = stage_map[action_type]
        current_stage = updated.get("stage") or "WELCOME"
        stage_order = ["WELCOME", "SELECT_SERVICE", "SELECT_DATE", "SELECT_SLOT", "HOLDING", "CONFIRMING", "DONE"]
        current_idx = stage_order.index(current_stage) if current_stage in stage_order else 0
        desired_idx = stage_order.index(desired_stage) if desired_stage in stage_order else current_idx
        updated["stage"] = stage_order[max(current_idx, desired_idx)]

    return updated


def select_voice_slot_options(slots: list[dict], preferred_minutes: int | None = None) -> list[dict]:
    if not slots:
        return []
    if preferred_minutes is None:
        return slots[:3]
    ranked = sorted(
        slots,
        key=lambda slot: (
            abs((slot_local_minutes(slot) or 0) - preferred_minutes),
            slot_local_minutes(slot) or 0,
        ),
    )
    return ranked[:3]


def summarize_slots_for_voice(slots: list[dict], preferred_minutes: int | None = None) -> str | None:
    """Summarize slots for voice in natural language."""
    if not slots:
        return None
    formatted = []
    for slot in select_voice_slot_options(slots, preferred_minutes):
        stylist = slot.get("stylist_name") or "a stylist"
        local_str, _ = slot_local_time_strings(slot)
        if not local_str:
            continue
        time_label = datetime.strptime(local_str, "%H:%M").strftime("%I:%M %p").lstrip("0")
        formatted.append(f"{time_label} with {stylist}")
        if len(formatted) >= 3:
            break
    if not formatted:
        return None
    if len(formatted) == 1:
        return f"I have {formatted[0]}. Would you like that?"
    if len(formatted) == 2:
        return f"I have {formatted[0]} or {formatted[1]}. Which works better for you?"
    return f"I have {formatted[0]}, {formatted[1]}, or {formatted[2]}. Which works for you?"


def extract_stylist_from_response(response_text: str, available_stylists: list[str]) -> str | None:
    """Extract stylist preference from AI response if user mentioned one."""
    response_lower = response_text.lower()
    for stylist in available_stylists:
        if stylist.lower() in response_lower:
            return stylist
    return None


def sanitize_voice_reply(text: str) -> str:
    if not text:
        return text
    cleaned = re.sub(
        r"\b(tap|click|button|buttons|chips|select from the list|list below|see below|i have listed|here are the options|options below)\b",
        "",
        text,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    return cleaned


def ensure_voice_prompt(text: str, context: dict) -> str:
    """Ensure we end with a clear voice question so callers know to respond."""
    if not text:
        return "What would you like to do next?"
    if "?" in text:
        return text

    if not (context.get("selected_service_id") or context.get("selected_service")):
        return "Which service would you like to book?"
    if not context.get("selected_date"):
        return "What day works best for you?"
    if context.get("available_slots") and not context.get("held_slot"):
        return "What time works best for you?"
    if context.get("held_slot") and not context.get("confirmed"):
        return "Should I confirm the booking?"
    return f"{text} What would you like to do next?"


def normalize_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def extract_date_from_speech(text: str, tz: ZoneInfo) -> str | None:
    """Parse natural date phrases to YYYY-MM-DD in given timezone."""
    if not text:
        return None
    now = datetime.now(tz).date()
    lowered = text.lower()

    # today / tomorrow
    if re.search(r"\btoday\b", lowered):
        return now.isoformat()
    if re.search(r"\btomorrow\b", lowered):
        return (now + timedelta(days=1)).isoformat()

    # weekdays
    weekday_map = {
        "monday": 0,
        "tuesday": 1,
        "wednesday": 2,
        "thursday": 3,
        "friday": 4,
        "saturday": 5,
        "sunday": 6,
    }
    for label, idx in weekday_map.items():
        if label in lowered:
            current_idx = now.weekday()
            delta = (idx - current_idx) % 7
            if "next" in lowered and delta == 0:
                delta = 7
            if delta == 0:
                delta = 7  # default to next occurrence if same day mentioned
            target = now + timedelta(days=delta)
            return target.isoformat()

    # month/day patterns
    month_map = {
        "january": 1,
        "february": 2,
        "march": 3,
        "april": 4,
        "may": 5,
        "june": 6,
        "july": 7,
        "august": 8,
        "september": 9,
        "october": 10,
        "november": 11,
        "december": 12,
        "jan": 1,
        "feb": 2,
        "mar": 3,
        "apr": 4,
        "jun": 6,
        "jul": 7,
        "aug": 8,
        "sep": 9,
        "sept": 9,
        "oct": 10,
        "nov": 11,
        "dec": 12,
    }

    # "15th of January" or "15 January"
    match = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?([a-zA-Z]+)\b", lowered)
    if match:
        day = int(match.group(1))
        month_name = match.group(2).lower()
        month = month_map.get(month_name)
        if month and 1 <= day <= 31:
            year = now.year
            candidate = date(year, month, day)
            if candidate < now:
                if month < now.month or (month == now.month and day < now.day):
                    year += 1
                    candidate = date(year, month, day)
            return candidate.isoformat()

    # "January 15"
    match = re.search(r"\b([a-zA-Z]+)\s+(\d{1,2})(?:st|nd|rd|th)?\b", lowered)
    if match:
        month_name = match.group(1).lower()
        day = int(match.group(2))
        month = month_map.get(month_name)
        if month and 1 <= day <= 31:
            year = now.year
            candidate = date(year, month, day)
            if candidate < now:
                if month < now.month or (month == now.month and day < now.day):
                    year += 1
                    candidate = date(year, month, day)
            return candidate.isoformat()

    return None


async def match_service_from_speech(session: AsyncSessionLocal, text: str) -> Service | None:
    normalized = normalize_text(text)
    if not normalized:
        return None
    result = await session.execute(select(Service).order_by(Service.id))
    services = result.scalars().all()
    best_service = None
    best_score = 0.0
    for svc in services:
        svc_name = normalize_text(svc.name)
        if not svc_name:
            continue
        if svc_name in normalized:
            return svc
        score = difflib.SequenceMatcher(None, normalized, svc_name).ratio()
        if score > best_score:
            best_score = score
            best_service = svc
    if best_score >= 0.72:
        return best_service
    return None


async def hold_selected_slot(state: dict, selected_slot: dict) -> dict | None:
    context = state.get("context", {}) or {}
    service_id = context.get("selected_service_id")
    date_str = context.get("selected_date")
    tz_offset = state.get("context", {}).get("tz_offset_minutes", 0)
    customer_name = context.get("customer_name")
    customer_phone = context.get("customer_phone")
    stylist_id = selected_slot.get("stylist_id")
    local_time_24, _ = slot_local_time_strings(selected_slot)
    slot_start = parse_slot_start(selected_slot)

    async with AsyncSessionLocal() as session:
        if not service_id:
            service_name = context.get("selected_service")
            if service_name:
                result = await session.execute(
                    select(Service).where(Service.name.ilike(f"%{service_name}%"))
                )
                service = result.scalar_one_or_none()
                if service:
                    service_id = service.id
                    context["selected_service_id"] = service_id
        if not date_str and slot_start:
            local_date = slot_start.astimezone(ZoneInfo(settings.chat_timezone)).date()
            date_str = local_date.strftime("%Y-%m-%d")
            context["selected_date"] = date_str

        missing = []
        if not service_id:
            missing.append("service_id")
        if not stylist_id:
            missing.append("stylist_id")
        if not date_str:
            missing.append("date")
        if not local_time_24:
            missing.append("start_time")
        if not customer_name:
            missing.append("customer_name")
        if not customer_phone:
            missing.append("customer_phone")
        if missing:
            logger.info(
                "voice_hold_missing_fields",
                extra={"call_sid": state.get("call_sid"), "missing": missing},
            )
            return None

        from .main import HoldRequest, create_hold

        payload = HoldRequest(
            service_id=int(service_id),
            date=str(date_str),
            start_time=local_time_24,
            stylist_id=int(stylist_id),
            customer_name=str(customer_name),
            customer_phone=str(customer_phone),
            customer_email=None,
            tz_offset_minutes=int(tz_offset),
        )
        hold_result = await create_hold(payload, session)
        return hold_result.model_dump()


@router.post("/voice")
async def twilio_voice(request: Request) -> Response:
    form = dict(await request.form())
    if not verify_twilio_signature(request, form):
        return Response("Invalid signature", status_code=403)

    call_sid = str(form.get("CallSid") or "unknown")
    prune_sessions()
    if call_sid not in CALL_SESSIONS:
        CALL_SESSIONS[call_sid] = {
            "messages": [],
            "queued_user_messages": [],
            "context": {"stage": "WELCOME", "tz_offset_minutes": get_local_tz_offset_minutes(), "channel": "voice"},
            "last_assistant": "",
            "no_input_count": 0,
            "updated_at": datetime.now(timezone.utc),
        }

    twiml = build_gather("Hi, thanks for calling Bishops Tempe. First, can I get your name and phone number?")
    return Response(str(twiml), media_type="application/xml")


@router.post("/gather")
async def twilio_gather(request: Request) -> Response:
    form = dict(await request.form())
    if not verify_twilio_signature(request, form):
        return Response("Invalid signature", status_code=403)

    call_sid = str(form.get("CallSid") or "unknown")
    speech_result = str(form.get("SpeechResult") or "").strip()

    prune_sessions()
    state = CALL_SESSIONS.setdefault(
        call_sid,
        {
            "messages": [],
            "queued_user_messages": [],
            "context": {"stage": "WELCOME", "tz_offset_minutes": get_local_tz_offset_minutes(), "channel": "voice"},
            "last_assistant": "",
            "no_input_count": 0,
            "updated_at": datetime.now(timezone.utc),
        },
    )

    try:
        if not speech_result:
            state["no_input_count"] = int(state.get("no_input_count") or 0) + 1
            if state["no_input_count"] >= MAX_NO_INPUT_REPROMPTS:
                logger.info("voice_no_input_hangup", extra={"call_sid": call_sid})
                twiml = build_hangup("Sorry, I still didn't catch that. Please call again anytime.")
                return Response(str(twiml), media_type="application/xml")
            logger.info("voice_no_input_reprompt", extra={"call_sid": call_sid, "count": state['no_input_count']})
            twiml = build_gather("Sorry, I didn't catch that. Please say it again.")
            return Response(str(twiml), media_type="application/xml")

        state["no_input_count"] = 0
        if is_goodbye_intent(speech_result):
            logger.info("voice_goodbye", extra={"call_sid": call_sid})
            twiml = build_hangup("Thanks for calling. Goodbye!")
            return Response(str(twiml), media_type="application/xml")

        logger.info("voice_input", extra={"call_sid": call_sid, "speech": speech_result})

        # Extract identity and name from speech - accumulate across turns
        phone = extract_phone_from_speech(speech_result)
        if phone:
            state["context"]["customer_phone"] = phone
        name = extract_name_from_speech(speech_result, prefer_simple=True)
        if name:
            state["context"]["customer_name"] = name
        logger.info(
            "voice_identity_extract",
            extra={
                "call_sid": call_sid,
                "name": state["context"].get("customer_name"),
                "phone": state["context"].get("customer_phone"),
                "phone_confirmed": state["context"].get("phone_confirmed"),
            },
        )

        # Voice identity must be name + phone. Confirm phone before proceeding.
        if phone and not state["context"].get("phone_confirmed"):
            state["context"]["pending_phone_confirmation"] = format_phone_for_voice(phone)

        pending_confirmation = state["context"].get("pending_phone_confirmation")
        if pending_confirmation:
            if is_affirmative_intent(speech_result):
                state["context"]["phone_confirmed"] = True
                state["context"].pop("pending_phone_confirmation", None)
                logger.info("voice_phone_confirmed", extra={"call_sid": call_sid})
            elif is_negative_intent(speech_result):
                state["context"].pop("customer_phone", None)
                state["context"].pop("pending_phone_confirmation", None)
                logger.info("voice_phone_rejected", extra={"call_sid": call_sid})
                twiml = build_gather("Okay, please say your phone number again.")
                return Response(str(twiml), media_type="application/xml")
            elif phone and format_phone_for_voice(phone) != pending_confirmation:
                state["context"]["pending_phone_confirmation"] = format_phone_for_voice(phone)
                logger.info("voice_phone_updated", extra={"call_sid": call_sid})
                twiml = build_gather(f"I heard {state['context']['pending_phone_confirmation']}. Is that right?")
                return Response(str(twiml), media_type="application/xml")
            else:
                logger.info("voice_phone_confirm_prompt", extra={"call_sid": call_sid})
                twiml = build_gather(f"I heard {pending_confirmation}. Is that right?")
                return Response(str(twiml), media_type="application/xml")

        if not state["context"].get("customer_phone"):
            state.setdefault("queued_user_messages", []).append(speech_result)
            logger.info("voice_prompt_phone", extra={"call_sid": call_sid})
            twiml = build_gather("What phone number should we use for the booking?")
            return Response(str(twiml), media_type="application/xml")

        if not state["context"].get("phone_confirmed"):
            logger.info("voice_prompt_phone_confirm", extra={"call_sid": call_sid})
            twiml = build_gather(f"I heard {format_phone_for_voice(state['context']['customer_phone'])}. Is that right?")
            return Response(str(twiml), media_type="application/xml")

        if not state["context"].get("customer_name"):
            state.setdefault("queued_user_messages", []).append(speech_result)
            logger.info("voice_prompt_name", extra={"call_sid": call_sid})
            twiml = build_gather("Great, and what's your name?")
            return Response(str(twiml), media_type="application/xml")

        # Extract preferred time if mentioned
        preferred_minutes = extract_time_minutes_from_speech(speech_result)
        if preferred_minutes is not None:
            state["context"]["preferred_time_minutes"] = preferred_minutes

        # Extract date if mentioned
        if not state["context"].get("selected_date"):
            parsed_date = extract_date_from_speech(speech_result, ZoneInfo(settings.chat_timezone))
            if parsed_date:
                state["context"]["selected_date"] = parsed_date
                state["context"]["stage"] = "SELECT_SLOT"
                logger.info("voice_date_set", extra={"call_sid": call_sid, "date": parsed_date})
                speech_result = f"Date selected: {parsed_date}"

        # Heuristic: if service is mentioned in speech but not set, lock it in to avoid loops.
        if not state["context"].get("selected_service_id"):
            async with AsyncSessionLocal() as session:
                matched_service = await match_service_from_speech(session, speech_result)
            if matched_service:
                state["context"]["selected_service_id"] = matched_service.id
                state["context"]["selected_service"] = matched_service.name
                state["context"]["stage"] = "SELECT_DATE"
                logger.info(
                    "voice_service_matched",
                    extra={"call_sid": call_sid, "service": matched_service.name},
                )
                if not state["context"].get("selected_date"):
                    twiml = build_gather("Great choice. What day works for you?")
                    return Response(str(twiml), media_type="application/xml")
            else:
                # Service still missing, ask directly and skip LLM
                twiml = build_gather("Which service would you like to book?")
                return Response(str(twiml), media_type="application/xml")

        if state["context"].get("held_slot") and is_confirm_intent(speech_result):
            booking_id = (state["context"].get("held_slot") or {}).get("booking_id")
            if booking_id:
                try:
                    async with AsyncSessionLocal() as session:
                        from .main import ConfirmRequest, confirm_booking

                        confirm_result = await confirm_booking(
                            ConfirmRequest(booking_id=uuid.UUID(str(booking_id))),
                            session,
                        )
                    reply_text = "Your booking is confirmed. You're all set."
                    state["context"]["confirmed"] = confirm_result.model_dump()
                    state["messages"].append(ChatMessage(role="assistant", content=reply_text))
                    state["last_assistant"] = reply_text
                    state["updated_at"] = datetime.now(timezone.utc)
                    twiml = build_gather(ensure_voice_prompt(reply_text, state["context"]))
                    return Response(str(twiml), media_type="application/xml")
                except Exception as exc:
                    logger.exception("voice_confirm_failed", extra={"call_sid": call_sid, "error": str(exc)})
                    twiml = build_gather("I couldn't confirm that. Should I try again?")
                    return Response(str(twiml), media_type="application/xml")
            speech_result = "confirm booking"

        available_slots = state["context"].get("available_slots") or []
        last_voice_slots = state["context"].get("last_voice_slots") or []

        if available_slots and not state["context"].get("held_slot"):
            selected_slot = None
            option_index = parse_option_index(speech_result)
            if option_index is not None and option_index < len(last_voice_slots):
                selected_slot = last_voice_slots[option_index]
            else:
                selected_slot = match_slot_from_speech(speech_result, available_slots)

            if selected_slot:
                time_24, _ = slot_local_time_strings(selected_slot)
                stylist_name = selected_slot.get("stylist_name") or "a stylist"
                if time_24:
                    logger.info("voice_slot_selected", extra={"call_sid": call_sid, "time": time_24, "stylist": stylist_name})
                    hold_payload = await hold_selected_slot(state, selected_slot)
                    if hold_payload:
                        state["context"]["held_slot"] = hold_payload
                        state["context"]["selected_slot"] = selected_slot
                        logger.info("voice_hold_success", extra={"call_sid": call_sid, "booking_id": hold_payload.get("booking_id")})
                        reply_text = "Your appointment is reserved for 5 minutes. Should I confirm it?"
                        state["messages"].append(ChatMessage(role="assistant", content=reply_text))
                        state["last_assistant"] = reply_text
                        state["updated_at"] = datetime.now(timezone.utc)
                        twiml = build_gather(reply_text)
                        return Response(str(twiml), media_type="application/xml")
                    speech_result = f"Time selected: {time_24} with {stylist_name}"
            elif preferred_minutes is not None:
                summary = summarize_slots_for_voice(available_slots, preferred_minutes)
                state["context"]["last_voice_slots"] = select_voice_slot_options(available_slots, preferred_minutes)
                if summary:
                    logger.info("voice_slot_summary", extra={"call_sid": call_sid})
                    twiml = build_gather(summary)
                    return Response(str(twiml), media_type="application/xml")

        queued = state.get("queued_user_messages") or []
        if queued:
            for queued_text in queued:
                state["messages"].append(ChatMessage(role="user", content=queued_text))
            state["queued_user_messages"] = []

        state["messages"].append(ChatMessage(role="user", content=speech_result))
        chat_request = ChatRequest(messages=state["messages"], context=state["context"])

        async with AsyncSessionLocal() as session:
            processor = getattr(request.app.state, "process_chat_turn", None)
            if processor is None:
                reply_text = "I'm having trouble right now. Please try again later."
                state["messages"].append(ChatMessage(role="assistant", content=reply_text))
                twiml = build_gather(reply_text)
                return Response(str(twiml), media_type="application/xml")
            
            try:
                # Add timeout to prevent Twilio from timing out
                import asyncio
                chat_response: ChatResponse = await asyncio.wait_for(
                    processor(chat_request, session), 
                    timeout=10.0
                )
            except (Exception, asyncio.TimeoutError) as e:
                logger.exception(f"Error in process_chat_turn: {e}")
                if isinstance(e, asyncio.TimeoutError):
                    reply_text = "Please hold on, let me process that."
                else:
                    reply_text = "Sorry, I'm having trouble understanding. Please try again."
                state["messages"].append(ChatMessage(role="assistant", content=reply_text))
                twiml = build_gather(reply_text)
                return Response(str(twiml), media_type="application/xml")

        reply_text = chat_response.reply
        action_type = (chat_response.action or {}).get("type")
        slots = chat_response.data.get("slots") if chat_response.data else None
        if action_type == "fetch_availability" and isinstance(slots, list):
            preferred_minutes = state["context"].get("preferred_time_minutes")
            summary = summarize_slots_for_voice(slots, preferred_minutes)
            if summary:
                reply_text = summary
                state["context"]["last_voice_slots"] = select_voice_slot_options(slots, preferred_minutes)
            else:
                reply_text = "What time works best for you?"
            logger.info("voice_availability_fetched", extra={"call_sid": call_sid, "slots": len(slots)})
        elif isinstance(slots, list):
            summary = summarize_slots_for_voice(slots, state["context"].get("preferred_time_minutes"))
            if summary:
                reply_text = summary

        if action_type == "hold_slot":
            reply_text = "Your appointment is reserved for 5 minutes. Should I confirm it?"
        elif action_type == "confirm_booking":
            booking_id = (state["context"].get("held_slot") or {}).get("booking_id")
            if booking_id:
                try:
                    async with AsyncSessionLocal() as session:
                        from .main import ConfirmRequest, confirm_booking

                        confirm_result = await confirm_booking(
                            ConfirmRequest(booking_id=uuid.UUID(str(booking_id))),
                            session,
                        )
                    state["context"]["confirmed"] = confirm_result.model_dump()
                    logger.info("voice_confirm_success", extra={"call_sid": call_sid, "booking_id": str(booking_id)})
                    reply_text = "Your booking is confirmed. Would you like a text confirmation to this number?"
                except Exception as exc:
                    logger.exception("voice_confirm_action_failed", extra={"call_sid": call_sid, "error": str(exc)})
                    reply_text = "I couldn't confirm that. Should I try again?"
            else:
                reply_text = "I have your appointment reserved. Should I confirm it?"
        logger.info("voice_action", extra={"call_sid": call_sid, "action": action_type})

        reply_text = sanitize_voice_reply(reply_text)
        new_context = update_context_from_response(state["context"], chat_response)
        if action_type is None:
            updated = ensure_voice_prompt(reply_text, new_context)
            if updated != reply_text:
                logger.info("voice_reply_fallback", extra={"call_sid": call_sid})
            reply_text = updated
        elif not reply_text:
            reply_text = "Thanks. What would you like to do next?"

        state["messages"].append(ChatMessage(role="assistant", content=reply_text))
        state["context"] = new_context
        state["last_assistant"] = reply_text
        state["updated_at"] = datetime.now(timezone.utc)

        twiml = build_gather(reply_text)
        return Response(str(twiml), media_type="application/xml")
    except Exception:
        logger.exception("Twilio gather failed", extra={"call_sid": call_sid})
        twiml = build_gather("Sorry, something went wrong. Let's try again.")
        return Response(str(twiml), media_type="application/xml")
