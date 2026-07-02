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
from coruscant.ingestion.orchestrator import IngestionOrchestrator
from coruscant.knowledge_graph.memory import InMemoryKnowledgeGraphStore
from coruscant.search.hybrid import HybridRetrievalEngine
from coruscant.watchlists.matcher import match_watch_items
from coruscant.watchlists.models import WatchItem
from coruscant.watchlists.store import SqliteWatchlistStore

APPLE = CompanyConfig(slug="apple", name="Apple", industry="Technology")
MSFT = CompanyConfig(slug="microsoft", name="Microsoft", industry="Technology")


def test_store_crud_and_idempotent_notifications(tmp_path: Path) -> None:
    store = SqliteWatchlistStore(f"sqlite:///{tmp_path / 'w.db'}")
    wl = store.create_watchlist(
        "u@e.com", "Tech", [WatchItem(type="company", value="apple")], created_at="2026-06-29"
    )
    assert store.list_watchlists("u@e.com")[0].name == "Tech"
    assert store.list_watchlists("other@e.com") == []  # user-scoped

    from coruscant.watchlists.models import Notification

    notes = [
        Notification(id="abc", watch_type="company", watch_value="apple", kind="change", title="t", detail="d")
    ]
    assert store.add_notifications("u@e.com", wl.id, notes) == 1
    assert store.add_notifications("u@e.com", wl.id, notes) == 0  # idempotent
    listed = store.list_notifications("u@e.com")
    assert len(listed) == 1 and listed[0].read is False
    assert store.mark_read("u@e.com", listed[0].id)
    assert store.list_notifications("u@e.com", unread_only=True) == []
    assert store.delete_watchlist("u@e.com", wl.id)


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
    ).run([APPLE, MSFT], [SourceSetting(type="sec_edgar")])
    return TestClient(
        create_app(
            engine,
            graph,
            intelligence_store=intel,
            watchlist_store=SqliteWatchlistStore(db),
            require_auth=False,
        )
    )


def test_company_watch_creates_notifications(client: TestClient) -> None:
    created = client.post(
        "/watchlists", json={"name": "Apple", "items": [{"type": "company", "value": "apple"}]}
    ).json()
    assert created["notifications_created"] >= 1
    notes = client.get("/notifications").json()
    assert notes
    note = notes[0]
    assert note["source_uri"]  # every notification links to its source
    assert note["canonical_id"]


def test_country_watch_uses_graph_exposure(client: TestClient) -> None:
    # Apple + Microsoft both rely on TSMC (Taiwan) and both have material SEC changes.
    created = client.post(
        "/watchlists",
        json={"name": "Taiwan", "items": [{"type": "country", "value": "Taiwan"}]},
    ).json()
    assert created["notifications_created"] >= 1
    values = {n["watch_value"] for n in client.get("/notifications").json()}
    assert "Taiwan" in values


def test_unknown_watch_type_rejected(client: TestClient) -> None:
    resp = client.post("/watchlists", json={"name": "x", "items": [{"type": "bogus", "value": "y"}]})
    assert resp.status_code == 400


def test_notification_read_and_delete_flow(client: TestClient) -> None:
    created = client.post(
        "/watchlists", json={"name": "kw", "items": [{"type": "keyword", "value": "guidance"}]}
    ).json()
    wl_id = created["watchlist"]["id"]
    notes = client.get("/notifications", params={"unread_only": True}).json()
    assert notes
    assert client.post(f"/notifications/{notes[0]['id']}/read").json()["ok"] is True
    assert client.delete(f"/watchlists/{wl_id}").json()["ok"] is True


def test_matcher_is_deterministic_and_sourced() -> None:
    from coruscant.intelligence.changes import ReferenceChangeDetector
    from coruscant.common.types import NormalizedDocument

    prev = NormalizedDocument(
        document_type="filing", source_uri="reference://sec/apple/2024", canonical_id="a1",
        title="Apple 10-K", sections=[{"title": "MD&A", "content": "Apple reaffirmed full-year guidance."}],
    )
    cur = NormalizedDocument(
        document_type="filing", source_uri="reference://sec/apple/2025", canonical_id="a2",
        title="Apple 10-K", sections=[{"title": "MD&A", "content": "Apple lowered full-year guidance amid weakness."}],
    )
    cs = ReferenceChangeDetector().diff(cur, prev, company_slug="apple", source_type="sec_edgar")
    notes = match_watch_items(
        [WatchItem(type="keyword", value="guidance")],
        events=[], change_sets=[cs], companies=[APPLE], graph=None, now_iso="2026-06-29",
    )
    assert notes
    assert notes[0].source_uri and notes[0].canonical_id
    # Deterministic id.
    again = match_watch_items(
        [WatchItem(type="keyword", value="guidance")],
        events=[], change_sets=[cs], companies=[APPLE], graph=None, now_iso="2026-06-29",
    )
    assert {n.id for n in notes} == {n.id for n in again}
