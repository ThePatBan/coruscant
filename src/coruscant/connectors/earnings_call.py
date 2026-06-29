"""Reference connector for earnings call transcripts."""

from __future__ import annotations

from coruscant.common.types import NormalizedDocument, SourceDocument
from coruscant.connectors.base import FetchRequest, SourceConnector
from coruscant.connectors.common import (
    build_source_document,
    developments_text,
    normalize_reference_document,
)

DOCUMENT_TYPE = "transcript"


class ReferenceEarningsCallConnector(SourceConnector):
    """Synthesizes a deterministic earnings call transcript for offline development."""

    def fetch(self, request: FetchRequest) -> SourceDocument:
        name = request.company_name or request.company_slug.title()
        period = request.period or "Q4 2025"
        blocks = [
            (
                "Prepared Remarks",
                f"The {name} management team opened the {period} earnings call by "
                "summarizing results and the operating environment for the quarter.",
            ),
            (
                "Outlook",
                f"{name} described demand trends and provided a forward outlook, noting "
                "investments in product development and operating efficiency.",
            ),
            (
                "Questions And Answers",
                f"Analysts asked {name} about margins, capital expenditure, and "
                "competitive dynamics; management addressed each in turn.",
            ),
            ("Recent Developments", developments_text(request.revision)),
        ]
        return build_source_document(
            source_type="earnings_call",
            source_uri=request.source_uri,
            blocks=blocks,
            source_name=request.source_name,
            metadata={
                "company_slug": request.company_slug,
                "company_name": name,
                "title": f"{name} {period} Earnings Call",
                "period": period,
                "published_at": request.published_at,
                "industry": request.industry,
            },
        )


def normalize_earnings_call(document: SourceDocument) -> NormalizedDocument:
    return normalize_reference_document(document, document_type=DOCUMENT_TYPE)
