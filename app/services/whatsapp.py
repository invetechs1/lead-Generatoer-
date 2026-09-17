"""WhatsApp delivery: wa.me deep link by default; Cloud API when configured."""
from urllib.parse import quote, urlencode

import httpx

from ..config import settings


def personal_demo(demo_url: str, lead) -> str:
    """Append the lead's name/city/phone/sector to the demo URL so the sample site shows THEIR name.
    Works with the bundled /demo/* pages; harmless on any other URL (extra query params are ignored)."""
    base = (demo_url or "").strip()
    if not base:
        return ""
    params = {k: v for k, v in {"n": lead.name, "c": lead.city, "p": lead.phone, "s": lead.sector}.items() if v}
    if not params:
        return base
    return base + ("&" if "?" in base else "?") + urlencode(params)


def issues_text(lead) -> str:
    """Bullet list of audit findings for the {issues} placeholder (empty when not audited)."""
    raw = (getattr(lead, "site_issues", "") or "").strip()
    return "\n".join(f"• {line.strip()}" for line in raw.splitlines() if line.strip())


def render(body: str, lead, demo_url: str = "", sender: str = "") -> str:
    demo = personal_demo(demo_url or settings.DEMO_URL or "", lead)
    return (
        body.replace("{name}", lead.name or "")
        .replace("{city}", lead.city or "")
        .replace("{sector}", lead.sector or "")
        .replace("{activity}", lead.sector or "")
        .replace("{website}", lead.website or "")
        .replace("{issues}", issues_text(lead))
        .replace("{demo}", demo)
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
