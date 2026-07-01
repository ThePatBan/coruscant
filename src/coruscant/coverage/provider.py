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

import csv
import io
import json
from collections.abc import Sequence
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
ANCHOR_BSE_CODE = "bse_code"  # India: the numeric BSE Security Code (distinct from ISIN)


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


class IndexMembership(BaseModel):
    """One issuer's membership of a market index (Nifty 50, BSE Sensex).

    An index is *not* an exchange — coverage is the whole NSE+BSE universe; the
    indices ride on top as :class:`~coruscant.knowledge_graph` ``Index`` nodes with
    ``constituent_of`` edges, so "an event on the Nifty → which of my holdings are in
    it" is a first-class query later. The constituent is linked to a covered Company
    by its ``isin`` (exact) or ``symbol`` (fallback); a constituent outside the
    ingested universe is counted, never fabricated."""

    index_key: str  # stable node key: "nifty-50", "bse-sensex"
    index_name: str  # "Nifty 50", "BSE Sensex"
    isin: str | None = None
    symbol: str | None = None
    source: str
    source_url: str | None = None


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


# -- India: NSE + BSE equity lists, ISIN-unified ------------------------------
#
# There is no single free "all issuers" feed like EDGAR for India, so the universe
# is the union of two exchange scrip lists. The unifier is the **ISIN**: a company
# listed on both NSE and BSE shares one ISIN, so ISIN is both the intra-India dedup
# key and the NSE↔BSE join. One node per ISIN carries *both* exchange symbols as
# anchors (NSE symbol → the `ticker` anchor so resolve.py works unchanged; BSE code
# → a `bse_code` anchor) — the market-plural payoff.

NSE_EQUITY_LIST_SOURCE = "nse-equity-list"
BSE_SCRIP_LIST_SOURCE = "bse-scrip-list"
INDIA_COVERAGE_SOURCE = "nse-bse-equity-list"
_NSE_EQUITY_LIST_URL = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
_BSE_SCRIP_LIST_URL = "https://www.bseindia.com/corporates/List_Scrips.html"
# A browser-like UA is the *best-effort* live path; NSE blocks scripts aggressively
# (403 without browser headers/cookies), so the operator --file download is primary.
_BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
# NSE equity series we keep as ordinary listed equity. EQ = rolling settlement,
# BE = trade-to-trade (still listed equity); other series (debt, ETFs, warrants)
# are excluded and counted, never silently dropped.
_NSE_EQUITY_SERIES = frozenset({"EQ", "BE"})


def _csv_columns(fieldnames: Sequence[str] | None, aliases: tuple[str, ...]) -> str | None:
    """First header (case-insensitive, whitespace-folded) matching any alias — NSE
    and BSE ship headers with stray spaces/casing, so we never index by raw name."""

    if not fieldnames:
        return None
    lookup = {" ".join(str(f).split()).lower(): f for f in fieldnames}
    for alias in aliases:
        if alias in lookup:
            return lookup[alias]
    return None


def _clean_isin(value: object) -> str | None:
    """Canonical ISIN form: uppercased, trimmed. Blank → None (absence is signal).
    Kept permissive (no checksum): a legitimate row is never dropped for over-strict
    validation; a blank/placeholder ISIN is what we exclude and count."""

    text = str(value or "").strip().upper()
    return text or None


def parse_nse_equity_list(text: str) -> tuple[list[dict[str, str]], dict[str, int]]:
    """Parse NSE ``EQUITY_L.csv`` (SYMBOL, NAME OF COMPANY, SERIES, ISIN NUMBER, …)
    into ``[{symbol, name, isin}]`` filtered to listed-equity series. Returns
    ``(rows, drops)`` — what was excluded, by reason (honest, counted)."""

    reader = csv.DictReader(io.StringIO(text))
    c_sym = _csv_columns(reader.fieldnames, ("symbol",))
    c_name = _csv_columns(reader.fieldnames, ("name of company", "company name", "name"))
    c_series = _csv_columns(reader.fieldnames, ("series",))
    c_isin = _csv_columns(reader.fieldnames, ("isin number", "isin code", "isin no", "isin"))
    rows: list[dict[str, str]] = []
    drops = {"nse_blank_isin": 0, "nse_non_equity_series": 0}
    if c_sym is None or c_isin is None:
        return rows, {"nse_malformed": 1}
    for row in reader:
        series = (row.get(c_series) or "").strip().upper() if c_series else "EQ"
        if series and series not in _NSE_EQUITY_SERIES:
            drops["nse_non_equity_series"] += 1
            continue
        isin = _clean_isin(row.get(c_isin))
        if isin is None:
            drops["nse_blank_isin"] += 1
            continue
        rows.append({
            "symbol": (row.get(c_sym) or "").strip().upper(),
            "name": (row.get(c_name) or "").strip() if c_name else "",
            "isin": isin,
        })
    return rows, drops


