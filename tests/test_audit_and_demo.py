import io
import os
import sys

os.environ["DATABASE_URL"] = "sqlite:///./test.db"
os.environ["ADMIN_PASSWORD"] = "TestPass123!"
if os.path.exists("test.db") and "app.main" not in sys.modules:  # fresh DB when this module runs first / alone
    os.remove("test.db")

import pytest
from fastapi.testclient import TestClient

from app.services import site_audit, whatsapp
from app.services.site_audit import Audit, grade


def test_grade_unreachable_site_scores_low():
    a = grade(Audit(url="https://x.example", ok=False), "")
    assert a.score == 60 and any("لا يفتح" in i for i in a.issues)


def test_grade_good_site_scores_high():
    html = "<html><head><title>مطعم البيت — الرياض</title><meta name='viewport' content='width=device-width'></head><body>" + "محتوى عربي طويل " * 200 + "<a href='https://wa.me/966500000000'>واتساب</a></body></html>"
    a = Audit(url="https://good.example", ok=True, status=200, https=True, ttfb_ms=400, mobile_ready=True, title="مطعم البيت — الرياض", has_arabic=True, has_whatsapp=True, size=len(html))
    assert grade(a, html).score == 100 and a.issues == []


def test_grade_weak_site_lists_reasons():
    html = "<html><head><title>Home</title></head><body>coming soon</body></html>"
    a = Audit(url="http://weak.example", ok=True, status=200, https=False, ttfb_ms=5000, mobile_ready=False, title="Home", has_arabic=False, has_whatsapp=False, size=len(html))
    grade(a, html)
    assert a.score < 60 and len(a.issues) >= 6


def test_render_personalises_demo_and_issues():
    class L:
        name, city, sector, phone, website = "عيادة نور", "جدة", "عيادات", "966559876543", "nour.example"
        site_issues = "بدون HTTPS\nبطيء"
    msg = whatsapp.render("{name} {website}\n{issues}\n{demo}", L(), demo_url="https://demo.example.com/demo/business", sender="x")
    assert "• بدون HTTPS\n• بطيء" in msg
    assert "https://demo.example.com/demo/business?n=%D8%B9%D9%8A%D8%A7%D8%AF%D8%A9+%D9%86%D9%88%D8%B1&c=" in msg and "p=966559876543" in msg


@pytest.fixture(scope="module")
def client():
    from app.main import app
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def auth(client):
    r = client.post("/api/auth/login", json={"email": "admin@bassir.net", "password": "TestPass123!"})
    return {"Authorization": "Bearer " + r.json()["access_token"]}


def test_demo_pages_served(client):
    r = client.get("/demo/restaurant?n=مطعم+البيت&c=الرياض&p=966551234567")
    assert r.status_code == 200 and "data-name" in r.text and "wa.me" in r.text
    assert client.get("/demo/business").status_code == 200
    assert "data-sector" in client.get("/demo/unknown-kind").text  # falls back to the generic page


def test_import_with_scores_and_audit_endpoint(client, auth, monkeypatch):
    csv = "name,phone,city,sector,website,site_score,site_issues,rating,reviews\nمكتب الأمل,0551112233,الرياض,مقاولات,amal.example,35,\"بدون HTTPS\nغير متجاوب\",4.5,120\n"
    r = client.post("/api/leads/import", files={"file": ("l.csv", io.BytesIO(csv.encode("utf-8")), "text/csv")}, headers=auth)
    assert r.json()["added"] == 1
    lead = client.get("/api/leads?has_website=true&max_score=60", headers=auth).json()["items"][0]
    assert lead["site_score"] == 35 and lead["reviews"] == 120 and lead["site_issues"].count("\n") == 1
    assert all(l["website"] for l in client.get("/api/leads?has_website=true", headers=auth).json()["items"])
    assert all(not l["website"] for l in client.get("/api/leads?has_website=false", headers=auth).json()["items"])

    async def fake_audit(url):
        return Audit(url=url, final_url="https://amal.example", ok=True, status=200, https=True, ttfb_ms=200, mobile_ready=False, title="Home", score=70, issues=["غير متجاوب مع الجوال"])
    monkeypatch.setattr(site_audit, "audit", fake_audit)
    r = client.post(f"/api/leads/{lead['id']}/audit", headers=auth)
    assert r.status_code == 200 and r.json()["score"] == 70
    lead2 = client.get(f"/api/leads/{lead['id']}", headers=auth).json()
    assert lead2["site_score"] == 70 and lead2["site_issues"] == "غير متجاوب مع الجوال"
    acts = client.get(f"/api/leads/{lead['id']}/activities", headers=auth).json()
    assert acts[0]["kind"] == "note" and "70/100" in acts[0]["content"]

    # send with the weak-website template renders the issues (reset the cap another test module may have lowered)
    client.put("/api/settings", json={"daily_send_cap": 100, "demo_url": "https://demo.example.com/demo/business"}, headers=auth)
    tpl = [t for t in client.get("/api/templates", headers=auth).json() if "ضعيف" in t["name"]][0]
    r = client.post(f"/api/leads/{lead['id']}/send", json={"template_id": tpl["id"]}, headers=auth)
    assert r.status_code == 200 and "• غير متجاوب مع الجوال" in r.json()["message"] and "amal.example" in r.json()["message"]
    assert "n=%D9%85%D9%83%D8%AA%D8%A8" in r.json()["message"]
