from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..auth import current_user, admin_only
from ..database import get_db
from ..models import Lead, Activity, Client, Invoice, Setting, User, LEAD_STATUSES
from ..config import settings

router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db), _: User = Depends(current_user)):
    today0 = datetime.combine(date.today(), datetime.min.time())
    week0 = today0 - timedelta(days=7)
    by_status = {s: 0 for s in LEAD_STATUSES}
    for s, n in db.query(Lead.status, func.count(Lead.id)).group_by(Lead.status):
        by_status[s] = n
    sent_today = db.query(func.count(Activity.id)).filter(Activity.kind == "whatsapp", Activity.created_at >= today0).scalar() or 0
    sent_week = db.query(func.count(Activity.id)).filter(Activity.kind == "whatsapp", Activity.created_at >= week0).scalar() or 0
    contacted = sum(by_status[s] for s in ["contacted", "replied", "demo_sent", "negotiating", "won", "lost"])
    replied = sum(by_status[s] for s in ["replied", "demo_sent", "negotiating", "won"])
    due = db.query(func.count(Lead.id)).filter(Lead.next_follow_up <= date.today(), Lead.status.notin_(["won", "lost", "do_not_contact"])).scalar() or 0
    active_clients = db.query(Client).filter(Client.status == "active").all()
    mrr = sum(c.monthly_fee for c in active_clients)
    unpaid = db.query(func.coalesce(func.sum(Invoice.amount + Invoice.vat), 0)).filter(Invoice.status.in_(["unpaid", "overdue"])).scalar() or 0
    overdue = db.query(func.count(Invoice.id)).filter(Invoice.status == "overdue").scalar() or 0
    cap_row = db.get(Setting, "daily_send_cap")
    # last 14 days sends
    series = []
    for i in range(13, -1, -1):
        d0 = today0 - timedelta(days=i)
        n = db.query(func.count(Activity.id)).filter(Activity.kind == "whatsapp", Activity.created_at >= d0, Activity.created_at < d0 + timedelta(days=1)).scalar() or 0
        series.append({"day": d0.strftime("%m-%d"), "sent": n})
    return {
        "leads_total": sum(by_status.values()), "by_status": by_status,
        "sent_today": sent_today, "sent_week": sent_week, "daily_cap": int(cap_row.value) if cap_row and cap_row.value else settings.DAILY_SEND_CAP,
        "reply_rate": round(replied / contacted * 100, 1) if contacted else 0.0,
        "win_rate": round(by_status["won"] / contacted * 100, 1) if contacted else 0.0,
        "follow_ups_due": due,
        "clients_active": len(active_clients), "mrr": mrr, "arr": mrr * 12, "unpaid_total": int(unpaid), "invoices_overdue": overdue,
        "series": series,
    }


DEFAULT_SETTINGS = {"daily_send_cap": str(settings.DAILY_SEND_CAP), "sender_name": settings.SENDER_NAME, "sender_phone": "", "demo_url": settings.DEMO_URL, "default_price": str(settings.DEFAULT_PRICE_SAR), "bank_name": "", "iban": "", "account_name": "", "vat_number": "", "cr_number": "", "terms_text": "", "terms_version": "1.0"}


@router.get("/settings")
def get_settings(db: Session = Depends(get_db), _: User = Depends(current_user)):
    out = dict(DEFAULT_SETTINGS)
    for s in db.query(Setting):
        out[s.key] = s.value
    out["whatsapp_api"] = bool(settings.WHATSAPP_TOKEN and settings.WHATSAPP_PHONE_ID)
    out["places_api"] = bool(settings.GOOGLE_PLACES_API_KEY)
    out["designer_api"] = bool(settings.ANTHROPIC_API_KEY)
    out["moyasar"] = bool(settings.MOYASAR_PUBLISHABLE_KEY and settings.MOYASAR_SECRET_KEY)
    return out


@router.put("/settings")
def put_settings(data: dict, db: Session = Depends(get_db), _: User = Depends(admin_only)):
    for k, v in data.items():
        if k not in DEFAULT_SETTINGS:
            continue
        row = db.get(Setting, k) or Setting(key=k)
        row.value = str(v)[:2000]
        db.add(row)
    db.commit()
    return get_settings(db, _)
