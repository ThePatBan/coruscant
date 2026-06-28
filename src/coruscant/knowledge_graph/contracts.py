from __future__ import annotations

from abc import ABC, abstractmethod

from coruscant.common.types import GraphEdge, GraphNode, NormalizedDocument


class EntityResolver(ABC):
    @abstractmethod
    def resolve(self, entity: dict[str, object], document: NormalizedDocument) -> GraphNode:
        raise NotImplementedError


class RelationshipExtractor(ABC):
    @abstractmethod
    def extract(self, document: NormalizedDocument) -> list[GraphEdge]:
        raise NotImplementedError


class GraphProjector(ABC):
    @abstractmethod
    def project(self, document: NormalizedDocument) -> tuple[list[GraphNode], list[GraphEdge]]:
        raise NotImplementedError
