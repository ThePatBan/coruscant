from __future__ import annotations

from pathlib import Path

from coruscant.common.config import CompanyConfig, SourceSetting
from coruscant.infrastructure.catalog import SqliteDocumentCatalog
from coruscant.infrastructure.repositories import (
    FileSystemNormalizedDocumentRepository,
    FileSystemRawDocumentRepository,
)
from coruscant.ingestion.orchestrator import IngestionOrchestrator
from coruscant.knowledge_graph.memory import InMemoryKnowledgeGraphStore
from coruscant.search.hybrid import HybridRetrievalEngine

COMPANIES = [
    CompanyConfig(slug="apple", name="Apple", industry="Technology"),
    CompanyConfig(slug="tesla", name="Tesla", industry="Automotive"),
]


def _orchestrator(tmp_path: Path) -> tuple[IngestionOrchestrator, SqliteDocumentCatalog, InMemoryKnowledgeGraphStore, HybridRetrievalEngine]:
    catalog = SqliteDocumentCatalog(f"sqlite:///{tmp_path / 'catalog.db'}")
    graph = InMemoryKnowledgeGraphStore()
    engine = HybridRetrievalEngine()
    orchestrator = IngestionOrchestrator(
        raw_repository=FileSystemRawDocumentRepository(tmp_path),
        normalized_repository=FileSystemNormalizedDocumentRepository(tmp_path),
        catalog=catalog,
        graph_store=graph,
        engine=engine,
    )
    return orchestrator, catalog, graph, engine


def test_orchestrator_runs_company_by_source_matrix(tmp_path: Path) -> None:
    orchestrator, catalog, graph, engine = _orchestrator(tmp_path)
    sources = [SourceSetting(type="sec_edgar"), SourceSetting(type="news")]

    report = orchestrator.run(COMPANIES, sources)

    assert report.document_count == 4
    assert set(report.source_types) == {"sec_edgar", "news"}
    assert set(report.companies) == {"apple", "tesla"}
    assert not report.errors

    assert catalog.count() == 4
    assert len(engine) == 4
    assert graph.get_node("Company", "apple") is not None
    assert (tmp_path / "raw" / "sec_edgar").exists()
    assert (tmp_path / "raw" / "news").exists()


def test_orchestrator_defaults_to_all_registered_sources(tmp_path: Path) -> None:
    orchestrator, _, _, _ = _orchestrator(tmp_path)
    report = orchestrator.run([COMPANIES[0]], sources=None)
    # one company x seven registered sources
    assert report.document_count == 7


def test_orchestrator_records_unknown_source_error(tmp_path: Path) -> None:
    orchestrator, _, _, _ = _orchestrator(tmp_path)
    report = orchestrator.run(COMPANIES, [SourceSetting(type="does_not_exist")])
    assert report.document_count == 0
    assert report.errors and "does_not_exist" in report.errors[0]


def test_orchestrator_skips_disabled_sources(tmp_path: Path) -> None:
    orchestrator, _, _, _ = _orchestrator(tmp_path)
    report = orchestrator.run(
        [COMPANIES[0]],
        [SourceSetting(type="news"), SourceSetting(type="patents", enabled=False)],
    )
    assert report.source_types == ["news"]
