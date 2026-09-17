# Campaign playbook — from zero to first paying client

## Day 0 — setup (≈ 1 hour)

1. **Google Places key** (free tier, 5,000 Text Search calls/month)
   - console.cloud.google.com → new project → *APIs & Services* → enable **Places API (New)** → *Credentials* → API key.
   - Restrict the key to the Places API. Put it in `.env` as `GOOGLE_PLACES_API_KEY=`.
2. **Deploy** (README → "Deploy on a VPS") or run locally. Set in `.env`:
   - `SENDER_NAME=` your name + brand (appears as `{sender}` in every message)
   - `DEMO_URL=https://YOUR-DOMAIN/demo/business` (or `/demo/restaurant`) — the bundled sample sites,
     personalised per lead automatically (`?n=name&c=city&p=phone&s=sector`).
   - `DAILY_SEND_CAP=20` for the first two weeks.
3. **WhatsApp**: install **WhatsApp Business** on the phone with the number you will use. Fill the
   business profile (name, category, address, hours, catalogue with the SAR 1,000 plan). Use the
   number normally for 1–2 weeks before outreach. Log in to WhatsApp Web on the same laptop as the CRM.

## Day 1 — build the list

```bash
source .venv/bin/activate
export GOOGLE_PLACES_API_KEY=...
# Tier-1 sectors, Riyadh + Jeddah, district level, ~600 calls:
python scripts/discover_bulk.py --cities الرياض جدة --tiers 1 --districts --max-calls 600 --mobile-only
# -> data/leads_no_website_<date>.csv   (import: Leads → استيراد CSV)
# -> data/leads_with_website_<date>.csv (next step)
python scripts/audit_sites.py data/leads_with_website_<date>.csv --max-score 60
# -> data/leads_weak_website_<date>.csv (import as well; {issues} is pre-filled)
```
`--mobile-only` keeps 9665… numbers so every wa.me link opens a real WhatsApp chat.
Landlines (9661…) are still valuable — call them instead.

## The proposal that closes (per lead, 2 minutes)

1. Lead drawer → **🎨 عرض مصمم**. Pull their Google photos (one click) or upload the logo + 3–5 photos you saved from Instagram.
2. Notes: two lines of what you noticed ("شعار أخضر غامق، متخصصون في التقويم، عرض للطلاب").
3. **تصميم العرض الآن** → open the link, skim 20 seconds (headline, prices) → edit anything via the API/PATCH if needed.
4. Send with the first-message template — `{proposal}` inserts the link. Then watch the drawer: *المشاهدات* tells you when they opened it; *أجاب العميل* tells you what they picked. A lead who taps "هذا الأسبوع" or "أبغى أبدأ" jumps to *negotiating* with today's follow-up — call them within the hour.

## Day 2+ — daily routine (45–60 min)

1. Dashboard → **المتابعات المستحقة** first (replies come from follow-ups, not first messages).
2. Leads → filter *new* → open a lead → check the Maps/Instagram link for 20 seconds (are they real?
   active? owner name visible?) → template auto-selected by sector → **فتح واتساب** → press send.
   Personalise one line if you saw something (a dish, a project, a review) — reply rates double.
3. Weak-website leads: press **🔍 فحص الموقع** once (it fills `{issues}`) → use the "موقعهم ضعيف" template.
4. Any reply → set status; any "إيقاف / لا / STOP" → **do_not_contact** and send the opt-out reply template.
5. Interested → send the demo link again + ask for logo/photos → **تحويل لعميل** → invoice auto-issued.

Best sending windows (KSA): Sun–Thu 10:00–13:00 and 16:30–21:00. Avoid Friday before 16:00.

## Message rules (keep the number alive)

- Identify yourself in the first line, always include the opt-out line, never send twice without a reply
  in between (the follow-up template is the second touch, max two follow-ups).
- Start at 20/day, +5 every 3 days up to 50. Stop for the day if two people report/block you.
- Vary text: the templates differ per sector and the demo link is unique per lead; add one personal line.
- Don't paste the same message into groups or broadcast lists. One chat at a time.

## Closing script (voice or text)

1. "شفتوا النموذج؟ وش رايكم بالتصميم؟" — get a reaction to the demo, not to the price.
2. Confirm what they need: menu / booking / services / gallery / map.
3. Price once, plainly: 1,000 ر.س شهريًا شامل كل شيء، بدون مقدم، تقدرون توقفون في أي وقت بإشعار شهر.
4. Objection → templates (السعر غالي / الإنستقرام يكفي). Offer annual: 10 months for 12.
5. Yes → send the closing template (what you need from them) + the first invoice. Site live in 48 h.

## Delivery checklist (48 h)

- Copy the matching demo, replace name/colours/logo/photos/menu, connect domain (.com or .sa), HTTPS.
- Google Business Profile: add the website URL — this is where the "found on Google" promise is fulfilled.
- Send the live link + a 30-second screen recording. Schedule the monthly content update reminder.
