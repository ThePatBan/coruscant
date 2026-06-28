from __future__ import annotations

from coruscant.common.types import NormalizedDocument, SourceDocument
from coruscant.connectors.base import FetchRequest, SourceConnector
from coruscant.connectors.sec_edgar import normalize_edgar_filing
from coruscant.ingestion.pipeline import IngestionPipeline
from coruscant.knowledge_graph.contracts import GraphProjector
from coruscant.knowledge_graph.store import KnowledgeGraphStore
from coruscant.knowledge_graph.projectors import ProjectingKnowledgeGraphStore
from coruscant.search.contracts import ReasoningLayer, RetrievalEngine
from coruscant.infrastructure.repositories import (
    NormalizedDocumentRepository,
    RawDocumentRepository,
)


class SecEdgarReferencePipeline(IngestionPipeline):
    def __init__(
        self,
        connector: SourceConnector,
        request: FetchRequest,
        raw_repository: RawDocumentRepository,
        normalized_repository: NormalizedDocumentRepository,
        projector: GraphProjector | None = None,
        graph_store: KnowledgeGraphStore | None = None,
        retrieval_engine: RetrievalEngine | None = None,
        reasoning_layer: ReasoningLayer | None = None,
    ) -> None:
        self.connector = connector
        self.request = request
        self.raw_repository = raw_repository
        self.normalized_repository = normalized_repository
        self.projector = projector
        self.graph_store = graph_store
        self.retrieval_engine = retrieval_engine
        self.reasoning_layer = reasoning_layer

    def fetch(self) -> SourceDocument:
        return self.connector.fetch(self.request)

    def store_raw(self, document: SourceDocument) -> None:
        self.raw_repository.save(document)

    def normalize(self, document: SourceDocument) -> NormalizedDocument:
        return normalize_edgar_filing(document)

    def extract_entities(self, document: NormalizedDocument) -> NormalizedDocument:
        return document

    def extract_relationships(self, document: NormalizedDocument) -> NormalizedDocument:
        return document

    def project_graph(self, document: NormalizedDocument) -> None:
        if self.graph_store is not None and self.projector is not None:
            projecting_store = ProjectingKnowledgeGraphStore(self.graph_store, self.projector)
            projecting_store.project_document(document)
        elif self.graph_store is not None:
            ProjectingKnowledgeGraphStore(self.graph_store).project_document(document)
        elif self.projector is not None:
            self.projector.project(document)

    def create_embeddings(self, document: NormalizedDocument) -> None:
        return None

    def index_search(self, document: NormalizedDocument) -> None:
        self.normalized_repository.save(document)
