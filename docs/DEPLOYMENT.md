# Bassir Leads — Server Deployment Guide (for the developer)

**Goal:** run the Bassir Leads system (FastAPI + PostgreSQL + Nginx, Docker Compose) on a public server with HTTPS, so the sales team can log in from phone/laptop and clients can open proposal links like `https://leads.YOUR-DOMAIN.com/p/<token>`.

Estimated time: **45–60 minutes** on a fresh server.

---

## 0. What you get

| Component | Container | Notes |
|---|---|---|
| API + web app | `api` (Python 3.12, uvicorn) | Serves the SPA, `/api/*`, proposal pages `/p/*`, sample sites `/demo/*`, uploads `/uploads/*` |
| Database | `db` (PostgreSQL 16) | Data in the `pgdata` volume |
| Reverse proxy | `nginx` (1.27) | Ports 80/443, rate limit on `/api/`, Let's Encrypt |
| Backups | `backup` | Daily `pg_dump` to `./backups/`, 30-day retention |

Source: repository branch `claude/b2b-website-sales-outreach-en81v1` (merge to `main` when ready).

---

## 1. Prerequisites

- A VPS with **2 vCPU / 2 GB RAM / 20 GB disk** minimum (Ubuntu 22.04 or 24.04 LTS recommended). Hetzner, DigitalOcean, Contabo, AWS Lightsail, or any Saudi provider all work.
- A domain or subdomain, e.g. `leads.example.com`, with DNS **A record → server IP** (and AAAA if IPv6). Wait until `ping leads.example.com` resolves before step 5.
- Ports **80 and 443** open in the provider firewall.
- SSH root (or sudo) access.

Optional API keys (the system works without them, features switch on when added):

| Key | Enables | Where to get it |
|---|---|---|
| `GOOGLE_PLACES_API_KEY` | Lead discovery from Google Maps + pulling a business's photos | Google Cloud Console → enable **Places API (New)** → Credentials → API key. Restrict it to the Places API. Free tier: 5,000 Text Search calls/month |
| `ANTHROPIC_API_KEY` | The designer agent (custom design brief per lead) | console.anthropic.com → API keys |
| `MOYASAR_PUBLISHABLE_KEY`, `MOYASAR_SECRET_KEY`, `MOYASAR_WEBHOOK_SECRET` | Online payment of invoices (Mada, Apple Pay, cards) | moyasar.com → Dashboard → API keys / Webhooks (see section 8c) |
| `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_ID`, `WHATSAPP_VERIFY_TOKEN`, `WHATSAPP_APP_SECRET` | Sending through WhatsApp Cloud API, interactive buttons, receiving replies | Meta for Developers → WhatsApp Business Platform (see section 8) |

---

## 2. Server preparation (Ubuntu)

```bash
# as root
apt update && apt -y upgrade
apt -y install ca-certificates curl git ufw

# Docker Engine + Compose plugin (official script)
curl -fsSL https://get.docker.com | sh
docker --version && docker compose version

# firewall
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

# (recommended) non-root deploy user
adduser --disabled-password --gecos "" deploy
usermod -aG docker deploy
```

---

## 3. Get the code

```bash
su - deploy
git clone https://github.com/invetechs1/lead-Generatoer-.git bassir-leads
cd bassir-leads
git checkout claude/b2b-website-sales-outreach-en81v1   # or main after merge
```

---

## 4. Configure `.env`

```bash
cp .env.example .env
nano .env
```

Set **every** line below. Generate secrets with `openssl rand -hex 32`.

