import io
import os
import sys
from datetime import date, timedelta

os.environ["DATABASE_URL"] = "sqlite:///./test.db"
os.environ["ADMIN_PASSWORD"] = "TestPass123!"
os.environ["SCHEDULER_ENABLED"] = "0"
if os.path.exists("test.db") and "app.main" not in sys.modules:
    os.remove("test.db")

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.services import scheduler

settings.UPLOAD_DIR = "./test_uploads"


@pytest.fixture(scope="module")
def client():
    from app.main import app
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def auth(client):
    r = client.post("/api/auth/login", json={"email": "admin@bassir.net", "password": "TestPass123!"})
    return {"Authorization": "Bearer " + r.json()["access_token"]}


def test_update_requests_flow(client, auth):
    client.put("/api/settings", json={"sender_phone": "966555000111", "daily_send_cap": 100}, headers=auth)
    lead = client.post("/api/leads", json={"name": "كافيه روح", "phone": "0588889999", "city": "الخبر", "sector": "مطاعم"}, headers=auth).json()
    c = client.post("/api/clients", json={"lead_id": lead["id"], "company": "كافيه روح", "phone": "0588889999"}, headers=auth).json()
    assert c["update_token"]
    assert client.get(f"/api/clients/{c['id']}/update-link", headers=auth).json()["url"].endswith("/u/" + c["update_token"])
    html = client.get(f"/u/{c['update_token']}").text
    assert "تحديث موقع كافيه روح" in html and "wa.me/966555000111" in html
    assert client.get("/u/nope").status_code == 404

    assert client.post(f"/api/public/update/{c['update_token']}", data={"text": "  "}).status_code == 400
    png = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c6360f8cfc00000030001010f5d4e5e0000000049454e44ae426082")
    r = client.post(f"/api/public/update/{c['update_token']}", data={"text": "ارفعوا سعر اللاتيه إلى 18 ريال"}, files=[("files", ("menu.png", io.BytesIO(png), "image/png")), ("files", ("x.exe", io.BytesIO(b"no"), "application/octet-stream"))])
    assert r.status_code == 200 and r.json()["files"] == 1
    us = client.get("/api/updates", headers=auth).json()
    assert len(us) == 1 and us[0]["company"] == "كافيه روح" and us[0]["photos"][0].startswith("/uploads/updates/")
    assert "قيد التنفيذ" in client.get(f"/u/{c['update_token']}").text
    acts = client.get(f"/api/leads/{lead['id']}/activities", headers=auth).json()
    assert any("طلب تحديث" in a["content"] for a in acts)

    # placeholder in monthly report
    tpl = [t for t in client.get("/api/templates", headers=auth).json() if "تقرير شهري" in t["name"]][0]
    msg = client.post(f"/api/leads/{lead['id']}/send", json={"template_id": tpl["id"], "mark_contacted": False}, headers=auth).json()["message"]
    assert "/u/" + c["update_token"] in msg

    done = client.post(f"/api/updates/{us[0]['id']}/done", headers=auth).json()
    assert done["status"] == "done" and done["done_at"]
    assert client.get("/api/updates?status=open", headers=auth).json() == []
    assert "تم التنفيذ" in client.get(f"/u/{c['update_token']}").text


def test_digest_and_daily_jobs(client, auth):
    # a due follow-up, a negotiating lead, an overdue-to-be invoice, a transfer notice
    l1 = client.post("/api/leads", json={"name": "عيادة سما", "phone": "0511112222", "city": "الرياض", "sector": "عيادات"}, headers=auth).json()
    client.patch(f"/api/leads/{l1['id']}", json={"status": "contacted", "next_follow_up": (date.today() - timedelta(days=1)).isoformat()}, headers=auth)
    l2 = client.post("/api/leads", json={"name": "مقاولات البناء", "phone": "0511113333", "city": "جدة", "sector": "مقاولات"}, headers=auth).json()
    client.patch(f"/api/leads/{l2['id']}", json={"status": "negotiating"}, headers=auth)
    old = client.post("/api/clients", json={"company": "عميل قديم", "phone": "0511114444", "start_date": "2026-01-15", "billing_day": 5}, headers=auth).json()
    inv = old["invoices"][0]
    assert inv["status"] == "unpaid" and inv["due_date"] == "2026-01-05"
    client.post(f"/api/public/invoice/{inv['token']}/transfer-notice")

    d = client.get("/api/digest", headers=auth).json()
    assert d["counts"]["due"] >= 1 and d["counts"]["negotiating"] >= 1 and d["counts"]["transfers"] == 1
    assert "عيادة سما" in d["text"] and "مقاولات البناء" in d["text"] and "عميل قديم" in d["text"] and d["wa_link"].startswith("https://wa.me/966555000111?text=")

    # run the daily jobs: overdue marking + digest stored; not day 1 → no billing
    from app.database import SessionLocal
    with SessionLocal() as db:
        out = scheduler.run_daily_jobs(db, today=date(2026, 3, 15))
        assert out["overdue"] >= 1 and out["issued"] == 0 and out["sent"] is False
        assert scheduler.due_now(db, now=__import__("datetime").datetime(2026, 3, 15, 9, 0, tzinfo=scheduler.RIYADH)) is False  # already ran today
        assert scheduler.due_now(db, now=__import__("datetime").datetime(2026, 3, 16, 7, 0, tzinfo=scheduler.RIYADH)) is False  # before DIGEST_HOUR
        assert scheduler.due_now(db, now=__import__("datetime").datetime(2026, 3, 16, 8, 5, tzinfo=scheduler.RIYADH)) is True
    cs = client.get("/api/clients", headers=auth).json()
    assert [c for c in cs if c["company"] == "عميل قديم"][0]["invoices"][0]["status"] == "overdue"
    assert client.get("/api/digest", headers=auth).json()["last_run"] == "2026-03-15"

    # day 1: issues this month's invoice for active clients only
    client.patch(f"/api/clients/{old['id']}", json={"status": "active"}, headers=auth)
    with SessionLocal() as db:
        out = scheduler.run_daily_jobs(db, today=date(2026, 4, 1))
        assert out["issued"] >= 1
        assert scheduler.run_daily_jobs(db, today=date(2026, 4, 1))["issued"] == 0  # idempotent
    cs = client.get("/api/clients", headers=auth).json()
    assert any(i["period"] == "2026-04" for i in [c for c in cs if c["company"] == "عميل قديم"][0]["invoices"])
    assert client.post("/api/jobs/run", headers=auth).status_code == 200
