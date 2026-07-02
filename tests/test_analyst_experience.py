"""Milestone 4 — Analyst Experience: saved searches, document comparison, and a
full daily-workflow smoke test (an analyst working entirely inside Coruscant)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from coruscant.exposure.sources import default_registry
from coruscant.apps.api import create_app
from coruscant.common.config import SourceSetting
from coruscant.exposure.domain_config import (
    CompanyConfig,
    load_entities,
)
from coruscant.infrastructure.catalog import SqliteDocumentCatalog
from coruscant.infrastructure.intelligence_store import SqliteIntelligenceStore
from coruscant.infrastructure.repositories import (
    FileSystemNormalizedDocumentRepository,
    FileSystemRawDocumentRepository,
)
from coruscant.infrastructure.saved_searches import SqliteSavedSearchStore
from coruscant.ingestion.orchestrator import IngestionOrchestrator
from coruscant.knowledge_graph.memory import InMemoryKnowledgeGraphStore
from coruscant.portfolio.store import SqlitePortfolioStore
from coruscant.search.hybrid import HybridRetrievalEngine
from coruscant.watchlists.store import SqliteWatchlistStore


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    db = f"sqlite:///{tmp_path / 'app.db'}"
    catalog = SqliteDocumentCatalog(db)
    intel = SqliteIntelligenceStore(db)
    graph = InMemoryKnowledgeGraphStore()
    engine = HybridRetrievalEngine()
    IngestionOrchestrator(
        registry=default_registry(),
        raw_repository=FileSystemRawDocumentRepository(tmp_path),
        normalized_repository=FileSystemNormalizedDocumentRepository(tmp_path),
        catalog=catalog,
        graph_store=graph,
        engine=engine,
        intelligence_store=intel,
        entities=load_entities(Path("config")),
    ).run([CompanyConfig(slug="apple", name="Apple", industry="Technology")], [SourceSetting(type="sec_edgar")])
    return TestClient(
        create_app(
            engine,
            graph,
            intelligence_store=intel,
            watchlist_store=SqliteWatchlistStore(db),
            portfolio_store=SqlitePortfolioStore(db),
            saved_search_store=SqliteSavedSearchStore(db),
            require_auth=False,
        )
    )


def test_saved_searches_crud(client: TestClient) -> None:
    created = client.post(
        "/saved-searches", json={"name": "Apple risks", "query": "Apple regulatory risk"}
    ).json()
    assert created["query"] == "Apple regulatory risk"
    listed = client.get("/saved-searches").json()
    assert [s["id"] for s in listed] == [created["id"]]
    # the saved query still drives retrieval
    results = client.post("/retrieve", json={"query": created["query"], "top_k": 3}).json()
    assert results["results"]
    assert client.delete(f"/saved-searches/{created['id']}").json()["ok"] is True
    assert client.get("/saved-searches").json() == []


def test_document_detail_exposes_provenance(client: TestClient) -> None:
    docs = client.get("/documents", params={"company": "apple", "source_type": "sec_edgar"}).json()
    detail = client.get(f"/documents/{docs[0]['canonical_id']}").json()
    assert detail["provenance"] is not None
    assert detail["provenance"]["source_type"] == "sec_edgar"
    assert detail["provenance"]["authority"] == 0.98


def test_document_comparison(client: TestClient) -> None:
    docs = client.get("/documents", params={"company": "apple", "source_type": "sec_edgar"}).json()
    by_date = {d["published_at"]: d["canonical_id"] for d in docs}
    current = by_date["2025-01-31"]
    prior = by_date["2024-01-31"]
    diff = client.get("/compare", params={"a": current, "b": prior}).json()
    assert diff["material"] is True
    assert diff["added_count"] >= 1
    # the diff is cited
    assert diff["changes"][0]["evidence"]["source_uri"]
    assert client.get("/compare", params={"a": current, "b": "missing"}).status_code == 404


def test_daily_workflow_end_to_end(client: TestClient) -> None:
    # Dashboard → company analyst → predictive signals → compare filings → save a
    # search → set a watchlist — entirely inside Coruscant.
    assert client.get("/dashboard").json()["documents"] >= 1
    analysis = client.post("/analyst/apple", json={"question": "Why worry about Apple?"}).json()
    assert analysis["concerns"]
    assert client.get("/signals/apple").json()
    changes = client.get("/companies/apple/changes").json()
    assert any(c["material"] for c in changes)
    assert client.post("/saved-searches", json={"name": "watch", "query": "Apple guidance"}).status_code == 200
    wl = client.post(
        "/watchlists", json={"name": "Apple", "items": [{"type": "company", "value": "apple"}]}
    ).json()
    assert wl["notifications_created"] >= 1
