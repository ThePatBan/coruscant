from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

from coruscant.common.types import (
    GraphEdge,
    GraphNode,
    NormalizedDocument,
    Provenance,
    SourceDocument,
)
from coruscant.connectors.base import FetchRequest, SourceConnector
from coruscant.infrastructure.repositories import (
    NormalizedDocumentRepository,
    RawDocumentRepository,
)
from coruscant.knowledge_graph.contracts import GraphProjector
from coruscant.knowledge_graph.projectors import ProjectingKnowledgeGraphStore
from coruscant.knowledge_graph.store import KnowledgeGraphStore


@dataclass
class PipelineResult:
    raw_document: SourceDocument
    normalized_document: NormalizedDocument
    graph_nodes: list[GraphNode] = field(default_factory=list)
    graph_edges: list[GraphEdge] = field(default_factory=list)
    indexed: bool = False


class DocumentIndex(Protocol):
    """A search engine that accepts normalized documents."""

    def add(self, document: NormalizedDocument) -> None: ...


class EmbeddingIndex(Protocol):
    """A vector index that embeds and stores a normalized document."""

    def add_document(self, document: NormalizedDocument) -> None: ...


class DocumentCatalog(Protocol):
    """A queryable store of normalized documents."""

    def upsert(self, document: NormalizedDocument, *, company_slug: str, source_type: str) -> None: ...


class IngestionPipeline(ABC):
    @abstractmethod
    def fetch(self) -> SourceDocument:
        raise NotImplementedError

    @abstractmethod
    def store_raw(self, document: SourceDocument) -> None:
        raise NotImplementedError

    @abstractmethod
    def normalize(self, document: SourceDocument) -> NormalizedDocument:
        raise NotImplementedError

    @abstractmethod
    def extract_entities(self, document: NormalizedDocument) -> NormalizedDocument:
        raise NotImplementedError

    @abstractmethod
    def extract_relationships(self, document: NormalizedDocument) -> NormalizedDocument:
        raise NotImplementedError

    @abstractmethod
    def project_graph(self, document: NormalizedDocument) -> None:
        raise NotImplementedError

    @abstractmethod
    def create_embeddings(self, document: NormalizedDocument) -> None:
        raise NotImplementedError

    @abstractmethod
    def index_search(self, document: NormalizedDocument) -> None:
        raise NotImplementedError

    def run(self) -> PipelineResult:
        raw = self.fetch()
        self.store_raw(raw)
        normalized = self.normalize(raw)
        normalized = self.extract_entities(normalized)
        normalized = self.extract_relationships(normalized)
        self.project_graph(normalized)
        self.create_embeddings(normalized)
        self.index_search(normalized)
        return PipelineResult(raw_document=raw, normalized_document=normalized)


class GenericIngestionPipeline(IngestionPipeline):
    """Source-agnostic pipeline driven by a connector and a normalizer.

    Every lifecycle stage is wired: immutable raw artifacts are persisted, the
    normalized document is projected into the knowledge graph, embedded into the
    vector index, indexed for retrieval, and recorded in the document catalog.
    Any collaborator may be omitted; the corresponding stage is then skipped.
    """

    def __init__(
        self,
        *,
        connector: SourceConnector,
        request: FetchRequest,
        normalizer: Callable[[SourceDocument], NormalizedDocument],
        raw_repository: RawDocumentRepository,
        normalized_repository: NormalizedDocumentRepository,
        graph_store: KnowledgeGraphStore | None = None,
        projector: GraphProjector | None = None,
        retrieval_engine: DocumentIndex | None = None,
        embedding_index: EmbeddingIndex | None = None,
        catalog: DocumentCatalog | None = None,
        authority: float = 0.6,
    ) -> None:
        self.connector = connector
        self.request = request
        self.normalizer = normalizer
        self.raw_repository = raw_repository
        self.normalized_repository = normalized_repository
        self.graph_store = graph_store
        self.projector = projector
        self.retrieval_engine = retrieval_engine
        self.embedding_index = embedding_index
        self.catalog = catalog
        self.authority = authority
        self._source_type = request.source_name
        self._nodes: list[GraphNode] = []
        self._edges: list[GraphEdge] = []
        self._indexed = False

    def fetch(self) -> SourceDocument:
        return self.connector.fetch(self.request)

    def store_raw(self, document: SourceDocument) -> None:
        self._source_type = document.source_type
        self.raw_repository.save(document)

    def normalize(self, document: SourceDocument) -> NormalizedDocument:
        normalized = self.normalizer(document)
        # Attach the common provenance record (M2): one shared schema for every
        # source, regardless of connector.
        normalized.provenance = Provenance(
            source_type=document.source_type,
            source_uri=document.source_uri,
            retrieved_at=document.fetched_at.isoformat(),
            authority=self.authority,
            publisher=document.metadata.get("publisher"),
        )
        return normalized

    def extract_entities(self, document: NormalizedDocument) -> NormalizedDocument:
        # Reference normalizers already attach entities; resolution happens in the projector.
        return document

    def extract_relationships(self, document: NormalizedDocument) -> NormalizedDocument:
        # Relationship extraction is performed by the graph projector.
        return document

    def project_graph(self, document: NormalizedDocument) -> None:
        if self.graph_store is None:
            if self.projector is not None:
                self._nodes, self._edges = self.projector.project(document)
            return
        store = ProjectingKnowledgeGraphStore(self.graph_store, self.projector)
        self._nodes, self._edges = store.project_document(document)

    def create_embeddings(self, document: NormalizedDocument) -> None:
        if self.embedding_index is not None:
            self.embedding_index.add_document(document)

    def index_search(self, document: NormalizedDocument) -> None:
        self.normalized_repository.save(document)
        if self.retrieval_engine is not None:
            self.retrieval_engine.add(document)
        if self.catalog is not None:
            self.catalog.upsert(
                document,
                company_slug=self.request.company_slug,
                source_type=self._source_type,
            )
        self._indexed = True

    def run(self) -> PipelineResult:
        result = super().run()
        result.graph_nodes = self._nodes
        result.graph_edges = self._edges
        result.indexed = self._indexed
        return result
