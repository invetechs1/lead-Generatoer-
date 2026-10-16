"""Video 6: morning digest on the dashboard → client self-service update page → request lands in CRM → marked done."""
import httpx
from datetime import date, timedelta
from pathlib import Path
from playwright.sync_api import sync_playwright
BASE = "http://127.0.0.1:8765"; OUT = Path("./e2e_out"); import os
CHROME = os.environ.get("CHROME_PATH")
results = []
def step(n, ok=True, note=""): results.append((n, ok, note)); print("PASS" if ok else "FAIL", n, note, flush=True)
def pause(pg, ms=900): pg.wait_for_timeout(ms)
c = httpx.Client(base_url=BASE, timeout=30)
tok = c.post("/api/auth/login", json={"email": "admin@bassir.net", "password": "ChangeMe123!"}).json()["access_token"]; h = {"Authorization": "Bearer " + tok}
c.put("/api/settings", json={"sender_phone": "966555000111", "sender_name": "م. يحيى — Bassir IT"}, headers=h)
for name, phone, city, sector, st, fu in [("عيادة سما لطب الأسنان", "0511112222", "الرياض", "عيادات", "contacted", -1), ("مقاولات البناء الحديث", "0511113333", "جدة", "مقاولات", "negotiating", 0), ("صالون لمسة", "0511115555", "الدمام", "تجميل", "demo_sent", -2)]:
    l = c.post("/api/leads", json={"name": name, "phone": phone, "city": city, "sector": sector}, headers=h).json()
    c.patch(f"/api/leads/{l['id']}", json={"status": st, "next_follow_up": (date.today() + timedelta(days=fu)).isoformat()}, headers=h)
lead = c.post("/api/leads", json={"name": "مطعم بيت المندي", "phone": "0551234567", "city": "الرياض", "sector": "مطاعم"}, headers=h).json()
cl = c.post("/api/clients", json={"lead_id": lead["id"], "company": "مطعم بيت المندي", "phone": "0551234567", "contact_name": "أبو فهد", "status": "active"}, headers=h).json()
old = c.post("/api/clients", json={"company": "ورشة الخليج", "phone": "0511114444", "start_date": "2026-08-10", "billing_day": 5}, headers=h).json()
c.post(f"/api/public/invoice/{old['invoices'][0]['token']}/transfer-notice")
with sync_playwright() as p:
    b = p.chromium.launch(executable_path=CHROME, args=["--no-sandbox"], slow_mo=120) if CHROME else p.chromium.launch(slow_mo=120)
    ctx = b.new_context(viewport={"width": 1280, "height": 800}, record_video_dir=str(OUT / "v6"), record_video_size={"width": 1280, "height": 800}, locale="ar-SA")
    pg = ctx.new_page()
    try:
        pg.goto(BASE); pg.fill("#em", "admin@bassir.net"); pg.fill("#pw", "ChangeMe123!"); pg.click("#go"); pg.wait_for_selector("#digest pre", timeout=10000); pause(pg, 1200)
        pg.locator("#digest").scroll_into_view_if_needed(); pause(pg, 2500)
        txt = pg.locator("#digest pre").inner_text(); assert "عيادة سما" in txt and "تحويلات تنتظر" in txt, txt; step("dashboard shows the morning digest (follow-ups, negotiating, transfer notices)")
        pg.click("#runjobs"); pg.wait_for_selector("text=تم:"); pause(pg, 1500); step("daily jobs run on demand (overdue marking)")
        pg.click("a:has-text('الاشتراكات')"); pg.wait_for_selector("text=صفحة التحديث"); pause(pg, 1500); step("clients page has the update-page link per client")
        with ctx.expect_page() as np:
            pg.click(f".card[data-id='{cl['id']}'] a:has-text('صفحة التحديث')")
        up = np.value; up.wait_for_selector("#t"); pause(up, 1200)
        up.click("button:has-text('تحديث الأسعار')"); up.fill("#t", "تحديث الأسعار: المندي 70 ريال بدل 65، وأضيفوا السليق بـ 45 ريال"); pause(up, 800)
        up.set_input_files("input[type=file]", ["./e2e_photos/2.jpg"]); pause(up, 600)
        up.click("#sb"); up.wait_for_selector("text=وصلنا طلبكم", timeout=10000); pause(up, 1500); step("client submitted a content update with a photo"); up.close()
        pg.bring_to_front(); pg.click("a:has-text('الرئيسية')"); pg.wait_for_selector("#upd .done", timeout=10000); pg.locator("#upd").scroll_into_view_if_needed(); pause(pg, 2200); step("request appears on the dashboard with the photo")
        pg.click("#upd .done"); pg.wait_for_selector("text=لا توجد طلبات مفتوحة", timeout=8000); pause(pg, 1500); step("marked done")
    except Exception as e:
        step("video6", False, repr(e)); pg.screenshot(path=str(OUT / "fail6.png"))
    ctx.close(); b.close()
print("FAILED" if any(not ok for _, ok, _ in results) else "ALL PASS")
