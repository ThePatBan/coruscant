from __future__ import annotations

from coruscant.common.types import GraphEdge, GraphNode, NormalizedDocument
from coruscant.knowledge_graph.contracts import GraphProjector
from coruscant.knowledge_graph.reference import ReferenceGraphProjector
from coruscant.knowledge_graph.store import KnowledgeGraphStore


class ProjectingKnowledgeGraphStore(KnowledgeGraphStore):
    def __init__(self, delegate: KnowledgeGraphStore, projector: GraphProjector | None = None) -> None:
        self.delegate = delegate
        self.projector = projector or ReferenceGraphProjector()

    def upsert_node(self, node: GraphNode) -> None:
        self.delegate.upsert_node(node)

    def upsert_edge(self, edge: GraphEdge) -> None:
        self.delegate.upsert_edge(edge)

    def project_document(self, document: NormalizedDocument) -> tuple[list[GraphNode], list[GraphEdge]]:
        nodes, edges = self.projector.project(document)
        for node in nodes:
            self.upsert_node(node)
        for edge in edges:
            self.upsert_edge(edge)
        return nodes, edges
