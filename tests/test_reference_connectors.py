from __future__ import annotations

import pytest

from coruscant.connectors.base import FetchRequest
from coruscant.connectors.earnings_call import ReferenceEarningsCallConnector, normalize_earnings_call
from coruscant.connectors.investor_relations import (
    ReferenceInvestorRelationsConnector,
    normalize_investor_relations,
)
from coruscant.connectors.job_postings import ReferenceJobPostingsConnector, normalize_job_postings
from coruscant.connectors.news import ReferenceNewsConnector, normalize_news
from coruscant.connectors.patents import ReferencePatentsConnector, normalize_patents
from coruscant.connectors.press_release import ReferencePressReleaseConnector, normalize_press_release

CASES = [
    (ReferenceInvestorRelationsConnector, normalize_investor_relations, "investor_relations", "investor_update"),
    (ReferenceEarningsCallConnector, normalize_earnings_call, "earnings_call", "transcript"),
    (ReferencePressReleaseConnector, normalize_press_release, "press_release", "press_release"),
    (ReferenceJobPostingsConnector, normalize_job_postings, "job_postings", "job_posting"),
    (ReferenceNewsConnector, normalize_news, "news", "news_article"),
    (ReferencePatentsConnector, normalize_patents, "patents", "patent"),
]


@pytest.mark.parametrize("connector_cls,normalizer,source_type,document_type", CASES)
def test_reference_connector_roundtrip(connector_cls, normalizer, source_type, document_type) -> None:
    connector = connector_cls()
    request = FetchRequest(
        company_slug="apple",
        source_name=source_type,
        source_uri=f"reference://{source_type}/apple",
        company_name="Apple",
        industry="Technology",
    )

    raw = connector.fetch(request)
    normalized = normalizer(raw)

    assert raw.source_type == source_type
    assert raw.metadata["provenance"] == "reference-sample"
    assert normalized.document_type == document_type
    assert len(normalized.sections) >= 2
    # Every section carries traceable evidence back to the source URI.
    for section in normalized.sections:
        assert section["evidence"][0]["source_uri"] == request.source_uri
    assert normalized.entities[0] == {"kind": "Company", "key": "apple", "name": "Apple"}
    assert "Apple" in (normalized.sections[0]["content"])


def test_reference_documents_are_deterministic() -> None:
    request = FetchRequest(
        company_slug="tesla",
        source_name="news",
        source_uri="reference://news/tesla",
        company_name="Tesla",
        industry="Automotive",
    )
    first = normalize_news(ReferenceNewsConnector().fetch(request))
    second = normalize_news(ReferenceNewsConnector().fetch(request))
    assert first.canonical_id == second.canonical_id
    assert [s["content"] for s in first.sections] == [s["content"] for s in second.sections]
