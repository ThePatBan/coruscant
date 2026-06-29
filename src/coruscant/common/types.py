from __future__ import annotations

from datetime import date, datetime
from hashlib import sha256
from typing import Any

from pydantic import BaseModel, Field

# Core domain-model schema version. Frozen at M1; evolve only via versioned,
# documented migrations (see ADR-0006).
SCHEMA_VERSION = "1.0"


def section_id(canonical_id: str, order: int) -> str:
    """Deterministic, stable identifier for a parsed section within a document.

    Stable across re-parses of the same document (same canonical_id + order) and
    unique even when two sections share a title.
    """

    return sha256(f"{canonical_id}:{order}".encode("utf-8")).hexdigest()[:16]


class SourceDocument(BaseModel):
    source_type: str
    source_uri: str
    fetched_at: datetime
    raw_content: str
    content_type: str | None = None
    source_id: str | None = None
    source_name: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def uri_hash(self) -> str:
        return sha256(self.source_uri.encode("utf-8")).hexdigest()


class NormalizedDocument(BaseModel):
    document_type: str
    source_uri: str
    canonical_id: str
    title: str | None = None
    published_at: datetime | date | None = None
    language: str | None = None
    sections: list[dict[str, Any]] = Field(default_factory=list)
    exhibits: list[dict[str, Any]] = Field(default_factory=list)
    entities: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RetrievalEvidence(BaseModel):
    source_uri: str
    title: str | None = None
    excerpt: str | None = None
    section_title: str | None = None
    canonical_id: str | None = None


class EvidenceSpan(BaseModel):
    source_uri: str
    excerpt: str
    section_title: str | None = None
    start_offset: int | None = None
    end_offset: int | None = None


class DocumentSection(BaseModel):
    title: str
    content: str
    order: int
    id: str | None = None  # deterministic, stable section identifier
    anchor: str | None = None
    evidence: list[EvidenceSpan] = Field(default_factory=list)


class DocumentExhibit(BaseModel):
    title: str
    content: str
    exhibit_number: str | None = None
    url: str | None = None
    evidence: list[EvidenceSpan] = Field(default_factory=list)


class GraphNode(BaseModel):
    kind: str
    key: str
    properties: dict[str, Any] = Field(default_factory=dict)


class GraphEdge(BaseModel):
    source_kind: str
    source_key: str
    relation: str
    target_kind: str
    target_key: str
    properties: dict[str, Any] = Field(default_factory=dict)