# BSE field aliases (whitespace-folded, lowercased). Cover both the CSV export
# headers ("Security Code") and the live JSON API keys ("SCRIP_CD", "ISIN_NUMBER",
# "scrip_id", "Issuer_Name", "Segment") so either source parses unchanged.
_BSE_CODE_ALIASES = ("security code", "scrip code", "sc_code", "scrip_cd")
_BSE_ID_ALIASES = ("security id", "scrip id", "sc_id", "scrip_id")
_BSE_NAME_ALIASES = ("security name", "issuer name", "issuer_name", "sc_name", "scrip_name", "name")
_BSE_ISIN_ALIASES = ("isin no", "isin number", "isin_number", "isin code", "isin")
_BSE_STATUS_ALIASES = ("status",)
_BSE_INSTR_ALIASES = ("instrument", "instrument type", "segment")


def _pick(row_lower: dict[str, str], aliases: tuple[str, ...]) -> str | None:
    """First value in ``row_lower`` (keys whitespace-folded/lowercased) whose key
    matches an alias — the per-row analogue of :func:`_csv_columns`, so JSON and CSV
    rows resolve fields the same way."""

    for alias in aliases:
        if alias in row_lower:
            return row_lower[alias]
    return None


def _bse_records(text: str) -> list[dict[str, Any]]:
    """Yield raw row dicts from either the BSE JSON API response (a list, or a
    ``{"Table": [...]}`` wrapper) or a CSV export — whichever the operator supplied."""

    stripped = text.lstrip()
    if stripped[:1] in ("[", "{"):
        data: Any = json.loads(stripped)
        if isinstance(data, dict):  # some BSE endpoints wrap the list in an envelope
            data = next((v for v in data.values() if isinstance(v, list)), [])
        return [r for r in data if isinstance(r, dict)] if isinstance(data, list) else []
    return list(csv.DictReader(io.StringIO(text)))


def parse_bse_scrip_list(text: str) -> tuple[list[dict[str, str]], dict[str, int]]:
    """Parse the BSE active-equity scrip list into ``[{code, security_id, name, isin}]``,
    kept to Active equity. Accepts the live JSON API response *or* a CSV export
    (Security Code, Security Id, Security Name, ISIN No, Status, Instrument, …).
    Returns ``(rows, drops)`` counted by reason. Empty input (BSE not supplied) → no
    rows, no drops (an NSE-only run is legitimate, not malformed)."""

    if not text.strip():
        return [], {}
    try:
        records = _bse_records(text)
    except (ValueError, json.JSONDecodeError):
        return [], {"bse_malformed": 1}
    rows: list[dict[str, str]] = []
    drops = {"bse_blank_isin": 0, "bse_inactive": 0, "bse_non_equity": 0}
    for raw in records:
        row_lower = {" ".join(str(k).split()).lower(): v for k, v in raw.items()}
        status = _pick(row_lower, _BSE_STATUS_ALIASES)
        if status is not None and str(status).strip().lower() not in ("active", ""):
            drops["bse_inactive"] += 1
            continue
        instrument = _pick(row_lower, _BSE_INSTR_ALIASES)
        if instrument is not None and "equity" not in str(instrument).strip().lower():
            drops["bse_non_equity"] += 1
            continue
        isin = _clean_isin(_pick(row_lower, _BSE_ISIN_ALIASES))
        if isin is None:
            drops["bse_blank_isin"] += 1
            continue
        rows.append({
            "code": str(_pick(row_lower, _BSE_CODE_ALIASES) or "").strip(),
            "security_id": str(_pick(row_lower, _BSE_ID_ALIASES) or "").strip().upper(),
            "name": str(_pick(row_lower, _BSE_NAME_ALIASES) or "").strip(),
            "isin": isin,
        })
    return rows, drops


