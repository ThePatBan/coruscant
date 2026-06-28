from __future__ import annotations

from dataclasses import dataclass, field

from coruscant.common.types import NormalizedDocument, RetrievalEvidence
from coruscant.search.contracts import (
    ReasoningLayer,
    RetrievalEngine,
)
from coruscant.search.embeddings import document_text


@dataclass
class InMemoryRetrievalEngine(RetrievalEngine):
    documents: list[NormalizedDocument] = field(default_factory=list)

    def add(self, document: NormalizedDocument) -> None:
        self.documents.append(document)

    @staticmethod
    def _haystack(document: NormalizedDocument) -> str:
        # Use real text (title, section titles/content, entity names) rather than
        # repr() of containers, which would leak Python syntax into matching.
        return (document.source_uri + " " + document_text(document)).lower()

    def retrieve(self, query: str, *, top_k: int = 10) -> list[NormalizedDocument]:
        terms = {term.lower() for term in query.split() if term}
        scored: list[tuple[int, NormalizedDocument]] = []
        for document in self.documents:
            haystack = self._haystack(document)
            score = sum(1 for term in terms if term in haystack)
            if score:
                scored.append((score, document))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [document for _, document in scored[:top_k]]

    def score_documents(self, query: str) -> dict[str, float]:
        """Normalized (0..1) lexical term-overlap score per canonical id."""

        terms = {term.lower() for term in query.split() if term}
        if not terms:
            return {document.canonical_id: 0.0 for document in self.documents}
        scores: dict[str, float] = {}
        for document in self.documents:
            haystack = self._haystack(document)
            matched = sum(1 for term in terms if term in haystack)
            scores[document.canonical_id] = matched / len(terms)
        return scores

    def retrieve_with_evidence(
        self, query: str, *, top_k: int = 10
    ) -> list[tuple[NormalizedDocument, list[RetrievalEvidence]]]:
        documents = self.retrieve(query, top_k=top_k)
        results: list[tuple[NormalizedDocument, list[RetrievalEvidence]]] = []
        terms = {term.lower() for term in query.split() if term}
        for document in documents:
            evidence: list[RetrievalEvidence] = []
            for section in document.sections:
                content = str(section.get("content") or "")
                if not any(term in content.lower() for term in terms):
                    continue
                section_evidence = section.get("evidence") or []
                excerpt = content[:280]
                section_title = str(section.get("title") or "")
                if isinstance(section_evidence, list) and section_evidence:
                    first = section_evidence[0]
                    if isinstance(first, dict):
                        excerpt = str(first.get("excerpt") or excerpt)
                evidence.append(
                    RetrievalEvidence(
                        source_uri=document.source_uri,
                        title=document.title,
                        excerpt=excerpt,
                        section_title=section_title,
                        canonical_id=document.canonical_id,
                    )
                )
            if not evidence:
                evidence.append(
                    RetrievalEvidence(
                        source_uri=document.source_uri,
                        title=document.title,
                        excerpt=(document.sections[0].get("content") if document.sections else None),
                        canonical_id=document.canonical_id,
                    )
                )
            results.append((document, evidence))
        return results


@dataclass
class TemplateReasoningLayer(ReasoningLayer):
    retrieval_engine: RetrievalEngine

    def answer(self, query: str) -> str:
        if hasattr(self.retrieval_engine, "retrieve_with_evidence"):
            evidence_engine = self.retrieval_engine  # type: ignore[assignment]
            matches = evidence_engine.retrieve_with_evidence(query, top_k=3)
            if not matches:
                return "No evidence found."
            lines = []
            for document, evidence_list in matches:
                first = evidence_list[0] if evidence_list else None
                if first and first.section_title:
                    lines.append(
                        f"- {document.title or document.document_type} [{first.section_title}]: {first.excerpt or document.source_uri}"
                    )
                else:
                    lines.append(f"- {document.title or document.document_type}: {document.source_uri}")
            return "\n".join(lines)

        matches = self.retrieval_engine.retrieve(query, top_k=3)
        if not matches:
            return "No evidence found."
        return "\n".join(f"- {doc.title or doc.document_type}: {doc.source_uri}" for doc in matches)
