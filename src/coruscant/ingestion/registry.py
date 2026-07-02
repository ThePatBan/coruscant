"""Registry mapping source types to their connector and normalizer.

Adding a new pipeline means registering a :class:`SourceDefinition`; no core domain code
changes. This module is the *generic* registry mechanism — the platform ships an empty,
pluggable :class:`SourceRegistry`. Workspace-specific source catalogs (e.g. the
Portfolio-Exposure finance sources + live-connector wiring) live in workspace modules
such as ``coruscant.exposure.sources`` (docs/PLATFORM.md §9, seam 4).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from coruscant.common.types import NormalizedDocument, SourceDocument
from coruscant.connectors.base import SourceConnector

ConnectorFactory = Callable[[], SourceConnector]
Normalizer = Callable[[SourceDocument], NormalizedDocument]


@dataclass(frozen=True)
class SourceDefinition:
    source_type: str
    label: str
    document_type: str
    connector_factory: ConnectorFactory
    normalizer: Normalizer
    # (display label, ISO date) per disclosure. Periodic sources carry two so the
    # change detector has a prior and a current version to diff; episodic sources
    # carry one. The last entry is treated as the current disclosure.
    periods: tuple[tuple[str, str], ...] = (("current", "2025-01-31"),)
    # Inherent source authority (0..1): official/regulatory filings rank above
    # commentary. Feeds the reliability score (see intelligence.reliability).
    authority: float = 0.6
    # How often the scheduler considers this source due for re-ingestion (days).
    cadence_days: int = 7

    @property
    def is_periodic(self) -> bool:
        return len(self.periods) > 1


class UnknownSourceError(KeyError):
    """Raised when a requested source type is not registered."""


class SourceRegistry:
    def __init__(self) -> None:
        self._definitions: dict[str, SourceDefinition] = {}

    def register(self, definition: SourceDefinition) -> None:
        self._definitions[definition.source_type] = definition

    def get(self, source_type: str) -> SourceDefinition:
        try:
            return self._definitions[source_type]
        except KeyError as exc:
            raise UnknownSourceError(source_type) from exc

    def has(self, source_type: str) -> bool:
        return source_type in self._definitions

    def source_types(self) -> list[str]:
        return list(self._definitions)

    def definitions(self) -> list[SourceDefinition]:
        return list(self._definitions.values())
