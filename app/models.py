from datetime import datetime, date
from sqlalchemy import String, Integer, Text, DateTime, Date, ForeignKey, Boolean, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def now() -> datetime:
    return datetime.utcnow()


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(190), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="agent")  # admin | agent
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


LEAD_STATUSES = ["new", "contacted", "replied", "demo_sent", "negotiating", "won", "lost", "do_not_contact"]


class Lead(Base):
    __tablename__ = "leads"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    phone: Mapped[str] = mapped_column(String(20), unique=True, index=True)  # E.164 digits only, e.g. 9665xxxxxxxx
    city: Mapped[str] = mapped_column(String(80), default="", index=True)
    sector: Mapped[str] = mapped_column(String(80), default="", index=True)
    instagram: Mapped[str] = mapped_column(String(200), default="")
    website: Mapped[str] = mapped_column(String(300), default="")
    maps_url: Mapped[str] = mapped_column(String(400), default="")
    rating: Mapped[float | None] = mapped_column(Numeric(3, 2), nullable=True)
    reviews: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(String(40), default="manual")  # manual | csv | places
    status: Mapped[str] = mapped_column(String(30), default="new", index=True)
    priority: Mapped[int] = mapped_column(Integer, default=2)  # 1 high, 2 normal, 3 low
    notes: Mapped[str] = mapped_column(Text, default="")
    next_follow_up: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    last_contacted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)

    owner = relationship("User")
    activities = relationship("Activity", back_populates="lead", cascade="all, delete-orphan")
    client = relationship("Client", back_populates="lead", uselist=False)


class Template(Base):
    __tablename__ = "templates"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    stage: Mapped[str] = mapped_column(String(30), default="first")  # first | follow_up | objection | closing
    sector: Mapped[str] = mapped_column(String(80), default="")  # "" = any
    body: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Activity(Base):
    __tablename__ = "activities"
    id: Mapped[int] = mapped_column(primary_key=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(30))  # whatsapp | call | note | status | email
    channel: Mapped[str] = mapped_column(String(30), default="")  # wa_link | wa_api
    template_id: Mapped[int | None] = mapped_column(ForeignKey("templates.id"), nullable=True)
    content: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, index=True)

    lead = relationship("Lead", back_populates="activities")
    user = relationship("User")


class Client(Base):
    __tablename__ = "clients"
    id: Mapped[int] = mapped_column(primary_key=True)
    lead_id: Mapped[int | None] = mapped_column(ForeignKey("leads.id"), nullable=True, unique=True)
    company: Mapped[str] = mapped_column(String(200))
    contact_name: Mapped[str] = mapped_column(String(120), default="")
    phone: Mapped[str] = mapped_column(String(20))
    email: Mapped[str] = mapped_column(String(190), default="")
    domain: Mapped[str] = mapped_column(String(200), default="")
    site_url: Mapped[str] = mapped_column(String(300), default="")
    monthly_fee: Mapped[int] = mapped_column(Integer, default=1000)
    start_date: Mapped[date] = mapped_column(Date, default=date.today)
    billing_day: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(20), default="active")  # onboarding | active | paused | cancelled
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    lead = relationship("Lead", back_populates="client")
    invoices = relationship("Invoice", back_populates="client", cascade="all, delete-orphan")


class Invoice(Base):
    __tablename__ = "invoices"
    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    number: Mapped[str] = mapped_column(String(40), unique=True)
    period: Mapped[str] = mapped_column(String(7))  # YYYY-MM
    amount: Mapped[int] = mapped_column(Integer)
    vat: Mapped[int] = mapped_column(Integer, default=0)
    due_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="unpaid")  # unpaid | paid | overdue | void
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    client = relationship("Client", back_populates="invoices")


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")
