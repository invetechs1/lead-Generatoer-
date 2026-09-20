"""End-to-end walkthrough of Bassir Leads with video recording (Playwright).

    pip install playwright && playwright install chromium
    DATABASE_URL=sqlite:///./e2e.db PUBLIC_BASE_URL=http://127.0.0.1:8765 uvicorn app.main:app --port 8765 &
    mkdir e2e_photos   # put 4 jpg photos named 1.jpg..4.jpg
    python scripts/e2e_record.py      # videos land in ./e2e_out/v1 v2 v3 (webm); results in e2e_out/results.json

Video 1 (crm):      login → dashboard → add lead → CSV import → open lead → audit → WhatsApp send → templates → settings
Video 2 (proposal): designer drawer → upload photos → generate → client opens page (desktop) → taps answers → CRM shows answers → convert → billing → dashboard
Video 3 (mobile):   the proposal page on a phone viewport
"""
import io, json, sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

BASE = "http://127.0.0.1:8765"
OUT = Path("./e2e_out"); OUT.mkdir(exist_ok=True)
import os
CHROME = os.environ.get("CHROME_PATH")  # None = Playwright's own chromium
ADMIN = ("admin@bassir.net", "ChangeMe123!")
results = []

def step(name, ok=True, note=""):
    results.append((name, ok, note)); print(("PASS" if ok else "FAIL"), name, note, flush=True)

def pause(pg, ms=900): pg.wait_for_timeout(ms)

def login(pg):
    pg.goto(BASE); pause(pg, 800)
    pg.fill("#em", ADMIN[0]); pg.fill("#pw", ADMIN[1]); pause(pg, 400)
    pg.click("#go"); pg.wait_for_selector("text=MRR", timeout=10000); pause(pg, 1200)

