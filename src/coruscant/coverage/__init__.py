"""Whole-exchange coverage: ingest the full universe of listed issuers for a
market as lightweight Company nodes so uploaded portfolios resolve.

Market-plural from day one. :class:`~coruscant.coverage.provider.CoverageProvider`
is the seam (mirroring ``screening`` and ``anchoring``): a provider lists the
issuers for one market; :func:`~coruscant.coverage.pipeline.ingest_coverage`
reconciles them into the graph by external anchor (CIK for US), enriching the
curated companies rather than duplicating them and creating stable surrogate
nodes for the rest. This is the *universe*, not deep filing ingestion — sectors,
holdings, and LEIs are attached on demand by the other pipelines.

Boundary: WORKSPACE (Portfolio-Exposure) — see docs/PLATFORM.md §7.
"""

from __future__ import annotations

from coruscant.coverage.pipeline import CoverageSummary, ingest_coverage
from coruscant.coverage.provider import (
    CoverageProvider,
    IssuerAnchor,
    IssuerRecord,
    StaticCoverageProvider,
    UsEdgarCoverageProvider,
    parse_company_tickers_exchange,
)
from coruscant.coverage.resolve import ResolveReport, build_ticker_index, resolve_positions

__all__ = [
    "CoverageProvider",
    "CoverageSummary",
    "IssuerAnchor",
    "IssuerRecord",
    "ResolveReport",
    "StaticCoverageProvider",
    "UsEdgarCoverageProvider",
    "build_ticker_index",
    "ingest_coverage",
    "parse_company_tickers_exchange",
    "resolve_positions",
]
