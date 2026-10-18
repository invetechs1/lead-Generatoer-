"""Video 7: closing message with contract link → client reads and e-signs the agreement → CRM shows it signed."""
import httpx
from pathlib import Path
from playwright.sync_api import sync_playwright
BASE = "http://127.0.0.1:8765"; OUT = Path("./e2e_out"); import os
CHROME = os.environ.get("CHROME_PATH")
results = []
def step(n, ok=True, note=""): results.append((n, ok, note)); print("PASS" if ok else "FAIL", n, note, flush=True)
def pause(pg, ms=900): pg.wait_for_timeout(ms)
c = httpx.Client(base_url=BASE, timeout=30)
tok = c.post("/api/auth/login", json={"email": "admin@bassir.net", "password": "ChangeMe123!"}).json()["access_token"]; h = {"Authorization": "Bearer " + tok}
c.put("/api/settings", json={"sender_phone": "966555000111", "sender_name": "م. يحيى — Bassir IT", "cr_number": "1010123456", "vat_number": "300000000000003"}, headers=h)
lead = c.post("/api/leads", json={"name": "مطعم بيت المندي", "phone": "0551234567", "city": "الرياض", "sector": "مطاعم"}, headers=h).json()
c.patch(f"/api/leads/{lead['id']}", json={"status": "negotiating"}, headers=h)
with sync_playwright() as p:
    b = p.chromium.launch(executable_path=CHROME, args=["--no-sandbox"], slow_mo=120) if CHROME else p.chromium.launch(slow_mo=120)
    ctx = b.new_context(viewport={"width": 1280, "height": 800}, record_video_dir=str(OUT / "v7"), record_video_size={"width": 1280, "height": 800}, locale="ar-SA")
    pg = ctx.new_page()
    try:
        pg.goto(BASE); pg.fill("#em", "admin@bassir.net"); pg.fill("#pw", "ChangeMe123!"); pg.click("#go"); pg.wait_for_selector("text=MRR"); pause(pg)
        pg.click("a:has-text('العملاء')"); pg.wait_for_selector("#list"); pg.click(".lead:has-text('بيت المندي')"); pg.wait_for_selector("#conv"); pause(pg, 800)
        pg.click("#conv"); pg.wait_for_selector("#co"); pg.fill("#cn", "أبو فهد"); pause(pg, 600); pg.click("#sv"); pg.wait_for_selector("text=BSR-"); pause(pg, 1500); step("converted to client: agreement + first invoice created")
        pg.wait_for_selector("text=بانتظار التوقيع"); step("clients page shows agreement pending with a send button"); pause(pg, 1200)
        pg.click("a:has-text('العملاء')"); pg.wait_for_selector("#list"); pg.click(".lead:has-text('بيت المندي')"); pg.wait_for_selector("#tp")
        opts = pg.locator("#tp option").all_text_contents(); pg.select_option("#tp", index=[i for i, t in enumerate(opts) if "بعد الموافقة" in t][0]); pause(pg, 1800)
        pv = pg.locator("#pv").inner_text(); assert "/c/" in pv and "/inv/" in pv, pv; step("closing message carries the agreement and invoice links"); pause(pg, 1200)
        url = [w for w in pv.split() if "/c/" in w][0]
        cl = ctx.new_page(); cl.goto(url); cl.wait_for_selector("text=القبول الإلكتروني"); pause(cl, 1500)
        for y in (700, 900, 900, 900): cl.mouse.wheel(0, y); pause(cl, 600)
        cl.locator("#sign").scroll_into_view_if_needed(); pause(cl, 800)
        cl.fill("#nm", "فهد بن محمد العتيبي"); pause(cl, 500); cl.check("#ag"); pause(cl, 600); cl.click("#ok"); cl.wait_for_selector("text=تم القبول إلكترونيًا", timeout=10000); pause(cl, 2000); step("client e-signed: name, time and reference shown"); cl.close()
        pg.bring_to_front(); pg.click(".close"); pg.click("a:has-text('الاشتراكات')"); pg.wait_for_selector("text=الاتفاقية موقّعة", timeout=8000); pause(pg, 1500); step("CRM shows the agreement as signed")
        pg.click("a:has-text('العملاء')"); pg.wait_for_selector("#list"); pg.click(".lead:has-text('بيت المندي')"); pg.wait_for_selector("text=السجل"); pg.locator("text=السجل").scroll_into_view_if_needed(); pause(pg, 1800)
        assert pg.locator("text=وقّع العميل الاتفاقية").count() >= 1; step("timeline records the signature")
    except Exception as e:
        step("video7", False, repr(e)); pg.screenshot(path=str(OUT / "fail7.png"))
    ctx.close(); b.close()
print("FAILED" if any(not ok for _, ok, _ in results) else "ALL PASS")
