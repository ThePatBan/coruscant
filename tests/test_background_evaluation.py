"""Background notification evaluation (Priority 3).

Notifications were evaluate-on-demand only. The worker now refreshes every user's
watchlists after each ingestion run, so alerts appear with no manual action. These
prove the batch evaluator generates notifications across users and is idempotent,
without touching the existing on-demand API path.
"""

from __future__ import annotations

from pathlib import Path

from coruscant.apps.workspace_runtime import (
    evaluate_all_watchlists,
    run_ingestion,
)
from coruscant.common.config import Settings
from coruscant.watchlists.models import WatchItem
from coruscant.watchlists.store import SqliteWatchlistStore


def test_all_watchlists_spans_every_user(tmp_path: Path) -> None:
    store = SqliteWatchlistStore(f"sqlite:///{tmp_path / 'w.db'}")
    store.create_watchlist("a@e.com", "A", [WatchItem(type="company", value="apple")], created_at="2026-06-29")
    store.create_watchlist("b@e.com", "B", [WatchItem(type="country", value="Taiwan")], created_at="2026-06-29")
    owners = {owner for owner, _ in store.all_watchlists()}
    assert owners == {"a@e.com", "b@e.com"}


def _settings(tmp_path: Path) -> Settings:
    data_dir = tmp_path / "data"
    return Settings(
        data_dir=data_dir,
        config_dir=Path("config"),
        database_url=f"sqlite:///{data_dir / 'c.db'}",
    )


def test_background_evaluation_generates_notifications_without_user_action(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    run_ingestion(settings)  # populates intelligence + graph snapshot

    # Create a watchlist directly in the store — bypassing the API so nothing is
    # evaluated on the user's behalf. The user has taken no action beyond saving it.
    store = SqliteWatchlistStore(settings.database_url)
    watchlist = store.create_watchlist(
        "analyst@e.com",
        "Taiwan exposure",
        [WatchItem(type="country", value="Taiwan")],
        created_at="2026-06-29T00:00:00+00:00",
    )
    assert store.list_notifications("analyst@e.com") == []  # nothing yet

    created = evaluate_all_watchlists(settings)
    assert created > 0  # the background loop produced alerts

    notifications = store.list_notifications("analyst@e.com")
    assert notifications
    assert all(n.watchlist_id == watchlist.id for n in notifications)
    # Source-linked, per the product's non-negotiable provenance rule.
    assert all(n.source_uri for n in notifications)


def test_background_evaluation_is_idempotent(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    run_ingestion(settings)
    store = SqliteWatchlistStore(settings.database_url)
    store.create_watchlist(
        "analyst@e.com",
        "Apple",
        [WatchItem(type="company", value="apple")],
        created_at="2026-06-29T00:00:00+00:00",
    )

    first = evaluate_all_watchlists(settings)
    assert first > 0
    second = evaluate_all_watchlists(settings)
    assert second == 0  # de-dup: a second pass over an unchanged corpus adds nothing
