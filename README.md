# Bassir Leads — نظام إدارة العملاء المحتملين والاشتراكات

Full-stack system for the "website-as-a-subscription" campaign (SAR 1,000/month).
**Stack:** FastAPI · SQLAlchemy 2 · PostgreSQL 16 · vanilla-JS SPA (RTL, mobile-first) · Docker Compose · Nginx.

## What it does
| Module | Features |
|---|---|
| Leads | CRUD, CSV import (Arabic/English headers), export, dedupe by phone (auto-normalized to 966…), filters, priority, follow-up dates, owner |
| Outreach | Template engine `{name} {city} {activity} {demo} {sender}`, one-tap WhatsApp (wa.me) with automatic activity log, status → contacted, follow-up scheduling, **daily send cap** (anti-ban), do-not-contact guard, optional WhatsApp Cloud API |
| Discover | Google Places (New) Text Search → businesses **without a website** with a phone number → save as leads (works once `GOOGLE_PLACES_API_KEY` is set). **Bulk:** `scripts/discover_bulk.py` runs the whole city × sector matrix in `data/targets.json` (district-level, budgeted against the 5,000 free calls/month) and writes import-ready CSVs |
| Website audit | `scripts/audit_sites.py` / **🔍 فحص الموقع** score an existing site 0–100 (HTTPS, mobile, speed, Arabic, parked/"coming soon", WhatsApp button) and fill the `{issues}` placeholder for the "your website is weak" pitch; filter leads by `has_website` / `max_score` |
| Designer agent | **🎨 عرض مصمم** per lead: upload the business's photos/logo or pull its own Google Maps photos, add what you learned, and a senior-designer agent on the Claude API (`app/services/designer.py`, strict JSON brief: palette from the photos, fonts, headline, services with prices, sections, offer) renders a premium proposal page at `/p/<token>`. No API key → curated sector presets. Any field is hand-editable afterwards |
| Client feedback | The proposal page has **tap-to-answer questions** (style swatches that re-theme the page live, what matters most, when to start, notes, "أبغى أبدأ"). Answers land in the lead's timeline, move the pipeline (negotiating / replied / lost) and set the follow-up. Views are counted ("he opened it 3 times") |
| WhatsApp buttons | Cloud API reply-buttons / list messages (`POST /api/whatsapp/leads/{id}/buttons`), marketing-template payloads, and a **webhook** (`/api/whatsapp/webhook`, signature-verified) that logs replies, maps button ids (`start*`, `later*`, `no*`, `stop*`) to pipeline moves and honours opt-outs |
| Live sites | **🚀 نشر الموقع**: the approved proposal becomes the client's real website at `/s/<slug>` or on **their own domain** pointed at this server (no ribbon, no questions, indexable, real hours/address/map/Instagram). WhatsApp / call / map clicks are tracked per site; this month's numbers show on the lead, on the Clients page, and in the `{stats}` / `{site}` placeholders of the monthly report template (the retention lever) |
| Payments | Every invoice has a public page `/inv/<token>` (simplified tax invoice: VAT number, 15% VAT, status). With Moyasar keys it embeds the hosted form (**Mada, Apple Pay, cards, STC Pay**); the callback and webhook re-verify the payment with the secret key and match the amount before marking paid. Without keys it shows your IBAN with an "I transferred" button that flags the invoice for confirmation. `{invoice}` placeholder + seeded reminder template; one-tap WhatsApp reminder per invoice on the Clients page |
| Morning digest | Dashboard card + one-tap "send to my WhatsApp": follow-ups due, leads in negotiation, proposals opened/answered yesterday, transfer notices to confirm, overdue invoices, open update requests. A built-in scheduler (no cron) runs daily after 08:00 Riyadh: marks overdue invoices, issues monthly invoices on day 1, stores the digest and sends it via the Cloud API when configured |
| Client updates | Each client gets a self-service page `/u/<token>` to send price/menu/photo/hours changes (quick chips + files). Requests land on the dashboard with photos, are logged on the lead, and are marked done with one tap. `{update_link}` placeholder is in the monthly report template |
| Agreements | Every client gets a subscription agreement at `/c/<token>` (default Arabic terms: scope, fee + VAT, monthly renewal, 30-day notice, late payment, content ownership, PDPL). Terms are editable in Settings with placeholders and a version; the client e-signs with name + checkbox and the system records time, IP, browser and the exact text accepted. Status shows on the Clients page; `{contract}` is in the closing template |
| Schema updates | On startup the app creates missing tables **and adds missing columns** to existing ones (`database.ensure_columns`), so upgrades need no manual SQL |
| Sample sites | `/demo/restaurant` and `/demo/business` — professional RTL sample websites, **personalised per lead** (`?n=name&c=city&p=phone&s=sector`); `{demo}` in templates becomes the lead's own link automatically |
| Pipeline | new → contacted → replied → demo_sent → negotiating → won / lost / do_not_contact, full activity timeline (WhatsApp, calls, notes, status changes) |
| Clients & Billing | Convert lead → client, monthly invoices (15% VAT), idempotent `run-billing`, overdue detection, mark paid, MRR/ARR |
| Dashboard | MRR, active subscriptions, sends today vs cap, due follow-ups, reply & win rate, 14-day send chart, funnel |
| Admin | JWT auth (bcrypt), roles admin/agent, user management, settings (sender, demo URL, cap, price), password change |

## Campaign docs
- `docs/MARKET_RESEARCH.md` — target sectors/cities, pricing position, unit economics, **compliance (CST anti-spam, PDPL, WhatsApp policy)**.
- `docs/PLAYBOOK.md` — day-0 setup, list building commands, daily routine, closing script, 48h delivery checklist.

