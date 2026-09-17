# Bassir Leads — نظام إدارة العملاء المحتملين والاشتراكات

Full-stack system for the "website-as-a-subscription" campaign (SAR 1,000/month).
**Stack:** FastAPI · SQLAlchemy 2 · PostgreSQL 16 · vanilla-JS SPA (RTL, mobile-first) · Docker Compose · Nginx.

## What it does
| Module | Features |
|---|---|
| Leads | CRUD, CSV import (Arabic/English headers), export, dedupe by phone (auto-normalized to 966…), filters, priority, follow-up dates, owner |
| Outreach | Template engine `{name} {city} {activity} {demo} {sender}`, one-tap WhatsApp (wa.me) with automatic activity log, status → contacted, follow-up scheduling, **daily send cap** (anti-ban), do-not-contact guard, optional WhatsApp Cloud API |
| Discover | Google Places (New) Text Search → businesses **without a website** with a phone number → save as leads (works once `GOOGLE_PLACES_API_KEY` is set) |
| Pipeline | new → contacted → replied → demo_sent → negotiating → won / lost / do_not_contact, full activity timeline (WhatsApp, calls, notes, status changes) |
| Clients & Billing | Convert lead → client, monthly invoices (15% VAT), idempotent `run-billing`, overdue detection, mark paid, MRR/ARR |
| Dashboard | MRR, active subscriptions, sends today vs cap, due follow-ups, reply & win rate, 14-day send chart, funnel |
| Admin | JWT auth (bcrypt), roles admin/agent, user management, settings (sender, demo URL, cap, price), password change |

## Security
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
Backups land in `./backups/` daily. Restore: `gunzip -c backups/bassir-YYYY-MM-DD.sql.gz | docker compose exec -T db psql -U bassir bassir`.

## Tests
```bash
python -m pytest -q tests     # 11 tests: auth, RBAC, phone normalization, CSV import, send + cap, billing, dashboard
```

## Daily workflow
1. **Discover** (or import CSV) → leads land as *new* with sector = your search term.
2. **Leads → "ابدأ الإرسال للجدد"** → open lead → template auto-selected by sector → **فتح واتساب** → WhatsApp opens with the message; the system logs it, sets *contacted*, schedules follow-up in 2 days.
3. **Dashboard → "المتابعات المستحقة"** every morning → follow-up template.
4. Reply → set status *replied / demo_sent / negotiating*; won → **تحويل لعميل** → first invoice issued automatically.
5. 1st of each month: **Settings/Clients → إصدار فواتير هذا الشهر**.

## CSV format
`name,phone,city,sector,instagram,website,maps_url,notes` — Arabic headers (الاسم, الجوال, المدينة, النشاط, ملاحظات) also accepted. Phones in any format (05…, +966…, 00966…).

## Roadmap hooks (already wired, just add keys in .env)
- `GOOGLE_PLACES_API_KEY` → Discover button turns on.
- `WHATSAPP_TOKEN` + `WHATSAPP_PHONE_ID` → sends go through Cloud API automatically (falls back to wa.me on error). Note: Cloud API free-form text needs a 24h customer window; for cold outreach use an approved Marketing template.