```ini
# ---- Core ----
APP_NAME=Bassir Leads
SECRET_KEY=<openssl rand -hex 32>                 # JWT signing key — never reuse the example
ACCESS_TOKEN_MINUTES=720
DATABASE_URL=postgresql+psycopg2://bassir:<DBPASS>@db:5432/bassir
POSTGRES_PASSWORD=<DBPASS>                        # must match the password inside DATABASE_URL
ALLOWED_ORIGINS=https://leads.example.com         # exact public origin, no trailing slash

# ---- First admin (created on first boot only) ----
ADMIN_EMAIL=admin@example.com
ADMIN_PASSWORD=<strong password>                  # change it after first login from Settings
ADMIN_NAME=Eng. Yahya

# ---- Sales defaults ----
DEFAULT_PRICE_SAR=1000
DAILY_SEND_CAP=20                                 # raise gradually (see PLAYBOOK.md)
SENDER_NAME=Eng. Yahya — Bassir IT
DEMO_URL=https://leads.example.com/demo/business  # fallback sample site; proposals override it
PUBLIC_BASE_URL=https://leads.example.com         # used to build /p/<token> links sent to clients
UPLOAD_DIR=uploads                                # docker-compose overrides this to /srv/uploads (volume)

# ---- Optional integrations ----
GOOGLE_PLACES_API_KEY=
ANTHROPIC_API_KEY=
DESIGN_MODEL=claude-opus-5
WHATSAPP_TOKEN=
WHATSAPP_PHONE_ID=
WHATSAPP_VERIFY_TOKEN=<openssl rand -hex 16>      # you choose it; Meta echoes it during webhook verification
WHATSAPP_APP_SECRET=
MOYASAR_PUBLISHABLE_KEY=
MOYASAR_SECRET_KEY=
MOYASAR_WEBHOOK_SECRET=
```

Then point Nginx at the domain:

```bash
sed -i 's/leads.bassir.net/leads.example.com/g' nginx/nginx.conf
```

---

## 5. First start (HTTP)

```bash
docker compose up -d --build
docker compose ps                      # all four services "running"/"healthy"
docker compose logs -f api             # wait for "Application startup complete"
curl -s http://leads.example.com/api/health   # → {"ok":true,"app":"Bassir Leads"}
```

Open `http://leads.example.com`, log in with `ADMIN_EMAIL` / `ADMIN_PASSWORD`.

Tables are created automatically on first boot (`Base.metadata.create_all`) and the admin user + message templates are seeded.

---

## 6. HTTPS (Let's Encrypt)

Run once (DNS must already point to the server):

```bash
docker run --rm \
  -v bassir-leads_certs:/etc/letsencrypt \
  -v bassir-leads_certs-www:/var/www/certbot \
  certbot/certbot certonly --webroot -w /var/www/certbot \
  -d leads.example.com --agree-tos -m you@example.com --non-interactive
```

> The volume prefix is the folder name (`bassir-leads_`). Check with `docker volume ls` if you cloned into a different folder.

Then in `nginx/nginx.conf`:

1. Uncomment the whole `server { listen 443 ssl http2; ... }` block.
2. In the port-80 block, replace the two `location` proxy blocks with a redirect (keep the acme-challenge location):

```nginx
server {
    listen 80;
    server_name leads.example.com;
    location /.well-known/acme-challenge/ { root /var/www/certbot; }
    location / { return 301 https://$host$request_uri; }
}
```

Reload:

```bash
docker compose restart nginx
curl -sI https://leads.example.com/api/health | head -1    # HTTP/2 200
```

Auto-renewal (every 12 hours; certbot only renews when < 30 days remain):

```bash
crontab -e
# add:
0 */12 * * * cd /home/deploy/bassir-leads && docker run --rm -v bassir-leads_certs:/etc/letsencrypt -v bassir-leads_certs-www:/var/www/certbot certbot/certbot renew --quiet && docker compose exec nginx nginx -s reload
```

---

## 7. Post-deploy checklist (do these in the app)

1. **Settings** → change the admin password; set **Sales WhatsApp number** (`9665xxxxxxxx`, the number clients will contact from proposal pages); confirm sender name, demo URL, daily cap.
2. **Users** → create an `agent` account for each salesperson (agents cannot delete leads or change settings).
3. Open `https://leads.example.com/demo/restaurant?n=Test&c=Riyadh&p=966500000000` — the sample site must load with fonts.
4. Create a test lead → **🎨 عرض مصمم** → generate → open the `/p/<token>` link on a phone → tap the questions → the lead's timeline must show the answers.
5. Send a test WhatsApp from the lead drawer (opens `wa.me`) — verify the message text and the `{proposal}` link.

---

## 8. WhatsApp Cloud API (optional — interactive buttons inside WhatsApp)

