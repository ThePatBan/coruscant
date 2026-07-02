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


def test_usage_summary_by_member_and_window(tmp_path: Path) -> None:
    store = SqliteUsageStore(f"sqlite:///{tmp_path / 'c.db'}")
    store.record("a@e.com", "retrieve", created_at="2026-06-29T09:00:00+00:00")
    store.record("a@e.com", "analyst", created_at="2026-06-29T10:00:00+00:00")
    store.record("b@e.com", "retrieve", created_at="2026-06-29T11:00:00+00:00")
    store.record("a@e.com", "retrieve", created_at="2000-01-01T00:00:00+00:00")  # ancient
    one = store.summary(["a@e.com"])
    assert one.total == 3 and one.actions["retrieve"] == 2
    both = store.summary(["a@e.com", "b@e.com"])
    assert both.total == 4
    assert store.summary([]).total == 0
    # since_iso windows out older events (per-day quota semantics)
    windowed = store.summary(["a@e.com"], since_iso="2026-06-29T00:00:00+00:00")
    assert windowed.total == 2  # ancient event excluded


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

    # Generate a metered usage event. /analyst is an authenticated, metered route (the
    # public /retrieve deliberately does NOT meter the shared anonymous scope).
    client.post("/analyst/apple", json={"question": "why worry?"})
    assert client.get("/usage").json()["total"] >= 1

    billing = client.get(f"/organizations/{org['id']}/billing").json()
    assert billing["plan"]["name"] == "pro"
    assert billing["api_calls"] >= 1
    assert billing["within_limits"] is True


def test_billing_is_owner_only_and_per_day(tmp_path: Path) -> None:
    db = f"sqlite:///{tmp_path / 'b.db'}"
    org_store = SqliteOrgStore(db)
    usage = SqliteUsageStore(db)
    client = TestClient(
        create_app(HybridRetrievalEngine(), org_store=org_store, usage_store=usage, require_auth=False)
    )
    # An org owned by someone else, with the caller (anonymous@local) only a member.
    other = org_store.create_org(
        "owner@x.com", "Acme", "pro", ["anonymous@local"], created_at="2026-06-29T00:00:00+00:00"
    )
    assert client.get(f"/organizations/{other.id}/billing").status_code == 403  # member != owner

    # An org the caller owns: ancient usage is excluded by the per-day window.
    mine = client.post("/organizations", json={"name": "Mine", "plan": "free"}).json()
    usage.record("anonymous@local", "retrieve", created_at="2000-01-01T00:00:00+00:00")
    billing = client.get(f"/organizations/{mine['id']}/billing").json()
    assert billing["api_calls"] == 0  # the ancient event is not counted today
    assert billing["within_limits"] is True


def test_org_creation_ignores_injected_members(client: TestClient) -> None:
    # A caller must not be able to inject another user's email as a member: that
    # email's private usage would otherwise surface in the org's billing summary.
    org = client.post(
        "/organizations", json={"name": "Acme", "members": ["victim@example.com"]}
    ).json()
    assert org["members"] == ["anonymous@local"]  # only the creator, injected member dropped


def test_unknown_plan_rejected_and_owner_only(client: TestClient) -> None:
    org = client.post("/organizations", json={"name": "Acme"}).json()
    assert org["plan"] == "free"  # default
    assert client.post(f"/organizations/{org['id']}/plan", json={"plan": "bogus"}).status_code == 400
    updated = client.post(f"/organizations/{org['id']}/plan", json={"plan": "enterprise"}).json()
    assert updated["plan"] == "enterprise"
