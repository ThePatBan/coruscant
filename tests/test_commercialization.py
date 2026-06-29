"""Milestone 5 — Commercialization: organizations, plans, usage/billing, backups."""

from __future__ import annotations

import tarfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from coruscant.apps.api import create_app
from coruscant.apps.runtime import backup
from coruscant.commercial.store import SqliteOrgStore, SqliteUsageStore
from coruscant.common.config import Settings
from coruscant.search.hybrid import HybridRetrievalEngine


def test_org_store_membership_and_plan(tmp_path: Path) -> None:
    store = SqliteOrgStore(f"sqlite:///{tmp_path / 'c.db'}")
    org = store.create_org("owner@e.com", "Acme", "pro", ["m@e.com"], created_at="2026-06-29")
    assert org.plan == "pro"
    assert set(org.members) == {"owner@e.com", "m@e.com"}
    assert store.list_orgs("m@e.com")[0].id == org.id  # members can see it
    assert store.list_orgs("nobody@e.com") == []  # non-members cannot
    assert store.get_org("nobody@e.com", org.id) is None
    assert store.set_plan("m@e.com", org.id, "enterprise") is False  # only owner
    assert store.set_plan("owner@e.com", org.id, "enterprise") is True
    assert store.get_org("owner@e.com", org.id).plan == "enterprise"  # type: ignore[union-attr]


def test_usage_summary_by_member(tmp_path: Path) -> None:
    store = SqliteUsageStore(f"sqlite:///{tmp_path / 'c.db'}")
    store.record("a@e.com", "retrieve", created_at="t")
    store.record("a@e.com", "analyst", created_at="t")
    store.record("b@e.com", "retrieve", created_at="t")
    one = store.summary(["a@e.com"])
    assert one.total == 2 and one.actions["retrieve"] == 1
    both = store.summary(["a@e.com", "b@e.com"])
    assert both.total == 3
    assert store.summary([]).total == 0


def test_backup_archives_the_data_dir(tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    (data / "marker.txt").write_text("state")
    settings = Settings(
        data_dir=data, config_dir=Path("config"), database_url=f"sqlite:///{data / 'c.db'}"
    )
    archive = backup(settings, out_path=tmp_path / "backup.tar.gz")
    assert archive.exists()
    with tarfile.open(archive) as tar:
        assert any(name.endswith("marker.txt") for name in tar.getnames())


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    db = f"sqlite:///{tmp_path / 'app.db'}"
    return TestClient(
        create_app(
            HybridRetrievalEngine(),
            org_store=SqliteOrgStore(db),
            usage_store=SqliteUsageStore(db),
            require_auth=False,
        )
    )


def test_org_billing_reflects_plan_and_usage(client: TestClient) -> None:
    org = client.post("/organizations", json={"name": "Acme", "plan": "pro"}).json()
    assert org["plan"] == "pro"
    assert "anonymous@local" in org["members"]  # creator is a member

    # Generate usage (retrieve records a usage event even with an empty corpus).
    client.post("/retrieve", json={"query": "Apple", "top_k": 2})
    assert client.get("/usage").json()["total"] >= 1

    billing = client.get(f"/organizations/{org['id']}/billing").json()
    assert billing["plan"]["name"] == "pro"
    assert billing["api_calls"] >= 1
    assert billing["within_limits"] is True


def test_unknown_plan_rejected_and_owner_only(client: TestClient) -> None:
    org = client.post("/organizations", json={"name": "Acme"}).json()
    assert org["plan"] == "free"  # default
    assert client.post(f"/organizations/{org['id']}/plan", json={"plan": "bogus"}).status_code == 400
    updated = client.post(f"/organizations/{org['id']}/plan", json={"plan": "enterprise"}).json()
    assert updated["plan"] == "enterprise"
