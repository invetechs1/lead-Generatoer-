import hashlib
import hmac
import io
import json
import os
import sys

os.environ["DATABASE_URL"] = "sqlite:///./test.db"
os.environ["ADMIN_PASSWORD"] = "TestPass123!"
os.environ["SCHEDULER_ENABLED"] = "0"
if os.path.exists("test.db") and "app.main" not in sys.modules:
    os.remove("test.db")

import pytest
from fastapi.testclient import TestClient

from app.common import limiter, safe_href, upload_ok
from app.config import settings
from app.services import designer, payments
from app.schemas import clean_url, clean_handle

settings.UPLOAD_DIR = "./test_uploads"
PNG = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c6360f8cfc00000030001010f5d4e5e0000000049454e44ae426082")


def test_safe_href_blocks_javascript_and_data_urls():
    assert safe_href("javascript:alert(1)") == "#" and safe_href("data:text/html,x") == "#" and safe_href("vbscript:x") == "#"
    assert safe_href("https://maps.google.com/?q=x") == "https://maps.google.com/?q=x" and safe_href("/uploads/a.jpg") == "/uploads/a.jpg" and safe_href("tel:+966500000000").startswith("tel:")


def test_url_and_handle_validators():
    assert clean_url("example.com/menu", allow_bare_domain=True) == "https://example.com/menu"
    assert clean_url("  ") == ""
    for bad in ("javascript:alert(1)", "ftp://x.y", "data:text/html,hi", "not a url"):
        with pytest.raises(ValueError):
            clean_url(bad, allow_bare_domain=True)
    assert clean_handle("https://www.instagram.com/bait.almandi/") == "bait.almandi" and clean_handle("@x_y") == "x_y"
    with pytest.raises(ValueError):
        clean_handle("javascript:alert(1)")


def test_upload_magic_bytes():
    assert upload_ok(".png", PNG, 1_000_000)
    assert not upload_ok(".png", b"<html><script>alert(1)</script></html>", 1_000_000)  # html dressed as png
    assert not upload_ok(".jpg", b"\x89PNG....", 1_000_000)  # wrong magic for extension
    assert not upload_ok(".svg", b"<svg/>", 1_000_000) and not upload_ok(".png", PNG, 10)
    assert upload_ok(".pdf", b"%PDF-1.4 ...", 1_000_000) and upload_ok(".webp", b"RIFF\x00\x00\x00\x00WEBPVP8 ", 1_000_000)


def test_brief_rejects_css_injection_and_unknown_fonts():
    class L:
        name, sector, city = "x", "مطاعم", "الرياض"
    b = designer.preset_brief(L())
    with pytest.raises(Exception):
        designer.Brief.model_validate({**b.model_dump(), "palette": {**b.palette, "primary": "red;} body{display:none"}})
    ok = designer.Brief.model_validate({**b.model_dump(), "font_display": "Comic Sans'); @import url(evil)", "hero_photo": 999})
    assert ok.font_display == "Cairo" and ok.hero_photo == 20


def test_payment_match_requires_our_invoice_token():
    class Inv:
        amount, vat, token = 1000, 150, "tok-A"
    assert payments.matches({"status": "paid", "amount": 115000, "currency": "SAR", "metadata": {"invoice_token": "tok-A"}}, Inv()) == (True, "ok")
    assert payments.matches({"status": "paid", "amount": 115000, "currency": "SAR", "metadata": {}}, Inv())[0] is False  # no token → never counts
    assert payments.matches({"status": "paid", "amount": 115000, "currency": "SAR", "metadata": {"invoice_token": "tok-B"}}, Inv())[0] is False


@pytest.fixture(scope="module")
def client():
    from app.main import app
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def auth(client):
    r = client.post("/api/auth/login", json={"email": "admin@bassir.net", "password": "TestPass123!"})
    return {"Authorization": "Bearer " + r.json()["access_token"]}


def test_lead_urls_are_validated_at_the_api(client, auth):
    r = client.post("/api/leads", json={"name": "x", "phone": "0501230000", "maps_url": "javascript:alert(1)"}, headers=auth)
    assert r.status_code == 422
    r = client.post("/api/leads", json={"name": "x", "phone": "0501230000", "website": "example.com", "instagram": "https://instagram.com/abc/"}, headers=auth)
    assert r.status_code == 201 and r.json()["website"] == "https://example.com" and r.json()["instagram"] == "abc"
    assert client.patch(f"/api/leads/{r.json()['id']}", json={"maps_url": "data:text/html,x"}, headers=auth).status_code == 422


