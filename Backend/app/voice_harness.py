from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .voice import (
    build_gather,
    ensure_voice_prompt,
    extract_date_from_speech,
    extract_phone_from_speech,
    sanitize_voice_reply,
    summarize_slots_for_voice,
)


def run() -> None:
    assert extract_phone_from_speech("206 790 2033") == "+12067902033"
    assert extract_phone_from_speech("+1 (623) 404-8440") == "+16234048440"

    tz = ZoneInfo("America/Phoenix")
    tomorrow = datetime.now(tz).date() + timedelta(days=1)
    assert extract_date_from_speech("tomorrow", tz) == tomorrow.isoformat()
    assert extract_date_from_speech("15th of January", tz) is not None

    slots = [
        {"stylist_name": "Alex", "start_time": "2026-01-02T17:00:00+00:00"},
        {"stylist_name": "Jamie", "start_time": "2026-01-02T18:00:00+00:00"},
        {"stylist_name": "Ashmit", "start_time": "2026-01-02T19:00:00+00:00"},
    ]
    summary = summarize_slots_for_voice(slots)
    assert summary and "Alex" in summary

    twiml = build_gather("Test prompt")
    assert "<Gather" in str(twiml)

    assert "tap" not in sanitize_voice_reply("Please tap a button")  # stripped UI language
    prompt = ensure_voice_prompt("Thanks", {"selected_service_id": 1})
    assert prompt.endswith("?")


if __name__ == "__main__":
    run()
    print("voice harness ok")
