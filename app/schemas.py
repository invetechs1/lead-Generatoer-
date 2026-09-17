import re
from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel, Field, field_validator, EmailStr

from .models import LEAD_STATUSES


def normalize_phone(raw: str) -> str:
    d = re.sub(r"\D", "", raw or "")
    if d.startswith("00"):
        d = d[2:]
    if d.startswith("05") and len(d) == 10:
        d = "966" + d[1:]
    elif d.startswith("5") and len(d) == 9:
        d = "966" + d
    if not (10 <= len(d) <= 15):
        raise ValueError("invalid phone number")
    return d


# ---- auth ----
class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "UserOut"


class UserIn(BaseModel):
    email: EmailStr
    name: str = Field(min_length=2, max_length=120)
    password: str = Field(min_length=8, max_length=128)
    role: str = Field(default="agent", pattern="^(admin|agent)$")


class UserOut(BaseModel):
    id: int
    email: str
    name: str
    role: str
    is_active: bool
    model_config = {"from_attributes": True}


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


# ---- leads ----
class LeadIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    phone: str
    city: str = ""
    sector: str = ""
    instagram: str = ""
    website: str = ""
    maps_url: str = ""
    rating: Optional[float] = None
    reviews: Optional[int] = None
    source: str = "manual"
    priority: int = Field(default=2, ge=1, le=3)
    notes: str = ""
    next_follow_up: Optional[date] = None

    @field_validator("phone")
    @classmethod
    def _phone(cls, v: str) -> str:
        return normalize_phone(v)


class LeadUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=200)
    city: Optional[str] = None
    sector: Optional[str] = None
    instagram: Optional[str] = None
    website: Optional[str] = None
    maps_url: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[int] = Field(default=None, ge=1, le=3)
    notes: Optional[str] = None
    next_follow_up: Optional[date] = None
    owner_id: Optional[int] = None

    @field_validator("status")
    @classmethod
    def _status(cls, v):
        if v is not None and v not in LEAD_STATUSES:
            raise ValueError(f"status must be one of {LEAD_STATUSES}")
        return v


class LeadOut(BaseModel):
    id: int
    name: str
    phone: str
    city: str
    sector: str
    instagram: str
    website: str
    maps_url: str
    rating: Optional[float]
    reviews: Optional[int]
    source: str
    site_score: Optional[int] = None
    site_issues: str = ""
    status: str
    priority: int
    notes: str
    next_follow_up: Optional[date]
    last_contacted_at: Optional[datetime]
    owner_id: Optional[int]
    created_at: datetime
    model_config = {"from_attributes": True}


class LeadPage(BaseModel):
    items: list[LeadOut]
    total: int
    page: int
    size: int


class ImportResult(BaseModel):
    added: int
    skipped_duplicates: int
    skipped_invalid: int
    errors: list[str] = []


# ---- templates ----
class TemplateIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    stage: str = Field(default="first", pattern="^(first|follow_up|objection|closing)$")
    sector: str = ""
    body: str = Field(min_length=1, max_length=4000)
    is_active: bool = True


class TemplateOut(TemplateIn):
    id: int
    model_config = {"from_attributes": True}


# ---- activities / messaging ----
class SendIn(BaseModel):
    template_id: Optional[int] = None
    body: Optional[str] = Field(default=None, max_length=4000)  # custom text overrides template
    mark_contacted: bool = True
    follow_up_in_days: int = Field(default=2, ge=0, le=60)


class AuditOut(BaseModel):
    lead_id: int
    url: str
    final_url: str
    ok: bool
    status: int
    https: bool
    ttfb_ms: int
    mobile_ready: bool
    title: str
    has_arabic: bool
    has_whatsapp: bool
    score: int
    issues: list[str]


class SendOut(BaseModel):
    lead_id: int
    phone: str
    message: str
    wa_link: str
    channel: str  # wa_link | wa_api
    sent_today: int
    daily_cap: int


class ActivityIn(BaseModel):
    kind: str = Field(pattern="^(call|note|email|whatsapp)$")
    content: str = Field(default="", max_length=4000)


class ActivityOut(BaseModel):
    id: int
    lead_id: int
    user_id: Optional[int]
    kind: str
    channel: str
    content: str
    created_at: datetime
    model_config = {"from_attributes": True}


# ---- clients / invoices ----
class ClientIn(BaseModel):
    lead_id: Optional[int] = None
    company: str = Field(min_length=1, max_length=200)
    contact_name: str = ""
    phone: str
    email: str = ""
    domain: str = ""
    site_url: str = ""
    monthly_fee: int = Field(default=1000, ge=0)
    start_date: date = Field(default_factory=date.today)
    billing_day: int = Field(default=1, ge=1, le=28)
    status: str = Field(default="onboarding", pattern="^(onboarding|active|paused|cancelled)$")
    notes: str = ""

    @field_validator("phone")
    @classmethod
    def _phone(cls, v: str) -> str:
        return normalize_phone(v)


class ClientUpdate(BaseModel):
    company: Optional[str] = None
    contact_name: Optional[str] = None
    email: Optional[str] = None
    domain: Optional[str] = None
    site_url: Optional[str] = None
    monthly_fee: Optional[int] = Field(default=None, ge=0)
    billing_day: Optional[int] = Field(default=None, ge=1, le=28)
    status: Optional[str] = Field(default=None, pattern="^(onboarding|active|paused|cancelled)$")
    notes: Optional[str] = None


class InvoiceOut(BaseModel):
    id: int
    client_id: int
    number: str
    period: str
    amount: int
    vat: int
    due_date: date
    status: str
    paid_at: Optional[datetime]
    model_config = {"from_attributes": True}


class ClientOut(BaseModel):
    id: int
    lead_id: Optional[int]
    company: str
    contact_name: str
    phone: str
    email: str
    domain: str
    site_url: str
    monthly_fee: int
    start_date: date
    billing_day: int
    status: str
    notes: str
    invoices: list[InvoiceOut] = []
    model_config = {"from_attributes": True}


# ---- discover ----
class DiscoverIn(BaseModel):
    query: str = Field(min_length=2, max_length=120)  # e.g. "مطاعم" or "dental clinic"
    city: str = Field(min_length=2, max_length=80)
    max_results: int = Field(default=20, ge=1, le=60)
    only_without_website: bool = True
    save: bool = False


class DiscoverItem(BaseModel):
    name: str
    phone: str
    city: str
    website: str
    maps_url: str
    rating: Optional[float]
    reviews: Optional[int]
    already_exists: bool


TokenOut.model_rebuild()
