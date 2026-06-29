"""Reference connector for company press releases."""

from __future__ import annotations

from coruscant.common.types import NormalizedDocument, SourceDocument
from coruscant.connectors.base import FetchRequest, SourceConnector
from coruscant.connectors.common import build_source_document, normalize_reference_document

DOCUMENT_TYPE = "press_release"


class ReferencePressReleaseConnector(SourceConnector):
    """Synthesizes a deterministic press release for offline development."""

    def fetch(self, request: FetchRequest) -> SourceDocument:
        name = request.company_name or request.company_slug.title()
        headline = f"{name} Announces New Product and Operational Milestones"
        blocks = [
            (
                headline,
                f"{name} today announced a new product initiative alongside operational "
                "milestones intended to expand its market presence.",
            ),
            (
                "Details",
                f"The announcement from {name} outlines availability, intended customers, "
                "and the strategic rationale behind the initiative.",
            ),
            (
                "About",
                f"{name} operates in the {request.industry or 'technology'} sector and "
                "serves customers across multiple markets.",
            ),
        ]
        return build_source_document(
            source_type="press_release",
            source_uri=request.source_uri,
            blocks=blocks,
            source_name=request.source_name,
            metadata={
                "company_slug": request.company_slug,
                "company_name": name,
                "title": headline,
                "headline": headline,
                "published_at": request.published_at,
                "industry": request.industry,
            },
        )


def normalize_press_release(document: SourceDocument) -> NormalizedDocument:
    return normalize_reference_document(document, document_type=DOCUMENT_TYPE)
