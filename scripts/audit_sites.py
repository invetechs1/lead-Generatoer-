#!/usr/bin/env python3
"""
Audit websites in bulk and rank the WEAK ones for the "your website is hurting you" pitch.

    python scripts/audit_sites.py data/leads_with_website_2026-09-17.csv           # -> data/leads_weak_website_<date>.csv
    python scripts/audit_sites.py --db --max-score 60                               # audit leads already in the DB that have a site
    python scripts/audit_sites.py --url https://example.com                         # one-off check

Output CSV keeps the Bassir import columns and adds site_score + site_issues, sorted worst-first,
so you can import it directly (Leads -> استيراد CSV) and the {issues} placeholder is ready to use.
"""
import argparse
import asyncio
import csv
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.services.site_audit import audit  # noqa: E402


async def audit_many(urls: list[str], concurrency: int = 8):
    sem = asyncio.Semaphore(concurrency)

    async def one(u):
        async with sem:
            return await audit(u)
    return await asyncio.gather(*(one(u) for u in urls))


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("csv", nargs="?", help="CSV with a 'website' column (output of discover_bulk.py --with-sites)")
    p.add_argument("--db", action="store_true", help="Audit leads in the database instead of a CSV, and store scores")
    p.add_argument("--url", help="Audit a single URL and print the result")
    p.add_argument("--max-score", type=int, default=60, help="Keep only sites scoring at or below this (weak sites)")
    p.add_argument("--out", default=f"data/leads_weak_website_{date.today()}.csv")
    p.add_argument("--concurrency", type=int, default=8)
    a = p.parse_args()

    if a.url:
        r = asyncio.run(audit(a.url))
        print(f"{r.url} -> score {r.score}/100  (status {r.status}, {r.ttfb_ms} ms, mobile={r.mobile_ready}, https={r.https})")
        for i in r.issues:
            print("  •", i)
        return

    if a.db:
        from app.database import SessionLocal
        from app.models import Lead
        with SessionLocal() as db:
            leads = db.query(Lead).filter(Lead.website != "").all()
            print(f"auditing {len(leads)} leads with a website...", file=sys.stderr)
            results = asyncio.run(audit_many([l.website for l in leads], a.concurrency))
            weak = 0
            for l, r in zip(leads, results):
                l.site_score = r.score
                l.site_issues = "\n".join(r.issues)
                if r.score <= a.max_score:
                    weak += 1
                    l.priority = min(l.priority, 2)
            db.commit()
        print(f"done: {weak} weak websites (score <= {a.max_score}) stored on leads")
        return

    if not a.csv:
        p.error("give a CSV path, --db or --url")
    rows = list(csv.DictReader(open(a.csv, encoding="utf-8-sig")))
    rows = [r for r in rows if (r.get("website") or "").strip()]
    print(f"auditing {len(rows)} sites...", file=sys.stderr)
    results = asyncio.run(audit_many([r["website"] for r in rows], a.concurrency))
    out = []
    for r, res in zip(rows, results):
        r["site_score"] = res.score
        r["site_issues"] = "\n".join(res.issues)
        if res.score <= a.max_score:
            out.append(r)
    out.sort(key=lambda r: (r["site_score"], -float(r.get("reviews") or 0)))
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    with open(a.out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["website", "site_score", "site_issues"])
        w.writeheader(); w.writerows(out)
    print(f"{len(out)} weak websites (score <= {a.max_score}) -> {a.out}")


if __name__ == "__main__":
    main()
