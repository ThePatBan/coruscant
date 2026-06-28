from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from coruscant.common.types import GraphEdge, GraphNode
from coruscant.knowledge_graph.store import KnowledgeGraphStore


@dataclass
class InMemoryKnowledgeGraphStore(KnowledgeGraphStore):
    nodes: dict[tuple[str, str], GraphNode] = field(default_factory=dict)
    edges: list[GraphEdge] = field(default_factory=list)

    def upsert_node(self, node: GraphNode) -> None:
        self.nodes[(node.kind, node.key)] = node

    def upsert_edge(self, edge: GraphEdge) -> None:
        key = (edge.source_kind, edge.source_key, edge.relation, edge.target_kind, edge.target_key)
        for existing in self.edges:
            existing_key = (
                existing.source_kind,
                existing.source_key,
                existing.relation,
                existing.target_kind,
                existing.target_key,
            )
            if existing_key == key:
                return
        self.edges.append(edge)

    # -- queries ---------------------------------------------------------------

    def get_node(self, kind: str, key: str) -> GraphNode | None:
        return self.nodes.get((kind, key))

    def nodes_of_kind(self, kind: str) -> list[GraphNode]:
        return [node for (node_kind, _), node in self.nodes.items() if node_kind == kind]

    def outgoing(self, kind: str, key: str) -> list[GraphEdge]:
        return [
            edge
            for edge in self.edges
            if edge.source_kind == kind and edge.source_key == key
        ]

    def neighbors(self, kind: str, key: str) -> list[tuple[GraphEdge, GraphNode | None]]:
        return [
            (edge, self.nodes.get((edge.target_kind, edge.target_key)))
            for edge in self.outgoing(kind, key)
        ]

    # -- serialization ---------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodes": [node.model_dump() for node in self.nodes.values()],
            "edges": [edge.model_dump() for edge in self.edges],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "InMemoryKnowledgeGraphStore":
        store = cls()
        for raw_node in data.get("nodes", []):
            store.upsert_node(GraphNode.model_validate(raw_node))
        for raw_edge in data.get("edges", []):
            store.upsert_edge(GraphEdge.model_validate(raw_edge))
        return store
