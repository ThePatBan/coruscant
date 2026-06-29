from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from coruscant.apps.api import create_app
from coruscant.auth.service import AuthService
from coruscant.auth.store import SqliteUserStore
from coruscant.enterprise.api_keys import SqliteApiKeyStore
from coruscant.enterprise.audit import SqliteAuditStore
from coruscant.workspaces.store import SqliteWorkspaceStore


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    db = f"sqlite:///{tmp_path / 'app.db'}"
    auth = AuthService(SqliteUserStore(db), secret="s", token_ttl_seconds=3600)
    auth.register("admin@e.com", "password123", role="admin")
    auth.register("ana@e.com", "password123", role="analyst")
    auth.register("other@e.com", "password123", role="analyst")
    return TestClient(
        create_app(
            auth_service=auth,
            require_auth=True,
            workspace_store=SqliteWorkspaceStore(db),
            api_key_store=SqliteApiKeyStore(db),
            audit_store=SqliteAuditStore(db),
        )
    )


def _hdr(client: TestClient, email: str) -> dict[str, str]:
    token = client.post("/auth/login", json={"email": email, "password": "password123"}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


def test_workspace_collaboration_and_access_control(client: TestClient) -> None:
    ana = _hdr(client, "ana@e.com")
    created = client.post("/workspaces", json={"name": "Research", "members": ["other@e.com"]}, headers=ana).json()
    wid = created["id"]
    # add a thesis item
    item = client.post(
        f"/workspaces/{wid}/items",
        json={"type": "thesis", "title": "Apple bull case", "body": "...", "ref": "apple"},
        headers=ana,
    )
    assert item.status_code == 200

    # a member can see it; a non-member cannot
    other = _hdr(client, "other@e.com")
    assert client.get(f"/workspaces/{wid}", headers=other).status_code == 200
    # register-and-login a stranger not in the workspace
    stranger = _hdr(client, "admin@e.com")  # admin is not a member of this workspace
    assert client.get(f"/workspaces/{wid}", headers=stranger).status_code == 404

    # unknown item type rejected
    assert client.post(f"/workspaces/{wid}/items", json={"type": "bogus", "title": "x"}, headers=ana).status_code == 400


def test_api_key_grants_programmatic_access(client: TestClient) -> None:
    ana = _hdr(client, "ana@e.com")
    created = client.post("/api-keys", json={"name": "ci"}, headers=ana).json()
    secret = created["secret"]
    assert secret.startswith("csk_")

    # The key authenticates without a session token.
    me = client.get("/auth/me", headers={"X-API-Key": secret})
    assert me.status_code == 200
    assert me.json()["email"] == "ana@e.com"

    # Listing never returns the raw secret; revoke works.
    listed = client.get("/api-keys", headers=ana).json()
    assert listed and "secret" not in listed[0]
    assert client.delete(f"/api-keys/{listed[0]['id']}", headers=ana).json()["ok"] is True
    assert client.get("/auth/me", headers={"X-API-Key": secret}).status_code == 401


def test_rbac_and_audit_log(client: TestClient) -> None:
    ana = _hdr(client, "ana@e.com")
    admin = _hdr(client, "admin@e.com")

    assert client.get("/auth/me", headers=admin).json()["role"] == "admin"
    assert client.get("/auth/me", headers=ana).json()["role"] == "analyst"

    # analyst cannot read the audit log; admin can
    assert client.get("/admin/audit", headers=ana).status_code == 403
    entries = client.get("/admin/audit", headers=admin).json()
    assert any(e["action"] == "login" for e in entries)  # logins were audited
