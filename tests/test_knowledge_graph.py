from __future__ import annotations

from coruscant.common.types import NormalizedDocument
from coruscant.knowledge_graph.memory import InMemoryKnowledgeGraphStore
from coruscant.knowledge_graph.projectors import ProjectingKnowledgeGraphStore


def test_graph_projector_creates_company_and_filing_nodes() -> None:
    document = NormalizedDocument(
        document_type="filing",
        source_uri="https://example.com/filing",
        canonical_id="abc123",
        title="10-K",
        sections=[
            {"title": "Item 1. Business", "content": "Details", "order": 1, "anchor": "item-1-business"}
        ],
        entities=[
            {"kind": "Company", "key": "apple", "name": "Apple"},
        ],
    )
    store = InMemoryKnowledgeGraphStore()
    projector = ProjectingKnowledgeGraphStore(store)

    nodes, edges = projector.project_document(document)

    assert ("Company", "apple") in store.nodes
    assert ("Filing", "abc123") in store.nodes
    assert ("Section", "item-1-business") in store.nodes
    assert edges
    assert any(edge.relation == "contains_section" for edge in edges)
    assert nodes
