from __future__ import annotations

from abc import ABC, abstractmethod

from coruscant.common.types import NormalizedDocument, RetrievalEvidence


class RetrievalEngine(ABC):
    @abstractmethod
    def retrieve(self, query: str, *, top_k: int = 10) -> list[NormalizedDocument]:
        raise NotImplementedError


class ReasoningLayer(ABC):
    @abstractmethod
    def answer(self, query: str) -> str:
        raise NotImplementedError


class EvidenceAwareRetrievalEngine(ABC):
    @abstractmethod
    def retrieve_with_evidence(
        self, query: str, *, top_k: int = 10
    ) -> list[tuple[NormalizedDocument, list[RetrievalEvidence]]]:
        raise NotImplementedError
