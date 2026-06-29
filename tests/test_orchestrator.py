from __future__ import annotations

from pathlib import Path

from coruscant.common.config import CompanyConfig, SourceSetting
from coruscant.infrastructure.catalog import SqliteDocumentCatalog
from coruscant.infrastructure.intelligence_store import SqliteIntelligenceStore
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


def _orchestrator(
    tmp_path: Path,
) -> tuple[
    IngestionOrchestrator,
    SqliteDocumentCatalog,
    InMemoryKnowledgeGraphStore,
    HybridRetrievalEngine,
    SqliteIntelligenceStore,
]:
    catalog = SqliteDocumentCatalog(f"sqlite:///{tmp_path / 'catalog.db'}")
    intel = SqliteIntelligenceStore(f"sqlite:///{tmp_path / 'catalog.db'}")
    graph = InMemoryKnowledgeGraphStore()
    engine = HybridRetrievalEngine()
    orchestrator = IngestionOrchestrator(
        raw_repository=FileSystemRawDocumentRepository(tmp_path),
        normalized_repository=FileSystemNormalizedDocumentRepository(tmp_path),
        catalog=catalog,
        graph_store=graph,
        engine=engine,
        intelligence_store=intel,
    )
    return orchestrator, catalog, graph, engine, intel


def test_orchestrator_runs_company_by_source_matrix(tmp_path: Path) -> None:
    orchestrator, catalog, graph, engine, intel = _orchestrator(tmp_path)
    # sec_edgar is periodic (2 periods); news is episodic (1 period).
    sources = [SourceSetting(type="sec_edgar"), SourceSetting(type="news")]

    report = orchestrator.run(COMPANIES, sources)

    # 2 companies × (sec_edgar:2 + news:1) = 6 documents.
    assert report.document_count == 6
    assert set(report.source_types) == {"sec_edgar", "news"}
    assert set(report.companies) == {"apple", "tesla"}
    assert not report.errors

    assert catalog.count() == 6
    assert len(engine) == 6
    assert graph.get_node("Company", "apple") is not None

    # Change detection runs only for the periodic source: one set per company.
    assert report.change_set_count == 2
    assert report.material_change_count == 2
    assert len(intel.list_change_sets(company_slug="apple")) == 1
    assert report.summary_count == 6  # one summary per document
    assert report.event_count > 0


def test_orchestrator_defaults_to_all_registered_sources(tmp_path: Path) -> None:
    orchestrator, _, _, _, _ = _orchestrator(tmp_path)
    report = orchestrator.run([COMPANIES[0]], sources=None)
    # one company × (4 periodic × 2 + 9 episodic × 1) = 17 documents.
    assert report.document_count == 17
    assert report.change_set_count == 4  # four periodic sources


def test_orchestrator_records_unknown_source_error(tmp_path: Path) -> None:
    orchestrator, _, _, _, _ = _orchestrator(tmp_path)
    report = orchestrator.run(COMPANIES, [SourceSetting(type="does_not_exist")])
    assert report.document_count == 0
    assert report.errors and "does_not_exist" in report.errors[0]


def test_orchestrator_skips_disabled_sources(tmp_path: Path) -> None:
    orchestrator, _, _, _, _ = _orchestrator(tmp_path)
    report = orchestrator.run(
        [COMPANIES[0]],
        [SourceSetting(type="news"), SourceSetting(type="patents", enabled=False)],
    )
    assert report.source_types == ["news"]


def test_orchestrator_change_set_is_material_and_cited(tmp_path: Path) -> None:
    orchestrator, _, _, _, intel = _orchestrator(tmp_path)
    orchestrator.run([COMPANIES[0]], [SourceSetting(type="sec_edgar")])
    change_sets = intel.list_change_sets(company_slug="apple")
    assert len(change_sets) == 1
    change_set = change_sets[0]
    assert change_set.material
    categories = {c.category for c in change_set.changes}
    assert categories & {"guidance", "executive", "regulatory"}
    for change in change_set.changes:
        assert change.evidence.source_uri
        assert change.evidence.canonical_id
