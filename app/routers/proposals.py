"""Designed proposals: photos → design brief (designer agent) → public page /p/{token} with tap-to-answer questions."""
import json
import secrets
from datetime import datetime, timedelta, date
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..auth import current_user
from ..config import settings
from ..database import get_db
from ..models import Lead, Proposal, Activity, User, Setting
from ..schemas import ProposalIn, ProposalOut, BriefPatch, AnswersIn
from ..services import designer, places

router = APIRouter(tags=["proposals"])
TEMPLATES = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))
ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp"}
MAX_UPLOAD = 8 * 1024 * 1024


def upload_dir(lead_id: int) -> Path:
    d = Path(settings.UPLOAD_DIR) / "leads" / str(lead_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def photo_urls(lead_id: int) -> list[str]:
    d = upload_dir(lead_id)
    files = sorted([f for f in d.iterdir() if f.suffix.lower() in ALLOWED_EXT], key=lambda f: f.name)
    return [f"/uploads/leads/{lead_id}/{f.name}" for f in files]


def _setting(db: Session, key: str, default: str) -> str:
    s = db.get(Setting, key)
    return s.value if s and s.value else default


def _base_url(request: Request) -> str:
    return (settings.PUBLIC_BASE_URL or str(request.base_url)).rstrip("/")


def _out(p: Proposal, base: str) -> ProposalOut:
    return ProposalOut(lead_id=p.lead_id, token=p.token, url=f"{base}/p/{p.token}", kind=p.kind, source=p.source, brief=json.loads(p.brief or "{}"),
                       photos=json.loads(p.photos or "[]"), answers=json.loads(p.answers or "{}"), views=p.views, last_viewed_at=p.last_viewed_at,
                       answered_at=p.answered_at, created_at=p.created_at)


# ---------------- photos ----------------

@router.get("/api/leads/{lead_id}/photos")
def list_photos(lead_id: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    if not db.get(Lead, lead_id):
        raise HTTPException(404, "Lead not found")
    return {"photos": photo_urls(lead_id)}


@router.post("/api/leads/{lead_id}/photos")
async def upload_photos(lead_id: int, files: list[UploadFile] = File(...), db: Session = Depends(get_db), _: User = Depends(current_user)):
    """Upload the business's own photos / logo (jpg, png, webp; 8 MB each). These feed the designer and the page."""
    if not db.get(Lead, lead_id):
        raise HTTPException(404, "Lead not found")
    d = upload_dir(lead_id)
    saved = []
    for f in files:
        ext = Path(f.filename or "").suffix.lower()
        if ext not in ALLOWED_EXT:
            continue
        data = await f.read()
        if len(data) > MAX_UPLOAD or not data:
            continue
        name = f"up_{secrets.token_hex(4)}{ext}"
        (d / name).write_bytes(data)
        saved.append(name)
    _sync_photos(db, lead_id)
    return {"saved": saved, "photos": photo_urls(lead_id)}


@router.delete("/api/leads/{lead_id}/photos/{name}", status_code=204)
def delete_photo(lead_id: int, name: str, db: Session = Depends(get_db), _: User = Depends(current_user)):
    f = upload_dir(lead_id) / Path(name).name
    if f.is_file():
        f.unlink()
    _sync_photos(db, lead_id)


@router.post("/api/leads/{lead_id}/photos/google")
async def fetch_google_photos(lead_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Pull the business's own photos from its Google Maps listing (needs GOOGLE_PLACES_API_KEY)."""
    lead = db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(404, "Lead not found")
    try:
        pid, names = await places.photo_names(lead.place_id, lead.name, lead.city)
    except RuntimeError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(502, f"Google Places error: {e}")
    if pid and not lead.place_id:
        lead.place_id = pid
    saved = await places.download_photos(names, upload_dir(lead_id)) if names else []
    db.add(Activity(lead_id=lead.id, user_id=user.id, kind="note", content=f"جُلبت {len(saved)} صورة من قوقل"))
    db.commit()
    _sync_photos(db, lead_id)
    return {"saved": saved, "photos": photo_urls(lead_id)}


def _sync_photos(db: Session, lead_id: int) -> None:
    p = db.query(Proposal).filter(Proposal.lead_id == lead_id).first()
    if p:
        p.photos = json.dumps(photo_urls(lead_id))
        db.commit()


# ---------------- proposal ----------------

@router.post("/api/leads/{lead_id}/proposal", response_model=ProposalOut)
async def create_proposal(lead_id: int, data: ProposalIn, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Run the designer agent and (re)build the lead's proposal page. Safe to call again after adding photos or notes."""
    lead = db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(404, "Lead not found")
    d = upload_dir(lead_id)
    paths = [d / Path(u).name for u in photo_urls(lead_id)]
    try:
        brief, source = await designer.generate_brief(lead, paths, notes=data.notes, kind=data.kind, instagram_bio=data.instagram_bio)
    except Exception as e:  # API/network error → never block the salesperson
        brief, source = designer.preset_brief(lead, data.kind), f"preset (designer error: {type(e).__name__})"
    p = db.query(Proposal).filter(Proposal.lead_id == lead_id).first()
    if not p:
        p = Proposal(lead_id=lead_id, token=secrets.token_urlsafe(18))
        db.add(p)
    p.kind = brief.kind
    p.brief = brief.model_dump_json()
    p.photos = json.dumps(photo_urls(lead_id))
    p.source = source[:20]
    db.add(Activity(lead_id=lead.id, user_id=user.id, kind="note", content=f"أُنشئ عرض التصميم ({source}) — {brief.mood}\n{brief.design_rationale}"))
    db.commit(); db.refresh(p)
    return _out(p, _base_url(request))


@router.get("/api/leads/{lead_id}/proposal", response_model=ProposalOut)
def get_proposal(lead_id: int, request: Request, db: Session = Depends(get_db), _: User = Depends(current_user)):
    p = db.query(Proposal).filter(Proposal.lead_id == lead_id).first()
    if not p:
        raise HTTPException(404, "No proposal yet")
    return _out(p, _base_url(request))


@router.patch("/api/leads/{lead_id}/proposal", response_model=ProposalOut)
def edit_proposal(lead_id: int, data: BriefPatch, request: Request, db: Session = Depends(get_db), _: User = Depends(current_user)):
    """Hand-edit any brief field (headline, prices, palette...) after generation."""
    p = db.query(Proposal).filter(Proposal.lead_id == lead_id).first()
    if not p:
        raise HTTPException(404, "No proposal yet")
    merged = {**json.loads(p.brief or "{}"), **data.brief}
    try:
        brief = designer.Brief.model_validate(merged)  # keeps the page renderable
    except Exception as e:
        raise HTTPException(422, f"Invalid brief: {e}")
    p.brief = brief.model_dump_json(); p.kind = brief.kind
    db.commit(); db.refresh(p)
    return _out(p, _base_url(request))


# ---------------- public ----------------

@router.get("/p/{token}", response_class=HTMLResponse, include_in_schema=False)
def public_proposal(token: str, request: Request, db: Session = Depends(get_db)):
    p = db.query(Proposal).filter(Proposal.token == token).first()
    if not p:
        raise HTTPException(404, "Not found")
    lead = p.lead
    now = datetime.utcnow()
    p.views += 1
    if not p.last_viewed_at or now - p.last_viewed_at > timedelta(hours=1):
        db.add(Activity(lead_id=lead.id, kind="note", content=f"👁 العميل فتح عرض التصميم (المرة {p.views})"))
    p.last_viewed_at = now
    if lead.status in ("new", "contacted"):
        lead.status = "demo_sent"
    db.commit()
    brief = json.loads(p.brief or "{}")
    photos = json.loads(p.photos or "[]")
    answers = json.loads(p.answers or "{}")
    return TEMPLATES.TemplateResponse(request, "proposal.html", {
        "brief": brief, "photos": photos, "lead": lead, "token": token, "answers": answers,
        "sender": _setting(db, "sender_name", settings.SENDER_NAME), "price": _setting(db, "default_price", str(settings.DEFAULT_PRICE_SAR)),
        "alt_palettes": designer.ALT_PALETTES, "wa_phone": _setting(db, "sender_phone", "") or lead.phone, "biz_phone": lead.phone,
    })


@router.post("/api/public/proposal/{token}/answers")
def public_answers(token: str, data: AnswersIn, db: Session = Depends(get_db)):
    """Called by the proposal page when the client taps their choices. No auth (token is the secret)."""
    p = db.query(Proposal).filter(Proposal.token == token).first()
    if not p:
        raise HTTPException(404, "Not found")
    lead = p.lead
    p.answers = data.model_dump_json()
    p.answered_at = datetime.utcnow()
    lines = [f"🎯 العميل أجاب على أسئلة العرض:", f"- النمط: {data.style or '-'}", f"- الأهم: {'، '.join(data.priorities) or '-'}", f"- التوقيت: {data.timing or '-'}"]
    if data.notes:
        lines.append(f"- ملاحظات: {data.notes}")
    if data.wants_start:
        lines.append("- ✅ ضغط «أبغى أبدأ»")
    db.add(Activity(lead_id=lead.id, kind="note", content="\n".join(lines)))
    if data.timing == "not_interested":
        lead.status = "lost" if lead.status not in ("won",) else lead.status
    elif data.wants_start or data.timing in ("this_week", "this_month"):
        if lead.status not in ("won", "lost", "do_not_contact"):
            lead.status = "negotiating"
            lead.priority = 1
            lead.next_follow_up = date.today()
    elif lead.status in ("new", "contacted", "demo_sent"):
        lead.status = "replied"
        lead.next_follow_up = date.today() + timedelta(days=1)
    db.commit()
    return {"ok": True}
