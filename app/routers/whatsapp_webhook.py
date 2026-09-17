"""WhatsApp Cloud API: send interactive button messages and receive replies (webhook)."""
import json
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from ..auth import current_user
from ..config import settings
from ..database import get_db
from ..models import Lead, Activity, User
from ..schemas import ButtonsSendIn
from ..services import whatsapp

router = APIRouter(prefix="/api/whatsapp", tags=["whatsapp"])
STOP_WORDS = ("إيقاف", "ايقاف", "لا أريد", "لا اريد", "stop", "unsubscribe", "لا ترسل", "ما ابغى", "ما أبغى")


@router.get("/webhook", include_in_schema=False)
def verify(hub_mode: str = Query("", alias="hub.mode"), hub_token: str = Query("", alias="hub.verify_token"), hub_challenge: str = Query("", alias="hub.challenge")):
    if hub_mode == "subscribe" and settings.WHATSAPP_VERIFY_TOKEN and hub_token == settings.WHATSAPP_VERIFY_TOKEN:
        return PlainTextResponse(hub_challenge)
    raise HTTPException(403, "Verification failed")


@router.post("/webhook", include_in_schema=False)
async def receive(request: Request, db: Session = Depends(get_db)):
    raw = await request.body()
    if not whatsapp.verify_signature(raw, request.headers.get("X-Hub-Signature-256", "")):
        raise HTTPException(403, "Bad signature")
    try:
        data = json.loads(raw or b"{}")
    except ValueError:
        raise HTTPException(400, "Bad JSON")
    handled = 0
    for ev in whatsapp.parse_webhook(data):
        if ev["kind"] == "status":
            continue  # delivery/read receipts: not stored (keeps the timeline clean)
        lead = db.query(Lead).filter(Lead.phone == ev["phone"]).first()
        if not lead:
            continue
        handled += 1
        label = {"button": "🔘 ضغط زر", "list": "📋 اختار من القائمة", "text": "💬 رد"}.get(ev["kind"], "رد")
        db.add(Activity(lead_id=lead.id, kind="reply", channel="wa_api", content=f"{label}: {ev['text']}" + (f" [{ev['reply_id']}]" if ev["reply_id"] else "")))
        apply_reply(lead, ev)
    db.commit()
    return {"ok": True, "handled": handled}


def apply_reply(lead: Lead, ev: dict) -> None:
    """Move the pipeline from what the client tapped/typed. Button ids are conventions used by the send endpoint & templates."""
    text = (ev.get("text") or "").strip().lower()
    rid = (ev.get("reply_id") or "").lower()
    if lead.status in ("won",):
        return
    if any(w in text for w in STOP_WORDS) or rid.startswith("stop"):
        lead.status = "do_not_contact"; lead.next_follow_up = None
        return
    if rid.startswith(("start", "yes", "interested", "call")):
        lead.status = "negotiating"; lead.priority = 1; lead.next_follow_up = date.today()
    elif rid.startswith(("later", "month")):
        lead.status = "replied"; lead.next_follow_up = date.today() + timedelta(days=7)
    elif rid.startswith(("no", "not")):
        lead.status = "lost"; lead.next_follow_up = None
    elif lead.status in ("new", "contacted", "demo_sent"):
        lead.status = "replied"; lead.next_follow_up = date.today()


@router.post("/leads/{lead_id}/buttons")
async def send_buttons(lead_id: int, data: ButtonsSendIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Send a reply-button message through the Cloud API (session message: the client must have written to you in the last 24h)."""
    lead = db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(404, "Lead not found")
    if lead.status == "do_not_contact":
        raise HTTPException(400, "Lead is marked do-not-contact")
    if not whatsapp.api_configured():
        raise HTTPException(400, "WhatsApp Cloud API is not configured (WHATSAPP_TOKEN / WHATSAPP_PHONE_ID)")
    payload = whatsapp.interactive_buttons_payload(lead.phone, data.body, [(b.get("id", f"btn{i}"), b.get("title", "")) for i, b in enumerate(data.buttons)], header=data.header)
    try:
        res = await whatsapp.send_payload(payload)
    except Exception as e:
        raise HTTPException(502, f"WhatsApp error: {e}")
    db.add(Activity(lead_id=lead.id, user_id=user.id, kind="whatsapp", channel="wa_api", content=data.body + "\n[" + " | ".join(b.get("title", "") for b in data.buttons) + "]"))
    db.commit()
    return {"ok": True, "response": res}
