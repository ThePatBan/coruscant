"""Milestone 2 — Source Platform: common provenance schema + scheduler."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from coruscant.apps.runtime import build_schedule_store
from coruscant.apps.workspace_runtime import (
    due_source_types,
    run_ingestion,
)
from coruscant.common.config import CompanyConfig, Settings, SourceSetting
from coruscant.infrastructure.catalog import SqliteDocumentCatalog
from coruscant.infrastructure.repositories import (
    FileSystemNormalizedDocumentRepository,
    FileSystemRawDocumentRepository,
)
from coruscant.infrastructure.schedule_store import SqliteScheduleStore
from coruscant.ingestion.orchestrator import IngestionOrchestrator
from coruscant.exposure.sources import default_registry
from coruscant.ingestion.scheduler import due_sources, is_due

UTC = timezone.utc


def test_every_document_gets_common_provenance(tmp_path: Path) -> None:
    db = f"sqlite:///{tmp_path / 'c.db'}"
    catalog = SqliteDocumentCatalog(db)
    IngestionOrchestrator(
        registry=default_registry(),
        raw_repository=FileSystemRawDocumentRepository(tmp_path),
        normalized_repository=FileSystemNormalizedDocumentRepository(tmp_path),
        catalog=catalog,
    ).run([CompanyConfig(slug="apple", name="Apple")], [SourceSetting(type="sec_edgar")])

    docs = catalog.list_documents(company_slug="apple")
    assert docs
    for doc in docs:
        assert doc.provenance is not None
        assert doc.provenance.source_type == "sec_edgar"
        assert doc.provenance.source_uri == doc.source_uri
        assert doc.provenance.authority == 0.98  # sec_edgar's registered authority
        assert doc.provenance.retrieved_at  # when it was fetched


def test_is_due_logic() -> None:
    now = datetime(2026, 1, 10, tzinfo=UTC)
    assert is_due(None, 1, now) is True  # never run
    assert is_due((now - timedelta(days=2)).isoformat(), 1, now) is True  # overdue
    assert is_due((now - timedelta(hours=1)).isoformat(), 1, now) is False  # too soon
    assert is_due("not-a-date", 1, now) is True  # corrupt -> re-run


def test_is_due_tolerates_naive_timestamps() -> None:
    # A naive stored timestamp or a naive `now` must not raise TypeError.
    naive_now = datetime(2026, 1, 10)  # noqa: DTZ001 - intentionally naive
    assert is_due("2026-01-01T00:00:00", 1, naive_now) is True  # both naive
    assert is_due("2026-01-01T00:00:00", 1, datetime(2026, 1, 10, tzinfo=UTC)) is True  # naive last
    assert is_due("2026-01-09T00:00:00+00:00", 1, naive_now) is True  # naive now, aware last


def test_due_sources_uses_cadence_and_last_run() -> None:
    now = datetime(2026, 1, 10, tzinfo=UTC)
    definitions = default_registry().definitions()
    last_runs = {
        "sec_edgar": (now - timedelta(days=2)).isoformat(),  # cadence 1 -> due
        "news": (now - timedelta(hours=2)).isoformat(),  # cadence 1 -> not due
    }
    due = set(due_sources(definitions, last_runs, now))
    assert "sec_edgar" in due
    assert "news" not in due
    assert "patents" in due  # never run -> due


def test_schedule_store_roundtrip(tmp_path: Path) -> None:
    store = SqliteScheduleStore(f"sqlite:///{tmp_path / 's.db'}")
    store.record_run("sec_edgar", "2026-01-01T00:00:00+00:00")
    store.record_run("sec_edgar", "2026-01-02T00:00:00+00:00")  # upsert
    assert store.last_runs() == {"sec_edgar": "2026-01-02T00:00:00+00:00"}


def test_run_ingestion_records_runs_so_nothing_is_immediately_due(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    settings = Settings(
        data_dir=data_dir,
        config_dir=Path("config"),
        database_url=f"sqlite:///{data_dir / 'c.db'}",
    )
    run_ingestion(settings)
    last = build_schedule_store(settings).last_runs()
    assert "sec_edgar" in last  # recorded after a successful run

    just_after = datetime.now(tz=UTC) + timedelta(minutes=1)
    assert due_source_types(settings, now=just_after) == []  # nothing due right after a run
    far_future = datetime.now(tz=UTC) + timedelta(days=30)
    assert "sec_edgar" in due_source_types(settings, now=far_future)  # due again later
