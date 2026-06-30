"""Config-driven orchestration of ingestion across companies and sources.

For each company × enabled source the orchestrator ingests every disclosure
period (prior + current for periodic sources), runs the intelligence layer
(summary + events) per document, and runs change detection between the current
and previous disclosure. Results are assembled into a knowledge graph, a hybrid
search engine, the document catalog, and the intelligence store, and reported in
an :class:`IngestionReport`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging

from coruscant.common.config import CompanyConfig, CompanyEntities, SourceSetting
from coruscant.common.types import NormalizedDocument
from coruscant.connectors.base import FetchRequest
from coruscant.knowledge_graph.entities import (
    entity_names_for,
    link_document_mentions,
    project_company_entities,
)
from coruscant.infrastructure.catalog import SqliteDocumentCatalog
from coruscant.infrastructure.dead_letter import SqliteDeadLetterStore
from coruscant.infrastructure.intelligence_store import SqliteIntelligenceStore
from coruscant.infrastructure.repositories import (
    NormalizedDocumentRepository,
    RawDocumentRepository,
)
from coruscant.ingestion.pipeline import GenericIngestionPipeline
from coruscant.ingestion.registry import SourceDefinition, SourceRegistry, default_registry
from coruscant.intelligence.changes import ReferenceChangeDetector
from coruscant.intelligence.events import ReferenceEventExtractor
from coruscant.intelligence.summarizer import ReferenceSummarizer
from coruscant.knowledge_graph.memory import InMemoryKnowledgeGraphStore
from coruscant.knowledge_graph.reference import ReferenceGraphProjector
from coruscant.search.hybrid import HybridRetrievalEngine

logger = logging.getLogger(__name__)


def reference_source_uri(source_type: str, company_slug: str, key: str) -> str:
    return f"reference://{source_type}/{company_slug}/{key}"


@dataclass(frozen=True)
class IngestionTarget:
    """One concrete disclosure to ingest for a company × source.

    The resolver seam: the default (reference) resolver derives targets from a
    source definition's synthetic periods; a live resolver derives them from real
    URLs (e.g. configured SEC filing documents). The orchestrator is agnostic to
    where the ``source_uri`` came from.
    """

    label: str
    published_at: str
    source_uri: str
    revision: int


# Resolves the concrete targets to ingest for a company × source. Pure and
# swappable so live ingestion never touches the orchestrator's core loop.
SourceResolver = Callable[[CompanyConfig, str, "SourceDefinition"], list[IngestionTarget]]


def reference_targets(
    company: CompanyConfig, source_type: str, definition: SourceDefinition
) -> list[IngestionTarget]:
    """Default resolver: synthetic ``reference://`` URIs, one per defined period.

    Reproduces the pre-resolver behavior exactly, so offline/dev ingestion is
    byte-for-byte unchanged.
    """

    return [
        IngestionTarget(
            label=label,
            published_at=published_at,
            source_uri=reference_source_uri(source_type, company.slug, published_at),
            revision=revision,
        )
        for revision, (label, published_at) in enumerate(definition.periods)
    ]


@dataclass
class IngestionItem:
    company_slug: str
    source_type: str
    canonical_id: str
    document_type: str
    title: str | None
    source_uri: str
    period: str
    published_at: str
    revision: int
    node_count: int
    edge_count: int


@dataclass
class IngestionReport:
    items: list[IngestionItem] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    summary_count: int = 0
    event_count: int = 0
    change_set_count: int = 0
    material_change_count: int = 0

    @property
    def document_count(self) -> int:
        return len(self.items)

    @property
    def companies(self) -> list[str]:
        return sorted({item.company_slug for item in self.items})

    @property
    def source_types(self) -> list[str]:
        return sorted({item.source_type for item in self.items})


class IngestionOrchestrator:
    def __init__(
        self,
        *,
        raw_repository: RawDocumentRepository,
        normalized_repository: NormalizedDocumentRepository,
        catalog: SqliteDocumentCatalog,
        graph_store: InMemoryKnowledgeGraphStore | None = None,
        engine: HybridRetrievalEngine | None = None,
        registry: SourceRegistry | None = None,
        intelligence_store: SqliteIntelligenceStore | None = None,
        entities: dict[str, CompanyEntities] | None = None,
        dead_letter_store: SqliteDeadLetterStore | None = None,
        resolver: SourceResolver | None = None,
        max_attempts: int = 1,
    ) -> None:
        self.raw_repository = raw_repository
        self.normalized_repository = normalized_repository
        self.catalog = catalog
        self.graph_store = graph_store if graph_store is not None else InMemoryKnowledgeGraphStore()
        self.engine = engine if engine is not None else HybridRetrievalEngine()
        self.registry = registry if registry is not None else default_registry()
        self.intelligence_store = intelligence_store
        self.entities = entities or {}
        self.dead_letter_store = dead_letter_store
        self.resolver = resolver if resolver is not None else reference_targets
        self.max_attempts = max(1, max_attempts)
        self._names_by_company: dict[str, dict[str, tuple[str, str]]] = {}
        self.projector = ReferenceGraphProjector()
        self.summarizer = ReferenceSummarizer()
        self.event_extractor = ReferenceEventExtractor()
        self.change_detector = ReferenceChangeDetector()

    def _resolve_sources(self, sources: list[SourceSetting] | None) -> list[SourceSetting]:
        # None means "use every registered source" (caller did not specify); an
        # explicit empty list means "ingest nothing" (e.g. a due-aware run with
        # nothing currently due) — these must not be conflated.
        if sources is None:
            return [SourceSetting(type=source_type) for source_type in self.registry.source_types()]
        return [source for source in sources if source.enabled]

    def run(
        self,
        companies: list[CompanyConfig],
        sources: list[SourceSetting] | None = None,
    ) -> IngestionReport:
        report = IngestionReport()
        # Gazetteer names are needed during ingestion for mention-linking; the
        # entity KB itself is projected after ingestion so the tracked-company
        # nodes are authoritative (the per-document projector also writes Company
        # nodes, and the last writer wins).
        self._names_by_company = {
            company.slug: entity_names_for(company.name, self.entities[company.slug])
            for company in companies
            if company.slug in self.entities
        }
        for source in self._resolve_sources(sources):
            if not self.registry.has(source.type):
                report.errors.append(f"unknown source: {source.type}")
                logger.warning("Skipping unknown source %s", source.type)
                continue
            definition = self.registry.get(source.type)
            for company in companies:
                self._ingest_company_source(company, source.type, definition, report)
        for company in companies:
            company_entities = self.entities.get(company.slug)
            if company_entities is not None:
                project_company_entities(
                    self.graph_store,
                    company_slug=company.slug,
                    company_name=company.name,
                    entities=company_entities,
                )
        return report

    def _dead_letter(
        self,
        company: CompanyConfig,
        source_type: str,
        period: str,
        exc: Exception,
        report: IngestionReport,
        *,
        attempts: int,
    ) -> None:
        """Record an ingestion failure so it is explicit, observable, and queryable.

        Never swallowed: the failure lands in the run report and (when configured)
        the dead-letter queue. Used for both per-disclosure fetch failures and
        live target-resolution (e.g. SEC discovery) failures.
        """

        message = f"{company.slug}:{source_type}:{period}: {exc}"
        report.errors.append(message)
        logger.error("Ingestion failed after %d attempt(s) for %s", attempts, message)
        if self.dead_letter_store is not None:
            self.dead_letter_store.record(
                company_slug=company.slug,
                source_type=source_type,
                period=period,
                attempts=attempts,
                error=str(exc),
                created_at=datetime.now(tz=timezone.utc).isoformat(),
            )

    def _ingest_company_source(
        self,
        company: CompanyConfig,
        source_type: str,
        definition: SourceDefinition,
        report: IngestionReport,
    ) -> None:
        # Resolving targets can itself reach the network (live discovery) and fail;
        # that failure is dead-lettered like any other rather than aborting the run.
        try:
            targets = self.resolver(company, source_type, definition)
        except Exception as exc:
            self._dead_letter(company, source_type, "resolve", exc, report, attempts=1)
            return

        documents: list[NormalizedDocument] = []
        for target in targets:
            try:
                item, normalized = self._ingest_one_with_retry(
                    company, source_type, definition, target
                )
            except Exception as exc:
                self._dead_letter(
                    company, source_type, target.label, exc, report, attempts=self.max_attempts
                )
                continue
            report.items.append(item)
            documents.append(normalized)
            names = self._names_by_company.get(company.slug)
            if names:
                link_document_mentions(self.graph_store, normalized, names)
            self._run_intelligence(normalized, company.slug, source_type, report)

        if self.intelligence_store is not None and len(documents) >= 2:
            change_set = self.change_detector.diff(
                documents[-1], documents[-2], company_slug=company.slug, source_type=source_type
            )
            self.intelligence_store.save_change_set(change_set)
            report.change_set_count += 1
            if change_set.material:
                report.material_change_count += 1

    def _run_intelligence(
        self,
        document: NormalizedDocument,
        company_slug: str,
        source_type: str,
        report: IngestionReport,
    ) -> None:
        if self.intelligence_store is None:
            return
        summary = self.summarizer.summarize(
            document, company_slug=company_slug, source_type=source_type
        )
        self.intelligence_store.save_summary(summary)
        report.summary_count += 1
        events = self.event_extractor.extract(
            document, company_slug=company_slug, source_type=source_type
        )
        self.intelligence_store.replace_events(document.canonical_id, events)
        report.event_count += len(events)

    def _ingest_one_with_retry(
        self,
        company: CompanyConfig,
        source_type: str,
        definition: SourceDefinition,
        target: IngestionTarget,
    ) -> tuple[IngestionItem, NormalizedDocument]:
        last_exc: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                return self._ingest_one(company, source_type, definition, target)
            except Exception as exc:
                last_exc = exc
                logger.warning(
                    "Attempt %d/%d failed for %s:%s:%s: %s",
                    attempt,
                    self.max_attempts,
                    company.slug,
                    source_type,
                    target.label,
                    exc,
                )
        assert last_exc is not None
        raise last_exc

    def _ingest_one(
        self,
        company: CompanyConfig,
        source_type: str,
        definition: SourceDefinition,
        target: IngestionTarget,
    ) -> tuple[IngestionItem, NormalizedDocument]:
        request = FetchRequest(
            company_slug=company.slug,
            source_name=source_type,
            source_uri=target.source_uri,
            company_name=company.name,
            industry=company.industry,
            period=target.label,
            published_at=target.published_at or None,
            revision=target.revision,
        )
        pipeline = GenericIngestionPipeline(
            connector=definition.connector_factory(),
            request=request,
            normalizer=definition.normalizer,
            raw_repository=self.raw_repository,
            normalized_repository=self.normalized_repository,
            graph_store=self.graph_store,
            projector=self.projector,
            retrieval_engine=self.engine,
            embedding_index=self.engine,
            catalog=self.catalog,
            authority=definition.authority,
        )
        result = pipeline.run()
        normalized = result.normalized_document
        item = IngestionItem(
            company_slug=company.slug,
            source_type=source_type,
            canonical_id=normalized.canonical_id,
            document_type=normalized.document_type,
            title=normalized.title,
            source_uri=normalized.source_uri,
            period=target.label,
            published_at=target.published_at,
            revision=target.revision,
            node_count=len(result.graph_nodes),
            edge_count=len(result.graph_edges),
        )
        return item, normalized
