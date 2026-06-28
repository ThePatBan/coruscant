from __future__ import annotations

from abc import ABC, abstractmethod

from coruscant.common.types import GraphEdge, GraphNode


class KnowledgeGraphStore(ABC):
    @abstractmethod
    def upsert_node(self, node: GraphNode) -> None:
        raise NotImplementedError

    @abstractmethod
    def upsert_edge(self, edge: GraphEdge) -> None:
        raise NotImplementedError
