"""Website audit: turns "your website is not good" into a measurable score with concrete reasons.

Score 0-100 (higher = better). Anything < 60 is a "poor website" lead for the upgrade pitch.
Checks (all cheap, one GET + one HEAD):
  - reachable (DNS/TLS/HTTP errors, 4xx/5xx)                       -40
  - no HTTPS or HTTP->HTTPS redirect missing                        -15
  - slow (> 3s first byte)                                          -10
  - not mobile-ready (no viewport meta)                             -15
  - no <title> / generic title                                      -5
  - no Arabic content when business is in KSA                       -5
  - free-builder / parked domain / "coming soon" / under construction -20
  - tiny page (< 1,500 chars of HTML)                               -10
  - no WhatsApp / phone link                                        -5
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field, asdict

import httpx

UA = "Mozilla/5.0 (Linux; Android 13; SM-S911B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Mobile Safari/537.36"
PARKED = ["domain is for sale", "buy this domain", "coming soon", "under construction", "قريباً", "قريبا", "تحت الإنشاء", "site is parked", "godaddy", "hostgator", "default web page", "welcome to nginx", "apache2 default", "index of /", "wix.com/website-template", "weebly", "site123", "webnode", "yolasite", "blogspot", "wordpress.com"]


@dataclass
class Audit:
    url: str
    final_url: str = ""
    ok: bool = False
    status: int = 0
    https: bool = False
    ttfb_ms: int = 0
    mobile_ready: bool = False
    title: str = ""
    has_arabic: bool = False
    has_whatsapp: bool = False
    size: int = 0
    score: int = 0
    issues: list[str] = field(default_factory=list)  # Arabic, ready to paste into the pitch

    def dict(self) -> dict:
        return asdict(self)


def normalize_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        raise ValueError("empty url")
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url
    return url


def grade(a: Audit, html: str) -> Audit:
    score = 100
    if not a.ok:
        score -= 40
        a.issues.append("الموقع لا يفتح أصلاً (خطأ أو صفحة غير موجودة)")
        a.score = max(score, 0)
        return a
    if not a.https:
        score -= 15; a.issues.append("الموقع بدون HTTPS — المتصفح يعرض تحذير \"غير آمن\"")
    if a.ttfb_ms > 3000:
        score -= 10; a.issues.append(f"بطيء جدًا ({a.ttfb_ms/1000:.1f} ثانية) — أغلب الزوار يغادرون بعد 3 ثوانٍ")
    if not a.mobile_ready:
        score -= 15; a.issues.append("غير متجاوب مع الجوال — ٩٠٪ من زوار السعودية يتصفحون من الجوال")
    if not a.title or len(a.title) < 4 or a.title.lower() in ("home", "index", "untitled", "welcome", "الرئيسية"):
        score -= 5; a.issues.append("بدون عنوان صفحة مناسب — يضعف الظهور في قوقل")
    if not a.has_arabic:
        score -= 5; a.issues.append("لا يوجد محتوى عربي — العميل السعودي يبحث بالعربي")
    low = html.lower()
    if any(k in low for k in PARKED):
        score -= 20; a.issues.append("الموقع مبني على قالب مجاني أو صفحة \"قريباً\" — يعطي انطباع غير احترافي")
    if a.size < 1500:
        score -= 10; a.issues.append("صفحة شبه فارغة — لا تعرض الخدمات ولا الأسعار ولا طريقة التواصل")
    if not a.has_whatsapp:
        score -= 5; a.issues.append("لا يوجد زر واتساب أو اتصال مباشر — العميل ما يقدر يتواصل بضغطة")
    a.score = max(score, 0)
    return a


async def audit(url: str, timeout: float = 12.0) -> Audit:
    a = Audit(url=url)
    try:
        target = normalize_url(url)
    except ValueError:
        a.issues.append("رابط غير صالح"); return grade(a, "")
    html = ""
    async with httpx.AsyncClient(follow_redirects=True, timeout=timeout, headers={"User-Agent": UA, "Accept-Language": "ar,en"}) as client:
        t0 = time.perf_counter()
        try:
            r = await client.get(target)
            a.ttfb_ms = int((time.perf_counter() - t0) * 1000)
            a.status = r.status_code
            a.final_url = str(r.url)
            a.ok = r.status_code < 400
            a.https = a.final_url.startswith("https://")
            html = r.text[:400_000] if a.ok else ""
        except Exception as e:  # DNS, TLS, timeout
            a.ttfb_ms = int((time.perf_counter() - t0) * 1000)
            a.issues.append(f"تعذّر الوصول: {type(e).__name__}")
            return grade(a, "")
    a.size = len(html)
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    a.title = re.sub(r"\s+", " ", m.group(1)).strip()[:120] if m else ""
    a.mobile_ready = bool(re.search(r"<meta[^>]+name=[\"']viewport[\"']", html, re.I))
    a.has_arabic = bool(re.search(r"[؀-ۿ]{3,}", html))
    a.has_whatsapp = bool(re.search(r"wa\.me|api\.whatsapp\.com|whatsapp://|href=[\"']tel:", html, re.I))
    return grade(a, html)


def audit_sync(url: str, timeout: float = 12.0) -> Audit:
    import asyncio
    return asyncio.run(audit(url, timeout))
