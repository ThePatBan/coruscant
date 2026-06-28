"""Typed, evidence-bearing outputs of the intelligence layer.

Every derived statement is a :class:`Claim` that carries the source URI and the
section it was lifted from. Nothing in this layer is allowed to assert something
without a traceable citation.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, computed_field


class Claim(BaseModel):
    """A statement plus the exact source span that supports it."""

    text: str
    source_uri: str
    section_title: str | None = None
    canonical_id: str | None = None
    category: str | None = None


class DocumentSummary(BaseModel):
    canonical_id: str
    company_slug: str
    document_type: str
    source_type: str
    title: str | None = None
    published_at: str | None = None
    source_uri: str
    overview: str
    key_points: list[Claim] = Field(default_factory=list)
    risks: list[Claim] = Field(default_factory=list)
    opportunities: list[Claim] = Field(default_factory=list)
    management_commentary: list[Claim] = Field(default_factory=list)
    financial_highlights: list[Claim] = Field(default_factory=list)
    events: list[Claim] = Field(default_factory=list)
    generator: str = "reference-extractive"


class ExtractedEvent(BaseModel):
    canonical_id: str
    company_slug: str
    source_type: str
    category: str
    title: str
    description: str
    occurred_at: str | None = None
    source_uri: str
    section_title: str | None = None


class DocumentChange(BaseModel):
    kind: str  # "added" | "removed"
    category: str
    statement: str
    evidence: Claim


class ChangeSet(BaseModel):
    company_slug: str
    source_type: str
    current_canonical_id: str
    previous_canonical_id: str | None = None
    current_title: str | None = None
    previous_title: str | None = None
    changes: list[DocumentChange] = Field(default_factory=list)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def material(self) -> bool:
        return bool(self.changes)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def added_count(self) -> int:
        return sum(1 for change in self.changes if change.kind == "added")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def removed_count(self) -> int:
        return sum(1 for change in self.changes if change.kind == "removed")
