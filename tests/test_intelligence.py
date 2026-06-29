from __future__ import annotations

from coruscant.common.types import NormalizedDocument
from coruscant.intelligence import (
    ReferenceChangeDetector,
    ReferenceEventExtractor,
    ReferenceSummarizer,
)


def _doc(canonical_id: str, sections: list[tuple[str, str]], **kw: object) -> NormalizedDocument:
    return NormalizedDocument(
        document_type=str(kw.get("document_type", "filing")),
        source_uri=f"reference://{canonical_id}",
        canonical_id=canonical_id,
        title=str(kw.get("title", f"Doc {canonical_id}")),
        published_at=kw.get("published_at"),  # type: ignore[arg-type]
        sections=[
            {"title": t, "content": c, "evidence": [{"source_uri": f"reference://{canonical_id}"}]}
            for t, c in sections
        ],
    )


APPLE_V1 = _doc(
    "apple-v1",
    [
        ("Item 1. Business", "Apple designs and markets devices and services."),
        (
            "Item 1A. Risk Factors",
            "Apple faces competition risk. The company is exposed to supply chain shortage risk.",
        ),
        (
            "Item 7. MD&A",
            "Apple reported revenue growth. Management expects full-year guidance to hold.",
        ),
    ],
    published_at="2024-01-31",
)

APPLE_V2 = _doc(
    "apple-v2",
    [
        ("Item 1. Business", "Apple designs and markets devices and services."),
        (
            "Item 1A. Risk Factors",
            "Apple faces competition risk. The company faces new regulatory investigation risk.",
        ),
        (
            "Item 7. MD&A",
            "Apple reported revenue growth. Management lowered guidance for the full year. "
            "Apple appointed a new chief financial officer.",
        ),
    ],
    published_at="2025-01-31",
)


def test_summarizer_buckets_are_cited() -> None:
    summary = ReferenceSummarizer().summarize(APPLE_V2, company_slug="apple", source_type="sec_edgar")
    assert summary.overview
    assert summary.risks, "expected risk claims"
    assert summary.management_commentary
    assert summary.financial_highlights
    # Every claim is traceable to its source.
    for bucket in (summary.risks, summary.key_points, summary.financial_highlights):
        for claim in bucket:
            assert claim.source_uri == APPLE_V2.source_uri
            assert claim.canonical_id == "apple-v2"
    risk_text = " ".join(c.text for c in summary.risks).lower()
    assert "risk" in risk_text


def test_event_extractor_finds_actions_with_evidence() -> None:
    events = ReferenceEventExtractor().extract(APPLE_V2, company_slug="apple", source_type="sec_edgar")
    categories = {e.category for e in events}
    assert "executive" in categories  # appointed a new CFO
    assert any(e.category == "guidance" for e in events)
    for event in events:
        assert event.source_uri == APPLE_V2.source_uri
        assert event.occurred_at == "2025-01-31"
        assert event.description


def test_change_detector_finds_material_added_and_removed() -> None:
    change_set = ReferenceChangeDetector().diff(
        APPLE_V2, APPLE_V1, company_slug="apple", source_type="sec_edgar"
    )
    assert change_set.material
    assert change_set.previous_canonical_id == "apple-v1"
    statements = {(c.kind, c.statement.lower()) for c in change_set.changes}
    # New regulatory risk appeared; supply chain risk disappeared.
    assert any(kind == "added" and "regulatory" in text for kind, text in statements)
    assert any(kind == "removed" and "supply chain" in text for kind, text in statements)
    # Executive + guidance changes surface and are evidence-backed.
    assert any(c.category == "executive" for c in change_set.changes)
    for change in change_set.changes:
        assert change.evidence.source_uri
        assert change.evidence.canonical_id in {"apple-v1", "apple-v2"}


def test_change_detector_first_disclosure_has_no_changes() -> None:
    change_set = ReferenceChangeDetector().diff(
        APPLE_V1, None, company_slug="apple", source_type="sec_edgar"
    )
    assert not change_set.material
    assert change_set.previous_canonical_id is None


def test_change_materiality_ordering() -> None:
    change_set = ReferenceChangeDetector().diff(
        APPLE_V2, APPLE_V1, company_slug="apple", source_type="sec_edgar"
    )
    # Guidance/executive rank above generic categories, so they lead.
    assert change_set.changes[0].category in {"guidance", "executive", "regulatory"}
