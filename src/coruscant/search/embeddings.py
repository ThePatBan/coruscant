"""Deterministic, dependency-free embeddings and an in-memory vector index.

Uses a signed hashing trick (the "hashing vectorizer") to map text into a fixed
dimensional space. Hashing is done with :mod:`hashlib` rather than the builtin
``hash`` so vectors are stable across processes. This is intentionally simple:
it gives the MVP a working ``embed -> index -> semantic search`` path with no
external model or service, and can be swapped for a real embedding model behind
the same interface.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import math
import re

from coruscant.common.types import NormalizedDocument

DEFAULT_DIMENSIONS = 256
_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def _bucket(token: str, dimensions: int) -> int:
    digest = sha256(token.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % dimensions


def _sign(token: str) -> float:
    digest = sha256(f"sign:{token}".encode("utf-8")).digest()
    return 1.0 if int.from_bytes(digest[:8], "big") % 2 == 0 else -1.0


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        raise ValueError(f"vector dimension mismatch: {len(a)} != {len(b)}")
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


class HashingEmbedder:
    def __init__(self, dimensions: int = DEFAULT_DIMENSIONS) -> None:
        self.dimensions = dimensions

    def embed_text(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for token in _tokenize(text):
            vector[_bucket(token, self.dimensions)] += _sign(token)
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0.0:
            return vector
        return [value / norm for value in vector]

    def embed_document(self, document: NormalizedDocument) -> list[float]:
        return self.embed_text(document_text(document))


def document_text(document: NormalizedDocument) -> str:
    parts: list[str] = [document.title or "", document.document_type]
    for section in document.sections:
        parts.append(str(section.get("title") or ""))
        parts.append(str(section.get("content") or ""))
    for entity in document.entities:
        parts.append(str(entity.get("name") or entity.get("key") or ""))
    return " ".join(part for part in parts if part)


@dataclass
class VectorMatch:
    document: NormalizedDocument
    score: float


@dataclass
class InMemoryVectorIndex:
    embedder: HashingEmbedder = field(default_factory=HashingEmbedder)
    _entries: dict[str, tuple[list[float], NormalizedDocument]] = field(default_factory=dict)

    def add_document(self, document: NormalizedDocument) -> None:
        vector = self.embedder.embed_document(document)
        self._entries[document.canonical_id] = (vector, document)

    def __len__(self) -> int:
        return len(self._entries)

    def search(self, query: str, *, top_k: int = 10) -> list[VectorMatch]:
        query_vector = self.embedder.embed_text(query)
        matches: list[VectorMatch] = []
        for vector, document in self._entries.values():
            score = cosine_similarity(query_vector, vector)
            if score > 0.0:
                matches.append(VectorMatch(document=document, score=score))
        matches.sort(key=lambda match: match.score, reverse=True)
        return matches[:top_k]

    def scores(self, query: str) -> dict[str, float]:
        query_vector = self.embedder.embed_text(query)
        return {
            document.canonical_id: cosine_similarity(query_vector, vector)
            for vector, document in self._entries.values()
        }
