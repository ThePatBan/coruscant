"""Resolve a portfolio's positions against the coverage universe — the proof that
whole-exchange coverage lets a real retail book land in the graph.

Precision-first: an exact **ticker** hit (the strong intra-market key coverage
attaches), then an exact **ISIN** hit (Indian exports — Zerodha/Groww — key by ISIN or
NSE symbol), then an exact **SEDOL** hit (UK exports — HL/AJ Bell — often key by SEDOL),
then the shared **org-name** core matcher as a fallback for rows that carry only a
description. Anything that clears none is reported unresolved — a labelled gap, never a
fabricated match. The resolve *rate* is the headline coverage metric.
"""

from __future__ import annotations

import csv
import io
import re

from pydantic import BaseModel, Field

from coruscant.coverage.pipeline import ANCHORS, COMPANY_KIND, TICKER
from coruscant.knowledge_graph.store import KnowledgeGraphStore
from coruscant.knowledge_graph.textmatch import normalize_name, org_score

_NAME_FLOOR = 0.97  # exact/core name match; below this we don't attribute a position


def _ticker_key(ticker: str) -> str:
    """Punctuation-folded ticker for matching: brokerages write share-class tickers
    with a dot (``BRK.B``) where SEC uses a dash (``BRK-B``). Folding both to
    ``BRKB`` recovers the same security without fabricating a match."""

    return re.sub(r"[^A-Z0-9]", "", ticker.upper())


class Position(BaseModel):
    ticker: str | None = None
    name: str | None = None
    isin: str | None = None
    sedol: str | None = None


class ResolvedPosition(BaseModel):
    input_ticker: str | None = None
    input_name: str | None = None
    input_isin: str | None = None
    input_sedol: str | None = None
    company_key: str | None = None
    method: str  # "ticker" | "isin" | "sedol" | "name" | "unresolved"
    score: float | None = None


class ResolveReport(BaseModel):
    total: int = 0
    resolved: int = 0
    by_ticker: int = 0
    by_isin: int = 0
    by_sedol: int = 0
    by_name: int = 0
    unresolved: int = 0
    positions: list[ResolvedPosition] = Field(default_factory=list)

    @property
    def rate(self) -> float:
        return round(self.resolved / self.total, 4) if self.total else 0.0


def build_ticker_index(store: KnowledgeGraphStore) -> dict[str, str]:
    """``{TICKER (upper) → Company node key}`` over the coverage universe."""

    index: dict[str, str] = {}
    for node in store.nodes_of_kind(COMPANY_KIND):
        ticker = node.properties.get(TICKER)
        if isinstance(ticker, str) and ticker.strip():
            index.setdefault(ticker.strip().upper(), node.key)
    return index


def _scheme_index(store: KnowledgeGraphStore, scheme: str) -> dict[str, str]:
    """``{anchor value (upper) → Company node key}`` for anchors of ``scheme``."""

    index: dict[str, str] = {}
    for node in store.nodes_of_kind(COMPANY_KIND):
        for a in node.properties.get(ANCHORS) or []:
            if isinstance(a, dict) and a.get("scheme") == scheme and a.get("value"):
                index.setdefault(str(a["value"]).strip().upper(), node.key)
    return index


def build_isin_index(store: KnowledgeGraphStore) -> dict[str, str]:
    """``{ISIN (upper) → Company node key}`` — the exact key an Indian brokerage
    export (Zerodha/Groww) carries."""

    return _scheme_index(store, "isin")


def build_sedol_index(store: KnowledgeGraphStore) -> dict[str, str]:
    """``{SEDOL (upper) → Company node key}`` — the exact key a UK brokerage export
    (Hargreaves Lansdown / AJ Bell) often carries."""

    return _scheme_index(store, "sedol")


def _company_norms(store: KnowledgeGraphStore) -> list[tuple[str, str]]:
    return [(n.key, normalize_name(str(n.properties.get("name") or n.key)))
            for n in store.nodes_of_kind(COMPANY_KIND)]


