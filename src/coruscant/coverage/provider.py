"""Coverage providers: the swappable universe feed behind the coverage pipeline.

``CoverageProvider`` is the seam. :class:`UsEdgarCoverageProvider` reads SEC's
``company_tickers_exchange.json`` (one request → ~10k issuers: ticker, CIK, name,
exchange); :class:`StaticCoverageProvider` replays a fixed record list so CI is
hermetic. Both yield :class:`IssuerRecord` — a *lightweight* listed-issuer node,
NOT a full filing — carrying generic per-market :class:`IssuerAnchor`s so India
(ISIN/symbol) and UK (ISIN/SEDOL/company_number) are new providers, not rewrites.

Invariant #2: the surrogate is the primary key; external IDs (CIK, ISIN, …) are
*anchors* on it. Invariant #1: every record names its ``source``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol
from urllib.request import Request, urlopen

from pydantic import BaseModel, Field

from coruscant.connectors.sec_edgar import RateLimiter

# The free, clean US universe feed: one request returns every ticker↔CIK↔exchange
# row SEC knows about. CC0-equivalent public data; no per-CIK submissions fan-out.
_US_TICKERS_EXCHANGE = "https://www.sec.gov/files/company_tickers_exchange.json"
SEC_COMPANY_TICKERS_SOURCE = "sec-company-tickers"

# Anchor schemes we model. US uses `cik` (a near-perfect intra-US key); the others
# are declared now so the India/UK providers drop in without touching the model.
ANCHOR_CIK = "cik"
ANCHOR_TICKER = "ticker"
ANCHOR_ISIN = "isin"
ANCHOR_SEDOL = "sedol"
ANCHOR_COMPANY_NUMBER = "company_number"
ANCHOR_FIGI = "figi"


class IssuerAnchor(BaseModel):
    """One external identifier that anchors a surrogate issuer node.

    Generic on purpose: ``scheme`` ∈ {cik, ticker, isin, sedol, company_number,
    figi, …}. The surrogate node key is never one of these — the anchors ride *on*
    it so the same node can gather more anchors over time without re-keying."""

    scheme: str
    value: str


class IssuerRecord(BaseModel):
    """A listed issuer from a market's coverage feed — a universe node, not a filing.

    ``market`` is an ISO-3166 alpha-2 (``US``, ``IN``, ``GB``). ``exchange`` is kept
    verbatim as reported (``Nasdaq``, ``NYSE``); a blank/OTC listing is filtered out
    upstream and counted, never silently dropped. ``anchors`` carries the external
    IDs; for US that is the CIK (plus the ticker)."""

    market: str
    name: str
    ticker: str | None = None
    exchange: str | None = None
    anchors: list[IssuerAnchor] = Field(default_factory=list)
    source: str
    source_url: str | None = None

    def anchor(self, scheme: str) -> str | None:
        """The value of the first anchor with ``scheme`` (or ``None``)."""

        for a in self.anchors:
            if a.scheme == scheme:
                return a.value
        return None


class CoverageProvider(Protocol):
    market: str
    name: str

    def connected(self) -> bool: ...

    def list_issuers(self) -> list[IssuerRecord]: ...


# -- US: SEC company_tickers_exchange.json ------------------------------------


def normalize_cik(value: object) -> str | None:
    """Canonical CIK form for dedup: the bare integer as a string ("0000320193",
    320193, "320193" → "320193"). The near-perfect intra-US key. Non-numeric → None."""

    text = str(value).strip()
    if not text:
        return None
    try:
        return str(int(text))
    except ValueError:
        return None


def is_real_exchange(exchange: object) -> bool:
    """A real listing venue (NYSE/Nasdaq/CBOE/…), excluding blanks and OTC.

    Retail brokerage books hold real-exchange listings; OTC is noisy and mostly
    shells. We keep everything with a named venue that is not OTC, so a future
    venue (e.g. "NYSE American") is included without a code change."""

    if not isinstance(exchange, str):
        return False
    text = exchange.strip()
    return bool(text) and "otc" not in text.lower()


def parse_company_tickers_exchange(payload: dict[str, Any]) -> tuple[list[IssuerRecord], dict[str, int]]:
    """Parse SEC's ``{"fields": [...], "data": [[...], ...]}`` envelope into issuer
    records, filtered to real exchanges. Returns ``(records, drops)`` where ``drops``
    counts what was excluded by reason (honest: absence is counted, not hidden)."""

    fields = [str(f).lower() for f in payload.get("fields", [])]
    rows = payload.get("data", [])
    if not isinstance(rows, list):
        return [], {"malformed": 1}
    try:
        i_cik, i_name, i_ticker, i_exch = (
            fields.index("cik"), fields.index("name"),
            fields.index("ticker"), fields.index("exchange"),
        )
    except ValueError:
        return [], {"malformed": len(rows)}

    records: list[IssuerRecord] = []
    drops = {"otc_or_blank_exchange": 0, "no_cik": 0}
    for row in rows:
        if not isinstance(row, (list, tuple)) or len(row) <= max(i_cik, i_name, i_ticker, i_exch):
            continue
        cik = normalize_cik(row[i_cik])
        if cik is None:
            drops["no_cik"] += 1
            continue
        exchange = row[i_exch]
        if not is_real_exchange(exchange):
            drops["otc_or_blank_exchange"] += 1
            continue
        name = str(row[i_name] or "").strip()
        ticker = str(row[i_ticker] or "").strip().upper() or None
        anchors = [IssuerAnchor(scheme=ANCHOR_CIK, value=cik)]
        if ticker:
            anchors.append(IssuerAnchor(scheme=ANCHOR_TICKER, value=ticker))
        records.append(
            IssuerRecord(
                market="US", name=name, ticker=ticker, exchange=str(exchange).strip(),
                anchors=anchors, source=SEC_COMPANY_TICKERS_SOURCE,
                source_url=f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}",
            )
        )
    return records, drops


class UsEdgarCoverageProvider:
    """Live US universe from SEC's ``company_tickers_exchange.json`` (one request).

    Reuses the EDGAR fair-access conventions (contact-bearing User-Agent + the
    shared :class:`RateLimiter`); does *not* fan out to the per-CIK submissions API
    (that would be ~10k requests). The full parse+filter path is exercised offline
    by injecting ``payload`` (or a local file), so no network call reaches CI."""

    market = "US"
    name = "us-edgar"

    def __init__(
        self,
        *,
        user_agent: str = "Coruscant/0.1 coverage (contact@coruscant.local)",
        url: str = _US_TICKERS_EXCHANGE,
        rate_limiter: RateLimiter | None = None,
        timeout: float = 30.0,
        payload: dict[str, Any] | None = None,
    ) -> None:
        self._user_agent = user_agent
        self._url = url
        self._rate_limiter = rate_limiter
        self._timeout = timeout
        self._payload = payload  # offline injection (tests / operator-supplied file)
        self._last_drops: dict[str, int] = {}

    @classmethod
    def from_file(cls, path: Path, **kwargs: Any) -> "UsEdgarCoverageProvider":
        """Build a provider that reads a downloaded ``company_tickers_exchange.json``
        instead of the network — the hermetic/operator path."""

        return cls(payload=json.loads(Path(path).read_text()), **kwargs)

    def connected(self) -> bool:
        if self._payload is not None:
            return True
        try:
            req = Request(self._url, headers={"User-Agent": self._user_agent}, method="HEAD")
            with urlopen(req, timeout=min(self._timeout, 5.0)) as r:  # noqa: S310 (trusted SEC host)
                return 200 <= int(r.getcode()) < 300
        except Exception:
            return False

    def _fetch(self) -> dict[str, Any]:
        if self._payload is not None:
            return self._payload
        if self._rate_limiter is not None:
            self._rate_limiter.acquire()
        req = Request(self._url, headers={"User-Agent": self._user_agent})
        try:
            with urlopen(req, timeout=self._timeout) as response:  # noqa: S310 (trusted SEC host)
                data = json.loads(response.read().decode("utf-8"))
        except Exception as error:  # noqa: BLE001 — surface as an explicit runtime failure
            raise RuntimeError(f"SEC coverage fetch failed for {self._url!r}: {error}") from error
        return data if isinstance(data, dict) else {}

    @property
    def last_drops(self) -> dict[str, int]:
        """What the most recent :meth:`list_issuers` filtered out, by reason."""

        return dict(self._last_drops)

    def list_issuers(self) -> list[IssuerRecord]:
        records, drops = parse_company_tickers_exchange(self._fetch())
        self._last_drops = drops
        return records


class StaticCoverageProvider:
    """Replays a fixed issuer list — the hermetic test double for any market."""

    def __init__(self, market: str, records: list[IssuerRecord], *, name: str = "static") -> None:
        self.market = market
        self.name = name
        self._records = records

    def connected(self) -> bool:
        return True

    def list_issuers(self) -> list[IssuerRecord]:
        return list(self._records)
