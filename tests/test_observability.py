from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from coruscant.common.config import SourceSetting
from coruscant.exposure.domain_config import CompanyConfig
from coruscant.common.types import SourceDocument
from coruscant.connectors.base import FetchRequest, SourceConnector
from coruscant.connectors.common import normalize_reference_document
from coruscant.infrastructure.catalog import SqliteDocumentCatalog
from coruscant.infrastructure.status import RunStatus, load_status, save_status
from coruscant.infrastructure.repositories import (
    FileSystemNormalizedDocumentRepository,
    FileSystemRawDocumentRepository,
)
from coruscant.ingestion.orchestrator import IngestionOrchestrator
from coruscant.ingestion.registry import SourceDefinition, SourceRegistry

COMPANY = CompanyConfig(slug="apple", name="Apple", industry="Technology")


class _FlakyConnector(SourceConnector):
    def __init__(self, state: dict[str, int], fail_until: int) -> None:
        self.state = state
        self.fail_until = fail_until

    def fetch(self, request: FetchRequest) -> SourceDocument:
        self.state["calls"] += 1
        if self.state["calls"] < self.fail_until:
            raise RuntimeError("transient fetch failure")
        return SourceDocument(
            source_type="flaky",
            source_uri=request.source_uri,
            fetched_at=datetime.now(tz=timezone.utc),
            raw_content="## Body\nApple reported revenue growth.",
            source_name=request.source_name,
            metadata={"company_slug": request.company_slug, "company_name": "Apple"},
        )


def _registry(state: dict[str, int], fail_until: int) -> SourceRegistry:
    registry = SourceRegistry()
    registry.register(
        SourceDefinition(
            source_type="flaky",
            label="Flaky",
            document_type="filing",
            connector_factory=lambda: _FlakyConnector(state, fail_until),
            normalizer=lambda doc: normalize_reference_document(doc, document_type="filing"),
            periods=(("p1", "2025-01-01"),),
        )
    )
    return registry


def _orchestrator(tmp_path: Path, registry: SourceRegistry, *, max_attempts: int) -> IngestionOrchestrator:
    return IngestionOrchestrator(
        raw_repository=FileSystemRawDocumentRepository(tmp_path),
        normalized_repository=FileSystemNormalizedDocumentRepository(tmp_path),
        catalog=SqliteDocumentCatalog(f"sqlite:///{tmp_path / 'c.db'}"),
        registry=registry,
        max_attempts=max_attempts,
    )


def test_failed_ingestion_retries_and_recovers(tmp_path: Path) -> None:
    state = {"calls": 0}
    orchestrator = _orchestrator(tmp_path, _registry(state, fail_until=2), max_attempts=3)
    report = orchestrator.run([COMPANY], [SourceSetting(type="flaky")])
    assert report.document_count == 1
    assert not report.errors
    assert state["calls"] == 2  # failed once, then succeeded


def test_exhausted_retries_are_logged_as_errors(tmp_path: Path) -> None:
    state = {"calls": 0}
    orchestrator = _orchestrator(tmp_path, _registry(state, fail_until=99), max_attempts=2)
    report = orchestrator.run([COMPANY], [SourceSetting(type="flaky")])
    assert report.document_count == 0
    assert len(report.errors) == 1
    assert "flaky" in report.errors[0]
    assert state["calls"] == 2  # exactly max_attempts


def test_duplicate_documents_are_idempotent(tmp_path: Path) -> None:
    catalog = SqliteDocumentCatalog(f"sqlite:///{tmp_path / 'c.db'}")
    orchestrator = IngestionOrchestrator(
        raw_repository=FileSystemRawDocumentRepository(tmp_path),
        normalized_repository=FileSystemNormalizedDocumentRepository(tmp_path),
        catalog=catalog,
    )
    sources = [SourceSetting(type="news")]
    orchestrator.run([COMPANY], sources)
    first = catalog.count()
    orchestrator.run([COMPANY], sources)  # same canonical ids -> upsert, no duplicates
    assert catalog.count() == first


def test_run_status_roundtrip(tmp_path: Path) -> None:
    from coruscant.ingestion.orchestrator import IngestionReport

    report = IngestionReport(summary_count=5, change_set_count=2, material_change_count=2)
    status = RunStatus.from_report(report, completed_at="2026-06-29T00:00:00+00:00")
    assert status.ok
    path = tmp_path / "status.json"
    save_status(status, path)
    loaded = load_status(path)
    assert loaded is not None
    assert loaded.summary_count == 5
    assert loaded.material_change_count == 2
    assert load_status(tmp_path / "absent.json") is None