def resolve_positions(
    store: KnowledgeGraphStore, positions: list[Position], *, name_floor: float = _NAME_FLOOR
) -> ResolveReport:
    """Resolve each position by exact ticker, then org-name fallback."""

    ticker_index = build_ticker_index(store)
    # Punctuation-folded fallback index (first-write-wins so it never shadows an
    # exact hit): BRK.B ↔ BRK-B. Collisions here would be two tickers differing only
    # in punctuation — not a real security clash.
    folded_index: dict[str, str] = {}
    for tkr, key in ticker_index.items():
        folded_index.setdefault(_ticker_key(tkr), key)
    isin_index: dict[str, str] | None = None  # built lazily on first ISIN lookup
    sedol_index: dict[str, str] | None = None  # built lazily on first SEDOL lookup
    company_norms: list[tuple[str, str]] | None = None  # built lazily on first name lookup
    report = ResolveReport(total=len(positions))
    for pos in positions:
        ticker = (pos.ticker or "").strip().upper()
        hit = ticker_index.get(ticker) or (folded_index.get(_ticker_key(ticker)) if ticker else None)
        if hit is not None:
            report.by_ticker += 1
            report.resolved += 1
            report.positions.append(ResolvedPosition(
                input_ticker=pos.ticker, input_name=pos.name, input_isin=pos.isin,
                input_sedol=pos.sedol, company_key=hit, method="ticker"))
            continue
        isin = (pos.isin or "").strip().upper()
        if isin:
            if isin_index is None:
                isin_index = build_isin_index(store)
            isin_hit = isin_index.get(isin)
            if isin_hit is not None:
                report.by_isin += 1
                report.resolved += 1
                report.positions.append(ResolvedPosition(
                    input_ticker=pos.ticker, input_name=pos.name, input_isin=pos.isin,
                    input_sedol=pos.sedol, company_key=isin_hit, method="isin"))
                continue
        sedol = (pos.sedol or "").strip().upper()
        if sedol:
            if sedol_index is None:
                sedol_index = build_sedol_index(store)
            sedol_hit = sedol_index.get(sedol)
            if sedol_hit is not None:
                report.by_sedol += 1
                report.resolved += 1
                report.positions.append(ResolvedPosition(
                    input_ticker=pos.ticker, input_name=pos.name, input_isin=pos.isin,
                    input_sedol=pos.sedol, company_key=sedol_hit, method="sedol"))
                continue
        if pos.name:
            if company_norms is None:
                company_norms = _company_norms(store)
            q = normalize_name(pos.name)
            best: tuple[str, float] | None = None
            if q:
                for key, norm in company_norms:
                    score = org_score(q, norm)
                    if best is None or score > best[1]:
                        best = (key, score)
            if best is not None and best[1] >= name_floor:
                report.by_name += 1
                report.resolved += 1
                report.positions.append(ResolvedPosition(
                    input_ticker=pos.ticker, input_name=pos.name, input_isin=pos.isin,
                    input_sedol=pos.sedol, company_key=best[0], method="name", score=best[1]))
                continue
        report.unresolved += 1
        report.positions.append(ResolvedPosition(
            input_ticker=pos.ticker, input_name=pos.name, input_isin=pos.isin,
            input_sedol=pos.sedol, method="unresolved"))
    return report


# Common brokerage-CSV header aliases (case-insensitive). ISIN aliases cover Indian
# exports (Zerodha/Groww); SEDOL covers UK exports (Hargreaves Lansdown / AJ Bell).
_TICKER_HEADERS = ("symbol", "ticker", "symbol/cusip", "trading symbol", "tradingsymbol",
                   "nse symbol", "tidm", "epic")
_NAME_HEADERS = ("name", "description", "security", "security description", "security name",
                 "company name", "instrument", "stock")
_ISIN_HEADERS = ("isin", "isin code", "isin no", "isin number")
_SEDOL_HEADERS = ("sedol", "sedol code")


def parse_brokerage_csv(text: str) -> list[Position]:
    """Parse a brokerage holdings CSV into positions.

    Tolerant of column naming: picks the first header matching a known ticker, name,
    ISIN, or SEDOL alias. Rows with none of the four are skipped (a footer/total line,
    not a holding)."""

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        return []
    lower = {" ".join(f.lower().split()): f for f in reader.fieldnames}
    t_col = next((lower[h] for h in _TICKER_HEADERS if h in lower), None)
    n_col = next((lower[h] for h in _NAME_HEADERS if h in lower), None)
    i_col = next((lower[h] for h in _ISIN_HEADERS if h in lower), None)
    s_col = next((lower[h] for h in _SEDOL_HEADERS if h in lower), None)
    positions: list[Position] = []
    for row in reader:
        ticker = (row.get(t_col) or "").strip() if t_col else ""
        name = (row.get(n_col) or "").strip() if n_col else ""
        isin = (row.get(i_col) or "").strip() if i_col else ""
        sedol = (row.get(s_col) or "").strip() if s_col else ""
        if not ticker and not name and not isin and not sedol:
            continue
        positions.append(Position(
            ticker=ticker or None, name=name or None, isin=isin or None, sedol=sedol or None))
    return positions
