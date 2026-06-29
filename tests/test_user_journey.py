"""The critical user journey, end to end at the API contract level.

Mirrors the PRD success criteria: log in, pick a company, see what materially
changed, and trace every statement back to its source document.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from coruscant.apps.api import create_app
from coruscant.auth.service import AuthService
from coruscant.auth.store import SqliteUserStore
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


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    db = f"sqlite:///{tmp_path / 'app.db'}"
    catalog = SqliteDocumentCatalog(db)
    intel = SqliteIntelligenceStore(db)
    graph = InMemoryKnowledgeGraphStore()
    engine = HybridRetrievalEngine()
    IngestionOrchestrator(
        raw_repository=FileSystemRawDocumentRepository(tmp_path),
        normalized_repository=FileSystemNormalizedDocumentRepository(tmp_path),
        catalog=catalog,
        graph_store=graph,
        engine=engine,
        intelligence_store=intel,
    ).run(
        [CompanyConfig(slug="apple", name="Apple", industry="Technology")],
        [SourceSetting(type="sec_edgar"), SourceSetting(type="news")],
    )
    service = AuthService(SqliteUserStore(db), secret="journey-secret", token_ttl_seconds=3600)
    return TestClient(
        create_app(engine, graph, intelligence_store=intel, auth_service=service, require_auth=True)
    )


def test_login_to_change_to_evidence(client: TestClient) -> None:
    # 1. Unauthenticated users cannot access the application.
    assert client.get("/dashboard").status_code == 401

    # 2. Create an account and authenticate.
    token = client.post(
        "/auth/register", json={"email": "investor@example.com", "password": "password123"}
    ).json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 3. Dashboard surfaces material changes.
    dashboard = client.get("/dashboard", headers=headers).json()
    assert dashboard["material_changes"] >= 1

    # 4. Pick a company and see what materially changed.
    changes = client.get("/companies/apple/changes", headers=headers).json()
    assert changes, "expected at least one change set"
    change_set = next(cs for cs in changes if cs["material"])
    change = change_set["changes"][0]
    assert change["kind"] in {"added", "removed"}
    assert change["category"]

    # 5. Trace the change back to its source evidence.
    evidence = change["evidence"]
    assert evidence["source_uri"]
    source_doc_id = evidence["canonical_id"]
    assert source_doc_id

    # 6. The cited document opens, and its AI summary is itself fully cited.
    document = client.get(f"/documents/{source_doc_id}", headers=headers).json()
    assert document["sections"]
    summary = client.get(f"/documents/{source_doc_id}/summary", headers=headers).json()
    # The overview itself is a cited claim (no uncited AI assertions).
    assert summary["overview"]["source_uri"] == document["source_uri"]
    for claim in summary["risks"] + summary["key_points"] + [summary["overview"]]:
        assert claim["source_uri"] == document["source_uri"]

    # 7. Natural-language search returns evidence-linked results.
    search = client.post(
        "/retrieve", json={"query": "Apple regulatory risk", "top_k": 3}, headers=headers
    ).json()
    assert search["results"]
    assert search["results"][0]["evidence"][0]["source_uri"]
