# Market investigation — "Website-as-a-subscription" for Saudi SMEs (SAR 1,000/month)

*Prepared 2026-09-17. Sources at the end. Numbers marked ≈ are estimates, not measured.*

## 1. The opportunity in one paragraph

Saudi Arabia has ~1.3M+ registered SMEs and one of the highest social-media penetration rates on earth
(Instagram ≈ 73 %, Snapchat ≈ 70 % of the population). A very large share of small businesses run
**exclusively** on Instagram / Snapchat / WhatsApp and have no website at all, or a parked / template
site nobody maintains. Meanwhile customers discover local businesses on **Google Maps and Google Search**,
where an Instagram account does not rank. That gap ("everyone searches on Google, you only exist on
Instagram") is the whole pitch. Monsha'at is actively pushing SME digitisation (SAR 800M disbursed,
30,000-SME Zoho programme), so the market is primed and the message is not new to owners.

## 2. Who to target (ranked)

| Tier | Sector (Arabic search terms in `data/targets.json`) | Why they convert | Watch-out |
|---|---|---|---|
| 1 | Clinics: dental, derma, physio, nutrition | High ticket per patient, patients Google first, booking currently by DM | Some belong to groups with an agency; skip hospitals |
| 1 | Beauty: مركز تجميل, صالون, ليزر, سبا | Instagram-native, DMs overflow, want bookings | Female-owned salons: use formal tone, no calls, WhatsApp only |
| 1 | Contractors & finishing: مقاولات, ترميم, تشطيبات, عوازل | B2B buyers verify company on Google before signing; site = trust | Owner often on-site; reply late, follow-up on day 3 and 7 |
| 1 | Real-estate offices & developers | High lead value, need listing pages | Big developers already have sites; target offices |
| 1 | Law / accounting / consulting offices | Trust-driven, price-insensitive, ashamed of no site | Formal Arabic, no emojis |
| 2 | Restaurants & cafés | Huge count, need menu + booking + map | Price-sensitive; lead with "menu + WhatsApp order" |
| 2 | Education: nurseries, training centres, language institutes | Parents search Google; enrolment seasons (Aug/Jan) | Seasonal |
| 2 | Auto: workshops, detailing, rentals | Maps-driven discovery; almost none have sites | Lower budgets; upsell later |
| 2 | Gyms / ladies' clubs | Membership sales by DM | |
| 2 | Home services: نقل عفش, تنظيف, مكافحة حشرات, تكييف | Pure Google-search businesses, lowest website adoption | Many use cheap SEO spam sites: pitch "weak site" |
| 3 | Retail (abayas, perfumes, gifts) | Many prefer Salla/Zid stores | Pitch a brand site that links to their store |
| 3 | Events: halls, استراحات, photographers | Gallery-heavy, seasonal | |

**Cities:** Riyadh, Jeddah, Dammam/Khobar first (density + purchasing power), then Makkah, Madinah,
Taif, Buraidah, Abha/Khamis, Tabuk, Hail, Jubail, Al-Ahsa. Searching **district by district** (the
`--districts` flag) surfaces 5–10× more businesses than city-level queries because Google Maps caps each
query at 60 results.

## 3. Two lead types, two pitches

1. **No website** (the bulk): Instagram/Snap only, phone on Google Maps. Pitch = "customers search
   Google, you're invisible there; here is a sample with your name".
2. **Weak website** (≈30–40 % of those that have one): parked domain, "coming soon", no HTTPS, not mobile,
   no Arabic, no WhatsApp button, slow. `scripts/audit_sites.py` scores each site 0–100 and produces the
   Arabic issue list that the `{issues}` placeholder drops straight into the message. Evidence-based
   criticism ("your site has no HTTPS and doesn't work on mobile") converts far better than "your site is bad".

## 4. Pricing position

Local benchmarks (2026): a simple business site costs SAR 2,500–5,000 up-front from agencies,
professional sites SAR 5,000–12,000, plus maintenance SAR 300–1,000/month. Several competitors already sell
"site from 999 SAR" one-off packages.

**SAR 1,000/month all-inclusive with zero upfront** is therefore positioned as: *no capex, no hosting
bills, no freelancer to chase, content updated monthly.* Use these anchors in objections:
- vs agency: "8–15k upfront + yearly maintenance, and no updates".
- vs DIY (Wix/Salla): "who is going to build it, write the Arabic, and keep it updated?"
- ROI framing: "one extra customer a month from Google pays the subscription".

Expect **price objections mainly in Tier 2/3**. Options that keep SAR 1,000 as the headline:
- Annual prepay: 10 months for 12 (SAR 10,000/year) → improves cash flow.
- "Lite" at SAR 600 for restaurants/workshops only if volume matters more than ARPU.
- Setup fee waived is the hook; do **not** discount the monthly.

## 5. Unit economics & income target