Without this the app opens `wa.me` links (one tap per message from the salesperson's own WhatsApp). With it, the app can send reply-button messages and receive the client's taps.

1. **Meta for Developers** → create a Business-type app → add **WhatsApp** product → add/verify a phone number that is *not* registered in the WhatsApp app.
2. Copy **Phone number ID** → `WHATSAPP_PHONE_ID`; create a **permanent System User token** with `whatsapp_business_messaging` + `whatsapp_business_management` → `WHATSAPP_TOKEN`.
3. App settings → Basic → **App secret** → `WHATSAPP_APP_SECRET`.
4. WhatsApp → Configuration → **Webhook**: Callback URL `https://leads.example.com/api/whatsapp/webhook`, Verify token = the value of `WHATSAPP_VERIFY_TOKEN` in `.env` → Verify and save → subscribe to the **messages** field.
5. Create a **Marketing template** (Arabic) for the cold first message with quick-reply buttons whose payloads are `start_now`, `later`, `no_thanks`, and a URL button `https://leads.example.com/p/{{1}}`. Wait for approval. The app builds the payload with `services.whatsapp.template_payload`.
6. `docker compose up -d` after editing `.env`. Test: reply to a message from a test phone; the reply must appear in that lead's timeline within seconds.

Button-id conventions understood by the webhook: `start*`/`yes*` → negotiating (follow-up today), `later*` → replied (follow-up in 7 days), `no*` → lost, `stop*` or the words إيقاف / STOP → do-not-contact.

---

## 8b. Client websites on their own domains

A published proposal is served at `https://leads.example.com/s/<slug>` immediately. To serve it on the client's own domain (e.g. `baitalmandi.com`):

1. In the lead's proposal drawer set **نطاق العميل** = `baitalmandi.com` and publish.
2. Client's DNS: `A` record `@` → server IP (and `www` → same, or CNAME to `@`).
3. Nginx must accept that host. Edit `nginx/nginx.conf`: change `server_name leads.example.com;` to `server_name leads.example.com baitalmandi.com www.baitalmandi.com;` in **both** the 80 and 443 blocks (or use `server_name _;` on the 80 block to accept any domain and redirect).
4. Certificate for the new domain (repeat per client domain, or add `-d` flags):
   ```bash
   docker run --rm -v bassir-leads_certs:/etc/letsencrypt -v bassir-leads_certs-www:/var/www/certbot certbot/certbot certonly --webroot -w /var/www/certbot -d baitalmandi.com -d www.baitalmandi.com --agree-tos -m you@example.com --non-interactive
   ```
   then add a second `server { listen 443 ssl http2; server_name baitalmandi.com www.baitalmandi.com; ssl_certificate /etc/letsencrypt/live/baitalmandi.com/fullchain.pem; ssl_certificate_key /etc/letsencrypt/live/baitalmandi.com/privkey.pem; location / { proxy_pass http://api:8000; proxy_set_header Host $host; proxy_set_header X-Forwarded-Proto https; } }` block and `docker compose restart nginx`.
5. The app routes by the `Host` header, so no app restart is needed. Verify: `curl -s https://baitalmandi.com | grep -c data-ev` → a number > 0.

> With more than ~10 client domains, switch Nginx to a wildcard-free automatic setup (Caddy or nginx-proxy + acme-companion) so certificates are issued on demand. Not needed at the start.

## 8c. Online payments (Moyasar — optional)

Without keys, invoice pages show the IBAN entered in Settings and an "I transferred" button. To accept Mada / Apple Pay / cards:

1. Create a Moyasar account (moyasar.com), complete business verification, and enable Mada + Apple Pay in the dashboard.
2. Dashboard → API keys: copy the **publishable** and **secret** keys → `MOYASAR_PUBLISHABLE_KEY`, `MOYASAR_SECRET_KEY` in `.env`. Use the test keys first (`pk_test_…`, `sk_test_…`).
3. Dashboard → Webhooks: URL `https://leads.example.com/api/payments/moyasar/webhook`, event **payment_paid**, set a secret token → `MOYASAR_WEBHOOK_SECRET`.
4. Apple Pay: register the domain in the Moyasar dashboard (it hosts the verification file through the hosted form) — follow Moyasar's Apple Pay guide for the domain association step.
5. `docker compose up -d`, then open any unpaid invoice link from the Clients page (**رابط**) and pay with a Moyasar test card. The invoice must flip to مدفوعة and the lead's timeline must show the payment.

The server never trusts the redirect: every callback and webhook fetches the payment with the secret key and checks status, currency and the exact amount before marking the invoice paid.

## 9. Building the lead list on the server

```bash
docker compose exec api python scripts/discover_bulk.py --cities الرياض جدة --tiers 1 --districts --max-calls 600 --mobile-only --save
docker compose exec api python scripts/audit_sites.py --db --max-score 60
```

`--save` inserts directly into the database. Without it the CSVs land in `/srv/data/` inside the container; copy them out with `docker compose cp api:/srv/data/. ./data/` and import from the UI. Keep `--max-calls` under the monthly free quota (5,000).

---

## 9b. Daily automation

The `api` container runs a built-in scheduler thread (`SCHEDULER_ENABLED=true` by default). Every day after `DIGEST_HOUR` (08:00 Riyadh) it marks overdue invoices, issues the monthly invoices on the 1st, builds the morning digest shown on the dashboard, and sends it to the sales WhatsApp number when the Cloud API is configured. No cron needed. Run it manually from the dashboard (**تشغيل مهام اليوم الآن**) or `POST /api/jobs/run`. If you ever run two `api` replicas, keep the scheduler on only one (`SCHEDULER_ENABLED=false` on the others).

## 10. Operations

**Update to a new version**
```bash
cd ~/bassir-leads && git pull
docker compose up -d --build
docker compose logs --tail=50 api
```
New tables **and new columns** are created automatically on startup (`database.ensure_columns` adds missing columns with their defaults; it never drops or changes existing ones). Watch the first lines of `docker compose logs api` after an update: `schema: added columns ...`.

**Backups** — `./backups/bassir-YYYY-MM-DD.sql.gz` daily; copy them off-server (rclone/S3/cron scp). Uploaded photos live in the `uploads` Docker volume — include it in off-server backups:
```bash
docker run --rm -v bassir-leads_uploads:/u -v $PWD/backups:/b alpine tar czf /b/uploads-$(date +%F).tgz -C /u .
```

**Restore**
```bash
gunzip -c backups/bassir-2026-09-17.sql.gz | docker compose exec -T db psql -U bassir bassir
```

**Logs / health**
```bash
docker compose logs -f api nginx
curl -s https://leads.example.com/api/health
```

**Run the test suite** (before deploying a change)
```bash
docker compose run --rm api python -m pytest -q tests
```

---

## 11. Security checklist

- [ ] `SECRET_KEY`, `POSTGRES_PASSWORD`, `ADMIN_PASSWORD` are unique and not the example values.
- [ ] `ALLOWED_ORIGINS` is exactly the HTTPS origin.
- [ ] Port 5432 is **not** exposed (compose keeps it internal — do not add `ports:` to `db`).
- [ ] HTTPS enabled, HTTP redirects, HSTS header on (in the 443 block).
- [ ] `.env` permissions `chmod 600 .env`; never commit it.
- [ ] Google API key restricted to Places API; WhatsApp token is a System User token, not a temporary one.
- [ ] Backups copied off-server weekly and a restore tested once.
- [ ] Keep `DAILY_SEND_CAP` conservative — see `docs/MARKET_RESEARCH.md` §6 for CST/PDPL obligations (opt-out handling is built in; do not disable it).

---

## 12. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `api` restarts, log says `password authentication failed` | `POSTGRES_PASSWORD` ≠ password inside `DATABASE_URL`. Fix `.env`, then `docker compose down -v` **only if the DB is still empty**, else just fix and `up -d` |
| Login works on HTTP but not HTTPS | `ALLOWED_ORIGINS` still `http://…` |
| Proposal links show `http://127.0.0.1` or wrong host | `PUBLIC_BASE_URL=https://leads.example.com` and restart `api` |
| Photo upload returns 413 | Nginx `client_max_body_size` (set to 50m in repo); check you restarted nginx after editing |
| "Designer" takes long / 504 | Normal 30–90 s; `proxy_read_timeout 180s` is set for `/api/`. If still 504, confirm the 443 block also has it |
| `GOOGLE_PLACES_API_KEY is not set` in UI | Key missing in `.env`, or `api` not restarted after editing |
| Webhook verification fails in Meta | Verify token mismatch, or HTTPS not active yet — Meta requires a valid certificate |
| Fonts missing on proposal pages | Server outbound HTTPS blocked to fonts.googleapis.com; allow it (pages degrade to system fonts otherwise) |