with sync_playwright() as p:
    b = p.chromium.launch(executable_path=CHROME, args=["--no-sandbox"], slow_mo=120) if CHROME else p.chromium.launch(slow_mo=120)

    # ---------------- VIDEO 1: CRM ----------------
    ctx = b.new_context(viewport={"width": 1280, "height": 800}, record_video_dir=str(OUT / "v1"), record_video_size={"width": 1280, "height": 800}, locale="ar-SA")
    pg = ctx.new_page()
    try:
        login(pg); step("login + dashboard")
        pg.click("a:has-text('العملاء')"); pg.wait_for_selector("#list"); pause(pg)
        pg.click("#add"); pause(pg, 600)
        pg.fill("#n", "مطعم بيت المندي"); pg.fill("#p", "0551234567"); pg.fill("#c", "الرياض"); pg.fill("#s", "مطاعم"); pg.fill("#ig", "baitalmandi"); pause(pg, 500)
        pg.click("#sv"); pg.wait_for_selector("text=مطعم بيت المندي"); step("add lead manually"); pause(pg)
        csv = "name,phone,city,sector,website,site_score,site_issues,rating,reviews\nعيادة نور لطب الأسنان,0559876543,جدة,عيادات,,,,4.9,140\nمكتب الأمل للمقاولات,0501112233,الرياض,مقاولات,amal-contracting.example,35,\"بدون HTTPS\nغير متجاوب مع الجوال\nصفحة قريباً\",4.4,52\nمكرر,0551234567,الرياض,مطاعم,,,,,\n"
        pg.set_input_files("#file", {"name": "leads.csv", "mimeType": "text/csv", "buffer": csv.encode("utf-8")}); pg.wait_for_selector("text=أُضيف 2", timeout=8000); step("CSV import (2 added, 1 duplicate skipped)"); pause(pg, 1200)
        pg.click(".lead:has-text('مكتب الأمل')"); pg.wait_for_selector("text=إرسال واتساب"); pause(pg, 1200)
        pg.click("#aud"); pg.wait_for_selector("text=نتيجة الموقع", timeout=30000); step("website audit runs from the drawer"); pause(pg, 1200)
        pg.wait_for_selector("#tp")
        opts = pg.locator("#tp option").all_text_contents(); idx = [i for i, t in enumerate(opts) if "ضعيف" in t][0]
        pg.select_option("#tp", index=idx); pause(pg, 1500)
        preview = pg.locator("#pv").inner_text(); assert "amal-contracting.example" in preview and "• " in preview, preview; step("weak-website template renders {website} and {issues}")
        pg.mouse.wheel(0, 400); pause(pg, 800)
        with ctx.expect_page() as newp:
            pg.click("#send")
        wa = newp.value; pause(pg, 1500); wa.close()
        pg.wait_for_selector(".lead:has-text('مكتب الأمل') .tag.contacted", timeout=8000); step("WhatsApp send opens wa.me (blocked in this sandbox) and the lead becomes contacted"); pause(pg)
        pg.click("a:has-text('الرسائل')"); pg.wait_for_selector("text=رسالة أولى"); step("templates page"); pause(pg, 1500)
        pg.click("a:has-text('الإعدادات')"); pg.wait_for_selector("#sp"); pg.fill("#sp", "966555000111"); pg.fill("#sn", "م. يحيى — Bassir IT"); pg.click("#sv"); pg.wait_for_selector("text=تم الحفظ"); step("settings saved (sales WhatsApp number)"); pause(pg, 1200)
    except Exception as e:
        step("video1", False, repr(e)); pg.screenshot(path=str(OUT / "fail1.png"))
    ctx.close()

    # ---------------- VIDEO 2: PROPOSAL + CLOSE ----------------
    ctx = b.new_context(viewport={"width": 1280, "height": 800}, record_video_dir=str(OUT / "v2"), record_video_size={"width": 1280, "height": 800}, locale="ar-SA")
    pg = ctx.new_page()
    try:
        login(pg); pg.click("a:has-text('العملاء')"); pg.wait_for_selector("#list"); pause(pg)
        pg.click(".lead:has-text('بيت المندي')"); pg.wait_for_selector("#prop"); pause(pg, 800)
        pg.click("#prop"); pg.wait_for_selector("#gen"); pause(pg, 1000)
        pg.set_input_files("#up", [f"./e2e_photos/{i}.jpg" for i in (1, 2, 3, 4)]); pg.wait_for_selector("text=صور المنشأة (4)", timeout=10000); step("4 photos uploaded"); pause(pg, 1200)
        pg.select_option("#kind", "restaurant"); pg.fill("#notes", "مندي على الفحم، جلسات عائلية، توصيل لكل الأحياء"); pause(pg, 800)
        pg.click("#gen"); pg.wait_for_selector("text=الرابط الحالي", timeout=60000); step("proposal generated (preset mode, no API key in this sandbox)"); pause(pg, 1500)
        url = pg.locator("input[readonly]").input_value(); assert "/p/" in url
        pg.mouse.wheel(0, 300); pause(pg, 800)
        # the client opens the link
        client = ctx.new_page(); client.goto(url); client.wait_for_selector("text=أبغى أبدأ"); pause(client, 1500)
        for y in (500, 900, 900, 900, 900, 900, 900): client.mouse.wheel(0, y); pause(client, 700)
        client.locator("#ask").scroll_into_view_if_needed(); pause(client, 800)
        client.click("#sw button:has-text('فاخر')"); pause(client, 900); client.click("#sw button:has-text('هادئ')"); pause(client, 900)
        client.click("#pri button:has-text('حجز/طلب عبر واتساب')"); client.click("#pri button:has-text('معرض صور احترافي')"); pause(client, 600)
        client.click("#tim button:has-text('هذا الأسبوع')"); client.fill("#notes", "أبغى المنيو بالصور وألوان الشعار البني"); pause(client, 800)
        client.click("button:has-text('إرسال رأيي')"); client.wait_for_selector("text=شكرًا لكم"); step("client tapped answers on the proposal page"); pause(client, 1500); client.close()
        # back in CRM: answers + timeline
        pg.bring_to_front(); pg.keyboard.press("Escape"); pg.click(".close"); pause(pg, 500)
        pg.click(".lead:has-text('بيت المندي')"); pg.wait_for_selector("#prop"); pause(pg, 600)
        pg.click("#prop"); pg.wait_for_selector("text=أجاب العميل", timeout=8000); step("CRM shows the client's answers and view count"); pause(pg, 2500)
        pg.click(".close"); pause(pg, 400)
        pg.click(".lead:has-text('بيت المندي')"); pg.wait_for_selector("text=السجل"); pg.locator("text=السجل").scroll_into_view_if_needed(); pause(pg, 1800)
        assert pg.locator("text=هذا الأسبوع").count() >= 1 or pg.locator("text=this_week").count() >= 1; step("timeline logs answers + page opens")
        tag = pg.locator("#st").input_value(); assert tag == "negotiating"; step("status auto-moved to negotiating")
        pg.click("#conv"); pg.wait_for_selector("#co"); pause(pg, 800); pg.fill("#cn", "أبو فهد"); pause(pg, 400)
        pg.click("#sv"); pg.wait_for_selector("text=BSR-", timeout=8000); step("converted to client; first invoice issued"); pause(pg, 1500)
        pg.click("button.pay >> nth=0"); pg.wait_for_selector("text=سُجّل الدفع"); step("invoice marked paid"); pause(pg, 1200)
        pg.click("a:has-text('الرئيسية')"); pg.wait_for_selector("text=MRR"); pause(pg, 2500); step("dashboard shows MRR and funnel")
    except Exception as e:
        step("video2", False, repr(e)); pg.screenshot(path=str(OUT / "fail2.png"))
    ctx.close()

    # ---------------- VIDEO 3: MOBILE PROPOSAL ----------------
    ctx = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True, record_video_dir=str(OUT / "v3"), record_video_size={"width": 390, "height": 844}, locale="ar-SA")
    pg = ctx.new_page()
    try:
        pg.goto(url); pg.wait_for_selector("text=أبغى أبدأ"); pause(pg, 1500)
        for _ in range(14): pg.mouse.wheel(0, 600); pause(pg, 550)
        pg.locator("#sw button:has-text('جريء')").click(); pause(pg, 1200)
        pg.locator("#ask").scroll_into_view_if_needed(); pause(pg, 800)
        pg.locator(".pricecard button").scroll_into_view_if_needed(); pause(pg, 600)
        pg.locator(".pricecard button").click(); pg.wait_for_selector("text=نبدأ فورًا"); step("mobile: 'أبغى أبدأ' flow"); pause(pg, 1800)
    except Exception as e:
        step("video3", False, repr(e)); pg.screenshot(path=str(OUT / "fail3.png"))
    ctx.close(); b.close()

json.dump(results, open(OUT / "results.json", "w"), ensure_ascii=False, indent=1)
print("FAILED" if any(not ok for _, ok, _ in results) else "ALL PASS")
