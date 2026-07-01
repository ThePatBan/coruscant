"""Resolve a portfolio's positions against the coverage universe — the proof that
whole-exchange coverage lets a real retail book land in the graph.

Two-stage, precision-first: an exact **ticker** hit (the strong intra-market key
coverage attaches) first, then the shared **org-name** core matcher as a fallback
for rows that carry only a description. Anything that clears neither is reported
unresolved — a labelled gap, never a fabricated match. The resolve *rate* is the
headline coverage metric.
"""

from __future__ import annotations

import csv
import io
import re

from pydantic import BaseModel, Field

from coruscant.coverage.pipeline import COMPANY_KIND, TICKER
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


class ResolvedPosition(BaseModel):
    input_ticker: str | None = None
    input_name: str | None = None
    company_key: str | None = None
    method: str  # "ticker" | "name" | "unresolved"
    score: float | None = None


class ResolveReport(BaseModel):
    total: int = 0
    resolved: int = 0
    by_ticker: int = 0
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
    company_norms: list[tuple[str, str]] | None = None  # built lazily on first name lookup
    report = ResolveReport(total=len(positions))
    for pos in positions:
        ticker = (pos.ticker or "").strip().upper()
        hit = ticker_index.get(ticker) or (folded_index.get(_ticker_key(ticker)) if ticker else None)
        if hit is not None:
            report.by_ticker += 1
            report.resolved += 1
            report.positions.append(ResolvedPosition(
                input_ticker=pos.ticker, input_name=pos.name,
                company_key=hit, method="ticker"))
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
                    input_ticker=pos.ticker, input_name=pos.name,
                    company_key=best[0], method="name", score=best[1]))
                continue
        report.unresolved += 1
        report.positions.append(ResolvedPosition(
            input_ticker=pos.ticker, input_name=pos.name, method="unresolved"))
    return report


# Common brokerage-CSV header aliases (case-insensitive).
_TICKER_HEADERS = ("symbol", "ticker", "symbol/cusip")
_NAME_HEADERS = ("name", "description", "security", "security description", "security name")


def parse_brokerage_csv(text: str) -> list[Position]:
    """Parse a brokerage holdings CSV into positions.

    Tolerant of column naming: picks the first header matching a known ticker or
    name alias. Rows with neither a symbol nor a name are skipped (a footer/total
    line, not a holding)."""

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        return []
    lower = {f.lower().strip(): f for f in reader.fieldnames}
    t_col = next((lower[h] for h in _TICKER_HEADERS if h in lower), None)
    n_col = next((lower[h] for h in _NAME_HEADERS if h in lower), None)
    positions: list[Position] = []
    for row in reader:
        ticker = (row.get(t_col) or "").strip() if t_col else ""
        name = (row.get(n_col) or "").strip() if n_col else ""
        if not ticker and not name:
            continue
        positions.append(Position(ticker=ticker or None, name=name or None))
    return positions
