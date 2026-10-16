import secrets
from datetime import date, datetime
from calendar import monthrange

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth import current_user, admin_only
from ..database import get_db
from ..models import Client, Invoice, Lead, User, Activity
from ..schemas import ClientIn, ClientUpdate, ClientOut, InvoiceOut

router = APIRouter(prefix="/api/clients", tags=["clients"])
VAT_RATE = 0.15


def _next_number(db: Session) -> str:
    n = db.query(Invoice).count() + 1
    return f"BSR-{date.today().year}-{n:05d}"


def _issue(db: Session, c: Client, period: str) -> Invoice:
    y, m = int(period[:4]), int(period[5:7])
    due = date(y, m, min(c.billing_day, monthrange(y, m)[1]))
    inv = Invoice(client_id=c.id, number=_next_number(db), period=period, amount=c.monthly_fee, vat=round(c.monthly_fee * VAT_RATE), due_date=due, token=secrets.token_urlsafe(18))
    db.add(inv); db.flush()
    return inv


@router.get("", response_model=list[ClientOut])
def list_clients(db: Session = Depends(get_db), _: User = Depends(current_user)):
    return db.query(Client).order_by(Client.id.desc()).all()


@router.post("", response_model=ClientOut, status_code=201)
def create(data: ClientIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if data.lead_id:
        lead = db.get(Lead, data.lead_id)
        if not lead:
            raise HTTPException(404, "Lead not found")
        if lead.client:
            raise HTTPException(409, "Lead already converted")
        lead.status = "won"
        db.add(Activity(lead_id=lead.id, user_id=user.id, kind="status", content="converted to client"))
    c = Client(**data.model_dump(), update_token=secrets.token_urlsafe(18)); db.add(c); db.flush()
    _issue(db, c, c.start_date.strftime("%Y-%m"))
    db.commit(); db.refresh(c)
    return c


@router.patch("/{cid}", response_model=ClientOut)
def update(cid: int, data: ClientUpdate, db: Session = Depends(get_db), _: User = Depends(current_user)):
    c = db.get(Client, cid)
    if not c:
        raise HTTPException(404, "Client not found")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(c, k, v)
    db.commit(); db.refresh(c)
    return c


@router.post("/run-billing", response_model=list[InvoiceOut])
def run_billing(db: Session = Depends(get_db), _: User = Depends(admin_only)):
    """Issue this month's invoice for every active client that doesn't have one yet. Safe to run repeatedly (idempotent)."""
    period = date.today().strftime("%Y-%m")
    created = []
    for c in db.query(Client).filter(Client.status == "active"):
        if not any(i.period == period for i in c.invoices):
            created.append(_issue(db, c, period))
    # mark overdue
    for inv in db.query(Invoice).filter(Invoice.status == "unpaid", Invoice.due_date < date.today()):
        inv.status = "overdue"
    db.commit()
    return created


@router.post("/invoices/{iid}/pay", response_model=InvoiceOut)
def pay(iid: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    inv = db.get(Invoice, iid)
    if not inv:
        raise HTTPException(404, "Invoice not found")
    inv.status = "paid"; inv.paid_at = datetime.utcnow(); inv.paid_via = inv.paid_via or "manual"
    if inv.client.status == "onboarding":
        inv.client.status = "active"
    db.commit(); db.refresh(inv)
    return inv


@router.post("/invoices/{iid}/void", response_model=InvoiceOut)
def void(iid: int, db: Session = Depends(get_db), _: User = Depends(admin_only)):
    inv = db.get(Invoice, iid)
    if not inv:
        raise HTTPException(404, "Invoice not found")
    inv.status = "void"; db.commit(); db.refresh(inv)
    return inv
