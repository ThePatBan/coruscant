from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from coruscant.common.types import GraphEdge, GraphNode
from coruscant.knowledge_graph.store import KnowledgeGraphStore


_EdgeId = tuple[str, str, str, str, str]


@dataclass
class InMemoryKnowledgeGraphStore(KnowledgeGraphStore):
    nodes: dict[tuple[str, str], GraphNode] = field(default_factory=dict)
    _edges: list[GraphEdge] = field(default_factory=list)
    # Identity index so upsert_edge dedups in O(1) instead of scanning every edge.
    # Without it ingestion is O(E²) (10k companies -> ~110s); with it, O(E).
    _edge_ids: set[_EdgeId] = field(default_factory=set, repr=False)

    @staticmethod
    def _identity(edge: GraphEdge) -> _EdgeId:
        return (edge.source_kind, edge.source_key, edge.relation, edge.target_kind, edge.target_key)

    @property
    def edges(self) -> list[GraphEdge]:
        return self._edges

    @edges.setter
    def edges(self, value: list[GraphEdge]) -> None:
        # Direct reassignment (a maintenance script filtering edges) rebuilds the
        # dedup index so later upserts stay consistent.
        self._edges = list(value)
        self._edge_ids = {self._identity(edge) for edge in self._edges}

    def upsert_node(self, node: GraphNode) -> None:
        self.nodes[(node.kind, node.key)] = node

    def upsert_edge(self, edge: GraphEdge) -> None:
        identity = self._identity(edge)
        if identity in self._edge_ids:  # first-write-wins
            return
        self._edge_ids.add(identity)
        self._edges.append(edge)

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

    def incoming(self, kind: str, key: str) -> list[GraphEdge]:
        return [
            edge
            for edge in self.edges
            if edge.target_kind == kind and edge.target_key == key
        ]

    def edges_by_relation(self, relation: str) -> list[GraphEdge]:
        return [edge for edge in self.edges if edge.relation == relation]

    def all_nodes(self) -> list[GraphNode]:
        return list(self.nodes.values())

    def all_edges(self) -> list[GraphEdge]:
        return list(self.edges)

    def node_count(self) -> int:
        return len(self.nodes)

    def edge_count(self) -> int:
        return len(self.edges)

    # `neighbors`, `neighbors_in`, and `to_dict` are inherited from the port —
    # their default implementations already resolve through this store's dict.

    # -- serialization ---------------------------------------------------------

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "InMemoryKnowledgeGraphStore":
        store = cls()
        for raw_node in data.get("nodes", []):
            store.upsert_node(GraphNode.model_validate(raw_node))
        for raw_edge in data.get("edges", []):
            store.upsert_edge(GraphEdge.model_validate(raw_edge))
        return store
