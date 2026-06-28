"""Reference connector for investor relations materials."""

from __future__ import annotations

from coruscant.common.types import NormalizedDocument, SourceDocument
from coruscant.connectors.base import FetchRequest, SourceConnector
from coruscant.connectors.common import (
    build_source_document,
    developments_text,
    normalize_reference_document,
)

DOCUMENT_TYPE = "investor_update"


class ReferenceInvestorRelationsConnector(SourceConnector):
    """Synthesizes a deterministic investor update for offline development."""

    def fetch(self, request: FetchRequest) -> SourceDocument:
        name = request.company_name or request.company_slug.title()
        period = request.period or "FY2025"
        blocks = [
            (
                f"{name} Investor Update {period}",
                f"{name} published a quarterly investor update covering financial "
                "performance, operating highlights, and forward guidance.",
            ),
            (
                "Financial Highlights",
                f"{name} reported revenue and operating margin in line with prior "
                "guidance, with growth across its core business segments.",
            ),
            (
                "Guidance",
                f"{name} reaffirmed full-year guidance and outlined capital allocation "
                "priorities including reinvestment and shareholder returns.",
            ),
            ("Recent Developments", developments_text(request.revision)),
        ]
        return build_source_document(
            source_type="investor_relations",
            source_uri=request.source_uri,
            blocks=blocks,
            source_name=request.source_name,
            metadata={
                "company_slug": request.company_slug,
                "company_name": name,
                "title": f"{name} Investor Update {period}",
                "period": period,
                "published_at": request.published_at,
                "industry": request.industry,
            },
        )


def normalize_investor_relations(document: SourceDocument) -> NormalizedDocument:
    return normalize_reference_document(document, document_type=DOCUMENT_TYPE)
