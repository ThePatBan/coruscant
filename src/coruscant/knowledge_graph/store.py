from __future__ import annotations

from abc import ABC, abstractmethod
from collections import deque
from typing import Any

from coruscant.common.types import GraphEdge, GraphNode


class KnowledgeGraphStore(ABC):
    """The graph-store port. Every backend (in-memory prototype, Kùzu, and later
    a server graph DB) implements this surface so the exposure engine
    (:mod:`coruscant.exposure.queries`) and the API depend on the port, not
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

    # -- traversal ------------------------------------------------------------

    def reachable(
        self, kind: str, key: str, relation: str, max_hops: int, *, direction: str = "any"
    ) -> dict[tuple[str, str], int]:
        """Nodes reachable from ``(kind, key)`` within ``max_hops`` following only
        ``relation`` edges, mapped to their shortest hop-distance (the source is
        excluded). ``direction``: ``"out"`` | ``"in"`` | ``"any"`` (undirected).

        This is the multi-hop primitive the flat JSON store could only fake with a
        hand-rolled scan; a real graph backend answers it natively (Kùzu overrides
        this with a variable-length ``SHORTEST`` Cypher path). The default here is a
        backend-agnostic breadth-first search over the port, and the golden test
        asserts the two agree — the same query, faster. It is also the shape the
        future ``owns*`` / ``supplies*`` ownership traversals will take (swap the
        relation, raise the depth)."""
        start = (kind, key)
        dist: dict[tuple[str, str], int] = {start: 0}
        queue: deque[tuple[str, str]] = deque([start])
        while queue:
            current = queue.popleft()
            depth = dist[current]
            if depth >= max_hops:
                continue
            neighbours: list[tuple[str, str]] = []
            if direction in ("out", "any"):
                neighbours += [
                    (e.target_kind, e.target_key)
                    for e in self.outgoing(*current)
                    if e.relation == relation
                ]
            if direction in ("in", "any"):
                neighbours += [
                    (e.source_kind, e.source_key)
                    for e in self.incoming(*current)
                    if e.relation == relation
                ]
            for neighbour in neighbours:
                if neighbour not in dist:
                    dist[neighbour] = depth + 1
                    queue.append(neighbour)
        dist.pop(start, None)
        return dist

    # -- serialization --------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """The portable JSON snapshot shape shared by every backend. Kept stable
        so a graph can round-trip between backends (and drive the golden
        cross-backend parity test)."""
        return {
            "nodes": [node.model_dump() for node in self.all_nodes()],
            "edges": [edge.model_dump() for edge in self.all_edges()],
        }
