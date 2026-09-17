import hashlib
import hmac
import io
import json
import os
import sys

os.environ["DATABASE_URL"] = "sqlite:///./test.db"
os.environ["ADMIN_PASSWORD"] = "TestPass123!"
os.environ["UPLOAD_DIR"] = "./test_uploads"
if os.path.exists("test.db") and "app.main" not in sys.modules:
    os.remove("test.db")

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.services import designer, whatsapp

settings.WHATSAPP_VERIFY_TOKEN = "verify-me"
settings.WHATSAPP_APP_SECRET = "app-secret"
settings.UPLOAD_DIR = "./test_uploads"


class L:
    name, sector, city, rating, reviews, website, site_issues, instagram = "عيادة نور", "عيادات", "جدة", 4.7, 88, "", "", ""


def test_preset_brief_is_valid_and_sector_aware():
    b = designer.preset_brief(L())
    assert b.kind == "clinic" and b.brand_name == "عيادة نور" and len(b.services) >= 3 and b.palette["primary"].startswith("#")
    assert designer.kind_for("مطاعم") == "restaurant" and designer.kind_for("غير معروف") == "business" and designer.kind_for("x", "beauty") == "beauty"


def test_interactive_payloads():
    p = whatsapp.interactive_buttons_payload("966500000000", "هل تحب نبدأ؟", [("start", "أبغى أبدأ"), ("later", "لاحقًا"), ("no", "لا شكرًا")], header="عرض الموقع")
    assert p["type"] == "interactive" and len(p["interactive"]["action"]["buttons"]) == 3 and p["interactive"]["header"]["text"] == "عرض الموقع"
    with pytest.raises(ValueError):
        whatsapp.interactive_buttons_payload("9665", "x", [("a", "1"), ("b", "2"), ("c", "3"), ("d", "4")])
    lst = whatsapp.interactive_list_payload("9665", "اختر", "الخيارات", [("r1", "منيو", "المنيو بالصور")])
    assert lst["interactive"]["type"] == "list"
    t = whatsapp.template_payload("9665", "website_offer", body_params=["عيادة نور"], button_url_param="abc")
    assert t["template"]["components"][1]["sub_type"] == "url"


def test_parse_webhook_button_and_text():
    data = {"entry": [{"changes": [{"value": {"contacts": [{"wa_id": "966501112233", "profile": {"name": "أحمد"}}], "messages": [
        {"from": "966501112233", "id": "wamid.1", "type": "interactive", "interactive": {"type": "button_reply", "button_reply": {"id": "start_now", "title": "أبغى أبدأ"}}},
        {"from": "966501112233", "id": "wamid.2", "type": "text", "text": {"body": "إيقاف"}}],
        "statuses": [{"id": "wamid.0", "status": "read", "recipient_id": "966501112233"}]}}]}]}
    evs = whatsapp.parse_webhook(data)
    assert [e["kind"] for e in evs] == ["button", "text", "status"] and evs[0]["reply_id"] == "start_now" and evs[0]["name"] == "أحمد"


@pytest.fixture(scope="module")
def client():
    from app.main import app
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def auth(client):
    r = client.post("/api/auth/login", json={"email": "admin@bassir.net", "password": "TestPass123!"})
    return {"Authorization": "Bearer " + r.json()["access_token"]}


