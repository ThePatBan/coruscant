"""Source reliability scoring and monitoring.

Blends inherent source authority with observed signals from what was actually
ingested (structure, completeness, ingestion success) into a 0..100 score and a
tier, so the platform can weight and monitor its sources.
"""

from __future__ import annotations

from pydantic import BaseModel

from coruscant.common.types import NormalizedDocument
from coruscant.intelligence.text import iso_date


class SourceReliability(BaseModel):
    source_type: str
    label: str
    authority: float
    document_count: int
    structure_score: float
    completeness_score: float
    success_rate: float
    score: int
    tier: str
    latest_published: str | None = None


def _tier(score: int) -> str:
    if score >= 85:
        return "high"
    if score >= 70:
        return "medium"
    return "low"


def score_source(
    *,
    source_type: str,
    label: str,
    authority: float,
    documents: list[NormalizedDocument],
    error_count: int,
) -> SourceReliability:
    count = len(documents)
    if count:
        structure = sum(1 for d in documents if len(d.sections) >= 2) / count
        completeness = sum(1 for d in documents if d.published_at and d.title) / count
        published = [iso_date(d.published_at) for d in documents if d.published_at]
        latest = max(p for p in published if p) if any(published) else None
    else:
        structure = 0.0
        completeness = 0.0
        latest = None

    attempts = count + error_count
    success_rate = (count / attempts) if attempts else 1.0

    raw = 0.5 * authority + 0.2 * structure + 0.15 * completeness + 0.15 * success_rate
    score = round(100 * raw)
    return SourceReliability(
        source_type=source_type,
        label=label,
        authority=authority,
        document_count=count,
        structure_score=round(structure, 3),
        completeness_score=round(completeness, 3),
        success_rate=round(success_rate, 3),
        score=score,
        tier=_tier(score),
        latest_published=latest,
    )


def errors_for_source(source_type: str, errors: list[str]) -> int:
    """Count run errors attributed to a source (errors are 'slug:source:label: ...')."""

    return sum(
        1
        for e in errors
        if f":{source_type}:" in e or e == f"unknown source: {source_type}"
    )
