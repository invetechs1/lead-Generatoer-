import csv
import io
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import or_, func
from sqlalchemy.orm import Session

from ..auth import current_user
from ..database import get_db
from ..models import Lead, Activity, Template, User, Setting, LEAD_STATUSES
from ..schemas import LeadIn, LeadUpdate, LeadOut, LeadPage, ImportResult, SendIn, SendOut, ActivityIn, ActivityOut, AuditOut, normalize_phone
from ..services import whatsapp, site_audit
from ..config import settings

router = APIRouter(prefix="/api/leads", tags=["leads"])


def _setting(db: Session, key: str, default: str) -> str:
    s = db.get(Setting, key)
    return s.value if s and s.value else default


@router.get("", response_model=LeadPage)
def list_leads(
    db: Session = Depends(get_db), _: User = Depends(current_user),
    q: Optional[str] = None, status: Optional[str] = None, city: Optional[str] = None, sector: Optional[str] = None,
    due: Optional[bool] = None, has_website: Optional[bool] = None, max_score: Optional[int] = Query(None, ge=0, le=100),
    page: int = Query(1, ge=1), size: int = Query(50, ge=1, le=500),
):
    qry = db.query(Lead)
    if has_website is True:
        qry = qry.filter(Lead.website != "")
    elif has_website is False:
        qry = qry.filter(Lead.website == "")
    if max_score is not None:
        qry = qry.filter(Lead.site_score <= max_score)
    if q:
        like = f"%{q}%"
        qry = qry.filter(or_(Lead.name.ilike(like), Lead.phone.ilike(like), Lead.notes.ilike(like)))
    if status:
        qry = qry.filter(Lead.status == status)
    if city:
        qry = qry.filter(Lead.city == city)
    if sector:
        qry = qry.filter(Lead.sector == sector)
    if due:
        qry = qry.filter(Lead.next_follow_up <= date.today(), Lead.status.notin_(["won", "lost", "do_not_contact"]))
    total = qry.count()
    items = qry.order_by(Lead.priority, Lead.next_follow_up.is_(None), Lead.next_follow_up, Lead.id.desc()).offset((page - 1) * size).limit(size).all()
    return LeadPage(items=items, total=total, page=page, size=size)


@router.get("/facets")
def facets(db: Session = Depends(get_db), _: User = Depends(current_user)):
    cities = [c for (c,) in db.query(Lead.city).distinct().order_by(Lead.city) if c]
    sectors = [s for (s,) in db.query(Lead.sector).distinct().order_by(Lead.sector) if s]
    return {"cities": cities, "sectors": sectors, "statuses": LEAD_STATUSES}