def test_proposal_flow(client, auth, monkeypatch):
    lead = client.post("/api/leads", json={"name": "مطعم الضيافة", "phone": "0509998877", "city": "الرياض", "sector": "مطاعم", "rating": 4.6, "reviews": 210}, headers=auth).json()
    client.put("/api/settings", json={"sender_phone": "966555000111", "daily_send_cap": 100}, headers=auth)

    # upload a photo (tiny valid PNG), bad extension ignored
    png = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c6360f8cfc00000030001010f5d4e5e0000000049454e44ae426082")
    r = client.post(f"/api/leads/{lead['id']}/photos", files=[("files", ("a.png", io.BytesIO(png), "image/png")), ("files", ("x.exe", io.BytesIO(b"nope"), "application/octet-stream"))], headers=auth)
    assert r.status_code == 200 and len(r.json()["photos"]) == 1

    # designer is called with the photo paths; we stub it to a preset-derived brief marked as claude
    seen = {}
    async def fake_generate(l, paths, notes="", kind="", instagram_bio=""):
        seen["paths"] = [str(p) for p in paths]; seen["notes"] = notes
        b = designer.preset_brief(l, kind); b.headline = "مندي يجمع العائلة"; return b, "claude"
    monkeypatch.setattr(designer, "generate_brief", fake_generate)
    r = client.post(f"/api/leads/{lead['id']}/proposal", json={"notes": "شعارهم بني", "kind": "restaurant"}, headers=auth)
    assert r.status_code == 200, r.text
    prop = r.json()
    assert prop["source"] == "claude" and prop["kind"] == "restaurant" and prop["url"].endswith("/p/" + prop["token"]) and len(prop["photos"]) == 1
    assert seen["notes"] == "شعارهم بني" and seen["paths"][0].endswith(".png")

    # hand edit a field, invalid palette rejected
    r = client.patch(f"/api/leads/{lead['id']}/proposal", json={"brief": {"headline": "عنوان جديد"}}, headers=auth)
    assert r.json()["brief"]["headline"] == "عنوان جديد"
    assert client.patch(f"/api/leads/{lead['id']}/proposal", json={"brief": {"services": []}}, headers=auth).status_code == 422

    # {proposal}/{demo} placeholders resolve to the page link
    r = client.post(f"/api/leads/{lead['id']}/send", json={"body": "شوف {proposal} و {demo}"}, headers=auth).json()
    assert r["message"].count("/p/" + prop["token"]) == 2

    # public page: renders, counts a view, moves status to demo_sent, uses salesperson number for CTA and business number in hours
    r = client.get(f"/p/{prop['token']}")
    assert r.status_code == 200 and "عنوان جديد" in r.text and "مطعم الضيافة" in r.text and "wa.me/966555000111" in r.text and "wa.me/966509998877" in r.text
    assert "4.6" in r.text and 'class="sw"' in r.text
    assert client.get("/p/nope").status_code == 404
    assert client.get(f"/api/leads/{lead['id']}", headers=auth).json()["status"] == "demo_sent"
    assert client.get(f"/api/leads/{lead['id']}/proposal", headers=auth).json()["views"] == 1

    # client taps answers → stored, status negotiating, priority high, activity logged
    r = client.post(f"/api/public/proposal/{prop['token']}/answers", json={"style": "warm", "priorities": ["حجز/طلب عبر واتساب", "معرض صور احترافي"], "timing": "this_week", "notes": "أبغى المنيو بالصور", "wants_start": True})
    assert r.status_code == 200
    l2 = client.get(f"/api/leads/{lead['id']}", headers=auth).json()
    assert l2["status"] == "negotiating" and l2["priority"] == 1
    p2 = client.get(f"/api/leads/{lead['id']}/proposal", headers=auth).json()
    assert p2["answers"]["wants_start"] is True and p2["answered_at"]
    acts = client.get(f"/api/leads/{lead['id']}/activities", headers=auth).json()
    assert any("أبغى أبدأ" in a["content"] for a in acts) and any("فتح عرض التصميم" in a["content"] for a in acts)


def test_webhook_verify_and_replies(client, auth):
    assert client.get("/api/whatsapp/webhook?hub.mode=subscribe&hub.verify_token=verify-me&hub.challenge=12345").text == "12345"
    assert client.get("/api/whatsapp/webhook?hub.mode=subscribe&hub.verify_token=wrong&hub.challenge=1").status_code == 403
    lead = client.post("/api/leads", json={"name": "مكتب البركة", "phone": "0507770000", "city": "جدة", "sector": "مقاولات"}, headers=auth).json()
    body = json.dumps({"entry": [{"changes": [{"value": {"messages": [{"from": "966507770000", "id": "w1", "type": "interactive", "interactive": {"type": "button_reply", "button_reply": {"id": "start", "title": "أبغى أبدأ"}}}]}}]}]}).encode()
    sig = "sha256=" + hmac.new(b"app-secret", body, hashlib.sha256).hexdigest()
    assert client.post("/api/whatsapp/webhook", content=body, headers={"X-Hub-Signature-256": "sha256=bad", "Content-Type": "application/json"}).status_code == 403
    r = client.post("/api/whatsapp/webhook", content=body, headers={"X-Hub-Signature-256": sig, "Content-Type": "application/json"})
    assert r.json()["handled"] == 1
    assert client.get(f"/api/leads/{lead['id']}", headers=auth).json()["status"] == "negotiating"
    body = json.dumps({"entry": [{"changes": [{"value": {"messages": [{"from": "966507770000", "id": "w2", "type": "text", "text": {"body": "لا أريد رسائل"}}]}}]}]}).encode()
    client.post("/api/whatsapp/webhook", content=body, headers={"X-Hub-Signature-256": "sha256=" + hmac.new(b"app-secret", body, hashlib.sha256).hexdigest(), "Content-Type": "application/json"})
    assert client.get(f"/api/leads/{lead['id']}", headers=auth).json()["status"] == "do_not_contact"
    # sending buttons requires the Cloud API to be configured
    assert client.post(f"/api/whatsapp/leads/{lead['id']}/buttons", json={"body": "x", "buttons": [{"id": "start", "title": "نبدأ"}]}, headers=auth).status_code == 400
