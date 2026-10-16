"""Morning digest + client self-service content updates."""
import json
import secrets
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..auth import current_user, admin_only
from ..config import settings
from ..database import get_db
from ..models import Client, UpdateRequest, Activity, Setting, User
from ..schemas import UpdateOut
from ..services import digest, scheduler

router = APIRouter(tags=["updates"])
TEMPLATES = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))
ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp", ".pdf"}


def _setting(db: Session, key: str, default: str = "") -> str:
    s = db.get(Setting, key)
    return s.value if s and s.value else default


def _base(request: Request) -> str:
    return (settings.PUBLIC_BASE_URL or str(request.base_url)).rstrip("/")


# ---------------- digest ----------------

@router.get("/api/digest")
def get_digest(request: Request, db: Session = Depends(get_db), _: User = Depends(current_user)):
    d = digest.build(db, _base(request))
    phone = _setting(db, "sender_phone")
    d["wa_link"] = f"https://wa.me/{phone}?text={quote(d['text'])}" if phone else ""
    d["last_run"] = _setting(db, "jobs_last_run")
    d["scheduler"] = settings.SCHEDULER_ENABLED
    return d


@router.post("/api/jobs/run")
def run_jobs_now(request: Request, db: Session = Depends(get_db), _: User = Depends(admin_only)):
    """Run the daily jobs immediately (overdue marking, day-1 billing, digest)."""
    return scheduler.run_daily_jobs(db, base_url=_base(request))


# ---------------- client self-service updates ----------------

def _out(u: UpdateRequest) -> UpdateOut:
    return UpdateOut(id=u.id, client_id=u.client_id, company=u.client.company, text=u.text, photos=json.loads(u.photos or "[]"), status=u.status, created_at=u.created_at, done_at=u.done_at)


@router.get("/u/{token}", response_class=HTMLResponse, include_in_schema=False)
def update_page(token: str, request: Request, db: Session = Depends(get_db)):
    c = db.query(Client).filter(Client.update_token == token).first()
    if not c:
        raise HTTPException(404, "Not found")
    recent = db.query(UpdateRequest).filter(UpdateRequest.client_id == c.id).order_by(UpdateRequest.created_at.desc()).limit(5).all()
    return TEMPLATES.TemplateResponse(request, "update.html", {"client": c, "recent": recent, "sender": _setting(db, "sender_name", settings.SENDER_NAME), "sender_phone": _setting(db, "sender_phone"), "sent": request.query_params.get("sent") == "1"})


@router.post("/api/public/update/{token}")
async def submit_update(token: str, text: str = Form(""), files: list[UploadFile] = File(default=[]), db: Session = Depends(get_db)):
    c = db.query(Client).filter(Client.update_token == token).first()
    if not c:
        raise HTTPException(404, "Not found")
    text = (text or "").strip()[:4000]
    saved: list[str] = []
    if files:
        d = Path(settings.UPLOAD_DIR) / "updates" / str(c.id)
        d.mkdir(parents=True, exist_ok=True)
        for f in files[:10]:
            ext = Path(f.filename or "").suffix.lower()
            data = await f.read()
            if ext not in ALLOWED_EXT or not data or len(data) > 10 * 1024 * 1024:
                continue
            name = f"{secrets.token_hex(4)}{ext}"
            (d / name).write_bytes(data)
            saved.append(f"/uploads/updates/{c.id}/{name}")
    if not text and not saved:
        raise HTTPException(400, "Nothing to submit")
    u = UpdateRequest(client_id=c.id, text=text, photos=json.dumps(saved))
    db.add(u)
    if c.lead_id:
        db.add(Activity(lead_id=c.lead_id, kind="note", content=f"✏️ طلب تحديث من العميل: {text[:200] or '(صور فقط)'}" + (f" + {len(saved)} ملف" if saved else "")))
    db.commit()
    return {"ok": True, "id": u.id, "files": len(saved)}


@router.get("/api/updates", response_model=list[UpdateOut])
def list_updates(status: str = "open", db: Session = Depends(get_db), _: User = Depends(current_user)):
    q = db.query(UpdateRequest)
    if status in ("open", "done"):
        q = q.filter(UpdateRequest.status == status)
    return [_out(u) for u in q.order_by(UpdateRequest.created_at.desc()).limit(200)]


@router.post("/api/updates/{uid}/done", response_model=UpdateOut)
def mark_done(uid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    u = db.get(UpdateRequest, uid)
    if not u:
        raise HTTPException(404, "Not found")
    u.status = "done"; u.done_at = datetime.utcnow()
    if u.client.lead_id:
        db.add(Activity(lead_id=u.client.lead_id, user_id=user.id, kind="note", content=f"✅ نُفّذ طلب التحديث #{u.id}"))
    db.commit(); db.refresh(u)
    return _out(u)


@router.get("/api/clients/{cid}/update-link")
def client_update_link(cid: int, request: Request, db: Session = Depends(get_db), _: User = Depends(current_user)):
    c = db.get(Client, cid)
    if not c:
        raise HTTPException(404, "Client not found")
    if not c.update_token:
        c.update_token = secrets.token_urlsafe(18); db.commit()
    return {"url": f"{_base(request)}/u/{c.update_token}"}
