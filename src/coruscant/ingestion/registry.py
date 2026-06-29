"""Registry mapping source types to their connector and normalizer.

Adding a new pipeline means registering a :class:`SourceDefinition`; no core
domain code changes. The default registry wires the reference connectors so the
full lifecycle runs offline, while leaving room for live connectors to be
substituted per deployment.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from coruscant.common.types import NormalizedDocument, SourceDocument
from coruscant.connectors.base import SourceConnector
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
from coruscant.connectors.sec_edgar import ReferenceEdgarConnector, normalize_edgar_filing

ConnectorFactory = Callable[[], SourceConnector]
Normalizer = Callable[[SourceDocument], NormalizedDocument]


@dataclass(frozen=True)
class SourceDefinition:
    source_type: str
    label: str
    document_type: str
    connector_factory: ConnectorFactory
    normalizer: Normalizer
    # (display label, ISO date) per disclosure. Periodic sources carry two so the
    # change detector has a prior and a current version to diff; episodic sources
    # carry one. The last entry is treated as the current disclosure.
    periods: tuple[tuple[str, str], ...] = (("current", "2025-01-31"),)
    # Inherent source authority (0..1): official/regulatory filings rank above
    # commentary. Feeds the reliability score (see intelligence.reliability).
    authority: float = 0.6

    @property
    def is_periodic(self) -> bool:
        return len(self.periods) > 1


class UnknownSourceError(KeyError):
    """Raised when a requested source type is not registered."""


class SourceRegistry:
    def __init__(self) -> None:
        self._definitions: dict[str, SourceDefinition] = {}

    def register(self, definition: SourceDefinition) -> None:
        self._definitions[definition.source_type] = definition

    def get(self, source_type: str) -> SourceDefinition:
        try:
            return self._definitions[source_type]
        except KeyError as exc:
            raise UnknownSourceError(source_type) from exc

    def has(self, source_type: str) -> bool:
        return source_type in self._definitions

    def source_types(self) -> list[str]:
        return list(self._definitions)

    def definitions(self) -> list[SourceDefinition]:
        return list(self._definitions.values())


_DEFAULT_DEFINITIONS: tuple[SourceDefinition, ...] = (
    SourceDefinition(
        source_type="sec_edgar",
        label="SEC EDGAR",
        document_type="filing",
        connector_factory=ReferenceEdgarConnector,
        normalizer=normalize_edgar_filing,
        periods=(("FY2024 10-K", "2024-01-31"), ("FY2025 10-K", "2025-01-31")),
        authority=0.98,
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


def default_registry() -> SourceRegistry:
    registry = SourceRegistry()
    for definition in _DEFAULT_DEFINITIONS:
        registry.register(definition)
    return registry
