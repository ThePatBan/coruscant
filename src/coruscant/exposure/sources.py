"""Portfolio-Exposure workspace — ingestion source catalog.

Boundary: WORKSPACE (Portfolio-Exposure) — see docs/PLATFORM.md §7, §9 (seam 4).

The finance source definitions and their live-connector wiring used to live in the
platform ``ingestion/registry.py``, which made the generic ingestion package a hidden
Portfolio-Exposure module. Phase 4 moves them here: this module owns *which* sources the
workspace ingests, built on the generic ``SourceRegistry``/``SourceDefinition`` primitives
from ``coruscant.ingestion.registry`` (workspace -> platform, the allowed direction).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace

from coruscant.connectors.earnings_call import (
    ReferenceEarningsCallConnector,
    normalize_earnings_call,
)
from coruscant.connectors.investor_relations import (
    ReferenceInvestorRelationsConnector,
    normalize_investor_relations,
)
from coruscant.connectors.job_postings import (
    ReferenceJobPostingsConnector,
    normalize_job_postings,
)
from coruscant.connectors.news import ReferenceNewsConnector, normalize_news
from coruscant.connectors.patents import ReferencePatentsConnector, normalize_patents
from coruscant.connectors.press_release import (
    ReferencePressReleaseConnector,
    normalize_press_release,
)
from coruscant.connectors.extended_sources import (
    ReferenceCourtFilingsConnector,
    ReferenceEsgConnector,
    ReferenceGlobalRegulatorsConnector,
    ReferenceGovernmentContractsConnector,
    ReferenceProcurementConnector,
    ReferenceSanctionsConnector,
    normalize_court_filings,
    normalize_esg,
    normalize_global_regulators,
    normalize_government_contracts,
    normalize_procurement,
    normalize_sanctions,
)
from coruscant.connectors.sec_edgar import (
    EdgarHttpConnector,
    RateLimiter,
    ReferenceEdgarConnector,
    normalize_edgar_filing,
)
from coruscant.ingestion.registry import ConnectorFactory, SourceDefinition, SourceRegistry


# Default SEC contact UA; the real value comes from Settings.edgar_user_agent and
# is threaded in by the runtime when live ingestion is enabled.
DEFAULT_EDGAR_USER_AGENT = "Coruscant/0.1.0 contact@coruscant.local"


def _live_connector_factory(
    source_type: str, edgar_user_agent: str, rate_limiter: RateLimiter | None
) -> ConnectorFactory | None:
    """Return the live (network) connector factory for a source, if one exists.

    Only sources with a real connector are eligible; anything else stays on its
    reference connector even if requested live, so an over-broad ``live_sources``
    setting can never silently break offline ingestion.
    """

    if source_type == "sec_edgar":
        return lambda: EdgarHttpConnector(edgar_user_agent, rate_limiter=rate_limiter)
    return None


_DEFAULT_DEFINITIONS: tuple[SourceDefinition, ...] = (
    SourceDefinition(
        source_type="sec_edgar",
        label="SEC EDGAR",
        document_type="filing",
        connector_factory=ReferenceEdgarConnector,
        normalizer=normalize_edgar_filing,
        periods=(("FY2024 10-K", "2024-01-31"), ("FY2025 10-K", "2025-01-31")),
        authority=0.98,
        cadence_days=1,
    ),
    SourceDefinition(
        source_type="global_regulators",
        label="Global Regulators",
        document_type="regulatory_action",
        connector_factory=ReferenceGlobalRegulatorsConnector,
        normalizer=normalize_global_regulators,
        periods=(("2024 review", "2024-09-15"), ("2025 review", "2025-05-20")),
        authority=0.95,
    ),
    SourceDefinition(
        source_type="court_filings",
        label="Court Filings",
        document_type="court_filing",
        connector_factory=ReferenceCourtFilingsConnector,
        normalizer=normalize_court_filings,
        periods=(("Mar 2025", "2025-03-22"),),
        authority=0.92,
    ),
    SourceDefinition(
        source_type="sanctions",
        label="Sanctions Screening",
        document_type="sanctions_notice",
        connector_factory=ReferenceSanctionsConnector,
        normalizer=normalize_sanctions,
        periods=(("May 2025", "2025-05-05"),),
        authority=0.9,
    ),
    SourceDefinition(
        source_type="government_contracts",
        label="Government Contracts",
        document_type="government_contract",
        connector_factory=ReferenceGovernmentContractsConnector,
        normalizer=normalize_government_contracts,
        periods=(("Q1 2025", "2025-02-18"),),
        authority=0.85,
    ),
    SourceDefinition(
        source_type="procurement_notices",
        label="Procurement Notices",
        document_type="procurement_notice",
        connector_factory=ReferenceProcurementConnector,
        normalizer=normalize_procurement,
        periods=(("Q1 2025", "2025-03-01"),),
        authority=0.8,
    ),
    SourceDefinition(
        source_type="investor_relations",
        label="Investor Relations",
        document_type="investor_update",
        connector_factory=ReferenceInvestorRelationsConnector,
        normalizer=normalize_investor_relations,
        periods=(("Q3 FY2025", "2025-04-30"), ("Q4 FY2025", "2025-07-31")),
        authority=0.8,
    ),
    SourceDefinition(
        source_type="earnings_call",
        label="Earnings Call Transcripts",
        document_type="transcript",
        connector_factory=ReferenceEarningsCallConnector,
        normalizer=normalize_earnings_call,
        periods=(("Q3 FY2025", "2025-04-30"), ("Q4 FY2025", "2025-07-31")),
        authority=0.78,
    ),
    SourceDefinition(
        source_type="esg_reports",
        label="ESG Reports",
        document_type="esg_report",
        connector_factory=ReferenceEsgConnector,
        normalizer=normalize_esg,
        periods=(("FY2025", "2025-06-30"),),
        authority=0.72,
    ),
    SourceDefinition(
        source_type="patents",
        label="Patent Metadata",
        document_type="patent",
        connector_factory=ReferencePatentsConnector,
        normalizer=normalize_patents,
        periods=(("Nov 2024", "2024-11-20"),),
        authority=0.7,
    ),
    SourceDefinition(
        source_type="press_release",
        label="Press Releases",
        document_type="press_release",
        connector_factory=ReferencePressReleaseConnector,
        normalizer=normalize_press_release,
        periods=(("Mar 2025", "2025-03-15"),),
        authority=0.55,
    ),
    SourceDefinition(
        source_type="news",
        label="News",
        document_type="news_article",
        connector_factory=ReferenceNewsConnector,
        normalizer=normalize_news,
        periods=(("Apr 2025", "2025-04-02"),),
        authority=0.5,
        cadence_days=1,
    ),
    SourceDefinition(
        source_type="job_postings",
        label="Job Postings",
        document_type="job_posting",
        connector_factory=ReferenceJobPostingsConnector,
        normalizer=normalize_job_postings,
        periods=(("Feb 2025", "2025-02-10"),),
        authority=0.45,
    ),
)


def default_registry(
    live_sources: Iterable[str] = (),
    *,
    edgar_user_agent: str = DEFAULT_EDGAR_USER_AGENT,
    rate_limiter: RateLimiter | None = None,
) -> SourceRegistry:
    """Build the source registry.

    With no ``live_sources`` (the default) every source uses its offline reference
    connector — dev/test stay fully deterministic and network-free. For each
    requested live source that has a real connector, its ``connector_factory`` is
    swapped for the live one (carrying the SEC ``user_agent`` + shared
    ``rate_limiter``); all other metadata is unchanged.
    """

    live = set(live_sources)
    registry = SourceRegistry()
    for definition in _DEFAULT_DEFINITIONS:
        if definition.source_type in live:
            factory = _live_connector_factory(
                definition.source_type, edgar_user_agent, rate_limiter
            )
            if factory is not None:
                definition = replace(definition, connector_factory=factory)
        registry.register(definition)
    return registry