| Metric (per agent, per working day) | Conservative | Realistic |
|---|---|---|
| WhatsApp first messages sent (under the daily cap) | 40 | 50 |
| Reply rate (B2B cold WhatsApp, Arabic, personalised demo) | 8 % | 15 % |
| Demo → negotiation | 40 % | 50 % |
| Close rate of negotiations | 20 % | 30 % |
| **New subscriptions / month (22 days)** | ≈ 5–6 | ≈ 15–17 |
| MRR after 3 months (churn ≈ 5 %/mo) | ≈ SAR 15,000 | ≈ SAR 45,000 |

Delivery cost per site (template-based, 48h build, shared hosting) ≈ SAR 150–250/month equivalent,
so gross margin ≈ 75–85 %. Bottleneck after month 2 is **delivery**, not leads: build 3–4 reusable
sector templates (the two in `app/static/demo/` are the first).

## 6. Compliance — read before sending (this is the real risk)

Saudi cold outreach is regulated:
- **CST "Regulations for Curbing SPAM Messages and Calls"** (Decision 493/1444): commercial messages
  need prior consent, an identified sender, and a working opt-out.
- **PDPL (SDAIA)**: direct marketing requires consent; SDAIA issued dozens of enforcement decisions in
  the last year specifically for WhatsApp marketing without consent; fines up to SAR 5M.
- **WhatsApp Business Policy**: unsolicited bulk messaging gets numbers banned within days; Cloud API
  marketing templates require opt-in.

How this system reduces (not eliminates) the risk — it is the user's decision to run the campaign:
1. **B2B only, to numbers the business itself publishes** on Google Maps as its business line. Never
   personal numbers, never scraped from Instagram DMs/followers.
2. **One human, one tap, one message** (wa.me flow) — not a bot blast. Daily cap (default 50) enforced.
3. Every first message identifies the sender and ends with an **opt-out line** ("اكتبوا إيقاف").
   Any "إيقاف / STOP / لا أريد" → status `do_not_contact` immediately (the system blocks further sends).
4. Keep a record (the activity log) of what was sent, when, and any opt-out — this is your evidence.
5. Prefer a **WhatsApp Business** account with a real business name, profile, and address; warm the
   number for 1–2 weeks (normal usage) before starting; start at 20/day, raise to 50 over two weeks.
6. Never send the identical text: templates already vary by sector; the demo link is unique per lead.
7. Do not message on Fridays before 4 pm or after 10 pm; best windows are 10:00–13:00 and 16:30–21:00.

## 7. What "a big list" looks like and how to get it

The sandbox this repository was built in blocks OpenStreetMap, Google Maps, Foursquare and Instagram, so
no live list could be pulled here. The pipeline is ready and only needs a Google Cloud key:

- Google Places API (New), **Text Search Pro: 5,000 free calls/month** (2026 pricing; $32/1,000 after).
- One call returns up to 20 businesses; `scripts/discover_bulk.py --all --districts --max-calls 4500`
  yields on the order of **20,000–40,000 businesses/month for free**, of which typically 60–80 % have no website.
- Every row has name, phone (normalised to 9665…), city, district, sector, rating, review count, Maps URL.

Run order: `discover_bulk.py` → `audit_sites.py` (for the with-website file) → import both CSVs.

## Sources
- Monsha'at digital-transformation report and SME programmes: https://www.monshaat.gov.sa/en/monshaat-reports , https://saudishopper.com.sa/en/monshaat-and-zoho-to-accelerate-smes-digital-transformation-and-e-commerce-adoption/
- Saudi SME numbers 2026: https://www.qoyod.com/en/reports/saudi-smes-2026/
- Social media penetration KSA: https://datareportal.com/reports/digital-2026-saudi-arabia , https://www.globalmediainsight.com/blog/saudi-arabia-social-media-statistics/ , https://vision2030.ai/encyclopedia/saudi-arabia-social-media-usage/
- Website pricing benchmarks KSA 2026: https://www.creativeedigital.com/ar/blogs/how-much-does-a-website-cost-in-saudi-arabia-2026-pricing-guide-for-riyadh-businesses , https://www.devbrickstech.com/blog/website-development-cost-in-saudi-arabia-full-pricing-breakdown-for-businesses-in-2026 , https://buildbusinesswebsite.sofyrus.com/
- CST anti-spam regulation: https://www.cst.gov.sa/en/regulations-and-licenses/decisions/Regulation-469 , https://www.cst.gov.sa/en/regulations-and-licenses/regulations/Document-522
- PDPL + WhatsApp marketing enforcement: https://watily.com/blog/en/saudi-pdpl-whatsapp-marketing-compliance-sme-2026/ , https://gmcsco.com/whatsapp-business-api-compliance-saudi-arabia-2026/ , https://routemobile.com/blog/whatsapp-business-api-in-saudi-arabia-features-limits-and-ksa-compliance-guide/
- Google Places pricing / free tier: https://developers.google.com/maps/documentation/places/web-service/usage-and-billing , https://www.mapsleads.co/blog/google-places-api-free-tier-limits-2026
