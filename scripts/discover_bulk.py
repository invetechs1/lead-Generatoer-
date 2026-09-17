#!/usr/bin/env python3
"""
Bulk lead discovery: runs Google Places (New) Text Search across the city x sector matrix in
data/targets.json, keeps businesses that have a phone number and NO website, and writes a CSV
that imports straight into Bassir Leads (or use --save to insert into the DB directly).

    export GOOGLE_PLACES_API_KEY=...
    python scripts/discover_bulk.py --cities الرياض جدة --tiers 1 --max-calls 300
    python scripts/discover_bulk.py --all --max-calls 4500 --out data/leads_all.csv
    python scripts/discover_bulk.py --cities الرياض --districts --save     # insert into DB

Budget: Text Search Pro SKU = 5,000 free calls/month (2026). One call = up to 20 businesses.
--max-calls is a hard stop so a run never exceeds the free allowance by accident.
Also keeps businesses WITH a website in a second file (--with-sites) for the "poor website" pitch.
"""
import argparse
import asyncio
import csv
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.schemas import normalize_phone  # noqa: E402
from app.services import places  # noqa: E402

TARGETS = json.loads((ROOT / "data" / "targets.json").read_text(encoding="utf-8"))
CSV_COLS = ["name", "phone", "city", "sector", "query", "district", "rating", "reviews", "website", "maps_url", "address", "notes"]


def excluded(name: str) -> bool:
    n = (name or "").lower()
    return any(k.lower() in n for k in TARGETS["exclude_name_keywords"])


def is_mobile_sa(phone: str) -> bool:
    return phone.startswith("9665") and len(phone) == 12


async def run(args) -> None:
    cities = [c for c in TARGETS["cities"] if args.all or c["name"] in args.cities or c["en"].lower() in [x.lower() for x in args.cities]]
    sectors = [s for s in TARGETS["sectors"] if s["tier"] in args.tiers]
    if not cities:
        sys.exit("No matching cities. Available: " + ", ".join(f"{c['name']} ({c['en']})" for c in TARGETS["cities"]))

    seen: set[str] = set()
    no_site: list[dict] = []
    with_site: list[dict] = []
    calls = 0
    per_query_pages = max(1, args.pages)

    for city in cities:
        areas = [city["name"]] + ([f"{d} {city['name']}" for d in city["districts"]] if args.districts else [])
        for sec in sectors:
            for q in sec["queries"]:
                for area in areas:
                    if calls >= args.max_calls:
                        print(f"[stop] reached --max-calls {args.max_calls}", file=sys.stderr)
                        break
                    try:
                        raw = await places.search(q, area, max_results=20 * per_query_pages)
                        calls += per_query_pages
                    except Exception as e:  # quota, network, bad key
                        print(f"[warn] {q} / {area}: {e}", file=sys.stderr)
                        calls += 1
                        continue
                    for r in raw:
                        if excluded(r["name"]):
                            continue
                        try:
                            phone = normalize_phone(r["phone"])
                        except ValueError:
                            continue
                        if args.mobile_only and not is_mobile_sa(phone):
                            continue
                        if phone in seen:
                            continue
                        seen.add(phone)
                        row = {
                            "name": r["name"], "phone": phone, "city": city["name"], "sector": sec["sector"], "query": q,
                            "district": area if area != city["name"] else "", "rating": r.get("rating") or "", "reviews": r.get("reviews") or "",
                            "website": r.get("website") or "", "maps_url": r.get("maps_url") or "", "address": r.get("address") or "",
                            "notes": f"places:{q}",
                        }
                        (with_site if row["website"] else no_site).append(row)
                    print(f"[{calls:>4} calls] {sec['sector']:<12} {q:<22} {area:<28} no-site={len(no_site):>5} with-site={len(with_site):>5}", file=sys.stderr)

    no_site.sort(key=lambda r: (-(float(r["reviews"] or 0)), r["city"]))
    write_csv(Path(args.out), no_site)
    print(f"\n{len(no_site)} leads WITHOUT a website -> {args.out}")
    if args.with_sites:
        write_csv(Path(args.with_sites), with_site)
        print(f"{len(with_site)} businesses WITH a website -> {args.with_sites}  (run scripts/audit_sites.py on this file)")
    print(f"API calls used: {calls}")

    if args.save:
        save_to_db(no_site)


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLS)
        w.writeheader()
        w.writerows(rows)


def save_to_db(rows: list[dict]) -> None:
    from app.database import SessionLocal, Base, engine
    from app.models import Lead
    Base.metadata.create_all(bind=engine)
    added = 0
    with SessionLocal() as db:
        existing = {p for (p,) in db.query(Lead.phone)}
        for r in rows:
            if r["phone"] in existing:
                continue
            db.add(Lead(name=r["name"], phone=r["phone"], city=r["city"], sector=r["sector"], website=r["website"], maps_url=r["maps_url"],
                        rating=float(r["rating"]) if r["rating"] else None, reviews=int(r["reviews"]) if r["reviews"] else None,
                        source="places", notes=r["notes"], priority=1 if TARGETS_TIER.get(r["sector"]) == 1 else 2))
            existing.add(r["phone"]); added += 1
        db.commit()
    print(f"inserted {added} new leads into the database")


TARGETS_TIER = {s["sector"]: s["tier"] for s in TARGETS["sectors"]}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--cities", nargs="*", default=["الرياض"], help="City names (Arabic or English) from data/targets.json")
    p.add_argument("--all", action="store_true", help="All cities")
    p.add_argument("--districts", action="store_true", help="Also search district by district (finds 5-10x more, costs more calls)")
    p.add_argument("--tiers", nargs="*", type=int, default=[1, 2], help="Sector tiers to include (1 = best fit)")
    p.add_argument("--pages", type=int, default=1, help="Result pages per query (20 results each)")
    p.add_argument("--max-calls", type=int, default=400, help="Hard budget of API calls for this run")
    p.add_argument("--mobile-only", action="store_true", help="Keep only Saudi mobile numbers (9665...) so WhatsApp always works")
    p.add_argument("--out", default=f"data/leads_no_website_{date.today()}.csv")
    p.add_argument("--with-sites", default=f"data/leads_with_website_{date.today()}.csv", help="Where to write businesses that DO have a site ('' to skip)")
    p.add_argument("--save", action="store_true", help="Insert results into the Bassir Leads database as well")
    args = p.parse_args()
    if not os.environ.get("GOOGLE_PLACES_API_KEY") and not places.settings.GOOGLE_PLACES_API_KEY:
        sys.exit("GOOGLE_PLACES_API_KEY is not set (export it or put it in .env). Get one: https://console.cloud.google.com -> APIs -> Places API (New)")
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
