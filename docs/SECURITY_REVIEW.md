# Security & code-quality review — everything added since the v1.0 import

Scope: commits `18db054..HEAD` (bulk discovery, website audit, designer agent, proposal pages, live sites, payments,
WhatsApp Cloud API, digest/scheduler, client updates). Method: manual review of every unauthenticated endpoint and every
template that renders user- or AI-supplied data, plus `ruff` (pyflakes/bugbear/bandit rules) and the test suite.
Date: 2026-10-17.

## Findings and fixes

| # | Severity | Finding | Fix (commit on this branch) |
|---|---|---|---|
| 1 | **High** | WhatsApp webhook accepted unsigned posts when `WHATSAPP_APP_SECRET` was empty — anyone could inject fake replies and flip leads to *do_not_contact* / *lost* | Fail closed: signature check returns false without a secret and the endpoint answers 503 until it is set; startup warning when a token exists without the secret |
| 2 | **High** | Moyasar payment match accepted a paid payment with **no** `invoice_token` metadata — a real payment for another merchant invoice of the same amount could have marked an invoice paid via the callback URL | Token must equal the invoice token, always |
| 3 | **High** | `javascript:` / `data:` URLs could reach `href` attributes (lead `maps_url`/`website`, live-site `maps_url`, client `site_url`) → stored XSS on client-facing pages | Schema validators accept only `http(s)` (bare domains get `https://`); Instagram stored as a handle; `safe_href` template filter as a second layer |
| 4 | **High** | Designer brief values (palette, fonts) from the AI or the PATCH endpoint were injected into `<style>` and the Google Fonts URL unvalidated → CSS injection / broken pages | Hex-colour validation, font allow-list, hero index bounds in `designer.Brief` |
| 5 | Medium | Uploads were checked by extension only — an HTML/SVG payload renamed `.png` would be stored under `/uploads` and served | Magic-byte check (JPEG/PNG/WebP/PDF) + size cap in a shared `upload_ok()`; SVG never allowed |
| 6 | Medium | Public write endpoints (proposal answers, site events, transfer notice, client updates, webhooks) had no rate limit → activity spam / DB growth | In-memory per-IP sliding-window limiter (`common.rate_limit`), honours `X-Forwarded-For` behind nginx; 429 on excess |
| 7 | Medium | `/demo/{kind}` built a path from the raw parameter (`.html` appended, so only HTML files, but `..` was honoured) | `kind` restricted to `[a-z0-9-]`, fallback to the generic page |
| 8 | Medium | Custom-domain lookup cache grew without bound on arbitrary `Host` headers | Bounded cache (2,000 entries), hosts > 253 chars rejected |
| 9 | Medium | `live` publish payload was an untyped dict rendered by the template (malformed `hours` → 500; unvalidated URLs) | Typed `LiveIn` model: hours rows `[label, value]`, URL/handle/phone validators |
| 10 | Low | Inline `<script>` on the invoice page interpolated settings via HTML-escaping (an apostrophe in the sender name would break the Moyasar init) | All script-context values rendered with `tojson` |
| 11 | Low | Default `SECRET_KEY` / `ADMIN_PASSWORD` / `ALLOWED_ORIGINS=*` could reach production silently | Loud `SECURITY WARNING` lines at startup |
| 12 | Quality | `_setting`, `_base_url`, `TEMPLATES` duplicated in four routers; `raise` inside `except` without `from`; unused imports; `zip()` without `strict` | Consolidated in `app/common.py`; lint clean for F/B904/B905/E401 |

## Verified as already sound
- Tokens for proposals, invoices and update pages: `secrets.token_urlsafe(18)` (144 bits), looked up by exact match.
- Jinja2 autoescape is on for all HTML templates (Starlette default); values in `<script>` use `tojson`.
- Uploads are served by `StaticFiles` (no directory listing) under `/uploads` only; file names are server-generated.
- Admin-only: user management, settings, delete lead, run-billing, void invoice, run jobs. Agents cannot escalate.
- JWT HS256 with 12 h expiry; login rate-limited (10 / 5 min / IP) in app and `/api/` rate-limited in nginx.
- Database access is ORM-only; `ensure_columns` builds DDL from model metadata, never from input.
- Moyasar: redirect parameters are never trusted; status, currency, amount and token are re-verified with the secret key; marking paid is idempotent.
- Secrets are read from `.env` only and never logged; `.env`, databases and uploads are git-ignored.

## Residual risks / recommendations (not code)
- The in-memory rate limiter is per process. Fine for one `api` container; use nginx `limit_req` on the public paths too if you scale out.
- No Content-Security-Policy header yet: templates use inline scripts/styles. Adding a nonce-based CSP is a reasonable next hardening step.
- Published client sites are indexable by design; proposals, invoices and update pages are `noindex` but reachable by anyone with the link — treat the links as private.
- Compliance (CST anti-spam, PDPL) is covered in `MARKET_RESEARCH.md` §6 and is operational, not technical.

## Test coverage added
`tests/test_security.py`: safe-href filter, URL/handle validators, magic-byte checks, brief CSS/font injection, strict payment token,
API-level URL validation for leads and live sites, demo path sanitisation, webhook fail-closed, rate limits (per IP), disguised
uploads on both upload endpoints, startup warnings. Full suite: 40 tests.