@router.post("", response_model=LeadOut, status_code=201)
def create_lead(data: LeadIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if db.query(Lead).filter(Lead.phone == data.phone).first():
        raise HTTPException(409, "Phone already exists")
    lead = Lead(**data.model_dump(), owner_id=user.id)
    db.add(lead); db.commit(); db.refresh(lead)
    return lead


@router.post("/import", response_model=ImportResult)
async def import_csv(file: UploadFile = File(...), db: Session = Depends(get_db), user: User = Depends(current_user)):
    """CSV with header. Accepted columns: name, phone, city, sector, instagram, website, maps_url, notes (Arabic headers also ok)."""
    raw = (await file.read()).decode("utf-8-sig", errors="ignore")
    alias = {"الاسم": "name", "المنشأة": "name", "الجوال": "phone", "الهاتف": "phone", "المدينة": "city", "النشاط": "sector", "القطاع": "sector", "ملاحظات": "notes"}
    reader = csv.DictReader(io.StringIO(raw))
    res = ImportResult(added=0, skipped_duplicates=0, skipped_invalid=0)
    existing = {p for (p,) in db.query(Lead.phone)}
    for i, row in enumerate(reader, start=2):
        row = {alias.get((k or "").strip(), (k or "").strip().lower()): (v or "").strip() for k, v in row.items()}
        try:
            phone = normalize_phone(row.get("phone", ""))
            name = row.get("name", "")
            if not name:
                raise ValueError("missing name")
        except ValueError as e:
            res.skipped_invalid += 1
            if len(res.errors) < 20:
                res.errors.append(f"row {i}: {e}")
            continue
        if phone in existing:
            res.skipped_duplicates += 1
            continue
        score = row.get("site_score", "")
        rating = row.get("rating", "")
        reviews = row.get("reviews", "")
        db.add(Lead(name=name, phone=phone, city=row.get("city", ""), sector=row.get("sector", ""), instagram=row.get("instagram", ""),
                    website=row.get("website", ""), maps_url=row.get("maps_url", ""), notes=row.get("notes", ""), source="csv", owner_id=user.id,
                    site_score=int(float(score)) if score.replace(".", "", 1).isdigit() else None, site_issues=row.get("site_issues", ""),
                    rating=float(rating) if rating.replace(".", "", 1).isdigit() else None, reviews=int(float(reviews)) if reviews.replace(".", "", 1).isdigit() else None))
        existing.add(phone); res.added += 1
    db.commit()
    return res


@router.get("/export")
def export_csv(db: Session = Depends(get_db), _: User = Depends(current_user)):
    buf = io.StringIO(); buf.write("\ufeff")
    w = csv.writer(buf)
    w.writerow(["id", "name", "phone", "city", "sector", "status", "priority", "instagram", "website", "site_score", "site_issues", "maps_url", "next_follow_up", "last_contacted_at", "notes"])
    for l in db.query(Lead).order_by(Lead.id):
        w.writerow([l.id, l.name, l.phone, l.city, l.sector, l.status, l.priority, l.instagram, l.website, l.site_score if l.site_score is not None else "", l.site_issues, l.maps_url, l.next_follow_up or "", l.last_contacted_at or "", l.notes])
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=leads.csv"})


@router.get("/{lead_id}", response_model=LeadOut)
def get_lead(lead_id: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    lead = db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(404, "Lead not found")
    return lead


@router.patch("/{lead_id}", response_model=LeadOut)
def update_lead(lead_id: int, data: LeadUpdate, db: Session = Depends(get_db), user: User = Depends(current_user)):
    lead = db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(404, "Lead not found")
    changes = data.model_dump(exclude_unset=True)
    if "status" in changes and changes["status"] != lead.status:
        db.add(Activity(lead_id=lead.id, user_id=user.id, kind="status", content=f"{lead.status} → {changes['status']}"))
    for k, v in changes.items():
        setattr(lead, k, v)
    db.commit(); db.refresh(lead)
    return lead


@router.delete("/{lead_id}", status_code=204)
def delete_lead(lead_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    lead = db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(404, "Lead not found")
    if user.role != "admin":
        raise HTTPException(403, "Admin only")
    db.delete(lead); db.commit()


@router.get("/{lead_id}/activities", response_model=list[ActivityOut])
def activities(lead_id: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    return db.query(Activity).filter(Activity.lead_id == lead_id).order_by(Activity.created_at.desc()).all()


@router.post("/{lead_id}/activities", response_model=ActivityOut, status_code=201)
def add_activity(lead_id: int, data: ActivityIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if not db.get(Lead, lead_id):
        raise HTTPException(404, "Lead not found")
    a = Activity(lead_id=lead_id, user_id=user.id, kind=data.kind, content=data.content)
    db.add(a); db.commit(); db.refresh(a)
    return a


@router.post("/{lead_id}/send", response_model=SendOut)
async def send_whatsapp(lead_id: int, data: SendIn, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    lead = db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(404, "Lead not found")
    if lead.status == "do_not_contact":
        raise HTTPException(400, "Lead is marked do-not-contact")

    cap = int(_setting(db, "daily_send_cap", str(settings.DAILY_SEND_CAP)))
    start = datetime.combine(date.today(), datetime.min.time())
    sent_today = db.query(func.count(Activity.id)).filter(Activity.kind == "whatsapp", Activity.created_at >= start).scalar() or 0
    if sent_today >= cap:
        raise HTTPException(429, f"Daily send cap reached ({cap}). Raise it in Settings or continue tomorrow.")

    body = data.body
    tpl = None
    if not body:
        if not data.template_id:
            raise HTTPException(400, "template_id or body is required")
        tpl = db.get(Template, data.template_id)
        if not tpl:
            raise HTTPException(404, "Template not found")
        body = tpl.body
    message = whatsapp.render(body, lead, _setting(db, "demo_url", settings.DEMO_URL), _setting(db, "sender_name", settings.SENDER_NAME), base_url=(settings.PUBLIC_BASE_URL or str(request.base_url)).rstrip("/"))

    channel = "wa_link"
    if whatsapp.api_configured():
        try:
            await whatsapp.send_via_api(lead.phone, message)
            channel = "wa_api"
        except Exception:
            channel = "wa_link"  # graceful fallback

    db.add(Activity(lead_id=lead.id, user_id=user.id, kind="whatsapp", channel=channel, template_id=tpl.id if tpl else None, content=message))
    if data.mark_contacted and lead.status == "new":
        lead.status = "contacted"
    lead.last_contacted_at = datetime.utcnow()
    if data.follow_up_in_days:
        lead.next_follow_up = date.today() + timedelta(days=data.follow_up_in_days)
    db.commit()
    return SendOut(lead_id=lead.id, phone=lead.phone, message=message, wa_link=whatsapp.wa_link(lead.phone, message), channel=channel, sent_today=sent_today + 1, daily_cap=cap)


@router.post("/{lead_id}/audit", response_model=AuditOut)
async def audit_website(lead_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Score the lead's existing website (0-100) and store the Arabic issue list for the {issues} placeholder."""
    lead = db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(404, "Lead not found")
    if not lead.website:
        raise HTTPException(400, "Lead has no website to audit (use the no-website templates)")
    a = await site_audit.audit(lead.website)
    lead.site_score = a.score
    lead.site_issues = "\n".join(a.issues)
    db.add(Activity(lead_id=lead.id, user_id=user.id, kind="note", content=f"فحص الموقع: {a.score}/100" + ("\n" + lead.site_issues if a.issues else "")))
    db.commit()
    return AuditOut(lead_id=lead.id, **a.dict())
