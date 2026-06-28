"""Hybrid retrieval blending lexical term overlap with vector similarity.

Documents are added to both a lexical engine (for keyword precision and evidence
extraction) and a vector index (for semantic recall). Ranking is a weighted blend
of the two normalized scores, and evidence is sourced from the lexical engine so
every result keeps a traceable excerpt.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from coruscant.common.types import NormalizedDocument, RetrievalEvidence
from coruscant.search.contracts import RetrievalEngine
from coruscant.search.embeddings import InMemoryVectorIndex
from coruscant.search.reference import InMemoryRetrievalEngine


@dataclass
class HybridRetrievalEngine(RetrievalEngine):
    lexical: InMemoryRetrievalEngine = field(default_factory=InMemoryRetrievalEngine)
    vector: InMemoryVectorIndex = field(default_factory=InMemoryVectorIndex)
    lexical_weight: float = 0.5
    vector_weight: float = 0.5
    _documents: dict[str, NormalizedDocument] = field(default_factory=dict)

    def add(self, document: NormalizedDocument) -> None:
        self.lexical.add(document)
        self.vector.add_document(document)
        self._documents[document.canonical_id] = document

    def add_document(self, document: NormalizedDocument) -> None:
        # Allow the hybrid engine to double as the pipeline's embedding index.
        self.add(document)

    def __len__(self) -> int:
        return len(self._documents)

    def all_documents(self) -> list[NormalizedDocument]:
        return list(self._documents.values())

    def get_document(self, canonical_id: str) -> NormalizedDocument | None:
        return self._documents.get(canonical_id)

    def _blended_scores(self, query: str) -> dict[str, float]:
        lexical_scores = self.lexical.score_documents(query)
        vector_scores = self.vector.scores(query)
        blended: dict[str, float] = {}
        for canonical_id in self._documents:
            lexical = lexical_scores.get(canonical_id, 0.0)
            vector = max(vector_scores.get(canonical_id, 0.0), 0.0)
            blended[canonical_id] = self.lexical_weight * lexical + self.vector_weight * vector
        return blended

    def retrieve(self, query: str, *, top_k: int = 10) -> list[NormalizedDocument]:
        ranked = sorted(
            self._blended_scores(query).items(), key=lambda item: item[1], reverse=True
        )
        results: list[NormalizedDocument] = []
        for canonical_id, score in ranked:
            if score <= 0.0:
                continue
            results.append(self._documents[canonical_id])
            if len(results) >= top_k:
                break
        return results

    def retrieve_with_evidence(
        self, query: str, *, top_k: int = 10
    ) -> list[tuple[NormalizedDocument, list[RetrievalEvidence]]]:
        documents = self.retrieve(query, top_k=top_k)
        results: list[tuple[NormalizedDocument, list[RetrievalEvidence]]] = []
        for document in documents:
            results.append((document, _evidence_for(query, document)))
        return results


def _evidence_for(query: str, document: NormalizedDocument) -> list[RetrievalEvidence]:
    terms = {term.lower() for term in query.split() if term}
    evidence: list[RetrievalEvidence] = []
    for section in document.sections:
        content = str(section.get("content") or "")
        if terms and not any(term in content.lower() for term in terms):
            continue
        excerpt = content[:280]
        section_evidence = section.get("evidence") or []
        if isinstance(section_evidence, list) and section_evidence:
            first = section_evidence[0]
            if isinstance(first, dict):
                excerpt = str(first.get("excerpt") or excerpt)
        evidence.append(
            RetrievalEvidence(
                source_uri=document.source_uri,
                title=document.title,
                excerpt=excerpt,
                section_title=str(section.get("title") or ""),
                canonical_id=document.canonical_id,
            )
        )
    if not evidence:
        first_content = document.sections[0].get("content") if document.sections else None
        evidence.append(
            RetrievalEvidence(
                source_uri=document.source_uri,
                title=document.title,
                excerpt=str(first_content) if first_content is not None else None,
                canonical_id=document.canonical_id,
            )
        )
    return evidence
