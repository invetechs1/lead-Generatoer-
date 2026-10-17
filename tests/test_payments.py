import os
import sys

os.environ["DATABASE_URL"] = "sqlite:///./test.db"
os.environ["ADMIN_PASSWORD"] = "TestPass123!"
if os.path.exists("test.db") and "app.main" not in sys.modules:
    os.remove("test.db")

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.services import payments

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


def test_invoice_page_bank_transfer_and_reminder(client, auth):
    client.put("/api/settings", json={"bank_name": "الراجحي", "iban": "SA0380000000608010167519", "account_name": "Bassir IT", "vat_number": "300000000000003", "sender_phone": "966555000111", "daily_send_cap": 100}, headers=auth)
    lead = client.post("/api/leads", json={"name": "عيادة الأمل", "phone": "0566667777", "city": "الرياض", "sector": "عيادات"}, headers=auth).json()
    c = client.post("/api/clients", json={"lead_id": lead["id"], "company": "عيادة الأمل", "phone": "0566667777"}, headers=auth).json()
    inv = c["invoices"][0]
    assert inv["token"] and inv["amount"] == 1000 and inv["vat"] == 150
    link = client.get(f"/api/clients/invoices/{inv['id']}/link", headers=auth).json()["url"]
    assert link.endswith("/inv/" + inv["token"])

    html = client.get(f"/inv/{inv['token']}").text
    assert inv["number"] in html and "1,150" in html and "SA0380000000608010167519" in html and "300000000000003" in html
    assert "Moyasar.init" not in html  # no keys → bank transfer only
    assert client.get("/inv/nope").status_code == 404

    # {invoice} placeholder + seeded reminder template
    tpl = [t for t in client.get("/api/templates", headers=auth).json() if "تذكير فاتورة" in t["name"]][0]
    msg = client.post(f"/api/leads/{lead['id']}/send", json={"template_id": tpl["id"], "mark_contacted": False}, headers=auth).json()["message"]
    assert "/inv/" + inv["token"] in msg

    # client says "I transferred" → flagged + timeline note; salesperson confirms
    assert client.post(f"/api/public/invoice/{inv['token']}/transfer-notice").status_code == 200
    c2 = client.get("/api/clients", headers=auth).json()[0]
    assert c2["invoices"][0]["transfer_claimed_at"]
    acts = client.get(f"/api/leads/{lead['id']}/activities", headers=auth).json()
    assert any("أبلغ بتحويل" in a["content"] for a in acts)
    paid = client.post(f"/api/clients/invoices/{inv['id']}/pay", headers=auth).json()
    assert paid["status"] == "paid" and paid["paid_via"] == "manual"
    assert "تم استلام الدفع" in client.get(f"/inv/{inv['token']}").text
    assert client.post(f"/api/public/invoice/{inv['token']}/transfer-notice").status_code == 404  # already paid


def test_moyasar_callback_and_webhook(client, auth, monkeypatch):
    monkeypatch.setattr(settings, "MOYASAR_PUBLISHABLE_KEY", "pk_test_x")
    monkeypatch.setattr(settings, "MOYASAR_SECRET_KEY", "sk_test_x")
    monkeypatch.setattr(settings, "MOYASAR_WEBHOOK_SECRET", "whsec")
    lead = client.post("/api/leads", json={"name": "مطعم الزاد", "phone": "0577778888", "city": "جدة", "sector": "مطاعم"}, headers=auth).json()
    c = client.post("/api/clients", json={"lead_id": lead["id"], "company": "مطعم الزاد", "phone": "0577778888"}, headers=auth).json()
    inv = c["invoices"][0]
    html = client.get(f"/inv/{inv['token']}").text
    assert "Moyasar.init" in html and "amount:115000" in html and f'invoice_token:"{inv["token"]}"' in html and "/callback" in html

    calls = {}
    async def fake_fetch(pid):
        calls["id"] = pid
        return calls["payment"]
    monkeypatch.setattr(payments, "fetch_payment", fake_fetch)

    # wrong amount → not applied, warning logged
    calls["payment"] = {"id": "pay_1", "status": "paid", "amount": 100000, "currency": "SAR", "metadata": {"invoice_token": inv["token"]}, "source": {"type": "creditcard"}}
    r = client.get(f"/inv/{inv['token']}/callback?id=pay_1&status=paid")
    assert r.status_code == 200 and "لم تكتمل" in r.text
    assert client.get("/api/clients", headers=auth).json()[0]["invoices"][0]["status"] == "unpaid"
    # failed status from gateway
    calls["payment"] = {"id": "pay_2", "status": "failed", "amount": 115000, "currency": "SAR", "metadata": {}}
    assert "Declined" in client.get(f"/inv/{inv['token']}/callback?id=pay_2&status=failed&message=Declined").text
    # correct payment → paid, idempotent on repeat
    calls["payment"] = {"id": "pay_3", "status": "paid", "amount": 115000, "currency": "SAR", "metadata": {"invoice_token": inv["token"]}, "source": {"type": "applepay"}}
    r = client.get(f"/inv/{inv['token']}/callback?id=pay_3&status=paid")
    assert "تم استلام الدفع" in r.text and calls["id"] == "pay_3"
    i2 = client.get("/api/clients", headers=auth).json()[0]["invoices"][0]
    assert i2["status"] == "paid" and i2["paid_via"] == "moyasar"
    acts = client.get(f"/api/leads/{lead['id']}/activities", headers=auth).json()
    assert sum("دُفعت الفاتورة" in a["content"] for a in acts) == 1 and any("غير مطابقة" in a["content"] for a in acts)
    assert "تم استلام الدفع" in client.get(f"/inv/{inv['token']}/callback?id=pay_3&status=paid").text

    # webhook on a fresh invoice (next month's billing)
    client.patch(f"/api/clients/{c['id']}", json={"status": "active"}, headers=auth)
    from datetime import date
    period = date.today().strftime("%Y-%m")
    created = client.post("/api/clients/run-billing", headers=auth).json()
    inv2 = [i for i in created if i["client_id"] == c["id"]]
    if not inv2:  # first invoice already covers this period → issue via a second client instead
        c3 = client.post("/api/clients", json={"company": "x", "phone": "0577770000", "start_date": f"{period}-01"}, headers=auth).json()
        inv2 = [c3["invoices"][0]]
    tok = inv2[0]["token"]
    assert client.post("/api/payments/moyasar/webhook", json={"type": "payment_paid", "secret_token": "wrong", "data": {"id": "pay_9", "metadata": {"invoice_token": tok}}}).status_code == 403
    calls["payment"] = {"id": "pay_9", "status": "paid", "amount": 115000, "currency": "SAR", "metadata": {"invoice_token": tok}}
    r = client.post("/api/payments/moyasar/webhook", json={"type": "payment_paid", "secret_token": "whsec", "data": {"id": "pay_9", "metadata": {"invoice_token": tok}}})
    assert r.json()["ok"] is True
    assert "تم استلام الدفع" in client.get(f"/inv/{tok}").text
    assert client.post("/api/payments/moyasar/webhook", json={"type": "payment_failed", "secret_token": "whsec", "data": {}}).json()["ignored"] == "payment_failed"
