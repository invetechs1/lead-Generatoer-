"""WhatsApp delivery: wa.me deep link by default; Cloud API when configured."""
import hashlib
import hmac
from urllib.parse import quote, urlencode

import httpx

from ..config import settings

GRAPH = "https://graph.facebook.com/v20.0"


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


def proposal_url(lead, base_url: str = "") -> str:
    """Public link to the lead's designed proposal page, or '' when none exists yet."""
    prop = getattr(lead, "proposal", None)
    if not prop:
        return ""
    base = (base_url or settings.PUBLIC_BASE_URL or "").rstrip("/")
    return f"{base}/p/{prop.token}"


def site_url(lead, base_url: str = "") -> str:
    prop = getattr(lead, "proposal", None)
    if not prop or not getattr(prop, "published", False):
        return ""
    if prop.custom_domain:
        return f"https://{prop.custom_domain}"
    base = (base_url or settings.PUBLIC_BASE_URL or "").rstrip("/")
    return f"{base}/s/{prop.slug}"


def stats_text(lead) -> str:
    """This month's live-site numbers for the {stats} placeholder (empty when not published)."""
    prop = getattr(lead, "proposal", None)
    if not prop or not getattr(prop, "published", False):
        return ""
    from datetime import date, datetime
    start = datetime.combine(date.today().replace(day=1), datetime.min.time())
    counts = {"view": 0, "wa": 0, "call": 0, "map": 0, "form": 0}
    for ev in getattr(prop, "events", []) or []:
        if ev.created_at >= start and ev.kind in counts:
            counts[ev.kind] += 1
    return f"{counts['view']} زيارة · {counts['wa']} ضغطة واتساب · {counts['call']} اتصال · {counts['map']} فتح للخريطة"


def invoice_url(lead, base_url: str = "") -> str:
    """Link to the client's oldest open invoice (overdue first), or '' when nothing is due."""
    client = getattr(lead, "client", None)
    if not client:
        return ""
    open_ = [i for i in client.invoices if i.status in ("unpaid", "overdue") and i.token]
    if not open_:
        return ""
    inv = sorted(open_, key=lambda i: i.due_date)[0]
    base = (base_url or settings.PUBLIC_BASE_URL or "").rstrip("/")
    return f"{base}/inv/{inv.token}"


def update_link(lead, base_url: str = "") -> str:
    client = getattr(lead, "client", None)
    if not client or not getattr(client, "update_token", ""):
        return ""
    base = (base_url or settings.PUBLIC_BASE_URL or "").rstrip("/")
    return f"{base}/u/{client.update_token}"


