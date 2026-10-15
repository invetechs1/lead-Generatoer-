"""Public invoice/payment pages and gateway callbacks."""
import json
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..auth import current_user
from ..config import settings
from ..database import get_db
from ..models import Invoice, Activity, Setting, User
from ..services import payments

router = APIRouter(tags=["payments"])
TEMPLATES = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))


def _settings(db: Session) -> dict:
    out = {"sender_name": settings.SENDER_NAME, "sender_phone": "", "bank_name": "", "iban": "", "account_name": "", "vat_number": "", "cr_number": ""}
    for s in db.query(Setting).filter(Setting.key.in_(list(out.keys()))):
        if s.value:
            out[s.key] = s.value
    return out


def _base(request: Request) -> str:
    return (settings.PUBLIC_BASE_URL or str(request.base_url)).rstrip("/")


def _page(request: Request, db: Session, inv: Invoice, state: str = "", message: str = ""):
    return TEMPLATES.TemplateResponse(request, "invoice.html", {
        "inv": inv, "client": inv.client, "s": _settings(db), "state": state, "message": message,
        "moyasar_key": settings.MOYASAR_PUBLISHABLE_KEY if payments.configured() else "",
        "amount_halalas": payments.halalas(inv), "callback_url": f"{_base(request)}/inv/{inv.token}/callback",
    })


def _log(db: Session, inv: Invoice, text: str) -> None:
    if inv.client.lead_id:
        db.add(Activity(lead_id=inv.client.lead_id, kind="note", content=text))


@router.get("/inv/{token}", response_class=HTMLResponse, include_in_schema=False)
def invoice_page(token: str, request: Request, db: Session = Depends(get_db)):
    inv = db.query(Invoice).filter(Invoice.token == token).first()
    if not inv or inv.status == "void":
        raise HTTPException(404, "Not found")
    return _page(request, db, inv)


@router.get("/inv/{token}/callback", response_class=HTMLResponse, include_in_schema=False)
async def moyasar_callback(token: str, request: Request, id: str = "", status: str = "", message: str = "", db: Session = Depends(get_db)):
    """Moyasar redirects here after the hosted form. The payment is verified with the secret key before anything changes."""
    inv = db.query(Invoice).filter(Invoice.token == token).first()
    if not inv:
        raise HTTPException(404, "Not found")
    if inv.status == "paid":
        return _page(request, db, inv, "paid")
    if not id or not payments.configured():
        return _page(request, db, inv, "failed", message or "لم تكتمل عملية الدفع")
    try:
        payment = await payments.fetch_payment(id)
    except Exception as e:
        return _page(request, db, inv, "failed", f"تعذّر التحقق من الدفع ({type(e).__name__}) — إن خُصم المبلغ تواصل معنا")
    ok, why = payments.matches(payment, inv)
    if not ok:
        _log(db, inv, f"⚠️ محاولة دفع غير مطابقة للفاتورة {inv.number}: {why} (payment {id})"); db.commit()
        return _page(request, db, inv, "failed", message or "لم تكتمل عملية الدفع")
    if payments.apply_paid(inv, payment):
        _log(db, inv, f"💳 دُفعت الفاتورة {inv.number} عبر Moyasar ({payment.get('source', {}).get('type', '')}) — {inv.amount + inv.vat} ر.س")
    db.commit()
    return _page(request, db, inv, "paid")


@router.post("/api/payments/moyasar/webhook", include_in_schema=False)
async def moyasar_webhook(request: Request, db: Session = Depends(get_db)):
    """Moyasar webhook (dashboard → Webhooks, event payment_paid). The body carries secret_token; we still re-verify via API."""
    try:
        data = json.loads(await request.body() or b"{}")
    except ValueError:
        raise HTTPException(400, "Bad JSON")
    if settings.MOYASAR_WEBHOOK_SECRET and data.get("secret_token") != settings.MOYASAR_WEBHOOK_SECRET:
        raise HTTPException(403, "Bad secret")
    if data.get("type") != "payment_paid":
        return {"ok": True, "ignored": data.get("type")}
    pdata = data.get("data") or {}
    token = (pdata.get("metadata") or {}).get("invoice_token", "")
    inv = db.query(Invoice).filter(Invoice.token == token).first() if token else None
    if not inv:
        return {"ok": True, "ignored": "no invoice"}
    try:
        payment = await payments.fetch_payment(str(pdata.get("id", "")))
    except Exception as e:
        raise HTTPException(502, f"verify failed: {e}")
    ok, why = payments.matches(payment, inv)
    if ok and payments.apply_paid(inv, payment):
        _log(db, inv, f"💳 دُفعت الفاتورة {inv.number} عبر Moyasar (webhook) — {inv.amount + inv.vat} ر.س")
    db.commit()
    return {"ok": ok, "why": why}


@router.post("/api/public/invoice/{token}/transfer-notice")
def transfer_notice(token: str, db: Session = Depends(get_db)):
    """Client pressed 'I have transferred' on the bank-transfer option: flag it for manual confirmation."""
    inv = db.query(Invoice).filter(Invoice.token == token).first()
    if not inv or inv.status not in ("unpaid", "overdue"):
        raise HTTPException(404, "Not found")
    inv.transfer_claimed_at = datetime.utcnow()
    _log(db, inv, f"🏦 العميل أبلغ بتحويل بنكي للفاتورة {inv.number} ({inv.amount + inv.vat} ر.س) — تأكد من الحساب ثم اضغط «تم الدفع»")
    db.commit()
    return {"ok": True}


@router.get("/api/clients/invoices/{iid}/link")
def invoice_link(iid: int, request: Request, db: Session = Depends(get_db), _: User = Depends(current_user)):
    inv = db.get(Invoice, iid)
    if not inv:
        raise HTTPException(404, "Invoice not found")
    return {"url": f"{_base(request)}/inv/{inv.token}", "token": inv.token}
