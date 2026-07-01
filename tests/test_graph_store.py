from __future__ import annotations

from pathlib import Path

from coruscant.common.types import GraphEdge, NormalizedDocument
from coruscant.knowledge_graph.memory import InMemoryKnowledgeGraphStore
from coruscant.knowledge_graph.persistence import load_graph, save_graph
from coruscant.knowledge_graph.projectors import ProjectingKnowledgeGraphStore


def _document(document_type: str = "filing") -> NormalizedDocument:
    return NormalizedDocument(
        document_type=document_type,
        source_uri="https://example.com/filing",
        canonical_id="abc123",
        title="Apple 10-K",
        sections=[{"title": "Item 1. Business", "content": "Details", "order": 1, "anchor": "item-1-business"}],
        entities=[{"kind": "Company", "key": "apple", "name": "Apple"}],
    )


def test_graph_queries() -> None:
    store = InMemoryKnowledgeGraphStore()
    ProjectingKnowledgeGraphStore(store).project_document(_document())

    assert store.get_node("Company", "apple") is not None
    assert store.nodes_of_kind("Section")
    relations = {edge.relation for edge, _ in store.neighbors("Company", "apple")}
    assert "filed" in relations


def test_non_filing_uses_document_kind_and_published_relation() -> None:
    store = InMemoryKnowledgeGraphStore()
    ProjectingKnowledgeGraphStore(store).project_document(_document("news_article"))
    assert store.get_node("Document", "abc123") is not None
    relations = {edge.relation for edge, _ in store.neighbors("Company", "apple")}
    assert "published" in relations


def test_edges_are_deduplicated() -> None:
    store = InMemoryKnowledgeGraphStore()
    ProjectingKnowledgeGraphStore(store).project_document(_document())
    edge_count = len(store.edges)
    ProjectingKnowledgeGraphStore(store).project_document(_document())
    assert len(store.edges) == edge_count


def test_edges_setter_rebuilds_dedup_index() -> None:
    # A maintenance script filters store.edges directly; the O(1) dedup index must
    # rebuild so a re-upsert of a removed edge is re-added, not swallowed.
    store = InMemoryKnowledgeGraphStore()
    ab = GraphEdge(source_kind="Company", source_key="a", relation="r", target_kind="Company", target_key="b")
    ac = GraphEdge(source_kind="Company", source_key="a", relation="r", target_kind="Company", target_key="c")
    store.upsert_edge(ab)
    store.upsert_edge(ac)
    assert len(store.edges) == 2

    store.edges = [edge for edge in store.edges if edge.target_key != "b"]  # drop ab
    assert len(store.edges) == 1
    store.upsert_edge(ab)  # removed -> re-added
    store.upsert_edge(ac)  # still present -> deduped
    assert len(store.edges) == 2


def test_graph_snapshot_roundtrip(tmp_path: Path) -> None:
    store = InMemoryKnowledgeGraphStore()
    ProjectingKnowledgeGraphStore(store).project_document(_document())
    path = tmp_path / "graph" / "graph.json"
    save_graph(store, path)

    loaded = load_graph(path)
    assert loaded.get_node("Company", "apple") is not None
    assert len(loaded.edges) == len(store.edges)
    assert len(loaded.nodes) == len(store.nodes)


def test_load_missing_graph_returns_empty(tmp_path: Path) -> None:
    loaded = load_graph(tmp_path / "absent.json")
    assert loaded.nodes == {}
    assert loaded.edges == []
