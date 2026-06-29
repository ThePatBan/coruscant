"""Reference connector for patent metadata."""

from __future__ import annotations

from coruscant.common.types import NormalizedDocument, SourceDocument
from coruscant.connectors.base import FetchRequest, SourceConnector
from coruscant.connectors.common import build_source_document, normalize_reference_document

DOCUMENT_TYPE = "patent"


class ReferencePatentsConnector(SourceConnector):
    """Synthesizes deterministic patent metadata for offline development."""

    def fetch(self, request: FetchRequest) -> SourceDocument:
        name = request.company_name or request.company_slug.title()
        title = f"{name} System And Method For Process Optimization"
        blocks = [
            (
                title,
                f"A patent assigned to {name} describing a system and method relevant to "
                "its core technology and operations.",
            ),
            (
                "Abstract",
                f"The disclosure covers techniques attributed to {name} for improving "
                "efficiency, reliability, or capability within its domain.",
            ),
            (
                "Claims",
                "The patent sets out independent and dependent claims defining the scope "
                "of the protected invention.",
            ),
        ]
        return build_source_document(
            source_type="patents",
            source_uri=request.source_uri,
            blocks=blocks,
            source_name=request.source_name,
            metadata={
                "company_slug": request.company_slug,
                "company_name": name,
                "title": title,
                "assignee": name,
                "published_at": request.published_at,
                "industry": request.industry,
            },
        )


def normalize_patents(document: SourceDocument) -> NormalizedDocument:
    return normalize_reference_document(document, document_type=DOCUMENT_TYPE)
