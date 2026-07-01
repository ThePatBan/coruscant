from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from coruscant.common.types import GraphEdge, GraphNode


class KnowledgeGraphStore(ABC):
    """The graph-store port. Every backend (in-memory prototype, Kùzu, and later
    a server graph DB) implements this surface so the exposure engine
    (:mod:`coruscant.knowledge_graph.queries`) and the API depend on the port, not
    a concrete store. The read methods below were lifted onto the port so a real
    graph store can be swapped in without touching the engine.

    Provenance is intrinsic: every edge carries its source statement on
    ``properties``. Backends must round-trip that faithfully (see :meth:`to_dict`)."""

    # -- writes ---------------------------------------------------------------

    @abstractmethod
    def upsert_node(self, node: GraphNode) -> None:
        raise NotImplementedError

    @abstractmethod
    def upsert_edge(self, edge: GraphEdge) -> None:
        """Insert the edge if absent. First-write-wins: an edge with the same
        (source, relation, target) identity keeps the properties it was first
        created with — backends must not silently overwrite provenance."""
        raise NotImplementedError

    # -- reads ----------------------------------------------------------------

    @abstractmethod
    def get_node(self, kind: str, key: str) -> GraphNode | None:
        raise NotImplementedError

    @abstractmethod
    def nodes_of_kind(self, kind: str) -> list[GraphNode]:
        raise NotImplementedError

    @abstractmethod
    def outgoing(self, kind: str, key: str) -> list[GraphEdge]:
        raise NotImplementedError

    @abstractmethod
    def incoming(self, kind: str, key: str) -> list[GraphEdge]:
        raise NotImplementedError

    @abstractmethod
    def edges_by_relation(self, relation: str) -> list[GraphEdge]:
        raise NotImplementedError

    @abstractmethod
    def all_nodes(self) -> list[GraphNode]:
        raise NotImplementedError

    @abstractmethod
    def all_edges(self) -> list[GraphEdge]:
        raise NotImplementedError

    # -- derived (default implementations in terms of the primitives) ---------

    def neighbors(self, kind: str, key: str) -> list[tuple[GraphEdge, GraphNode | None]]:
        return [
            (edge, self.get_node(edge.target_kind, edge.target_key))
            for edge in self.outgoing(kind, key)
        ]

    def neighbors_in(self, kind: str, key: str) -> list[tuple[GraphEdge, GraphNode | None]]:
        return [
            (edge, self.get_node(edge.source_kind, edge.source_key))
            for edge in self.incoming(kind, key)
        ]

    def node_count(self) -> int:
        return len(self.all_nodes())

    def edge_count(self) -> int:
        return len(self.all_edges())

    # -- serialization --------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """The portable JSON snapshot shape shared by every backend. Kept stable
        so a graph can round-trip between backends (and drive the golden
        cross-backend parity test)."""
        return {
            "nodes": [node.model_dump() for node in self.all_nodes()],
            "edges": [edge.model_dump() for edge in self.all_edges()],
        }
