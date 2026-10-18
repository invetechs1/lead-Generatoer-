import os
import sys

os.environ["DATABASE_URL"] = "sqlite:///./test.db"
os.environ["ADMIN_PASSWORD"] = "TestPass123!"
os.environ["SCHEDULER_ENABLED"] = "0"
if os.path.exists("test.db") and "app.main" not in sys.modules:
    os.remove("test.db")

import pytest
from fastapi.testclient import TestClient

from app.common import limiter
from app.config import settings

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


def test_agreement_lifecycle(client, auth):
    limiter.reset()
    client.put("/api/settings", json={"sender_name": "Bassir IT", "sender_phone": "966555000111", "cr_number": "1010", "daily_send_cap": 100}, headers=auth)
    lead = client.post("/api/leads", json={"name": "مطعم الريف", "phone": "0544445555", "city": "الرياض", "sector": "مطاعم"}, headers=auth).json()
    c = client.post("/api/clients", json={"lead_id": lead["id"], "company": "مطعم الريف", "phone": "0544445555", "contact_name": "أبو سعد", "monthly_fee": 1000, "billing_day": 5}, headers=auth).json()
    assert c["agreement_token"] and c["agreement_accepted_at"] is None
    ag = client.get(f"/api/clients/{c['id']}/agreement", headers=auth).json()
    assert ag["url"].endswith("/c/" + c["agreement_token"]) and ag["terms_version"] == "1.0"

    html = client.get(f"/c/{c['agreement_token']}").text
    assert "مطعم الريف" in html and "أبو سعد" in html and "1,000" in html and "1,150" in html and "يوم 5" in html and "بانتظار التوقيع" in html and "Bassir IT" in html
    assert client.get("/c/nope").status_code == 404

    # closing template fills {contract} and {invoice} (rendered in-process so the daily send counter used by other tests is untouched)
    tpl = [t for t in client.get("/api/templates", headers=auth).json() if t["stage"] == "closing" and "إغلاق" in t["name"]][0]
    from app.database import SessionLocal
    from app.models import Lead
    from app.services import whatsapp
    with SessionLocal() as db:
        msg = whatsapp.render(tpl["body"], db.get(Lead, lead["id"]), base_url="https://x.test")
    assert "https://x.test/c/" + c["agreement_token"] in msg and "https://x.test/inv/" in msg

    # custom terms + regenerate before acceptance
    client.put("/api/settings", json={"terms_text": "شروط مخصصة لـ {company} بقيمة {total} ريال", "terms_version": "2.0"}, headers=auth)
    ag2 = client.post(f"/api/clients/{c['id']}/agreement/regenerate", headers=auth).json()
    assert ag2["terms_version"] == "2.0" and "شروط مخصصة لـ مطعم الريف بقيمة 1,150 ريال" in client.get(f"/c/{c['agreement_token']}").text
    assert client.get("/api/settings/terms-preview", headers=auth).json()["version"] == "2.0"

    # acceptance: validation, record, idempotent, blocks regenerate
    assert client.post(f"/api/public/agreement/{c['agreement_token']}/accept", json={"name": "x", "agree": True}).status_code == 422
    assert client.post(f"/api/public/agreement/{c['agreement_token']}/accept", json={"name": "فهد العتيبي", "agree": False}).status_code == 422
    r = client.post(f"/api/public/agreement/{c['agreement_token']}/accept", json={"name": "فهد العتيبي", "agree": True}, headers={"X-Forwarded-For": "198.51.100.7", "User-Agent": "TestBrowser/1.0"})
    assert r.status_code == 200 and r.json()["accepted_at"]
    again = client.post(f"/api/public/agreement/{c['agreement_token']}/accept", json={"name": "شخص آخر", "agree": True}).json()
    assert again.get("already") is True
    html = client.get(f"/c/{c['agreement_token']}").text
    assert "تم القبول إلكترونيًا" in html and "فهد العتيبي" in html and "شخص آخر" not in html
    cl = [x for x in client.get("/api/clients", headers=auth).json() if x["id"] == c["id"]][0]
    assert cl["agreement_accepted_at"]
    acts = client.get(f"/api/leads/{lead['id']}/activities", headers=auth).json()
    assert any("وقّع العميل الاتفاقية" in a["content"] and "فهد العتيبي" in a["content"] for a in acts)
    assert client.post(f"/api/clients/{c['id']}/agreement/regenerate", headers=auth).status_code == 409
    from app.database import SessionLocal
    from app.models import Agreement
    with SessionLocal() as db:
        a = db.query(Agreement).filter(Agreement.token == c["agreement_token"]).first()
        assert a.accepted_ip == "198.51.100.7" and a.accepted_ua == "TestBrowser/1.0" and "شروط مخصصة" in a.terms_snapshot
    limiter.reset()
