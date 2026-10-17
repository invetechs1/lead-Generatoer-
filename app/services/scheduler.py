"""Tiny in-process scheduler (no cron, no Celery): a daemon thread wakes every few minutes and runs the daily jobs
once per day after DIGEST_HOUR Riyadh time. Idempotent: the last run date is stored in the settings table."""
from __future__ import annotations

import asyncio
import threading
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ..config import settings
from ..models import Setting, Invoice, Client

RIYADH = timezone(timedelta(hours=3))
_stop = threading.Event()


def _get(db: Session, key: str) -> str:
    s = db.get(Setting, key)
    return s.value if s else ""


def _set(db: Session, key: str, value: str) -> None:
    row = db.get(Setting, key) or Setting(key=key)
    row.value = value
    db.add(row)


def run_daily_jobs(db: Session, today: date | None = None, base_url: str = "") -> dict:
    """Mark overdue invoices, issue this month's invoices on day 1, build + store the digest, optionally send it."""
    from ..routers.clients import _issue
    from . import digest, whatsapp

    today = today or datetime.now(RIYADH).date()
    out = {"overdue": 0, "issued": 0, "sent": False}
    for inv in db.query(Invoice).filter(Invoice.status == "unpaid", Invoice.due_date < today):
        inv.status = "overdue"; out["overdue"] += 1
    if today.day == 1:
        period = today.strftime("%Y-%m")
        for c in db.query(Client).filter(Client.status == "active"):
            if not any(i.period == period for i in c.invoices):
                _issue(db, c, period); out["issued"] += 1
    db.flush()
    d = digest.build(db, base_url or settings.PUBLIC_BASE_URL)
    _set(db, "digest_text", d["text"])
    _set(db, "digest_date", today.isoformat())
    _set(db, "jobs_last_run", today.isoformat())
    phone = _get(db, "sender_phone")
    if phone and whatsapp.api_configured():
        try:
            asyncio.run(whatsapp.send_via_api(phone, d["text"]))
            out["sent"] = True
        except Exception as e:  # digest still visible in the dashboard
            out["error"] = f"{type(e).__name__}"
    db.commit()
    return out


def due_now(db: Session, now: datetime | None = None) -> bool:
    now = now or datetime.now(RIYADH)
    return now.hour >= settings.DIGEST_HOUR and _get(db, "jobs_last_run") != now.date().isoformat()


def _loop(session_factory, interval: int) -> None:
    while not _stop.is_set():
        try:
            with session_factory() as db:
                if due_now(db):
                    run_daily_jobs(db)
        except Exception as e:  # never kill the thread
            print("scheduler error:", type(e).__name__, e)
        _stop.wait(interval)


def start(session_factory, interval: int = 300) -> threading.Thread:
    _stop.clear()
    t = threading.Thread(target=_loop, args=(session_factory, interval), name="bassir-scheduler", daemon=True)
    t.start()
    return t


def stop() -> None:
    _stop.set()
