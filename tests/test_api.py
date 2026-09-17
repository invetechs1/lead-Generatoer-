import os, io
os.environ["DATABASE_URL"] = "sqlite:///./test.db"
os.environ["ADMIN_PASSWORD"] = "TestPass123!"
if os.path.exists("test.db"):
    os.remove("test.db")

import pytest
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def auth(client):
    r = client.post("/api/auth/login", json={"email": "admin@bassir.net", "password": "TestPass123!"})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["access_token"]}


def test_health(client):
    assert client.get("/api/health").json()["ok"] is True


def test_requires_auth(client):
    assert client.get("/api/leads").status_code == 401


def test_bad_login(client):
    assert client.post("/api/auth/login", json={"email": "admin@bassir.net", "password": "wrong-pass"}).status_code == 401


def test_templates_seeded(client, auth):
    t = client.get("/api/templates", headers=auth).json()
    assert len(t) >= 6


def test_lead_crud_and_phone_normalization(client, auth):
    r = client.post("/api/leads", json={"name": "مطعم البيت", "phone": "055 123 4567", "city": "الرياض", "sector": "مطاعم"}, headers=auth)
    assert r.status_code == 201, r.text
    lead = r.json()
    assert lead["phone"] == "966551234567"
    # duplicate phone rejected
    assert client.post("/api/leads", json={"name": "x", "phone": "+966551234567"}, headers=auth).status_code == 409
    # update status
    r = client.patch(f"/api/leads/{lead['id']}", json={"status": "replied"}, headers=auth)
    assert r.json()["status"] == "replied"
    assert client.patch(f"/api/leads/{lead['id']}", json={"status": "bogus"}, headers=auth).status_code == 422


def test_csv_import(client, auth):
    csv = "الاسم,الجوال,المدينة,النشاط\nعيادة نور,0559876543,جدة,عيادات\nمكرر,0551234567,الرياض,مطاعم\nسيء,123,x,y\n"
    r = client.post("/api/leads/import", files={"file": ("leads.csv", io.BytesIO(csv.encode("utf-8")), "text/csv")}, headers=auth)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["added"] == 1 and d["skipped_duplicates"] == 1 and d["skipped_invalid"] == 1


def test_send_renders_template_and_logs(client, auth):
    lead = client.get("/api/leads?q=نور", headers=auth).json()["items"][0]
    tpl = [t for t in client.get("/api/templates", headers=auth).json() if t["stage"] == "first"][0]
    r = client.post(f"/api/leads/{lead['id']}/send", json={"template_id": tpl["id"], "follow_up_in_days": 2}, headers=auth)
    assert r.status_code == 200, r.text
    d = r.json()
    assert "عيادة نور" in d["message"] and d["wa_link"].startswith("https://wa.me/966559876543?text=")
    assert d["channel"] == "wa_link" and d["sent_today"] == 1
    lead2 = client.get(f"/api/leads/{lead['id']}", headers=auth).json()
    assert lead2["status"] == "contacted" and lead2["next_follow_up"] is not None
    acts = client.get(f"/api/leads/{lead['id']}/activities", headers=auth).json()
    assert acts[0]["kind"] == "whatsapp"


def test_daily_cap(client, auth):
    client.put("/api/settings", json={"daily_send_cap": 1}, headers=auth)
    lead = client.get("/api/leads?q=البيت", headers=auth).json()["items"][0]
    r = client.post(f"/api/leads/{lead['id']}/send", json={"body": "hi {name}"}, headers=auth)
    assert r.status_code == 429
    client.put("/api/settings", json={"daily_send_cap": 50}, headers=auth)


def test_convert_and_billing(client, auth):
    lead = client.get("/api/leads?q=البيت", headers=auth).json()["items"][0]
    r = client.post("/api/clients", json={"lead_id": lead["id"], "company": lead["name"], "phone": lead["phone"], "monthly_fee": 1000, "status": "active"}, headers=auth)
    assert r.status_code == 201, r.text
    c = r.json()
    assert len(c["invoices"]) == 1 and c["invoices"][0]["amount"] == 1000 and c["invoices"][0]["vat"] == 150
    assert client.get(f"/api/leads/{lead['id']}", headers=auth).json()["status"] == "won"
    # idempotent billing
    assert client.post("/api/clients/run-billing", headers=auth).json() == []
    inv = c["invoices"][0]
    assert client.post(f"/api/clients/invoices/{inv['id']}/pay", headers=auth).json()["status"] == "paid"
    dash = client.get("/api/dashboard", headers=auth).json()
    assert dash["mrr"] == 1000 and dash["clients_active"] == 1


def test_agent_cannot_admin(client, auth):
    client.post("/api/auth/users", json={"name": "Agent One", "email": "agent@bassir.net", "password": "AgentPass123", "role": "agent"}, headers=auth)
    tok = client.post("/api/auth/login", json={"email": "agent@bassir.net", "password": "AgentPass123"}).json()["access_token"]
    h = {"Authorization": "Bearer " + tok}
    assert client.get("/api/leads", headers=h).status_code == 200
    assert client.post("/api/templates", json={"name": "x", "body": "y"}, headers=h).status_code == 403
    assert client.put("/api/settings", json={"daily_send_cap": 99}, headers=h).status_code == 403


def test_spa_served(client):
    r = client.get("/")
    assert r.status_code == 200 and "Bassir" in r.text
    assert r.headers["x-frame-options"] == "DENY"
