from __future__ import annotations

from coruscant.common.types import NormalizedDocument
from coruscant.search.reference import InMemoryRetrievalEngine, TemplateReasoningLayer


def test_in_memory_retrieval_and_reasoning() -> None:
    document = NormalizedDocument(
        document_type="filing",
        source_uri="https://example.com/filing",
        canonical_id="abc123",
        title="Apple 10-K",
        sections=[
            {
                "title": "Business",
                "content": "Apple entered a new market",
                "evidence": [
                    {
                        "source_uri": "https://example.com/filing",
                        "excerpt": "Apple entered a new market",
                        "section_title": "Business",
                    }
                ],
            }
        ],
        entities=[{"kind": "Company", "key": "apple"}],
    )
    engine = InMemoryRetrievalEngine()
    engine.add(document)
    reasoning = TemplateReasoningLayer(engine)

    results = engine.retrieve("Apple market")
    answer = reasoning.answer("Apple market")

    assert results == [document]
    assert "Apple 10-K" in answer
    assert "Business" in answer
    assert "Apple entered a new market" in answer
