from __future__ import annotations

from hashlib import sha256

from coruscant.common.types import GraphEdge, GraphNode, NormalizedDocument
from coruscant.knowledge_graph.contracts import EntityResolver, GraphProjector, RelationshipExtractor


def document_node_kind(document_type: str) -> str:
    """Graph node label for a document of the given normalized type."""

    return "Filing" if document_type == "filing" else "Document"


def company_document_relation(document_type: str) -> str:
    """Relationship label connecting a company to one of its documents."""

    return "filed" if document_type == "filing" else "published"


class ReferenceEntityResolver(EntityResolver):
    def resolve(self, entity: dict[str, object], document: NormalizedDocument) -> GraphNode:
        kind = str(entity.get("kind", "Unknown"))
        key = str(entity.get("key") or sha256(repr(entity).encode("utf-8")).hexdigest())
        properties = {k: v for k, v in entity.items() if k not in {"kind", "key"}}
        properties["source_canonical_id"] = document.canonical_id
        properties["source_uri"] = document.source_uri
        return GraphNode(kind=kind, key=key, properties=properties)


class ReferenceRelationshipExtractor(RelationshipExtractor):
    def extract(self, document: NormalizedDocument) -> list[GraphEdge]:
        edges: list[GraphEdge] = []
        doc_kind = document_node_kind(document.document_type)
        relation = company_document_relation(document.document_type)
        filing_key = document.canonical_id
        company_key = None
        for entity in document.entities:
            if entity.get("kind") == "Company":
                company_key = str(entity.get("key"))
        if company_key and filing_key:
            edges.append(
                GraphEdge(
                    source_kind="Company",
                    source_key=company_key,
                    relation=relation,
                    target_kind=doc_kind,
                    target_key=filing_key,
                    properties={"source_canonical_id": document.canonical_id, "source_uri": document.source_uri},
                )
            )
        for section in document.sections:
            title = str(section.get("title") or "Section")
            anchor = str(section.get("anchor") or title)
            edges.append(
                GraphEdge(
                    source_kind=doc_kind,
                    source_key=filing_key,
                    relation="contains_section",
                    target_kind="Section",
                    target_key=anchor,
                    properties={
                        "section_title": title,
                        "source_canonical_id": document.canonical_id,
                        "source_uri": document.source_uri,
                    },
                )
            )
        return edges


class ReferenceGraphProjector(GraphProjector):
    def __init__(
        self,
        resolver: EntityResolver | None = None,
        relationship_extractor: RelationshipExtractor | None = None,
    ) -> None:
        self.resolver = resolver or ReferenceEntityResolver()
        self.relationship_extractor = relationship_extractor or ReferenceRelationshipExtractor()

    def project(self, document: NormalizedDocument) -> tuple[list[GraphNode], list[GraphEdge]]:
        nodes = [self.resolver.resolve(entity, document) for entity in document.entities]
        edges = self.relationship_extractor.extract(document)
        filing_node = GraphNode(
            kind=document_node_kind(document.document_type),
            key=document.canonical_id,
            properties={
                "source_uri": document.source_uri,
                "document_type": document.document_type,
                "title": document.title,
            },
        )
        nodes.append(filing_node)
        for section in document.sections:
            nodes.append(
                GraphNode(
                    kind="Section",
                    key=str(section.get("anchor") or section.get("title") or "section"),
                    properties={
                        "title": section.get("title"),
                        "order": section.get("order"),
                        "source_canonical_id": document.canonical_id,
                        "source_uri": document.source_uri,
                        "evidence": section.get("evidence", []),
                    },
                )
            )
        return nodes, edges
