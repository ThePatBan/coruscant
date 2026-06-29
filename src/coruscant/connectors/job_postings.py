"""Reference connector for company job postings."""

from __future__ import annotations

from coruscant.common.types import NormalizedDocument, SourceDocument
from coruscant.connectors.base import FetchRequest, SourceConnector
from coruscant.connectors.common import build_source_document, normalize_reference_document

DOCUMENT_TYPE = "job_posting"


class ReferenceJobPostingsConnector(SourceConnector):
    """Synthesizes a deterministic job posting for offline development."""

    def fetch(self, request: FetchRequest) -> SourceDocument:
        name = request.company_name or request.company_slug.title()
        role = "Senior Software Engineer"
        blocks = [
            (
                f"{role} at {name}",
                f"{name} is hiring a {role} to build and operate systems supporting its "
                "core products. This posting signals investment in engineering capacity.",
            ),
            (
                "Responsibilities",
                "Design, build, and maintain production systems; collaborate across teams; "
                "and contribute to architecture and reliability.",
            ),
            (
                "Requirements",
                "Experience with distributed systems, data pipelines, and modern tooling, "
                f"plus alignment with the {name} engineering culture.",
            ),
        ]
        return build_source_document(
            source_type="job_postings",
            source_uri=request.source_uri,
            blocks=blocks,
            source_name=request.source_name,
            metadata={
                "company_slug": request.company_slug,
                "company_name": name,
                "title": f"{role} at {name}",
                "role": role,
                "published_at": request.published_at,
                "industry": request.industry,
            },
        )


def normalize_job_postings(document: SourceDocument) -> NormalizedDocument:
    return normalize_reference_document(document, document_type=DOCUMENT_TYPE)
