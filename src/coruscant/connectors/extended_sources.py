"""Reference connectors for the Phase 3 intelligence sources.

Each synthesizes a deterministic, evidence-bearing sample document (markdown
``## Heading`` blocks parsed by :func:`normalize_reference_document`). Content
weaves in regulator, agency, and country mentions so the entity graph (Phase 4)
has material to extract.
"""

from __future__ import annotations

from coruscant.common.types import NormalizedDocument, SourceDocument
from coruscant.connectors.base import FetchRequest, SourceConnector
from coruscant.connectors.common import build_source_document, normalize_reference_document


def _connector(source_type: str, document_type: str, build_blocks):  # type: ignore[no-untyped-def]
    class _Reference(SourceConnector):
        def fetch(self, request: FetchRequest) -> SourceDocument:
            name = request.company_name or request.company_slug.title()
            blocks, title = build_blocks(name, request)
            return build_source_document(
                source_type=source_type,
                source_uri=request.source_uri,
                blocks=blocks,
                source_name=request.source_name,
                metadata={
                    "company_slug": request.company_slug,
                    "company_name": name,
                    "title": title,
                    "period": request.period,
                    "published_at": request.published_at,
                    "industry": request.industry,
                },
            )

    def normalize(document: SourceDocument) -> NormalizedDocument:
        return normalize_reference_document(document, document_type=document_type)

    return _Reference, normalize


def _global_regulators_blocks(name: str, request: FetchRequest):  # type: ignore[no-untyped-def]
    title = f"Regulatory Action Concerning {name}"
    blocks = [
        (title, f"A global regulator opened a regulatory review concerning {name}."),
        (
            "Findings",
            f"The European Commission and other regulators examined {name}'s competitive "
            "conduct and compliance posture across jurisdictions.",
        ),
        (
            "Implications",
            f"{name} faces potential regulatory and antitrust risk pending the investigation.",
        ),
    ]
    return blocks, title


def _esg_blocks(name: str, request: FetchRequest):  # type: ignore[no-untyped-def]
    title = f"{name} ESG Report"
    blocks = [
        (title, f"{name} published its annual sustainability and ESG report."),
        (
            "Environmental",
            f"{name} disclosed emissions, energy use, and supply chain sustainability targets.",
        ),
        ("Governance", f"{name} described board governance and risk oversight practices."),
    ]
    return blocks, title


def _gov_contracts_blocks(name: str, request: FetchRequest):  # type: ignore[no-untyped-def]
    title = f"Government Contract Awarded to {name}"
    blocks = [
        (title, f"The US Government awarded a contract to {name}."),
        (
            "Scope",
            f"The contract covers products and services {name} will deliver to a federal agency.",
        ),
        ("Value", f"The award represents a multi-year commitment relevant to {name}'s outlook."),
    ]
    return blocks, title


def _court_filings_blocks(name: str, request: FetchRequest):  # type: ignore[no-untyped-def]
    title = f"Court Filing Involving {name}"
    blocks = [
        (title, f"A court filing names {name} as a party to litigation."),
        (
            "Claims",
            f"The lawsuit sets out claims and a legal proceeding involving {name} and a counterparty.",
        ),
        ("Status", f"The matter is pending; {name} disclosed potential litigation risk."),
    ]
    return blocks, title


def _sanctions_blocks(name: str, request: FetchRequest):  # type: ignore[no-untyped-def]
    title = f"Sanctions Screening Notice — {name}"
    blocks = [
        (title, f"A sanctions screening notice references exposure relevant to {name}."),
        (
            "Detail",
            f"Regulators flagged sanctions and compliance considerations affecting {name}'s "
            "operations in certain countries.",
        ),
        ("Action", f"{name} is reviewing compliance controls in response."),
    ]
    return blocks, title


def _procurement_blocks(name: str, request: FetchRequest):  # type: ignore[no-untyped-def]
    title = f"Procurement Notice Relevant to {name}"
    blocks = [
        (title, f"A public procurement notice is relevant to {name}."),
        (
            "Requirement",
            f"A government agency solicited products and services that {name} may supply.",
        ),
        ("Opportunity", f"The notice signals a potential new opportunity for {name}."),
    ]
    return blocks, title


ReferenceGlobalRegulatorsConnector, normalize_global_regulators = _connector(
    "global_regulators", "regulatory_action", _global_regulators_blocks
)
ReferenceEsgConnector, normalize_esg = _connector("esg_reports", "esg_report", _esg_blocks)
ReferenceGovernmentContractsConnector, normalize_government_contracts = _connector(
    "government_contracts", "government_contract", _gov_contracts_blocks
)
ReferenceCourtFilingsConnector, normalize_court_filings = _connector(
    "court_filings", "court_filing", _court_filings_blocks
)
ReferenceSanctionsConnector, normalize_sanctions = _connector(
    "sanctions", "sanctions_notice", _sanctions_blocks
)
ReferenceProcurementConnector, normalize_procurement = _connector(
    "procurement_notices", "procurement_notice", _procurement_blocks
)
