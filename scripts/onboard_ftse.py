"""Onboard cross-listed FTSE companies (20-F filers) and merge them into the live
company config, so the Atlas shows UK↔US linkages.

UK companies don't file with the SEC — except the cross-listed ones, which file
Form 20-F (their directors are by-reference in the proxy, but the filing text is
enough for the co-mention graph). This is a NETWORK step.

Run after generating the FTSE config with the form-aware onboard:

    SSL_CERT_FILE=$(python3 -m certifi) python3 scripts/onboard_companies.py \\
      --out deploy/ftse-config/companies.yml --form 20-F --country "United Kingdom" \\
      SHEL BP AZN HSBC UL DEO BCS RIO BTI VOD NWG RELX NGG GSK PUK

    SSL_CERT_FILE=$(python3 -m certifi) CORUSCANT_CONFIG_DIR=deploy/dow-config \\
      CORUSCANT_DATA_DIR=data python3 scripts/onboard_ftse.py

It fetches + normalizes each 20-F into the data store and appends the companies to
the live config with distinctive display names (so the gazetteer matches the right
form). Then re-run `scripts/recompute_intelligence.py` and restart the API; the
extraction (with its verified false-positive exclusions) produces the cross-border
co-mention edges.
"""

from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import yaml

from coruscant.common.config import Settings, load_companies
from coruscant.common.types import SourceDocument
from coruscant.connectors.sec_edgar import normalize_edgar_filing
from coruscant.infrastructure.repositories import FileSystemNormalizedDocumentRepository

# Distinctive display names so the co-mention gazetteer matches the right form
# (e.g. "GSK plc" → core "gsk" is too short; "GlaxoSmithKline plc" matches).
CLEAN_NAMES = {
    "shel": "Shell plc",
    "bp": "BP plc",
    "azn": "AstraZeneca plc",
    "hsbc": "HSBC plc",
    "ul": "Unilever plc",
    "deo": "Diageo plc",
    "bcs": "Barclays plc",
    "rio": "Rio Tinto plc",
    "bti": "British American Tobacco plc",
    "vod": "Vodafone plc",
    "nwg": "NatWest plc",
    "relx": "RELX plc",
    "ngg": "National Grid plc",
    "gsk": "GlaxoSmithKline plc",
    "puk": "Prudential plc",
}
_UA = {"User-Agent": "Coruscant FTSE onboarding contact@coruscant.local"}


def _get(url: str) -> bytes:
    time.sleep(0.12)  # SEC fair-access
    return urlopen(Request(url, headers=_UA), timeout=45).read()  # noqa: S310 (trusted SEC host)


def main() -> None:
    settings = Settings()
    ftse = load_companies(Path("deploy/ftse-config"))
    repo = FileSystemNormalizedDocumentRepository(settings.data_dir)

    normalized = 0
    for company in ftse:
        for url in company.sec_filings:
            try:
                html = _get(url).decode("utf-8", "replace")
            except (HTTPError, URLError) as exc:
                print(f"  ! {company.slug} {url[-28:]} — {exc}")
                continue
            match = re.search(r"(\d{8})\.html?$", url)
            document = SourceDocument(
                source_type="sec_edgar",
                source_uri=url,
                fetched_at=datetime.now(tz=timezone.utc),
                raw_content=html,
                metadata={
                    "company_slug": company.slug,
                    "form_type": "20-F",
                    "company_name": company.name,
                    "filing_date": (
                        f"{match.group(1)[:4]}-{match.group(1)[4:6]}-{match.group(1)[6:]}" if match else None
                    ),
                    "source_name": "20-F",
                },
            )
            repo.save(normalize_edgar_filing(document))
            normalized += 1
        print(f"  + {company.slug:5} {company.name[:30]:30} {len(company.sec_filings)} 20-F")

    # Merge into the live config with clean display names.
    config_path = settings.config_dir / "companies.yml"
    live = yaml.safe_load(config_path.read_text())["companies"]
    existing = {c["slug"] for c in live}
    added = 0
    for company in ftse:
        if company.slug in existing:
            continue
        live.append(
            {
                "slug": company.slug,
                "name": CLEAN_NAMES.get(company.slug, company.name),
                "aliases": sorted({company.slug.upper(), *company.aliases}),
                "industry": company.industry,
                "country": company.country,
                "cik": company.cik,
                "sec_filings": company.sec_filings,
            }
        )
        added += 1
    config_path.write_text(yaml.safe_dump({"companies": live}, sort_keys=False, width=200))
    print(f"\nNormalized {normalized} 20-F docs; merged {added} FTSE companies into {config_path}.")


if __name__ == "__main__":
    main()
