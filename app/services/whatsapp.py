"""WhatsApp delivery: wa.me deep link by default; Cloud API when configured."""
from urllib.parse import quote

import httpx

from ..config import settings


def render(body: str, lead, demo_url: str = "", sender: str = "") -> str:
    return (
        body.replace("{name}", lead.name or "")
        .replace("{city}", lead.city or "")
        .replace("{sector}", lead.sector or "")
        .replace("{activity}", lead.sector or "")
        .replace("{demo}", demo_url or settings.DEMO_URL or "")
        .replace("{sender}", sender or settings.SENDER_NAME or "")
    )


def wa_link(phone: str, message: str) -> str:
    return f"https://wa.me/{phone}?text={quote(message)}"


def api_configured() -> bool:
    return bool(settings.WHATSAPP_TOKEN and settings.WHATSAPP_PHONE_ID)


async def send_via_api(phone: str, message: str) -> dict:
    """Send a free-form text via WhatsApp Cloud API (requires an open 24h window or approved template)."""
    url = f"https://graph.facebook.com/v20.0/{settings.WHATSAPP_PHONE_ID}/messages"
    payload = {"messaging_product": "whatsapp", "to": phone, "type": "text", "text": {"body": message}}
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(url, json=payload, headers={"Authorization": f"Bearer {settings.WHATSAPP_TOKEN}"})
        r.raise_for_status()
        return r.json()
