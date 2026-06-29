from __future__ import annotations

from coruscant.intelligence.analyst import ReferenceAnalyst
from coruscant.intelligence.changes import ReferenceChangeDetector
from coruscant.common.types import NormalizedDocument
from coruscant.intelligence.events import ReferenceEventExtractor


def _docs() -> tuple[NormalizedDocument, NormalizedDocument]:
    prev = NormalizedDocument(
        document_type="filing",
        source_uri="reference://sec_edgar/apple/2024",
        canonical_id="a1",
        title="Apple 10-K",
        sections=[{"title": "MD&A", "content": "Apple reaffirmed full-year guidance."}],
    )
    cur = NormalizedDocument(
        document_type="filing",
        source_uri="reference://sec_edgar/apple/2025",
        canonical_id="a2",
        title="Apple 10-K",
        sections=[
            {
                "title": "MD&A",
                "content": "Apple lowered full-year guidance amid softer demand. "
                "Apple disclosed a new regulatory investigation risk. "
                "Apple appointed a new chief financial officer.",
            }
        ],
    )
    return prev, cur


def test_analyst_produces_cited_confidence_banded_concerns() -> None:
    prev, cur = _docs()
    change_set = ReferenceChangeDetector().diff(cur, prev, company_slug="apple", source_type="sec_edgar")
    events = ReferenceEventExtractor().extract(cur, company_slug="apple", source_type="sec_edgar")

    report = ReferenceAnalyst().analyze(
        company_slug="apple",
        company_name="Apple",
        question="Why should I worry about Apple over the next six months?",
        change_sets=[change_set],
        events=events,
        country_exposures=[("Taiwan", "TSMC")],
    )

    assert report.focus == "risk"
    assert report.concerns
    categories = {c.category for c in report.concerns}
    assert {"guidance", "regulatory", "executive"} <= categories
    assert any(c.category == "supply_chain" and "Taiwan" in c.title for c in report.concerns)

    # Multi-step method is explicit and ordered.
    assert [s.label for s in report.steps] == ["Search", "Read", "Reason", "Compare", "Cite", "Answer"]

    # Every concern is cited and never claims certainty.
    for concern in report.concerns:
        assert concern.evidence and concern.evidence[0].source_uri
        assert 0.0 < concern.confidence <= 0.85
    # High-severity concerns lead.
    assert report.concerns[0].severity == "high"
    assert "Apple" in report.headline


def test_analyst_detects_opportunity_focus() -> None:
    report = ReferenceAnalyst().analyze(
        company_slug="apple",
        company_name="Apple",
        question="What is the upside / opportunity for Apple?",
        change_sets=[],
        events=[],
        country_exposures=[],
    )
    assert report.focus == "opportunity"
    assert "Apple" in report.headline
