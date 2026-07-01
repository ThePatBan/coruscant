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

    # Read surface: pure pass-through to the wrapped store so this projector is a
    # concrete KnowledgeGraphStore (writes project; reads defer to the delegate).
    def get_node(self, kind: str, key: str) -> GraphNode | None:
        return self.delegate.get_node(kind, key)

    def nodes_of_kind(self, kind: str) -> list[GraphNode]:
        return self.delegate.nodes_of_kind(kind)

    def outgoing(self, kind: str, key: str) -> list[GraphEdge]:
        return self.delegate.outgoing(kind, key)

    def incoming(self, kind: str, key: str) -> list[GraphEdge]:
        return self.delegate.incoming(kind, key)

    def edges_by_relation(self, relation: str) -> list[GraphEdge]:
        return self.delegate.edges_by_relation(relation)

    def all_nodes(self) -> list[GraphNode]:
        return self.delegate.all_nodes()

    def all_edges(self) -> list[GraphEdge]:
        return self.delegate.all_edges()

    def project_document(self, document: NormalizedDocument) -> tuple[list[GraphNode], list[GraphEdge]]:
        nodes, edges = self.projector.project(document)
        for node in nodes:
            self.upsert_node(node)
        for edge in edges:
            self.upsert_edge(edge)
        return nodes, edges