## Build the lead list
```bash
export GOOGLE_PLACES_API_KEY=...            # Places API (New), free tier: 5,000 Text Search calls/month
python scripts/discover_bulk.py --cities الرياض جدة --tiers 1 --districts --max-calls 600 --mobile-only
python scripts/audit_sites.py data/leads_with_website_<date>.csv --max-score 60
# import both CSVs from Leads → استيراد CSV (or add --save to insert directly)
```

## Security
- Review of everything added after v1.0, with findings and fixes: `docs/SECURITY_REVIEW.md`
- Public pages: only http(s) URLs are stored or rendered in links; uploads are checked by magic bytes; public write endpoints are rate-limited per IP; webhooks fail closed without their secrets; payments are re-verified server-side
- bcrypt password hashing, HS256 JWT (12h default), login rate-limit (10 tries / 5 min / IP)
- Role-based authorization on every mutating admin endpoint
- Pydantic validation on all input; SQLAlchemy ORM only (no raw SQL)
- Security headers (nosniff, frame-deny, referrer, permissions), CORS locked to `ALLOWED_ORIGINS`
- Nginx rate-limit on `/api/`, TLS via Let's Encrypt, non-root container user, daily Postgres backups (30-day retention)

## Run locally (SQLite, 30 seconds)
```bash
pip install -r requirements.txt
cp .env.example .env            # edit ADMIN_PASSWORD at least
DATABASE_URL=sqlite:///./bassir.db uvicorn app.main:app --reload
# open http://127.0.0.1:8000  — API docs: /api/docs
```

## Deploy on a VPS (Docker)
```bash
git clone <repo> bassir-leads && cd bassir-leads
cp .env.example .env
# set: SECRET_KEY (openssl rand -hex 32), ADMIN_PASSWORD, POSTGRES_PASSWORD, ALLOWED_ORIGINS=https://leads.bassir.net
sed -i 's/leads.bassir.net/YOUR-DOMAIN/g' nginx/nginx.conf
docker compose up -d --build
# HTTPS (once DNS points to the server):
docker run --rm -v bassir-leads_certs:/etc/letsencrypt -v bassir-leads_certs-www:/var/www/certbot certbot/certbot certonly --webroot -w /var/www/certbot -d YOUR-DOMAIN --agree-tos -m you@bassir.net
# then uncomment the 443 block in nginx/nginx.conf and: docker compose restart nginx
```
Backups land in `./backups/` daily (database dump + uploads archive). Restore: `gunzip -c backups/bassir-YYYY-MM-DD.sql.gz | docker compose exec -T db psql -U bassir bassir`.

## Tests
```bash
python -m pytest -q tests     # 41 tests: auth, RBAC, phone normalization, CSV import, send + cap, billing, dashboard, site audit, demo pages
```

## Daily workflow
1. **Discover** (or import CSV) → leads land as *new* with sector = your search term.
2. **Leads → "ابدأ الإرسال للجدد"** → open lead → template auto-selected by sector → **فتح واتساب** → WhatsApp opens with the message; the system logs it, sets *contacted*, schedules follow-up in 2 days.
3. **Dashboard → "المتابعات المستحقة"** every morning → follow-up template.
4. Reply → set status *replied / demo_sent / negotiating*; won → **تحويل لعميل** → first invoice issued automatically.
5. 1st of each month: invoices are issued automatically by the scheduler (or **Clients → إصدار فواتير هذا الشهر** manually).

## CSV format
`name,phone,city,sector,instagram,website,maps_url,notes` — Arabic headers (الاسم, الجوال, المدينة, النشاط, ملاحظات) also accepted. Phones in any format (05…, +966…, 00966…).

## Template placeholders
`{name} {city} {activity}/{sector} {website} {issues} {demo} {proposal} {site} {stats} {invoice} {update_link} {contract} {sender}` — `{issues}` is the bullet list from the site audit, `{proposal}` is the designed proposal link (`{demo}` also resolves to it once a proposal exists, otherwise to the personalised sample site).

## Proposal workflow (what makes a client say yes)
1. Open the lead → **🎨 عرض مصمم** → upload their logo/photos or **جلب صورهم من قوقل** (their own Maps photos).
2. Add one line of notes (logo colours, specialty, an offer you saw) → **تصميم العرض الآن** (≈ 30–60 s with the API key).
3. Send the link with the first-message template (`{proposal}`). The page is `noindex`, personal, and tracks opens.
4. When the client taps answers, the lead jumps to *negotiating* with today's follow-up; the timeline shows exactly what they picked.

## WhatsApp Cloud API (buttons inside WhatsApp)
Reply buttons and lists only exist on the Cloud API (Meta Business Platform), not in the WhatsApp Business app. Setup: Meta Business → WhatsApp → add a phone number → `WHATSAPP_TOKEN` + `WHATSAPP_PHONE_ID`; Webhooks → callback `https://YOUR-DOMAIN/api/whatsapp/webhook`, verify token = `WHATSAPP_VERIFY_TOKEN`, subscribe to `messages`; set `WHATSAPP_APP_SECRET` so signatures are verified. Cold messages must be **approved Marketing templates** (create one with quick-reply buttons `start_now` / `later` / `no_thanks` and a URL button carrying the proposal token — `services.whatsapp.template_payload`). Free-form buttons (`/buttons`) work inside the 24-hour window after the client replies.

## Roadmap hooks (already wired, just add keys in .env)
- `GOOGLE_PLACES_API_KEY` → Discover button turns on.
- `WHATSAPP_TOKEN` + `WHATSAPP_PHONE_ID` → sends go through Cloud API automatically (falls back to wa.me on error). Note: Cloud API free-form text needs a 24h customer window; for cold outreach use an approved Marketing template.
