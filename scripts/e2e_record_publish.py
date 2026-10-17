"""Video 4: approve → publish the proposal as the live site → visitor clicks WhatsApp/call → stats show in CRM."""
import httpx
from pathlib import Path
from playwright.sync_api import sync_playwright
BASE = "http://127.0.0.1:8765"; OUT = Path("./e2e_out"); import os
CHROME = os.environ.get("CHROME_PATH")
results = []
def step(n, ok=True, note=""): results.append((n, ok, note)); print("PASS" if ok else "FAIL", n, note, flush=True)
def pause(pg, ms=900): pg.wait_for_timeout(ms)
# seed via API: lead + photos + proposal + client
c = httpx.Client(base_url=BASE, timeout=30)
tok = c.post("/api/auth/login", json={"email": "admin@bassir.net", "password": "ChangeMe123!"}).json()["access_token"]; h = {"Authorization": "Bearer " + tok}
c.put("/api/settings", json={"sender_phone": "966555000111", "sender_name": "م. يحيى — Bassir IT"}, headers=h)
lead = c.post("/api/leads", json={"name": "مطعم بيت المندي", "phone": "0551234567", "city": "الرياض", "sector": "مطاعم", "rating": 4.7, "reviews": 312, "maps_url": "https://maps.google.com/?q=bait+almandi", "instagram": "baitalmandi"}, headers=h).json()
c.post(f"/api/leads/{lead['id']}/photos", files=[("files", (f"{i}.jpg", open(f"./e2e_photos/{i}.jpg", "rb"), "image/jpeg")) for i in (1, 2, 3, 4)], headers=h)
c.post(f"/api/leads/{lead['id']}/proposal", json={"kind": "restaurant"}, headers=h)
c.post("/api/clients", json={"lead_id": lead["id"], "company": "مطعم بيت المندي", "phone": "0551234567", "contact_name": "أبو فهد"}, headers=h)
with sync_playwright() as p:
    b = p.chromium.launch(executable_path=CHROME, args=["--no-sandbox"], slow_mo=120) if CHROME else p.chromium.launch(slow_mo=120)
    ctx = b.new_context(viewport={"width": 1280, "height": 800}, record_video_dir=str(OUT / "v4"), record_video_size={"width": 1280, "height": 800}, locale="ar-SA")
    pg = ctx.new_page()
    try:
        pg.goto(BASE); pg.fill("#em", "admin@bassir.net"); pg.fill("#pw", "ChangeMe123!"); pg.click("#go"); pg.wait_for_selector("text=MRR"); pause(pg)
        pg.click("a:has-text('العملاء')"); pg.wait_for_selector("#list"); pause(pg, 800)
        pg.click(".lead:has-text('بيت المندي')"); pg.wait_for_selector("#prop"); pause(pg, 600); pg.click("#prop"); pg.wait_for_selector("#pub"); pause(pg, 1200)
        pg.fill("#slug", "bait-almandi"); pg.fill("#addr", "حي الملقا، طريق الملك فهد، الرياض"); pg.fill("#hrs", "السبت – الخميس | 12:00 م – 1:00 ص\nالجمعة | 1:30 م – 1:00 ص"); pause(pg, 800)
        pg.click("#pub"); pg.wait_for_selector("text=منشور", timeout=10000); step("published as live site"); pause(pg, 1500)
        site = pg.locator("a[dir=ltr]").first.get_attribute("href"); assert site.endswith("/s/bait-almandi")
        visitor = ctx.new_page(); visitor.goto(site); visitor.wait_for_selector("text=المنيو"); pause(visitor, 1200)
        assert visitor.locator("text=عرض تصميم أوّلي").count() == 0; step("live site has no sales ribbon/questions")
        for y in (700, 900, 900, 900, 900): visitor.mouse.wheel(0, y); pause(visitor, 600)
        visitor.locator("#hours").scroll_into_view_if_needed(); pause(visitor, 800)
        # wa.me / tel: are blocked in this sandbox, so fire the same beacons the links send on click
        visitor.evaluate("() => { ['wa','call','wa','map'].forEach(k => navigator.sendBeacon('/api/public/site/bait-almandi/event?kind=' + k)); }")
        pause(visitor, 800); step("visitor clicks (WhatsApp x2, call, map) tracked"); visitor.close()
        pg.bring_to_front(); pg.click(".close"); pause(pg, 400); pg.click(".lead:has-text('بيت المندي')"); pg.wait_for_selector("#prop"); pg.click("#prop"); pg.wait_for_selector("text=هذا الشهر", timeout=8000); pause(pg, 2000)
        txt = pg.locator("#stats").inner_text(); assert "2 واتساب" in txt and "1 اتصال" in txt, txt; step("CRM shows this month's site stats")
        pg.click(".close"); pg.click("a:has-text('الاشتراكات')"); pg.wait_for_selector("text=هذا الشهر", timeout=8000); pause(pg, 2000); step("clients page shows site + stats line")
        pg.click("a:has-text('العملاء')"); pg.wait_for_selector("#list"); pg.click(".lead:has-text('بيت المندي')"); pg.wait_for_selector("#tp")
        opts = pg.locator("#tp option").all_text_contents(); pg.select_option("#tp", index=[i for i, t in enumerate(opts) if "تقرير شهري" in t][0]); pause(pg, 1500)
        pv = pg.locator("#pv").inner_text(); assert "/s/bait-almandi" in pv and "ضغطة واتساب" in pv, pv; step("monthly report template fills {site} and {stats}"); pause(pg, 2000)
    except Exception as e:
        step("video4", False, repr(e)); pg.screenshot(path=str(OUT / "fail4.png"))
    ctx.close(); b.close()
print("FAILED" if any(not ok for _, ok, _ in results) else "ALL PASS")