def unify_india_issuers(
    nse_rows: list[dict[str, str]], bse_rows: list[dict[str, str]]
) -> tuple[list[IssuerRecord], dict[str, int]]:
    """Join NSE + BSE rows on ISIN into one :class:`IssuerRecord` per issuer carrying
    both exchange symbols as anchors. ``exchange`` ∈ {NSE, BSE, ``NSE & BSE``} so the
    dual-listed overlap (NSE∩BSE) is a first-class bucket, not a hidden merge.

    Stats: ``nse_only`` / ``bse_only`` / ``dual_listed`` counts (the overlap proof)."""

    nse_by_isin: dict[str, dict[str, str]] = {}
    for r in nse_rows:
        nse_by_isin.setdefault(r["isin"], r)  # first wins; a re-listed symbol is rare
    bse_by_isin: dict[str, dict[str, str]] = {}
    for r in bse_rows:
        bse_by_isin.setdefault(r["isin"], r)

    stats = {"nse_only": 0, "bse_only": 0, "dual_listed": 0}
    records: list[IssuerRecord] = []
    # Deterministic order: NSE rows first (in file order), then BSE-only rows.
    ordered_isins = list(nse_by_isin) + [i for i in bse_by_isin if i not in nse_by_isin]
    for isin in ordered_isins:
        nse = nse_by_isin.get(isin)
        bse = bse_by_isin.get(isin)
        if nse and bse:
            exchange, stats["dual_listed"] = "NSE & BSE", stats["dual_listed"] + 1
        elif nse:
            exchange, stats["nse_only"] = "NSE", stats["nse_only"] + 1
        else:
            exchange, stats["bse_only"] = "BSE", stats["bse_only"] + 1

        nse_symbol = (nse or {}).get("symbol") or None
        bse_id = (bse or {}).get("security_id") or None
        bse_code = (bse or {}).get("code") or None
        ticker = nse_symbol or bse_id  # resolve-facing symbol; NSE preferred
        name = (nse or bse or {}).get("name") or ticker or isin

        anchors = [IssuerAnchor(scheme=ANCHOR_ISIN, value=isin)]
        if ticker:
            anchors.append(IssuerAnchor(scheme=ANCHOR_TICKER, value=ticker))
        if bse_code:
            anchors.append(IssuerAnchor(scheme=ANCHOR_BSE_CODE, value=bse_code))
        records.append(IssuerRecord(
            market="IN", name=name, ticker=ticker, exchange=exchange,
            anchors=anchors, source=INDIA_COVERAGE_SOURCE,
            source_url=f"https://www.nseindia.com/get-quotes/equity?symbol={nse_symbol}"
            if nse_symbol else _BSE_SCRIP_LIST_URL,
        ))
    return records, stats


def parse_index_constituents(
    text: str, *, index_key: str, index_name: str, source: str, source_url: str | None = None
) -> list[IndexMembership]:
    """Parse an index constituent CSV (Nifty ``ind_nifty50list.csv``: Company Name,
    Symbol, ISIN Code; Sensex lists similar) into :class:`IndexMembership` rows keyed
    by ISIN (preferred) and/or symbol. Rows with neither are skipped."""

    reader = csv.DictReader(io.StringIO(text))
    c_isin = _csv_columns(reader.fieldnames, ("isin code", "isin no", "isin number", "isin"))
    c_sym = _csv_columns(reader.fieldnames, ("symbol", "security id", "scrip id"))
    out: list[IndexMembership] = []
    for row in reader:
        isin = _clean_isin(row.get(c_isin)) if c_isin else None
        symbol = ((row.get(c_sym) or "").strip().upper() or None) if c_sym else None
        if not isin and not symbol:
            continue
        out.append(IndexMembership(
            index_key=index_key, index_name=index_name, isin=isin, symbol=symbol,
            source=source, source_url=source_url,
        ))
    return out


# Index catalog: (role, node key, display name, provenance source).
_INDIA_INDEX_CATALOG = {
    "nifty": ("nifty-50", "Nifty 50", "nse-indices"),
    "sensex": ("bse-sensex", "BSE Sensex", "bse-indices"),
}


def _read_source(text: str | None, path: Path | None) -> str | None:
    if text is not None:
        return text
    if path is not None:
        return Path(path).read_text()
    return None


