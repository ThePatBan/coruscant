from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from coruscant.exposure.sources import default_registry
from coruscant.apps.api import create_app
from coruscant.common.config import CompanyConfig, SourceSetting, load_entities
from coruscant.infrastructure.catalog import SqliteDocumentCatalog
from coruscant.infrastructure.intelligence_store import SqliteIntelligenceStore
from coruscant.infrastructure.repositories import (
    FileSystemNormalizedDocumentRepository,
    FileSystemRawDocumentRepository,
)
from coruscant.ingestion.orchestrator import IngestionOrchestrator
from coruscant.knowledge_graph.memory import InMemoryKnowledgeGraphStore
from coruscant.portfolio.store import SqlitePortfolioStore
from coruscant.search.hybrid import HybridRetrievalEngine

APPLE = CompanyConfig(slug="apple", name="Apple", industry="Technology")


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
    ).run([APPLE], [SourceSetting(type="sec_edgar"), SourceSetting(type="job_postings"), SourceSetting(type="patents")])
    return TestClient(
        create_app(
            engine,
            graph,
            intelligence_store=intel,
            portfolio_store=SqlitePortfolioStore(db),
            require_auth=False,
        )
    )


def test_analyst_endpoint_multistep_and_cited(client: TestClient) -> None:
    report = client.post(
        "/analyst/apple", json={"question": "Why should I worry about Apple over six months?"}
    ).json()
    assert report["focus"] == "risk"
    assert [s["label"] for s in report["steps"]] == ["Search", "Read", "Reason", "Compare", "Cite", "Answer"]
    assert report["concerns"]
    for concern in report["concerns"]:
        assert concern["evidence"][0]["source_uri"]
        assert 0 < concern["confidence"] <= 0.85
    # Supply-chain / geopolitical concern surfaces from the entity graph.
    assert any("Taiwan" in c["title"] for c in report["concerns"])


def test_signals_endpoint_probabilistic_and_cited(client: TestClient) -> None:
    signals = client.get("/signals/apple").json()
    assert signals
    types = {s["type"] for s in signals}
    # Hiring (job postings), patents, geopolitical, and a change-driven signal.
    assert {"hiring", "patent_momentum", "geopolitical"} <= types
    for s in signals:
        assert 0 < s["strength"] <= 0.8  # never certainty
        assert s["evidence"][0]["source_uri"]


def test_portfolio_briefing_aggregates_changes(client: TestClient) -> None:
    created = client.post(
        "/portfolios",
        json={"name": "Mine", "holdings": [{"company_slug": "apple"}]},
    ).json()
    briefing = client.get(f"/portfolios/{created['id']}/briefing").json()
    assert briefing["companies_with_changes"] >= 1
    assert briefing["material_changes"]
    assert "holdings" in briefing
    # user-scoped delete
    assert client.delete(f"/portfolios/{created['id']}").json()["ok"] is True
