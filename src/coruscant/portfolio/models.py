"""Portfolio models."""

from __future__ import annotations

from pydantic import BaseModel, Field

from coruscant.intelligence.models import ChangeSet, ExtractedEvent


class Holding(BaseModel):
    company_slug: str
    label: str | None = None


class Portfolio(BaseModel):
    id: str
    name: str
    holdings: list[Holding] = Field(default_factory=list)
    created_at: str


class PortfolioBriefing(BaseModel):
    portfolio_id: str
    name: str
    holdings: list[Holding] = Field(default_factory=list)
    headline: str
    material_changes: list[ChangeSet] = Field(default_factory=list)
    recent_events: list[ExtractedEvent] = Field(default_factory=list)
    companies_with_changes: int = 0
