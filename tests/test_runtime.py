from __future__ import annotations

from pathlib import Path

from coruscant.apps.runtime import load_engine, load_graph_store, run_ingestion
from coruscant.common.config import Settings


def _settings(tmp_path: Path) -> Settings:
    data_dir = tmp_path / "data"
    return Settings(
        data_dir=data_dir,
        config_dir=Path("config"),
        database_url=f"sqlite:///{data_dir / 'coruscant.db'}",
    )


def test_run_ingestion_end_to_end(tmp_path: Path) -> None:
    settings = _settings(tmp_path)

    report = run_ingestion(settings)

    # 6 companies × (3 periodic sources × 2 periods + 4 episodic × 1) = 60 documents.
    assert report.document_count == 60
    assert len(report.companies) == 6
    assert len(report.source_types) == 7
    assert not report.errors
    assert settings.graph_snapshot_path.exists()

    # Intelligence ran for every document; change detection for every periodic combo.
    assert report.summary_count == 60
    assert report.event_count > 0
    assert report.change_set_count == 18  # 6 companies × 3 periodic sources
    assert report.material_change_count == 18


def test_loaders_rebuild_corpus_from_persisted_state(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    run_ingestion(settings)

    engine = load_engine(settings)
    graph = load_graph_store(settings)

    assert len(engine) == 60
    assert graph.get_node("Company", "apple") is not None
    answer = engine.retrieve("Apple risk factors", top_k=1)
    assert answer and answer[0].metadata["company_slug"] == "apple"
