"""M5 quota enforcement (Priority 2).

Plan limits were computed (billing) but never enforced. These pin the smallest
practical enforcement surface — per-day API calls and watchlist count — and prove
it is gated on a multi-tenant deployment so single-tenant behavior never regresses.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from coruscant.apps.api import create_app
from coruscant.auth.service import AuthService
from coruscant.auth.store import SqliteUserStore
from coruscant.commercial.store import SqliteOrgStore, SqliteUsageStore
from coruscant.search.hybrid import HybridRetrievalEngine
from coruscant.watchlists.store import SqliteWatchlistStore

ANON = "anonymous@local"  # the shared identity when require_auth=False


def _today() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT00:00:00+00:00")


def _seed_usage(usage: SqliteUsageStore, email: str, action: str, n: int) -> None:
    for _ in range(n):
        usage.record(email, action, created_at=datetime.now(tz=timezone.utc).isoformat())


def _client(
    tmp_path: Path, *, with_org: bool = True, with_watchlists: bool = False
) -> tuple[TestClient, SqliteOrgStore, SqliteUsageStore]:
    db = f"sqlite:///{tmp_path / 'app.db'}"
    org = SqliteOrgStore(db)
    usage = SqliteUsageStore(db)
    client = TestClient(
        create_app(
            HybridRetrievalEngine(),
            org_store=org if with_org else None,
            usage_store=usage,
            watchlist_store=SqliteWatchlistStore(db) if with_watchlists else None,
            require_auth=False,
        )
    )
    return client, org, usage


# ---- API call quota --------------------------------------------------------


def test_retrieve_meters_authenticated_but_never_the_anonymous_scope(tmp_path: Path) -> None:
    # The public /retrieve is quota-metered ONLY for authenticated callers; an
    # authenticated caller over their plan's daily cap is blocked, while an anonymous
    # visitor is never metered against the shared bucket (they are per-IP rate-limited
    # instead), so one abuser cannot quota-lock open discovery for everyone.
    db = f"sqlite:///{tmp_path / 'app.db'}"
    usage = SqliteUsageStore(db)
    auth = AuthService(SqliteUserStore(db), secret="s", token_ttl_seconds=3600)
    client = TestClient(
        create_app(
            HybridRetrievalEngine(),
            org_store=SqliteOrgStore(db),
            usage_store=usage,
            auth_service=auth,
            require_auth=True,
        )
    )
    token = client.post(
        "/auth/register", json={"email": "u@e.com", "password": "password123"}
    ).json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    client.post("/organizations", json={"name": "Acme", "plan": "free"}, headers=headers)  # 100/day
    _seed_usage(usage, "u@e.com", "retrieve", 100)  # that user's free quota is now spent

    blocked = client.post("/retrieve", json={"query": "Apple", "top_k": 2}, headers=headers)
    assert blocked.status_code == 429
    assert "quota" in blocked.json()["detail"].lower()

    # No token → anonymous public read → not metered, discovery stays open.
    assert client.post("/retrieve", json={"query": "Apple", "top_k": 2}).status_code == 200


def test_higher_plan_lifts_the_limit(tmp_path: Path) -> None:
    # /analyst is the metered authenticated route used here (retrieve no longer meters
    # the anonymous scope); on a pro plan the same 100 prior calls do not block.
    client, _org, usage = _client(tmp_path)
    client.post("/organizations", json={"name": "Acme", "plan": "pro"})  # 10k/day
    _seed_usage(usage, ANON, "analyst", 100)  # would block on free, fine on pro

    assert client.post("/analyst/apple", json={"question": "why?"}).status_code == 200


def test_analyst_endpoint_is_also_metered(tmp_path: Path) -> None:
    client, _org, usage = _client(tmp_path)
    client.post("/organizations", json={"name": "Acme", "plan": "free"})
    _seed_usage(usage, ANON, "analyst", 100)
    assert client.post("/analyst/apple", json={"question": "why worry?"}).status_code == 429


def test_single_tenant_is_never_throttled(tmp_path: Path) -> None:
    # No org store configured (single-tenant/offline) → enforcement is inert even
    # with usage well past any plan limit. Preserves pre-existing behavior.
    client, _org, usage = _client(tmp_path, with_org=False)
    _seed_usage(usage, ANON, "retrieve", 500)
    assert client.post("/retrieve", json={"query": "Apple", "top_k": 2}).status_code == 200


# ---- watchlist quota -------------------------------------------------------


def test_watchlist_creation_blocked_at_plan_limit(tmp_path: Path) -> None:
    client, _org, _usage = _client(tmp_path, with_watchlists=True)
    client.post("/organizations", json={"name": "Acme", "plan": "free"})  # free = 3 watchlists
    for i in range(3):
        ok = client.post("/watchlists", json={"name": f"w{i}", "items": [{"type": "keyword", "value": "x"}]})
        assert ok.status_code == 200
    blocked = client.post("/watchlists", json={"name": "w4", "items": [{"type": "keyword", "value": "x"}]})
    assert blocked.status_code == 429
    assert "watchlist limit" in blocked.json()["detail"].lower()


# ---- /quota status surface -------------------------------------------------


def test_quota_status_reports_plan_usage_and_remaining(tmp_path: Path) -> None:
    client, _org, usage = _client(tmp_path)
    client.post("/organizations", json={"name": "Acme", "plan": "pro"})
    _seed_usage(usage, ANON, "retrieve", 5)

    status = client.get("/quota").json()
    assert status["plan"] == "pro"
    assert status["max_api_calls_per_day"] == 10_000
    assert status["api_calls_today"] == 5
    assert status["api_calls_remaining"] == 9_995
    assert status["enforced"] is True


def test_quota_status_defaults_to_free_without_orgs(tmp_path: Path) -> None:
    client, _org, _usage = _client(tmp_path, with_org=False)
    status = client.get("/quota").json()
    assert status["plan"] == "free"
    assert status["enforced"] is False  # not enforced without a multi-tenant store
