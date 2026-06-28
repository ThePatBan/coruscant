"""Reference connector for company news articles."""

from __future__ import annotations

from coruscant.common.types import NormalizedDocument, SourceDocument
from coruscant.connectors.base import FetchRequest, SourceConnector
from coruscant.connectors.common import build_source_document, normalize_reference_document

DOCUMENT_TYPE = "news_article"


class ReferenceNewsConnector(SourceConnector):
    """Synthesizes a deterministic news article for offline development."""

    def fetch(self, request: FetchRequest) -> SourceDocument:
        name = request.company_name or request.company_slug.title()
        headline = f"{name} Expands Operations Amid Sector Shifts"
        blocks = [
            (
                headline,
                f"{name} is reportedly expanding operations as it responds to shifting "
                f"conditions in the {request.industry or 'broader'} sector.",
            ),
            (
                "Context",
                f"Industry observers note that {name} faces both opportunities and risks "
                "as competitive and macroeconomic conditions evolve.",
            ),
            (
                "Analysis",
                f"Analysts suggest the move could influence how {name} is positioned "
                "relative to peers over the coming year.",
            ),
        ]
        return build_source_document(
            source_type="news",
            source_uri=request.source_uri,
            blocks=blocks,
            source_name=request.source_name,
            metadata={
                "company_slug": request.company_slug,
                "company_name": name,
                "title": headline,
                "headline": headline,
                "publisher": "Reference Newswire",
                "industry": request.industry,
            },
        )


def normalize_news(document: SourceDocument) -> NormalizedDocument:
    return normalize_reference_document(document, document_type=DOCUMENT_TYPE)
