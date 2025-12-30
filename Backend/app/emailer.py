import base64
import logging

import httpx

from .core.config import get_settings

logger = logging.getLogger(__name__)


async def send_booking_email_with_ics(
    to_email: str,
    subject: str,
    html: str,
    ics_filename: str,
    ics_text: str,
) -> None:
    settings = get_settings()
    if not settings.resend_api_key or not settings.resend_from:
        logger.warning("Resend is not configured; skipping email send.")
        return

    attachment_content = base64.b64encode(ics_text.encode("utf-8")).decode("ascii")
    payload = {
        "from": settings.resend_from,
        "to": to_email,
        "subject": subject,
        "html": html,
        "attachments": [
            {
                "filename": ics_filename,
                "content": attachment_content,
                "content_type": "text/calendar; charset=utf-8",
            }
        ],
    }

    headers = {
        "Authorization": f"Bearer {settings.resend_api_key}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post("https://api.resend.com/emails", json=payload, headers=headers)
        response.raise_for_status()
