"""Ports for the intelligence layer.

The reference implementations are deterministic and extractive. A Claude-backed
adapter can implement these same Protocols (activated when an API key is present)
without any change to callers — see ADR-0004.
"""

from __future__ import annotations

from typing import Protocol

from coruscant.common.types import NormalizedDocument
from coruscant.intelligence.models import ChangeSet, DocumentSummary, ExtractedEvent


class Summarizer(Protocol):
    def summarize(
        self, document: NormalizedDocument, *, company_slug: str, source_type: str
    ) -> DocumentSummary: ...


class EventExtractor(Protocol):
    def extract(
        self, document: NormalizedDocument, *, company_slug: str, source_type: str
    ) -> list[ExtractedEvent]: ...


class ChangeDetector(Protocol):
    def diff(
        self,
        current: NormalizedDocument,
        previous: NormalizedDocument | None,
        *,
        company_slug: str,
        source_type: str,
    ) -> ChangeSet: ...
