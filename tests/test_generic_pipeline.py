from __future__ import annotations

from pathlib import Path

from coruscant.connectors.base import FetchRequest
from coruscant.infrastructure.catalog import SqliteDocumentCatalog
from coruscant.infrastructure.repositories import (
    FileSystemNormalizedDocumentRepository,
    FileSystemRawDocumentRepository,
)
from coruscant.ingestion.pipeline import GenericIngestionPipeline
from coruscant.ingestion.registry import default_registry
from coruscant.knowledge_graph.memory import InMemoryKnowledgeGraphStore
from coruscant.knowledge_graph.reference import ReferenceGraphProjector
from coruscant.search.hybrid import HybridRetrievalEngine


def test_generic_pipeline_wires_every_stage(tmp_path: Path) -> None:
    definition = default_registry().get("press_release")
    catalog = SqliteDocumentCatalog(f"sqlite:///{tmp_path / 'catalog.db'}")
    graph = InMemoryKnowledgeGraphStore()
    engine = HybridRetrievalEngine()

    pipeline = GenericIngestionPipeline(
        connector=definition.connector_factory(),
        request=FetchRequest(
            company_slug="apple",
            source_name="press_release",
            source_uri="reference://press_release/apple",
            company_name="Apple",
            industry="Technology",
        ),
        normalizer=definition.normalizer,
        raw_repository=FileSystemRawDocumentRepository(tmp_path),
        normalized_repository=FileSystemNormalizedDocumentRepository(tmp_path),
        graph_store=graph,
        projector=ReferenceGraphProjector(),
        retrieval_engine=engine,
        embedding_index=engine,
        catalog=catalog,
    )

    result = pipeline.run()

    assert result.indexed is True
    assert result.normalized_document.document_type == "press_release"
    assert result.graph_nodes and result.graph_edges
    # Ingestion feeds search, the graph, the catalog, and the filesystem.
    assert len(engine) == 1
    assert catalog.count() == 1
    assert graph.get_node("Document", result.normalized_document.canonical_id) is not None
    assert list((tmp_path / "raw" / "press_release").glob("*.json"))
    assert list((tmp_path / "normalized" / "press_release").glob("*.json"))


def test_generic_pipeline_optional_collaborators_are_skipped(tmp_path: Path) -> None:
    definition = default_registry().get("news")
    pipeline = GenericIngestionPipeline(
        connector=definition.connector_factory(),
        request=FetchRequest(
            company_slug="tesla",
            source_name="news",
            source_uri="reference://news/tesla",
            company_name="Tesla",
        ),
        normalizer=definition.normalizer,
        raw_repository=FileSystemRawDocumentRepository(tmp_path),
        normalized_repository=FileSystemNormalizedDocumentRepository(tmp_path),
    )
    result = pipeline.run()
    assert result.indexed is True
    assert result.graph_nodes == []
    assert result.graph_edges == []
