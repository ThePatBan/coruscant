from __future__ import annotations

from coruscant.common.types import NormalizedDocument
from coruscant.search.hybrid import HybridRetrievalEngine


def _apple_doc() -> NormalizedDocument:
    return NormalizedDocument(
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


def test_hybrid_retrieve_and_evidence() -> None:
    engine = HybridRetrievalEngine()
    engine.add(_apple_doc())

    results = engine.retrieve("Apple market")
    assert [doc.canonical_id for doc in results] == ["abc123"]

    with_evidence = engine.retrieve_with_evidence("Apple market")
    document, evidence = with_evidence[0]
    assert document.canonical_id == "abc123"
    assert evidence[0].section_title == "Business"
    assert evidence[0].excerpt == "Apple entered a new market"


def test_hybrid_read_model_accessors() -> None:
    engine = HybridRetrievalEngine()
    engine.add(_apple_doc())
    assert len(engine) == 1
    assert engine.get_document("abc123") is not None
    assert engine.get_document("missing") is None
    assert [doc.canonical_id for doc in engine.all_documents()] == ["abc123"]


def test_hybrid_semantic_recall_without_exact_terms() -> None:
    engine = HybridRetrievalEngine()
    engine.add(_apple_doc())
    # No lexical overlap with the stored "market" wording, but the same tokens
    # embed near each other so the vector half still surfaces the document.
    results = engine.retrieve("Apple entered market")
    assert results and results[0].canonical_id == "abc123"
