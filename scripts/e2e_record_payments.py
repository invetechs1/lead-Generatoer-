"""Video 5: invoice link from the Clients page → client's invoice page (bank transfer mode) → "I transferred" → CRM flag → mark paid → receipt."""
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
c.put("/api/settings", json={"sender_phone": "966555000111", "sender_name": "م. يحيى — Bassir IT", "bank_name": "مصرف الراجحي", "iban": "SA0380000000608010167519", "account_name": "مؤسسة بصير لتقنية المعلومات", "vat_number": "300000000000003", "cr_number": "1010123456"}, headers=h)
lead = c.post("/api/leads", json={"name": "مطعم بيت المندي", "phone": "0551234567", "city": "الرياض", "sector": "مطاعم"}, headers=h).json()
c.post("/api/clients", json={"lead_id": lead["id"], "company": "مطعم بيت المندي", "phone": "0551234567", "contact_name": "أبو فهد"}, headers=h)
with sync_playwright() as p:
    b = p.chromium.launch(executable_path=CHROME, args=["--no-sandbox"], slow_mo=120) if CHROME else p.chromium.launch(slow_mo=120)
    ctx = b.new_context(viewport={"width": 1280, "height": 800}, record_video_dir=str(OUT / "v5"), record_video_size={"width": 1280, "height": 800}, locale="ar-SA")
    pg = ctx.new_page()
    try:
        pg.goto(BASE); pg.fill("#em", "admin@bassir.net"); pg.fill("#pw", "ChangeMe123!"); pg.click("#go"); pg.wait_for_selector("text=MRR"); pause(pg)
        pg.click("a:has-text('الاشتراكات')"); pg.wait_for_selector("text=BSR-"); pause(pg, 1500); step("clients page lists the invoice with reminder + link buttons")
        tokv = pg.locator(".lnk").first.get_attribute("data-t")
        client_pg = ctx.new_page(); client_pg.goto(f"{BASE}/inv/{tokv}"); client_pg.wait_for_selector("text=الإجمالي المستحق"); pause(client_pg, 1800)
        assert "SA0380000000608010167519" in client_pg.content() and "1,150" in client_pg.content(); step("invoice page: tax invoice + IBAN (no gateway keys here)")
        client_pg.mouse.wheel(0, 500); pause(client_pg, 800); client_pg.click("#tn"); client_pg.wait_for_selector("text=وصلنا إشعاركم"); pause(client_pg, 1500); step("client pressed 'I transferred'"); client_pg.close()
        pg.bring_to_front(); pg.click("a:has-text('العملاء')"); pg.wait_for_selector("#list"); pg.click("a:has-text('الاشتراكات')"); pg.wait_for_selector("text=أبلغ بالتحويل", timeout=8000); pause(pg, 1500); step("CRM shows the transfer notice badge")
        pg.click("button.pay >> nth=0"); pg.wait_for_selector("text=سُجّل الدفع"); pause(pg, 1200); step("salesperson confirms payment")
        rc = ctx.new_page(); rc.goto(f"{BASE}/inv/{tokv}"); rc.wait_for_selector("text=تم استلام الدفع"); pause(rc, 1800); step("invoice page now shows the paid receipt"); rc.close()
        pg.bring_to_front(); pg.click("a:has-text('الرئيسية')"); pg.wait_for_selector("text=MRR"); pause(pg, 1800)
        mob = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True)
        m = mob.new_page(); m.goto(f"{BASE}/inv/{tokv}"); m.wait_for_selector("text=الإجمالي"); m.screenshot(path=str(OUT / "invoice_mobile.png"), full_page=True); mob.close()
    except Exception as e:
        step("video5", False, repr(e)); pg.screenshot(path=str(OUT / "fail5.png"))
    ctx.close(); b.close()
print("FAILED" if any(not ok for _, ok, _ in results) else "ALL PASS")
