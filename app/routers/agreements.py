"""Service agreement pages with electronic acceptance."""
import secrets
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from ..auth import current_user
from ..common import TEMPLATES, setting, base_url, rate_limit, client_ip
from ..config import settings
from ..database import get_db
from ..models import Client, Agreement, Activity, User
from ..schemas import AgreementOut, AcceptIn
from ..services import terms

router = APIRouter(tags=["agreements"])


def _out(a: Agreement, base: str) -> AgreementOut:
    return AgreementOut(client_id=a.client_id, token=a.token, url=f"{base}/c/{a.token}", terms_version=a.terms_version, accepted_at=a.accepted_at, accepted_name=a.accepted_name, created_at=a.created_at)


def _ensure(db: Session, c: Client) -> Agreement:
    if not c.agreement:
        c.agreement = Agreement(client_id=c.id, token=secrets.token_urlsafe(18), terms_version=terms.version(db), terms_snapshot=terms.render(db, c))
        db.add(c.agreement); db.commit(); db.refresh(c)
    return c.agreement


@router.get("/api/clients/{cid}/agreement", response_model=AgreementOut)
def get_agreement(cid: int, request: Request, db: Session = Depends(get_db), _: User = Depends(current_user)):
    c = db.get(Client, cid)
    if not c:
        raise HTTPException(404, "Client not found")
    return _out(_ensure(db, c), base_url(request))


@router.post("/api/clients/{cid}/agreement/regenerate", response_model=AgreementOut)
def regenerate(cid: int, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Re-render the terms from the current Settings text (only while not yet accepted)."""
    c = db.get(Client, cid)
    if not c:
        raise HTTPException(404, "Client not found")
    a = _ensure(db, c)
    if a.accepted_at:
        raise HTTPException(409, "Already accepted — create a new client record for new terms")
    a.terms_version, a.terms_snapshot = terms.version(db), terms.render(db, c)
    db.commit(); db.refresh(a)
    return _out(a, base_url(request))


@router.get("/api/settings/terms-preview")
def terms_preview(db: Session = Depends(get_db), _: User = Depends(current_user)):
    return {"version": terms.version(db), "template": terms.template(db), "default": terms.DEFAULT_TERMS}


@router.get("/c/{token}", response_class=HTMLResponse, include_in_schema=False)
def agreement_page(token: str, request: Request, db: Session = Depends(get_db)):
    a = db.query(Agreement).filter(Agreement.token == token).first()
    if not a:
        raise HTTPException(404, "Not found")
    return TEMPLATES.TemplateResponse(request, "agreement.html", {"a": a, "client": a.client, "sender": setting(db, "sender_name", settings.SENDER_NAME), "sender_phone": setting(db, "sender_phone"), "cr": setting(db, "cr_number"), "vat_number": setting(db, "vat_number"), "state": request.query_params.get("state", "")})


@router.post("/api/public/agreement/{token}/accept", dependencies=[Depends(rate_limit("agreement_accept", 5))])
def accept(token: str, data: AcceptIn, request: Request, db: Session = Depends(get_db)):
    a = db.query(Agreement).filter(Agreement.token == token).first()
    if not a:
        raise HTTPException(404, "Not found")
    if a.accepted_at:
        return {"ok": True, "already": True, "accepted_at": a.accepted_at}
    a.accepted_at = datetime.utcnow()
    a.accepted_name = data.name.strip()
    a.accepted_ip = client_ip(request)
    a.accepted_ua = (request.headers.get("user-agent") or "")[:300]
    c = a.client
    if c.status == "onboarding":
        pass  # activation happens when the site is published / first invoice paid
    if c.lead_id:
        db.add(Activity(lead_id=c.lead_id, kind="note", content=f"✍️ وقّع العميل الاتفاقية (v{a.terms_version}) باسم «{a.accepted_name}» — {a.accepted_at:%Y-%m-%d %H:%M} UTC"))
    db.commit()
    return {"ok": True, "accepted_at": a.accepted_at}
