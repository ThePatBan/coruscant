"""Milestone 3 — Intelligence Layer: uniform output contract.

Every intelligence output must carry evidence, a recorded (bounded) confidence,
provenance, and be reproducible (deterministic + a generator marker).
"""

from __future__ import annotations

from coruscant.common.types import NormalizedDocument
from coruscant.intelligence.analyst import ReferenceAnalyst
from coruscant.intelligence.changes import ReferenceChangeDetector
from coruscant.intelligence.confidence import MAX_CONFIDENCE
from coruscant.intelligence.events import ReferenceEventExtractor
from coruscant.intelligence.signals import ReferenceSignalEngine
from coruscant.intelligence.summarizer import ReferenceSummarizer


def _doc(cid: str, content: str) -> NormalizedDocument:
    return NormalizedDocument(
        document_type="filing",
        source_uri=f"reference://sec_edgar/apple/{cid}",
        canonical_id=cid,
        title="Apple 10-K",
        sections=[{"title": "MD&A", "content": content}],
    )


PREV = _doc("p", "Apple reaffirmed full-year guidance.")
CUR = _doc(
    "c",
    "Apple lowered full-year guidance amid softer demand. "
    "Apple disclosed a new regulatory investigation risk.",
)


def _bounded(confidence: float) -> bool:
    return 0.0 < confidence <= MAX_CONFIDENCE


def test_summary_claims_carry_confidence_and_provenance() -> None:
    summary = ReferenceSummarizer().summarize(CUR, company_slug="apple", source_type="sec_edgar")
    assert summary.generator
    claims = summary.risks + summary.key_points + summary.financial_highlights + [summary.overview]
    assert claims
    for claim in claims:
        assert claim.source_uri  # evidence
        assert claim.canonical_id  # provenance
        assert _bounded(claim.confidence)  # recorded, bounded confidence


def test_events_carry_confidence_provenance_generator() -> None:
    events = ReferenceEventExtractor().extract(CUR, company_slug="apple", source_type="sec_edgar")
    assert events
    for event in events:
        assert event.source_uri and event.canonical_id
        assert event.generator
        assert _bounded(event.confidence)


def test_changes_carry_confidence_and_cited_evidence() -> None:
    change_set = ReferenceChangeDetector().diff(CUR, PREV, company_slug="apple", source_type="sec_edgar")
    assert change_set.generator
    assert change_set.changes
    for change in change_set.changes:
        assert _bounded(change.confidence)
        assert change.evidence.source_uri and change.evidence.canonical_id
        assert _bounded(change.evidence.confidence)


def test_outputs_are_reproducible() -> None:
    # Deterministic: identical inputs -> identical outputs (reproducibility).
    s1 = ReferenceSummarizer().summarize(CUR, company_slug="apple", source_type="sec_edgar")
    s2 = ReferenceSummarizer().summarize(CUR, company_slug="apple", source_type="sec_edgar")
    assert s1.model_dump() == s2.model_dump()
    c1 = ReferenceChangeDetector().diff(CUR, PREV, company_slug="apple", source_type="sec_edgar")
    c2 = ReferenceChangeDetector().diff(CUR, PREV, company_slug="apple", source_type="sec_edgar")
    assert c1.model_dump() == c2.model_dump()


def test_analyst_and_signals_already_bounded_and_cited() -> None:
    change_set = ReferenceChangeDetector().diff(CUR, PREV, company_slug="apple", source_type="sec_edgar")
    events = ReferenceEventExtractor().extract(CUR, company_slug="apple", source_type="sec_edgar")
    report = ReferenceAnalyst().analyze(
        company_slug="apple",
        company_name="Apple",
        question="risk?",
        change_sets=[change_set],
        events=events,
        country_exposures=[("Taiwan", "TSMC")],
    )
    for concern in report.concerns:
        assert _bounded(concern.confidence) and concern.evidence[0].source_uri
    signals = ReferenceSignalEngine().signals_for(
        company_slug="apple",
        company_name="Apple",
        documents=[CUR],
        change_sets=[change_set],
        events=events,
        country_exposures=[("Taiwan", "TSMC")],
    )
    for signal in signals:
        assert _bounded(signal.strength) and signal.evidence[0].source_uri
