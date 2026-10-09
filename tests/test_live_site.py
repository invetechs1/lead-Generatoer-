import os
import sys

os.environ["DATABASE_URL"] = "sqlite:///./test.db"
os.environ["ADMIN_PASSWORD"] = "TestPass123!"
if os.path.exists("test.db") and "app.main" not in sys.modules:
    os.remove("test.db")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.config import settings
from app.database import Base, ensure_columns
from app import models  # noqa: F401

settings.UPLOAD_DIR = "./test_uploads"


def test_ensure_columns_adds_missing_columns_to_old_schema(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path}/old.db")
    with eng.begin() as c:  # a v1.0-era leads table without the newer columns
        c.execute(text("CREATE TABLE leads (id INTEGER PRIMARY KEY, name VARCHAR(200), phone VARCHAR(20))"))
        c.execute(text("INSERT INTO leads (name, phone) VALUES ('x', '9665')"))
    added = ensure_columns(eng)
    assert "leads.site_score" in added and "leads.place_id" in added and "leads.site_issues" in added
    with eng.connect() as c:
        row = c.execute(text("SELECT site_score, place_id, priority FROM leads")).first()
    assert row[0] is None and row[1] == "" and row[2] == 2  # defaults applied
    assert ensure_columns(eng) == []  # idempotent


@pytest.fixture(scope="module")
def client():
    from app.main import app
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def auth(client):
    r = client.post("/api/auth/login", json={"email": "admin@bassir.net", "password": "TestPass123!"})
    return {"Authorization": "Bearer " + r.json()["access_token"]}


def test_publish_live_site_tracking_and_stats(client, auth):
    lead = client.post("/api/leads", json={"name": "صالون لمسة", "phone": "0533334444", "city": "الدمام", "sector": "تجميل", "maps_url": "https://maps.google.com/?q=x"}, headers=auth).json()
    client.put("/api/settings", json={"sender_phone": "966555000111", "daily_send_cap": 100}, headers=auth)
    assert client.post(f"/api/leads/{lead['id']}/proposal/publish", json={"slug": "lamsa"}, headers=auth).status_code == 404  # no proposal yet
    client.post(f"/api/leads/{lead['id']}/proposal", json={"kind": "beauty"}, headers=auth)
    cl = client.post("/api/clients", json={"lead_id": lead["id"], "company": "صالون لمسة", "phone": "0533334444"}, headers=auth).json()

    assert client.post(f"/api/leads/{lead['id']}/proposal/publish", json={"slug": "Bad Slug!"}, headers=auth).status_code == 422
    r = client.post(f"/api/leads/{lead['id']}/proposal/publish", json={"slug": "lamsa-salon", "custom_domain": "https://Lamsa-Salon.com/", "live": {"address": "حي الشاطئ، الدمام", "hours": [["السبت – الخميس", "9 ص – 10 م"]], "instagram": "@lamsa", "phone": "966533334444"}}, headers=auth)
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["published"] and p["custom_domain"] == "lamsa-salon.com" and p["site_url"] == "https://lamsa-salon.com"
    assert client.get("/api/clients", headers=auth).json()[0]["site_url"] == "https://lamsa-salon.com"
    assert client.get("/api/clients", headers=auth).json()[0]["status"] == "active"

    # live page: no sales ribbon / questionnaire, business number on CTAs, custom hours, map link, indexable
    html = client.get("/s/lamsa-salon").text
    assert "عرض تصميم أوّلي" not in html and 'id="ask"' not in html and 'id="offer"' not in html
    assert "wa.me/966533334444" in html and "wa.me/966555000111" not in html
    assert "حي الشاطئ" in html and "9 ص – 10 م" in html and 'data-ev="map"' in html and "index,follow" in html and "instagram.com/lamsa" in html
    # the proposal page still has the sales sections
    prop = client.get(f"/api/leads/{lead['id']}/proposal", headers=auth).json()
    assert 'id="ask"' in client.get(f"/p/{prop['token']}").text

    # custom domain routing at /
    assert "صالون لمسة" in client.get("/", headers={"host": "lamsa-salon.com"}).text and 'data-ev="wa"' in client.get("/", headers={"host": "lamsa-salon.com"}).text
    assert "<title>" in client.get("/", headers={"host": "other.example"}).text  # SPA for unknown hosts
    assert client.get("/s/nope").status_code == 404

    # click beacons + stats
    for k in ("wa", "wa", "call"):
        assert client.post(f"/api/public/site/lamsa-salon/event?kind={k}").status_code == 204
    assert client.post("/api/public/site/lamsa-salon/event?kind=bogus").status_code == 400
    st = client.get(f"/api/leads/{lead['id']}/site/stats", headers=auth).json()
    assert st["this_month"]["view"] == 3 and st["this_month"]["wa"] == 2 and st["this_month"]["call"] == 1
    assert client.get(f"/api/clients/{cl['id']}/stats", headers=auth).json()["url"] == "https://lamsa-salon.com"

    # placeholders in the monthly report template
    tpl = [t for t in client.get("/api/templates", headers=auth).json() if "تقرير شهري" in t["name"]][0]
    msg = client.post(f"/api/leads/{lead['id']}/send", json={"template_id": tpl["id"], "mark_contacted": False}, headers=auth).json()["message"]
    assert "https://lamsa-salon.com" in msg and "3 زيارة · 2 ضغطة واتساب · 1 اتصال" in msg

    # slug clash + unpublish
    lead2 = client.post("/api/leads", json={"name": "آخر", "phone": "0533335555"}, headers=auth).json()
    client.post(f"/api/leads/{lead2['id']}/proposal", json={}, headers=auth)
    assert client.post(f"/api/leads/{lead2['id']}/proposal/publish", json={"slug": "lamsa-salon"}, headers=auth).status_code == 409
    assert client.post(f"/api/leads/{lead['id']}/proposal/unpublish", headers=auth).json()["published"] is False
    assert client.get("/s/lamsa-salon").status_code == 404
    assert "<title>" in client.get("/", headers={"host": "lamsa-salon.com"}).text
