"""EDGAR 13F connector — the holding primitive the graph lacks (Phase 2).

A 13F-HR is an institutional manager's quarterly holdings disclosure (free, SEC).
Its *information table* lists each position: issuer name, CUSIP, value, shares. We
parse that table (a pure, fixture-testable function) and, separately, fetch a
filer's latest 13F live from EDGAR. The graph projection (issuer → Company
resolution + `holds` edges) lives in :mod:`coruscant.portfolio.holdings`.
"""

from __future__ import annotations

import json
import re
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pydantic import BaseModel, Field

_ARCHIVES = "https://www.sec.gov/Archives/edgar/data"


class FundHolding(BaseModel):
    issuer: str
    cusip: str | None = None
    title: str | None = None
    value: int = 0  # as reported on the 13F (USD; historically USD thousands)
    shares: int | None = None


class FundFiling(BaseModel):
    cik: str
    name: str
    period: str | None = None  # report period end (YYYY-MM-DD)
    source_url: str | None = None
    holdings: list[FundHolding] = Field(default_factory=list)


def _local_tag(block: str, tag: str) -> str | None:
    """Extract a tag's text, tolerating any XML namespace prefix (``ns1:`` etc.)."""
    match = re.search(rf"<(?:\w+:)?{tag}\b[^>]*>(.*?)</(?:\w+:)?{tag}>", block, re.S | re.I)
    return match.group(1).strip() if match else None


def _to_int(value: str | None) -> int | None:
    if not value:
        return None
    try:
        return int(float(value.replace(",", "").strip()))
    except ValueError:
        return None


def parse_13f_info_table(xml: str) -> list[FundHolding]:
    """Parse a 13F information-table XML into holdings (namespace-tolerant)."""
    holdings: list[FundHolding] = []
    for block in re.findall(r"<(?:\w+:)?infoTable\b[^>]*>(.*?)</(?:\w+:)?infoTable>", xml, re.S | re.I):
        issuer = _local_tag(block, "nameOfIssuer")
        if not issuer:
            continue
        holdings.append(
            FundHolding(
                issuer=issuer.strip(),
                cusip=(_local_tag(block, "cusip") or None),
                title=(_local_tag(block, "titleOfClass") or None),
                value=_to_int(_local_tag(block, "value")) or 0,
                shares=_to_int(_local_tag(block, "sshPrnamt")),
            )
        )
    return holdings


def fetch_latest_13f(cik: str, *, user_agent: str, pause_seconds: float = 0.13) -> FundFiling | None:
    """Fetch a filer's most recent 13F-HR and return its parsed holdings. Returns
    ``None`` if the filer has no 13F or EDGAR is unreachable (an observable zero,
    not an error)."""

    headers = {"User-Agent": user_agent}
    padded = str(cik).lstrip("0").zfill(10)

    def _get(url: str) -> bytes:
        with urlopen(Request(url, headers=headers), timeout=30) as resp:  # noqa: S310 (trusted SEC host)
            return resp.read()

    try:
        submissions = json.loads(_get(f"https://data.sec.gov/submissions/CIK{padded}.json"))
    except (HTTPError, URLError, ValueError):
        return None
    name = str(submissions.get("name") or cik)
    recent = submissions.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    accessions = recent.get("accessionNumber", [])
    periods = recent.get("reportDate", [])
    index = next((i for i, form in enumerate(forms) if str(form).startswith("13F-HR")), None)
    if index is None:
        return None
    acc = accessions[index].replace("-", "")
    period = periods[index] if index < len(periods) else None
    base = f"{_ARCHIVES}/{int(cik)}/{acc}"
    try:
        listing = json.loads(_get(f"{base}/index.json"))
    except (HTTPError, URLError, ValueError):
        return None

    # The info table is the .xml document that contains an <informationTable>.
    xml_names = [item.get("name", "") for item in listing.get("directory", {}).get("item", [])
                 if str(item.get("name", "")).lower().endswith(".xml")]
    for candidate in sorted(xml_names, key=lambda n: ("info" not in n.lower(), n)):
        try:
            body = _get(f"{base}/{candidate}").decode("utf-8", "replace")
        except (HTTPError, URLError):
            continue
        time.sleep(pause_seconds)  # SEC fair-access courtesy
        if "informationtable" in body.lower():
            holdings = parse_13f_info_table(body)
            if holdings:
                return FundFiling(cik=str(int(cik)), name=name, period=period,
                                  source_url=f"{base}/{candidate}", holdings=holdings)
    return None
