#!/usr/bin/env python3
"""Onboard exchange-listed companies into a Coruscant companies.yml by CIK.

Resolves tickers -> CIK (SEC company_tickers.json), then pulls each company's
latest 10-K filings and SIC industry from the SEC submissions API, emitting a
companies.yml the live SEC connector can ingest directly. This removes the
hand-listed-filing-URL bottleneck: onboarding a market becomes a ticker list.

Usage:
    python scripts/onboard_companies.py --out config/companies.yml [--filings 2] [TICKER ...]

With no tickers, the current Dow 30 set is used.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen

import yaml

UA = "Coruscant Research onboarding (contact: dev@coruscant.local)"

# Dow Jones Industrial Average constituents (2025).
DOW_30 = [
    "MMM", "AXP", "AMGN", "AMZN", "AAPL", "BA", "CAT", "CVX", "CSCO", "KO",
    "DIS", "GS", "HD", "HON", "IBM", "JNJ", "JPM", "MCD", "MRK", "MSFT",
    "NKE", "NVDA", "PG", "CRM", "SHW", "TRV", "UNH", "VZ", "V", "WMT",
]


def _get(url: str) -> bytes:
    with urlopen(Request(url, headers={"User-Agent": UA}), timeout=30) as resp:
        return resp.read()


def _slugify(value: str) -> str:
    import re

    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "company"


def load_ticker_map() -> dict[str, dict]:
    data = json.loads(_get("https://www.sec.gov/files/company_tickers.json"))
    return {str(row["ticker"]).upper(): row for row in data.values()}


def latest_10k_urls(cik: int, n: int) -> tuple[list[str], str, str]:
    cik10 = f"{cik:010d}"
    sub = json.loads(_get(f"https://data.sec.gov/submissions/CIK{cik10}.json"))
    recent = sub["filings"]["recent"]
    picks: list[str] = []
    for i in range(len(recent["form"])):
        if recent["form"][i] != "10-K":
            continue
        accession = recent["accessionNumber"][i].replace("-", "")
        doc = recent["primaryDocument"][i]
        if not doc:
            continue
        picks.append(f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{doc}")
        if len(picks) >= n:
            break
    picks.reverse()  # oldest -> newest, so the change detector sees prior + current
    return picks, sub.get("name", ""), sub.get("sicDescription", "") or "Unknown"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--filings", type=int, default=2)
    ap.add_argument("tickers", nargs="*", default=[])
    args = ap.parse_args()
    tickers = [t.upper() for t in (args.tickers or DOW_30)]

    tmap = load_ticker_map()
    companies: list[dict] = []
    for ticker in tickers:
        row = tmap.get(ticker)
        if not row:
            print(f"  ! {ticker}: not found in SEC ticker map; skipping", file=sys.stderr)
            continue
        cik = int(row["cik_str"])
        try:
            urls, name, sic = latest_10k_urls(cik, args.filings)
        except Exception as exc:  # noqa: BLE001 — onboarding is best-effort per ticker
            print(f"  ! {ticker} (CIK {cik}): {exc}; skipping", file=sys.stderr)
            continue
        if not urls:
            print(f"  ! {ticker}: no 10-K filings found; skipping", file=sys.stderr)
            continue
        name = name or str(row.get("title") or ticker)
        companies.append(
            {
                "slug": ticker.lower(),
                "name": name.title() if name.isupper() else name,
                "aliases": [ticker, name],
                "industry": sic,
                "country": "United States",
                "cik": str(cik),
                "sec_filings": urls,
            }
        )
        print(f"  + {ticker:5} {name[:38]:40} {len(urls)} 10-K  [{sic}]")
        time.sleep(0.2)  # be polite to SEC

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(yaml.safe_dump({"companies": companies}, sort_keys=False, width=200))
    print(f"\nWrote {len(companies)} companies -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
