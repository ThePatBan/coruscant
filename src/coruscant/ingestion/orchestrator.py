"""Config-driven orchestration of ingestion across companies and sources.

For each company × enabled source the orchestrator ingests every disclosure
period (prior + current for periodic sources), runs the intelligence layer
(summary + events) per document, and runs change detection between the current
and previous disclosure. Results are assembled into a knowledge graph, a hybrid
search engine, the document catalog, and the intelligence store, and reported in
an :class:`IngestionReport`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging

from coruscant.common.config import CompanyConfig, SourceSetting
from coruscant.common.types import NormalizedDocument
from coruscant.connectors.base import FetchRequest
from coruscant.infrastructure.catalog import SqliteDocumentCatalog
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
    ) -> None:
        self.raw_repository = raw_repository
        self.normalized_repository = normalized_repository
        self.catalog = catalog
        self.graph_store = graph_store if graph_store is not None else InMemoryKnowledgeGraphStore()
        self.engine = engine if engine is not None else HybridRetrievalEngine()
        self.registry = registry if registry is not None else default_registry()
        self.intelligence_store = intelligence_store
        self.projector = ReferenceGraphProjector()
        self.summarizer = ReferenceSummarizer()
        self.event_extractor = ReferenceEventExtractor()
        self.change_detector = ReferenceChangeDetector()

    def _resolve_sources(self, sources: list[SourceSetting] | None) -> list[SourceSetting]:
        if sources:
            return [source for source in sources if source.enabled]
        return [SourceSetting(type=source_type) for source_type in self.registry.source_types()]

    def run(
        self,
        companies: list[CompanyConfig],
        sources: list[SourceSetting] | None = None,
    ) -> IngestionReport:
        report = IngestionReport()
        for source in self._resolve_sources(sources):
            if not self.registry.has(source.type):
                report.errors.append(f"unknown source: {source.type}")
                logger.warning("Skipping unknown source %s", source.type)
                continue
            definition = self.registry.get(source.type)
            for company in companies:
                self._ingest_company_source(company, source.type, definition, report)
        return report

    def _ingest_company_source(
        self,
        company: CompanyConfig,
        source_type: str,
        definition: SourceDefinition,
        report: IngestionReport,
    ) -> None:
        documents: list[NormalizedDocument] = []
        for revision, (label, published_at) in enumerate(definition.periods):
            try:
                item, normalized = self._ingest_one(
                    company, source_type, definition, label, published_at, revision
                )
            except Exception as exc:  # pragma: no cover - defensive guard
                message = f"{company.slug}:{source_type}:{label}: {exc}"
                report.errors.append(message)
                logger.exception("Ingestion failed for %s", message)
                continue
            report.items.append(item)
            documents.append(normalized)
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

    def _ingest_one(
        self,
        company: CompanyConfig,
        source_type: str,
        definition: SourceDefinition,
        label: str,
        published_at: str,
        revision: int,
    ) -> tuple[IngestionItem, NormalizedDocument]:
        request = FetchRequest(
            company_slug=company.slug,
            source_name=source_type,
            source_uri=reference_source_uri(source_type, company.slug, published_at),
            company_name=company.name,
            industry=company.industry,
            period=label,
            published_at=published_at,
            revision=revision,
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
            period=label,
            published_at=published_at,
            revision=revision,
            node_count=len(result.graph_nodes),
            edge_count=len(result.graph_edges),
        )
        return item, normalized
