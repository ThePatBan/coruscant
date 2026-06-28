"""Config-driven orchestration of ingestion across companies and sources.

Iterates the company registry (``config/companies.yml``) crossed with the enabled
sources (``config/sources.yml``), runs a :class:`GenericIngestionPipeline` for each
pair, and assembles the results into a knowledge graph, a hybrid search engine,
and the SQLite catalog. Returns a structured :class:`IngestionReport`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging

from coruscant.common.config import CompanyConfig, SourceSetting
from coruscant.connectors.base import FetchRequest
from coruscant.infrastructure.catalog import SqliteDocumentCatalog
from coruscant.infrastructure.repositories import (
    NormalizedDocumentRepository,
    RawDocumentRepository,
)
from coruscant.ingestion.pipeline import GenericIngestionPipeline
from coruscant.ingestion.registry import SourceRegistry, default_registry
from coruscant.knowledge_graph.memory import InMemoryKnowledgeGraphStore
from coruscant.knowledge_graph.reference import ReferenceGraphProjector
from coruscant.search.hybrid import HybridRetrievalEngine

logger = logging.getLogger(__name__)


def reference_source_uri(source_type: str, company_slug: str, period: str | None) -> str:
    suffix = f"/{period.replace(' ', '-')}" if period else ""
    return f"reference://{source_type}/{company_slug}{suffix}"


@dataclass
class IngestionItem:
    company_slug: str
    source_type: str
    canonical_id: str
    document_type: str
    title: str | None
    source_uri: str
    node_count: int
    edge_count: int


@dataclass
class IngestionReport:
    items: list[IngestionItem] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

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
    ) -> None:
        self.raw_repository = raw_repository
        self.normalized_repository = normalized_repository
        self.catalog = catalog
        self.graph_store = graph_store if graph_store is not None else InMemoryKnowledgeGraphStore()
        self.engine = engine if engine is not None else HybridRetrievalEngine()
        self.registry = registry if registry is not None else default_registry()
        self.projector = ReferenceGraphProjector()

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
            for company in companies:
                try:
                    item = self._ingest_one(company, source, definition_source_type=source.type)
                except Exception as exc:  # pragma: no cover - defensive guard
                    message = f"{company.slug}:{source.type}: {exc}"
                    report.errors.append(message)
                    logger.exception("Ingestion failed for %s", message)
                    continue
                report.items.append(item)
        return report

    def _ingest_one(
        self,
        company: CompanyConfig,
        source: SourceSetting,
        *,
        definition_source_type: str,
    ) -> IngestionItem:
        definition = self.registry.get(definition_source_type)
        request = FetchRequest(
            company_slug=company.slug,
            source_name=source.type,
            source_uri=reference_source_uri(source.type, company.slug, source.period),
            company_name=company.name,
            industry=company.industry,
            period=source.period,
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
        return IngestionItem(
            company_slug=company.slug,
            source_type=source.type,
            canonical_id=normalized.canonical_id,
            document_type=normalized.document_type,
            title=normalized.title,
            source_uri=normalized.source_uri,
            node_count=len(result.graph_nodes),
            edge_count=len(result.graph_edges),
        )
