"""Morning digest: what the salesperson must do today, as structured data and as a WhatsApp-ready text."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from ..models import Lead, Invoice, Proposal, UpdateRequest, Activity


def build(db: Session, base_url: str = "") -> dict:
    today = date.today()
    y0 = datetime.combine(today - timedelta(days=1), datetime.min.time())
    active = Lead.status.notin_(["won", "lost", "do_not_contact"])
    due = db.query(Lead).filter(Lead.next_follow_up <= today, active).order_by(Lead.priority, Lead.next_follow_up).all()
    hot = db.query(Lead).filter(Lead.status == "negotiating").order_by(Lead.updated_at.desc()).all()
    overdue = db.query(Invoice).filter(Invoice.status == "overdue").all()
    transfers = db.query(Invoice).filter(Invoice.transfer_claimed_at.isnot(None), Invoice.status.in_(["unpaid", "overdue"])).all()
    opened = db.query(Proposal).filter(Proposal.last_viewed_at >= y0, Proposal.answered_at.is_(None)).all()
    answered = db.query(Proposal).filter(Proposal.answered_at >= y0).all()
    updates = db.query(UpdateRequest).filter(UpdateRequest.status == "open").all()
    replies = db.query(Activity).filter(Activity.kind == "reply", Activity.created_at >= y0).count()
    sent_y = db.query(Activity).filter(Activity.kind == "whatsapp", Activity.created_at >= y0).count()

    lines = [f"☀️ ملخص اليوم {today.strftime('%Y-%m-%d')}"]
    if due:
        lines.append(f"\n📞 متابعات مستحقة ({len(due)}):")
        lines += [f"• {l.name} — {l.city or ''} · {l.status}" for l in due[:8]]
        if len(due) > 8:
            lines.append(f"… و{len(due) - 8} غيرهم")
    if hot:
        lines.append(f"\n🔥 في مرحلة التفاوض ({len(hot)}): " + "، ".join(l.name for l in hot[:5]))
    if answered:
        lines.append(f"\n🎯 أجابوا على عرض التصميم أمس ({len(answered)}): " + "، ".join(p.lead.name for p in answered[:5]))
    if opened:
        lines.append(f"\n👁 فتحوا العرض أمس ولم يجيبوا ({len(opened)}): " + "، ".join(p.lead.name for p in opened[:5]))
    if transfers:
        lines.append(f"\n🏦 تحويلات تنتظر تأكيدك ({len(transfers)}): " + "، ".join(f"{i.client.company} {i.amount + i.vat} ر.س" for i in transfers[:5]))
    if overdue:
        lines.append(f"\n⚠️ فواتير متأخرة ({len(overdue)}): " + "، ".join(f"{i.client.company} ({i.period})" for i in overdue[:5]))
    if updates:
        lines.append(f"\n✏️ طلبات تحديث من العملاء ({len(updates)}): " + "، ".join(u.client.company for u in updates[:5]))
    lines.append(f"\nأمس: {sent_y} رسالة مُرسلة · {replies} رد وارد")
    if base_url:
        lines.append(f"{base_url.rstrip('/')}/#dash")
    return {
        "date": today.isoformat(), "text": "\n".join(lines),
        "counts": {"due": len(due), "negotiating": len(hot), "answered": len(answered), "opened": len(opened), "transfers": len(transfers), "overdue": len(overdue), "updates": len(updates), "sent_yesterday": sent_y, "replies_yesterday": replies},
        "due": [{"id": l.id, "name": l.name, "city": l.city, "status": l.status, "next_follow_up": l.next_follow_up.isoformat() if l.next_follow_up else None} for l in due[:20]],
        "updates": [{"id": u.id, "company": u.client.company, "text": u.text[:120]} for u in updates[:20]],
    }
