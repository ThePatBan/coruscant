from __future__ import annotations

from coruscant.common.types import NormalizedDocument
from coruscant.intelligence.reliability import errors_for_source, score_source


def _doc(sections: int, published: str | None = "2025-01-31") -> NormalizedDocument:
    return NormalizedDocument(
        document_type="filing",
        source_uri="reference://x",
        canonical_id="x",
        title="T",
        published_at=published,  # type: ignore[arg-type]
        sections=[{"title": str(i), "content": "c"} for i in range(sections)],
    )


def test_high_authority_structured_source_scores_high() -> None:
    rel = score_source(
        source_type="sec_edgar",
        label="SEC EDGAR",
        authority=0.98,
        documents=[_doc(3), _doc(3)],
        error_count=0,
    )
    assert rel.tier == "high"
    assert rel.score >= 85
    assert rel.document_count == 2
    assert rel.latest_published == "2025-01-31"


def test_low_authority_source_scores_lower() -> None:
    high = score_source(
        source_type="sec_edgar", label="SEC", authority=0.98, documents=[_doc(3)], error_count=0
    )
    low = score_source(
        source_type="news", label="News", authority=0.5, documents=[_doc(3)], error_count=0
    )
    assert low.score < high.score


def test_errors_reduce_success_rate() -> None:
    rel = score_source(
        source_type="news", label="News", authority=0.5, documents=[_doc(2)], error_count=3
    )
    assert rel.success_rate < 1.0
    assert rel.document_count == 1


def test_errors_for_source_matches_run_error_format() -> None:
    errors = ["apple:news:Apr 2025: boom", "tesla:sec_edgar:FY2025: bad", "unknown source: bogus"]
    assert errors_for_source("news", errors) == 1
    assert errors_for_source("sec_edgar", errors) == 1
    assert errors_for_source("bogus", errors) == 1
    assert errors_for_source("patents", errors) == 0
