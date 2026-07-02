"""Milestone 1 — Foundation Hardening regression tests.

Asserts the M1 exit criteria: no swallowed exceptions (failures are explicit and
observable), deterministic stable section IDs, durable + deterministic +
provenance-first graph projection, and the frozen API version surface.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from urllib.error import URLError

import pytest
from fastapi.testclient import TestClient

from coruscant.apps.api import API_VERSION, create_app
from coruscant.common.config import SourceSetting
from coruscant.exposure.domain_config import (
    CompanyConfig,
    load_entities,
)
from coruscant.common.errors import FetchError
from coruscant.common.types import SCHEMA_VERSION, SourceDocument, section_id
from coruscant.connectors import sec_edgar
from coruscant.connectors.base import FetchRequest
from coruscant.connectors.common import normalize_reference_document
from coruscant.connectors.sec_edgar import EdgarHttpConnector, normalize_edgar_filing
from coruscant.infrastructure.catalog import SqliteDocumentCatalog
from coruscant.infrastructure.dead_letter import SqliteDeadLetterStore
from coruscant.infrastructure.repositories import (
    FileSystemNormalizedDocumentRepository,
    FileSystemRawDocumentRepository,
)
from coruscant.ingestion.orchestrator import IngestionOrchestrator
from coruscant.ingestion.registry import SourceDefinition, SourceRegistry
from coruscant.knowledge_graph.memory import InMemoryKnowledgeGraphStore


# ---- No swallowed exceptions: fetch failures are explicit -------------------


def test_edgar_fetch_failure_raises_typed_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_args: object, **_kwargs: object) -> object:
        raise URLError("network down")

    monkeypatch.setattr(sec_edgar, "urlopen", boom)
    connector = EdgarHttpConnector(user_agent="test")
    with pytest.raises(FetchError):
        connector.fetch(FetchRequest(company_slug="apple", source_name="10-K", source_uri="https://x/y.htm"))


# ---- Deterministic parsing: stable, unique section IDs ----------------------


def test_section_ids_are_deterministic_and_unique() -> None:
    raw = SourceDocument(
        source_type="news",
        source_uri="reference://news/apple/2025",
        fetched_at=datetime.now(tz=timezone.utc),
        raw_content="## Heading\nfirst body.\n\n## Heading\nsecond body.",  # duplicate titles
        source_name="news",
        metadata={"company_slug": "apple", "company_name": "Apple"},
    )
    first = normalize_reference_document(raw, document_type="news_article")
    again = normalize_reference_document(raw, document_type="news_article")
    ids = [s["id"] for s in first.sections]
    assert all(ids)  # every section has an id
    assert len(set(ids)) == len(ids)  # unique even with duplicate titles
    assert ids == [s["id"] for s in again.sections]  # deterministic across re-parse
    assert ids[0] == section_id(first.canonical_id, 1)


def test_malformed_filing_falls_back_without_crashing() -> None:
    raw = SourceDocument(
        source_type="sec_edgar",
        source_uri="https://example.com/malformed",
        fetched_at=datetime.now(tz=timezone.utc),
        raw_content=Path("tests/fixtures/sec_edgar/malformed-primary.txt").read_text(),
        source_name="sec_edgar",
        metadata={"company_slug": "apple", "form_type": "10-K"},
    )
    normalized = normalize_edgar_filing(raw)
    assert normalized.sections  # raw-filing fallback
    assert all(s.get("id") for s in normalized.sections)


# ---- Observable failures: dead-letter queue ---------------------------------


class _AlwaysFails(sec_edgar.SourceConnector):  # type: ignore[name-defined]
    def fetch(self, request: FetchRequest) -> SourceDocument:
        raise FetchError("simulated permanent failure")


def test_exhausted_failures_land_in_dead_letter(tmp_path: Path) -> None:
    db = f"sqlite:///{tmp_path / 'c.db'}"
    dead = SqliteDeadLetterStore(db)
    registry = SourceRegistry()
    registry.register(
        SourceDefinition(
            source_type="flaky",
            label="Flaky",
            document_type="filing",
            connector_factory=_AlwaysFails,
            normalizer=lambda doc: normalize_reference_document(doc, document_type="filing"),
            periods=(("p1", "2025-01-01"),),
        )
    )
    orchestrator = IngestionOrchestrator(
        raw_repository=FileSystemRawDocumentRepository(tmp_path),
        normalized_repository=FileSystemNormalizedDocumentRepository(tmp_path),
        catalog=SqliteDocumentCatalog(db),
        registry=registry,
        dead_letter_store=dead,
        max_attempts=2,
    )
    report = orchestrator.run(
        [CompanyConfig(slug="apple", name="Apple")], [SourceSetting(type="flaky")]
    )
    assert report.document_count == 0
    assert report.errors  # observable in the report
    entries = dead.list_entries()
    assert len(entries) == 1  # and durably recorded in the dead-letter queue
    assert entries[0].attempts == 2
    assert "simulated permanent failure" in entries[0].error


# ---- Durable, deterministic, provenance-first graph -------------------------


def _run_graph(tmp_path: Path, tag: str) -> InMemoryKnowledgeGraphStore:
    db = f"sqlite:///{tmp_path / f'{tag}.db'}"
    graph = InMemoryKnowledgeGraphStore()
    IngestionOrchestrator(
        raw_repository=FileSystemRawDocumentRepository(tmp_path / tag),
        normalized_repository=FileSystemNormalizedDocumentRepository(tmp_path / tag),
        catalog=SqliteDocumentCatalog(db),
        graph_store=graph,
        entities=load_entities(Path("config")),
    ).run([CompanyConfig(slug="apple", name="Apple", industry="Technology")], [SourceSetting(type="sec_edgar")])
    return graph


def test_graph_projection_is_deterministic_and_provenanced(tmp_path: Path) -> None:
    a = _run_graph(tmp_path, "a")
    b = _run_graph(tmp_path, "b")

    a_nodes = sorted(a.nodes.keys())
    b_nodes = sorted(b.nodes.keys())
    assert a_nodes == b_nodes  # identical node identities across runs

    def edge_keys(g: InMemoryKnowledgeGraphStore) -> list[tuple[str, str, str, str, str]]:
        return sorted(
            (e.source_kind, e.source_key, e.relation, e.target_kind, e.target_key) for e in g.edges
        )

    assert edge_keys(a) == edge_keys(b)  # identical edges across runs (deterministic dedup)

    # Provenance-first: every projected edge carries provenance — either a
    # `source` tag (entity edges) or a `source_uri` to the originating document.
    assert a.edges
    assert all(
        e.properties.get("source") or e.properties.get("source_uri") for e in a.edges
    )


# ---- Frozen API surface -----------------------------------------------------


def test_version_endpoint_is_public_and_frozen() -> None:
    with TestClient(create_app(require_auth=False)) as client:
        body = client.get("/version").json()
        assert body == {"api_version": API_VERSION, "schema_version": SCHEMA_VERSION}
