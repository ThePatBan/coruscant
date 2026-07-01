"""Project 13F holdings into the graph as Fund -holds-> Company edges.

The holding primitive the exposure engine has been missing: a real institutional
book, from which "does this event touch *my* holdings?" becomes answerable. Each
13F line item's issuer name is resolved to a Company node with the org-name core
matcher (13F issuer names are SEC-conformed, like our node names, so this is
high-yield); positions outside our coverage are counted, never fabricated. Edges
carry provenance + access_tier + valid-time (as-of the 13F report period).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from pydantic import BaseModel

from coruscant.common.types import GraphEdge, GraphNode
from coruscant.knowledge_graph import substrate
from coruscant.knowledge_graph.store import KnowledgeGraphStore
from coruscant.knowledge_graph.textmatch import normalize_name, org_score
from coruscant.portfolio.thirteenf import FundFiling

FUND_KIND = "Fund"
HOLDS = "holds"
THIRTEENF_SOURCE = "sec-13f"
_CONFIRM_FLOOR = 0.97  # exact/core issuer-name match; below this we don't attribute a holding


class FundSummary(BaseModel):
    fund: str  # node key
    name: str
    period: str | None = None
    positions: int  # line items on the 13F
    resolved: int  # distinct Company nodes we hold in coverage
    out_of_coverage: int  # positions with no Company node yet (honest, not fabricated)


@dataclass
class _Agg:
    value: int
    shares: int
    cusip: str | None
    issuer: str
    score: float


def _company_norms(store: KnowledgeGraphStore) -> list[tuple[str, str]]:
    return [(node.key, normalize_name(str(node.properties.get("name") or node.key)))
            for node in store.nodes_of_kind("Company")]


def _resolve(companies: list[tuple[str, str]], issuer: str, floor: float) -> tuple[str, float] | None:
    q = normalize_name(issuer)
    if not q:
        return None
    best: tuple[str, float] | None = None
    for key, norm in companies:
        score = org_score(q, norm)
        if best is None or score > best[1]:
            best = (key, score)
    return best if best is not None and best[1] >= floor else None


def ingest_fund_holdings(
    store: KnowledgeGraphStore,
    filing: FundFiling,
    *,
    observed_at: date | str,
    confirm_floor: float = _CONFIRM_FLOOR,
) -> FundSummary:
    """Upsert the Fund node and its ``holds`` edges to the companies we cover."""

    fund_key = f"fund-{filing.cik}"
    companies = _company_norms(store)

    # Aggregate line items (multiple share classes of one issuer) per resolved company.
    agg: dict[str, _Agg] = {}
    resolved_positions = 0
    for holding in filing.holdings:
        match = _resolve(companies, holding.issuer, confirm_floor)
        if match is None:
            continue
        resolved_positions += 1
        key, score = match
        entry = agg.setdefault(key, _Agg(value=0, shares=0, cusip=holding.cusip,
                                         issuer=holding.issuer, score=score))
        entry.value += int(holding.value)
        if holding.shares:
            entry.shares += int(holding.shares)

    positions = len(filing.holdings)
    store.upsert_node(
        GraphNode(
            kind=FUND_KIND, key=fund_key,
            properties={
                "name": filing.name, "source": THIRTEENF_SOURCE, "cik": filing.cik,
                "period": filing.period, "source_url": filing.source_url,
                "positions": positions, "resolved": len(agg),
                "out_of_coverage": positions - resolved_positions,
            },
        )
    )
    for key, entry in agg.items():
        store.upsert_edge(
            GraphEdge(
                source_kind=FUND_KIND, source_key=fund_key, relation=HOLDS,
                target_kind="Company", target_key=key,
                properties=substrate.stamp(
                    {"value": entry.value, "shares": entry.shares or None,
                     "cusip": entry.cusip, "matched_name": entry.issuer,
                     "score": entry.score, "review_status": "confirmed"},
                    source=THIRTEENF_SOURCE, access_tier=substrate.AccessTier.PUBLIC,
                    observed_at=observed_at, valid_from=filing.period,
                ),
            )
        )
    return FundSummary(
        fund=fund_key, name=filing.name, period=filing.period, positions=positions,
        resolved=len(agg), out_of_coverage=positions - resolved_positions,
    )