def render(body: str, lead, demo_url: str = "", sender: str = "", base_url: str = "") -> str:
    demo = proposal_url(lead, base_url) or personal_demo(demo_url or settings.DEMO_URL or "", lead)
    return (
        body.replace("{name}", lead.name or "")
        .replace("{proposal}", proposal_url(lead, base_url))
        .replace("{site}", site_url(lead, base_url))
        .replace("{invoice}", invoice_url(lead, base_url))
        .replace("{update_link}", update_link(lead, base_url))
        .replace("{stats}", stats_text(lead))
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
    url = f"{GRAPH}/{settings.WHATSAPP_PHONE_ID}/messages"
    payload = {"messaging_product": "whatsapp", "to": phone, "type": "text", "text": {"body": message}}
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(url, json=payload, headers={"Authorization": f"Bearer {settings.WHATSAPP_TOKEN}"})
        r.raise_for_status()
        return r.json()


# ---------------- Cloud API: interactive messages + webhook ----------------

def interactive_buttons_payload(phone: str, body: str, buttons: list[tuple[str, str]], header: str = "", footer: str = "") -> dict:
    """Reply-button message (max 3 buttons, titles <= 20 chars). Session message: needs an open 24h window."""
    if not 1 <= len(buttons) <= 3:
        raise ValueError("WhatsApp reply buttons: 1-3 buttons")
    inter: dict = {"type": "button", "body": {"text": body[:1024]}, "action": {"buttons": [{"type": "reply", "reply": {"id": bid[:256], "title": title[:20]}} for bid, title in buttons]}}
    if header:
        inter["header"] = {"type": "text", "text": header[:60]}
    if footer:
        inter["footer"] = {"text": footer[:60]}
    return {"messaging_product": "whatsapp", "recipient_type": "individual", "to": phone, "type": "interactive", "interactive": inter}


def interactive_list_payload(phone: str, body: str, button_label: str, rows: list[tuple[str, str, str]], header: str = "") -> dict:
    """List message (up to 10 rows). rows = [(id, title<=24, description<=72)]. Session message."""
    if not 1 <= len(rows) <= 10:
        raise ValueError("WhatsApp list: 1-10 rows")
    inter: dict = {"type": "list", "body": {"text": body[:1024]}, "action": {"button": button_label[:20], "sections": [{"title": header[:24] or "الخيارات", "rows": [{"id": rid[:200], "title": t[:24], "description": d[:72]} for rid, t, d in rows]}]}}
    return {"messaging_product": "whatsapp", "recipient_type": "individual", "to": phone, "type": "interactive", "interactive": inter}


def template_payload(phone: str, template_name: str, lang: str = "ar", body_params: list[str] | None = None, button_url_param: str = "") -> dict:
    """Approved Marketing template (the only way to open a cold conversation via the Cloud API). Quick-reply buttons
    are defined on the template in Meta Business Manager; the URL button can carry the proposal token."""
    comps: list[dict] = []
    if body_params:
        comps.append({"type": "body", "parameters": [{"type": "text", "text": p} for p in body_params]})
    if button_url_param:
        comps.append({"type": "button", "sub_type": "url", "index": "0", "parameters": [{"type": "text", "text": button_url_param}]})
    return {"messaging_product": "whatsapp", "to": phone, "type": "template", "template": {"name": template_name, "language": {"code": lang}, "components": comps}}


async def send_payload(payload: dict) -> dict:
    url = f"{GRAPH}/{settings.WHATSAPP_PHONE_ID}/messages"
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(url, json=payload, headers={"Authorization": f"Bearer {settings.WHATSAPP_TOKEN}"})
        r.raise_for_status()
        return r.json()


def verify_signature(raw_body: bytes, signature_header: str) -> bool:
    """X-Hub-Signature-256: sha256=<hmac>. Always False when WHATSAPP_APP_SECRET is not configured (fail closed)."""
    if not settings.WHATSAPP_APP_SECRET:
        return False
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(settings.WHATSAPP_APP_SECRET.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header[7:])


def parse_webhook(data: dict) -> list[dict]:
    """Flatten a Cloud API webhook into events: {phone, name, kind: text|button|list|status, text, reply_id, status, wamid}."""
    out: list[dict] = []
    for entry in data.get("entry", []) or []:
        for ch in entry.get("changes", []) or []:
            v = ch.get("value", {}) or {}
            names = {c.get("wa_id"): (c.get("profile") or {}).get("name", "") for c in v.get("contacts", []) or []}
            for m in v.get("messages", []) or []:
                ev = {"phone": m.get("from", ""), "name": names.get(m.get("from", ""), ""), "wamid": m.get("id", ""), "kind": "text", "text": "", "reply_id": ""}
                t = m.get("type")
                if t == "text":
                    ev["text"] = (m.get("text") or {}).get("body", "")
                elif t == "interactive":
                    inter = m.get("interactive") or {}
                    if inter.get("type") == "button_reply":
                        ev["kind"] = "button"; ev["reply_id"] = inter["button_reply"].get("id", ""); ev["text"] = inter["button_reply"].get("title", "")
                    elif inter.get("type") == "list_reply":
                        ev["kind"] = "list"; ev["reply_id"] = inter["list_reply"].get("id", ""); ev["text"] = inter["list_reply"].get("title", "")
                elif t == "button":  # quick-reply on a template
                    ev["kind"] = "button"; ev["reply_id"] = (m.get("button") or {}).get("payload", ""); ev["text"] = (m.get("button") or {}).get("text", "")
                else:
                    ev["text"] = f"[{t}]"
                out.append(ev)
            for st in v.get("statuses", []) or []:
                out.append({"phone": st.get("recipient_id", ""), "name": "", "wamid": st.get("id", ""), "kind": "status", "text": st.get("status", ""), "reply_id": "", "status": st.get("status", "")})
    return out
