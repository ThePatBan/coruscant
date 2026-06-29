from __future__ import annotations

from coruscant.common.types import NormalizedDocument
from coruscant.search.embeddings import (
    HashingEmbedder,
    InMemoryVectorIndex,
    cosine_similarity,
)


def _doc(canonical_id: str, title: str, content: str, document_type: str = "filing") -> NormalizedDocument:
    return NormalizedDocument(
        document_type=document_type,
        source_uri=f"reference://{canonical_id}",
        canonical_id=canonical_id,
        title=title,
        sections=[{"title": "Body", "content": content}],
    )


def test_embedding_is_deterministic() -> None:
    embedder = HashingEmbedder()
    assert embedder.embed_text("apple revenue growth") == embedder.embed_text("apple revenue growth")


def test_embedding_is_unit_normalized() -> None:
    embedder = HashingEmbedder()
    vector = embedder.embed_text("apple designs devices and services")
    magnitude = sum(value * value for value in vector) ** 0.5
    assert abs(magnitude - 1.0) < 1e-9


def test_cosine_similar_beats_dissimilar() -> None:
    embedder = HashingEmbedder()
    base = embedder.embed_text("apple designs devices and services")
    near = embedder.embed_text("apple designs devices")
    far = embedder.embed_text("orbital rocket launch mission")
    assert cosine_similarity(base, near) > cosine_similarity(base, far)


def test_vector_index_ranks_relevant_document_first() -> None:
    index = InMemoryVectorIndex()
    index.add_document(_doc("a", "Apple 10-K", "Apple designs devices and services"))
    index.add_document(_doc("b", "SpaceX News", "orbital rocket launch mission", "news_article"))

    results = index.search("apple devices services")

    assert len(index) == 2
    assert results[0].document.canonical_id == "a"
    assert results[0].score > 0.0
