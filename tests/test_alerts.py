"""Alerts surface: bulk watchlist evaluation, notification summary, mark-all-read.

These cover the additive endpoints that turn the (already-tested) notification
store into the product's ambient "what changed" loop. The store-level tests pin
user-scoping and idempotency; the API tests pin the wiring end to end.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

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
from coruscant.search.hybrid import HybridRetrievalEngine
from coruscant.watchlists.models import Notification, WatchItem
from coruscant.watchlists.store import SqliteWatchlistStore

APPLE = CompanyConfig(slug="apple", name="Apple", industry="Technology")
MSFT = CompanyConfig(slug="microsoft", name="Microsoft", industry="Technology")


def _note(nid: str) -> Notification:
    return Notification(
        id=nid, watch_type="company", watch_value="apple", kind="change", title="t", detail="d"
    )


def test_summary_and_mark_all_read_are_scoped(tmp_path: Path) -> None:
    store = SqliteWatchlistStore(f"sqlite:///{tmp_path / 'w.db'}")
    wl = store.create_watchlist(
        "u@e.com", "Tech", [WatchItem(type="company", value="apple")], created_at="2026-06-29"
    )
    store.add_notifications("u@e.com", wl.id, [_note("a"), _note("b")])

    assert store.summary("u@e.com") == (2, 2)  # total, unread
    assert store.summary("other@e.com") == (0, 0)  # user-scoped

    assert store.mark_all_read("u@e.com") == 2
    assert store.summary("u@e.com") == (2, 0)  # total preserved, all read
    assert store.mark_all_read("u@e.com") == 0  # idempotent: nothing left unread
    assert store.mark_all_read("other@e.com") == 0  # never touches another user


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


def test_summary_empty_then_populated(client: TestClient) -> None:
    assert client.get("/notifications/summary").json() == {"total": 0, "unread": 0}
    client.post("/watchlists", json={"name": "Apple", "items": [{"type": "company", "value": "apple"}]})
    summary = client.get("/notifications/summary").json()
    assert summary["total"] >= 1
    assert summary["unread"] == summary["total"]  # freshly created → all unread


def test_evaluate_all_is_idempotent(client: TestClient) -> None:
    client.post("/watchlists", json={"name": "A", "items": [{"type": "company", "value": "apple"}]})
    client.post("/watchlists", json={"name": "B", "items": [{"type": "company", "value": "microsoft"}]})

    first = client.post("/watchlists/evaluate-all").json()
    assert first["watchlists_evaluated"] == 2
    # Notifications were already created at watchlist creation time; a re-check over
    # an unchanged corpus must create none (de-dup), but still report coverage.
    assert first["notifications_created"] == 0

    second = client.post("/watchlists/evaluate-all").json()
    assert second == {"watchlists_evaluated": 2, "notifications_created": 0}


def test_evaluate_all_with_no_watchlists(client: TestClient) -> None:
    assert client.post("/watchlists/evaluate-all").json() == {
        "watchlists_evaluated": 0,
        "notifications_created": 0,
    }


def test_read_all_clears_unread(client: TestClient) -> None:
    client.post("/watchlists", json={"name": "Apple", "items": [{"type": "company", "value": "apple"}]})
    before = client.get("/notifications/summary").json()
    assert before["unread"] > 0

    marked = client.post("/notifications/read-all").json()["marked"]
    assert marked == before["unread"]

    after = client.get("/notifications/summary").json()
    assert after["unread"] == 0
    assert after["total"] == before["total"]  # read, not deleted
    assert client.post("/notifications/read-all").json()["marked"] == 0  # idempotent


def test_summary_route_not_shadowed_by_id_route(client: TestClient) -> None:
    # Guards route ordering: GET /notifications/summary must resolve to the summary
    # handler, not be swallowed by a parameterized notification route.
    resp = client.get("/notifications/summary")
    assert resp.status_code == 200
    assert set(resp.json()) == {"total", "unread"}
