from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from coruscant.exposure.sources import default_registry
from coruscant.apps.api import create_app
from coruscant.common.config import SourceSetting
from coruscant.exposure.domain_config import CompanyConfig
from coruscant.infrastructure.catalog import SqliteDocumentCatalog
from coruscant.infrastructure.intelligence_store import SqliteIntelligenceStore
from coruscant.infrastructure.repositories import (
    FileSystemNormalizedDocumentRepository,
    FileSystemRawDocumentRepository,
)
from coruscant.ingestion.orchestrator import IngestionOrchestrator
from coruscant.knowledge_graph.memory import InMemoryKnowledgeGraphStore
from coruscant.search.hybrid import HybridRetrievalEngine


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    catalog = SqliteDocumentCatalog(f"sqlite:///{tmp_path / 'c.db'}")
    intel = SqliteIntelligenceStore(f"sqlite:///{tmp_path / 'c.db'}")
    graph = InMemoryKnowledgeGraphStore()
    engine = HybridRetrievalEngine()
    orchestrator = IngestionOrchestrator(
        registry=default_registry(),
        raw_repository=FileSystemRawDocumentRepository(tmp_path),
        normalized_repository=FileSystemNormalizedDocumentRepository(tmp_path),
        catalog=catalog,
        graph_store=graph,
        engine=engine,
        intelligence_store=intel,
    )
    orchestrator.run(
        [CompanyConfig(slug="apple", name="Apple", industry="Technology")],
        [SourceSetting(type="sec_edgar"), SourceSetting(type="news")],
    )
    return TestClient(create_app(engine, graph, intelligence_store=intel, require_auth=False))


def test_dashboard(client: TestClient) -> None:
    body = client.get("/dashboard").json()
    assert body["documents"] == 3  # sec_edgar (2 periods) + news (1)
    assert body["material_changes"] >= 1
    assert body["latest_documents"]
    assert isinstance(body["recent_events"], list)


def test_company_changes_are_material_and_cited(client: TestClient) -> None:
    changes = client.get("/companies/apple/changes").json()
    assert len(changes) == 1  # one periodic source (sec_edgar)
    change_set = changes[0]
    assert change_set["material"] is True
    assert change_set["added_count"] >= 1
    assert change_set["changes"][0]["evidence"]["source_uri"]


def test_company_timeline(client: TestClient) -> None:
    events = client.get("/companies/apple/timeline").json()
    assert events
    # Sorted by occurred_at descending.
    dates = [e["occurred_at"] for e in events if e["occurred_at"]]
    assert dates == sorted(dates, reverse=True)


def test_document_summary_is_cited(client: TestClient) -> None:
    # Find a document id from the listing, then fetch its AI summary.
    docs = client.get("/documents", params={"company": "apple"}).json()
    sec_doc = next(d for d in docs if d["source_uri"].startswith("reference://sec_edgar"))
    summary = client.get(f"/documents/{sec_doc['canonical_id']}/summary").json()
    assert summary["overview"]
    assert summary["risks"]
    for claim in summary["risks"]:
        assert claim["source_uri"] == sec_doc["source_uri"]


def test_summary_404_when_missing(client: TestClient) -> None:
    assert client.get("/documents/nonexistent/summary").status_code == 404