def test_publish_live_fields_validated_and_maps_href_safe(client, auth):
    lead = client.post("/api/leads", json={"name": "صالون أمان", "phone": "0501231111", "city": "جدة", "sector": "تجميل"}, headers=auth).json()
    client.post(f"/api/leads/{lead['id']}/proposal", json={"kind": "beauty"}, headers=auth)
    bad = client.post(f"/api/leads/{lead['id']}/proposal/publish", json={"slug": "aman-salon", "live": {"maps_url": "javascript:alert(1)"}}, headers=auth)
    assert bad.status_code == 422
    bad = client.post(f"/api/leads/{lead['id']}/proposal/publish", json={"slug": "aman-salon", "live": {"hours": [["a", "b", "c"]]}}, headers=auth)
    assert bad.status_code == 422
    ok = client.post(f"/api/leads/{lead['id']}/proposal/publish", json={"slug": "aman-salon", "live": {"maps_url": "maps.app.goo.gl/abc", "instagram": "@aman_salon", "hours": [["السبت", "9-9"]]}}, headers=auth)
    assert ok.status_code == 200 and ok.json()["live"]["maps_url"] == "https://maps.app.goo.gl/abc" and ok.json()["live"]["instagram"] == "aman_salon"
    html = client.get("/s/aman-salon").text
    assert 'href="https://maps.app.goo.gl/abc"' in html and "instagram.com/aman_salon" in html


def test_demo_kind_is_sanitised(client):
    assert client.get("/demo/restaurant").status_code == 200
    r = client.get("/demo/..%2F..%2Fmain")  # traversal attempt: never serves a file outside static/demo
    assert r.status_code == 200 and "import" not in r.text and ("data-sector" in r.text or 'id="app"' in r.text)
    assert "data-sector" in client.get("/demo/....restaurant").text  # dots/odd names never resolve to another file
    assert "data-sector" in client.get("/demo/UPPER_case").text


def test_whatsapp_webhook_fails_closed_without_secret(client, auth, monkeypatch):
    monkeypatch.setattr(settings, "WHATSAPP_APP_SECRET", "")
    body = json.dumps({"entry": []}).encode()
    assert client.post("/api/whatsapp/webhook", content=body, headers={"Content-Type": "application/json"}).status_code == 503
    monkeypatch.setattr(settings, "WHATSAPP_APP_SECRET", "s3cret")
    sig = "sha256=" + hmac.new(b"s3cret", body, hashlib.sha256).hexdigest()
    assert client.post("/api/whatsapp/webhook", content=body, headers={"Content-Type": "application/json", "X-Hub-Signature-256": sig}).status_code == 200


def test_public_write_endpoints_are_rate_limited(client, auth):
    limiter.reset()
    lead = client.post("/api/leads", json={"name": "مكتب حد", "phone": "0501232222", "city": "الرياض", "sector": "مقاولات"}, headers=auth).json()
    prop = client.post(f"/api/leads/{lead['id']}/proposal", json={}, headers=auth).json()
    codes = [client.post(f"/api/public/proposal/{prop['token']}/answers", json={"style": "warm"}, headers={"X-Forwarded-For": "203.0.113.9"}).status_code for _ in range(12)]
    assert codes[:10] == [200] * 10 and codes[10:] == [429, 429]
    # a different IP is not affected
    assert client.post(f"/api/public/proposal/{prop['token']}/answers", json={"style": "warm"}, headers={"X-Forwarded-For": "203.0.113.10"}).status_code == 200
    c = client.post("/api/clients", json={"lead_id": lead["id"], "company": "مكتب حد", "phone": "0501232222"}, headers=auth).json()
    tok = c["invoices"][0]["token"]
    codes = [client.post(f"/api/public/invoice/{tok}/transfer-notice", headers={"X-Forwarded-For": "203.0.113.11"}).status_code for _ in range(7)]
    assert codes[5:] == [429, 429]
    limiter.reset()


def test_upload_endpoints_reject_disguised_files(client, auth):
    lead = client.post("/api/leads", json={"name": "x2", "phone": "0501233333"}, headers=auth).json()
    r = client.post(f"/api/leads/{lead['id']}/photos", files=[("files", ("evil.png", io.BytesIO(b"<script>alert(1)</script>"), "image/png")), ("files", ("ok.png", io.BytesIO(PNG), "image/png"))], headers=auth)
    assert r.json()["saved"] and len(r.json()["photos"]) == 1 and r.json()["photos"][0].endswith(".png")
    c = client.post("/api/clients", json={"lead_id": lead["id"], "company": "x2", "phone": "0501233333"}, headers=auth).json()
    r = client.post(f"/api/public/update/{c['update_token']}", data={"text": "صور"}, files=[("files", ("menu.pdf", io.BytesIO(b"<html>not a pdf</html>"), "application/pdf"))])
    assert r.status_code == 200 and r.json()["files"] == 0


def test_startup_warnings_flag_default_secrets():
    from app.main import startup_warnings
    w = startup_warnings()
    assert any("SECRET_KEY" in x for x in w)  # test env uses the dev default
