"""Shared helpers for reference connectors and normalizers.

Reference connectors emit small, deterministic sample documents so the full
ingestion lifecycle can run offline. Each document is rendered as markdown-style
``## Heading`` blocks; :func:`normalize_reference_document` parses those blocks
back into provenance-carrying sections. Live connectors (for example
:class:`coruscant.connectors.sec_edgar.EdgarHttpConnector`) remain the production
path and reuse the same normalized document model.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from hashlib import sha256
import re

from coruscant.common.types import (
    DocumentSection,
    EvidenceSpan,
    NormalizedDocument,
    SourceDocument,
    section_id,
)

EXCERPT_LIMIT = 280
_HEADING_RE = re.compile(r"(?m)^##\s+(?P<title>.+?)\s*$")

# Period-over-period variation that drives the change-detection demo. The prior
# revision carries a risk that is later resolved; the current revision discloses
# new, materially different developments. Sentences are deliberately distinct so
# the diff is clean and each change traces to a real source span.
_PRIOR_DEVELOPMENT = "The company flagged supply chain shortage risk during the prior period."
_CURRENT_DEVELOPMENTS = (
    "The company disclosed a new regulatory investigation risk.",
    "The company appointed a new chief financial officer.",
    "The company lowered full-year guidance amid softer demand.",
)


def developments_text(revision: int) -> str:
    """Revision-specific 'recent developments' prose for periodic sources."""

    if revision <= 0:
        return _PRIOR_DEVELOPMENT
    return " ".join(_CURRENT_DEVELOPMENTS)


def canonical_id_for(source_uri: str) -> str:
    """Stable canonical identifier derived from a source URI."""

    return sha256(source_uri.encode("utf-8")).hexdigest()


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "section"


def make_evidence(source_uri: str, section_title: str, excerpt: str) -> EvidenceSpan:
    return EvidenceSpan(
        source_uri=source_uri,
        section_title=section_title,
        excerpt=excerpt[:EXCERPT_LIMIT],
    )


def parse_reference_date(value: object) -> datetime | date | None:
    if isinstance(value, (datetime, date)):
        return value
    if isinstance(value, str):
        for fmt in ("%Y-%m-%d", "%Y%m%d", "%Y-%m-%dT%H:%M:%S%z"):
            try:
                parsed = datetime.strptime(value, fmt)
            except ValueError:
                continue
            return parsed.date() if fmt in {"%Y-%m-%d", "%Y%m%d"} else parsed
    return None


def render_reference_document(blocks: list[tuple[str, str]]) -> str:
    """Render ``(title, body)`` blocks into the ``## Heading`` markdown format."""

    parts = [f"## {title}\n{body.strip()}" for title, body in blocks]
    return "\n\n".join(parts)


def _split_reference_sections(text: str) -> list[tuple[str, str]]:
    matches = list(_HEADING_RE.finditer(text))
    if not matches:
        stripped = text.strip()
        return [("Document", stripped)] if stripped else []
    blocks: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        title = match.group("title").strip()
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        if body:
            blocks.append((title, body))
    return blocks


def reference_company_entities(document: SourceDocument) -> list[dict[str, str]]:
    entities: list[dict[str, str]] = []
    slug = document.metadata.get("company_slug")
    if slug:
        entities.append(
            {
                "kind": "Company",
                "key": str(slug),
                "name": str(document.metadata.get("company_name", slug)),
            }
        )
    return entities


def build_source_document(
    *,
    source_type: str,
    source_uri: str,
    blocks: list[tuple[str, str]],
    source_name: str,
    metadata: dict[str, object],
) -> SourceDocument:
    """Construct a reference :class:`SourceDocument` from rendered blocks."""

    payload = dict(metadata)
    payload.setdefault("provenance", "reference-sample")
    return SourceDocument(
        source_type=source_type,
        source_uri=source_uri,
        fetched_at=datetime.now(tz=timezone.utc),
        raw_content=render_reference_document(blocks),
        content_type="text/markdown",
        source_name=source_name,
        metadata=payload,
    )


def normalize_reference_document(
    document: SourceDocument,
    *,
    document_type: str,
) -> NormalizedDocument:
    """Parse a reference source document into a normalized, evidence-bearing form."""

    canonical_id = canonical_id_for(document.source_uri)
    sections: list[dict[str, object]] = []
    for order, (title, content) in enumerate(_split_reference_sections(document.raw_content), start=1):
        sections.append(
            DocumentSection(
                title=title,
                content=content,
                order=order,
                id=section_id(canonical_id, order),
                anchor=slugify(title),
                evidence=[make_evidence(document.source_uri, title, content)],
            ).model_dump()
        )
    published_at = parse_reference_date(
        document.metadata.get("published_at") or document.metadata.get("filing_date")
    )
    doc_title = (
        document.metadata.get("title")
        or document.metadata.get("headline")
        or document.metadata.get("company_name")
        or document.source_name
    )
    metadata = dict(document.metadata)
    if document.source_name:
        metadata.setdefault("source_name", document.source_name)
    return NormalizedDocument(
        document_type=document_type,
        source_uri=document.source_uri,
        canonical_id=canonical_id,
        title=str(doc_title) if doc_title is not None else None,
        published_at=published_at,
        language=str(document.metadata.get("language", "en")),
        sections=sections,
        entities=reference_company_entities(document),
        metadata=metadata,
    )