class IndiaCoverageProvider:
    """India universe from the NSE + BSE equity scrip lists, unified by ISIN.

    Files (or best-effort live fetch) in; unified :class:`IssuerRecord`\\ s
    (``market="IN"``) out — the pipeline's ISIN dedup then enriches across re-runs.
    Nifty 50 / BSE Sensex constituent lists become :class:`IndexMembership` rows the
    pipeline turns into ``Index`` nodes + ``constituent_of`` edges. Hermetic in CI via
    injected text; the live fetch is operator-invoked (``SSL_CERT_FILE=$(python3 -m
    certifi)``) and best-effort — NSE blocks scripts, so ``--file`` is the primary path."""

    market = "IN"
    name = "india-nse-bse"

    def __init__(
        self,
        *,
        nse_text: str | None = None,
        bse_text: str | None = None,
        nifty_text: str | None = None,
        sensex_text: str | None = None,
        user_agent: str = _BROWSER_UA,
        nse_url: str = _NSE_EQUITY_LIST_URL,
        timeout: float = 30.0,
    ) -> None:
        self._nse_text = nse_text
        self._bse_text = bse_text
        self._nifty_text = nifty_text
        self._sensex_text = sensex_text
        self._user_agent = user_agent
        self._nse_url = nse_url
        self._timeout = timeout
        self._last_drops: dict[str, int] = {}

    @classmethod
    def from_files(
        cls,
        *,
        nse: Path | None = None,
        bse: Path | None = None,
        nifty: Path | None = None,
        sensex: Path | None = None,
        **kwargs: Any,
    ) -> "IndiaCoverageProvider":
        """Build a provider from downloaded CSVs — the hermetic/operator path."""

        return cls(
            nse_text=_read_source(None, nse), bse_text=_read_source(None, bse),
            nifty_text=_read_source(None, nifty), sensex_text=_read_source(None, sensex),
            **kwargs,
        )

    def connected(self) -> bool:
        if any(t is not None for t in (self._nse_text, self._bse_text)):
            return True
        try:  # best-effort reachability; the real live fetch fills the text below
            req = Request(self._nse_url, headers={"User-Agent": self._user_agent}, method="HEAD")
            with urlopen(req, timeout=min(self._timeout, 5.0)) as r:  # noqa: S310 (trusted NSE host)
                return 200 <= int(r.getcode()) < 300
        except Exception:
            return False

    def _fetch(self, url: str) -> str:
        req = Request(url, headers={"User-Agent": self._user_agent, "Accept": "text/csv,*/*"})
        try:
            with urlopen(req, timeout=self._timeout) as response:  # noqa: S310 (operator-invoked)
                return response.read().decode("utf-8", errors="replace")
        except Exception as error:  # noqa: BLE001 — surface as an explicit runtime failure
            raise RuntimeError(f"India coverage fetch failed for {url!r}: {error}") from error

    @property
    def last_drops(self) -> dict[str, int]:
        return dict(self._last_drops)

    def list_issuers(self) -> list[IssuerRecord]:
        nse_text = self._nse_text if self._nse_text is not None else self._fetch(self._nse_url)
        # BSE has no stable direct-CSV endpoint; live BSE is operator-supplied text.
        bse_text = self._bse_text or ""
        nse_rows, nse_drops = parse_nse_equity_list(nse_text or "")
        bse_rows, bse_drops = parse_bse_scrip_list(bse_text)
        records, _stats = unify_india_issuers(nse_rows, bse_rows)
        # Only true drops go to `excluded`; the NSE∩BSE overlap is a by_exchange
        # bucket ("NSE & BSE"), so it is reported without polluting the drop reasons.
        self._last_drops = {**nse_drops, **bse_drops}
        return records

    def list_index_memberships(self) -> list[IndexMembership]:
        """Nifty 50 + BSE Sensex constituents (whichever lists were supplied)."""

        out: list[IndexMembership] = []
        for role, text in (("nifty", self._nifty_text), ("sensex", self._sensex_text)):
            if not text:
                continue
            key, display, src = _INDIA_INDEX_CATALOG[role]
            out.extend(parse_index_constituents(
                text, index_key=key, index_name=display, source=src))
        return out


class StaticCoverageProvider:
    """Replays a fixed issuer list — the hermetic test double for any market.

    Optionally replays ``index_memberships`` too, so the Index/constituent_of
    pipeline path is testable without the full :class:`IndiaCoverageProvider`."""

    def __init__(
        self,
        market: str,
        records: list[IssuerRecord],
        *,
        name: str = "static",
        index_memberships: list[IndexMembership] | None = None,
    ) -> None:
        self.market = market
        self.name = name
        self._records = records
        self._index_memberships = index_memberships

    def connected(self) -> bool:
        return True

    def list_issuers(self) -> list[IssuerRecord]:
        return list(self._records)

    def list_index_memberships(self) -> list[IndexMembership]:
        return list(self._index_memberships or [])
