"""Phase 7 — enterprise entitlement (Scope B) + API-key scope/expiry hardening (Scope C).

Scope B: the enterprise surface is a real entitlement decision, not "any authenticated
user". `/entitlements` is the single backend source of truth; `/enterprise/summary` is
the first route behind the seam — proven across anonymous, basic-authenticated,
entitled, and admin callers.

Scope C: API keys carry least-privilege scopes + optional expiry, migrate safely, never
grant admin by default, and cannot reach admin/enterprise routes unless explicitly
scoped.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from coruscant.apps.api import create_app
from coruscant.auth.service import AuthService
from coruscant.auth.store import SqliteUserStore
from coruscant.commercial.store import SqliteOrgStore, SqliteUsageStore
from coruscant.enterprise.api_keys import SqliteApiKeyStore
from coruscant.enterprise.audit import SqliteAuditStore


def _client(tmp_path: Path) -> tuple[TestClient, AuthService]:
    db = f"sqlite:///{tmp_path / 'c.db'}"
    service = AuthService(SqliteUserStore(db), secret="s", token_ttl_seconds=3600)
    app = create_app(
        auth_service=service,
        require_auth=True,
        api_key_store=SqliteApiKeyStore(db),
        audit_store=SqliteAuditStore(db),
        org_store=SqliteOrgStore(db),
        usage_store=SqliteUsageStore(db),
    )
    return TestClient(app), service


def _login(client: TestClient, service: AuthService, email: str, role: str = "analyst") -> dict[str, str]:
    service.register(email, "password123", role=role)
    token = client.post("/auth/login", json={"email": email, "password": "password123"}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


# ============================ Scope B — enterprise entitlement ============================


def test_entitlements_endpoint_requires_auth(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    assert client.get("/entitlements").status_code == 401


def test_basic_authenticated_user_is_not_entitled(tmp_path: Path) -> None:
    client, service = _client(tmp_path)
    hdr = _login(client, service, "basic@e.com")
    ent = client.get("/entitlements", headers=hdr).json()
    assert ent["enterprise"] is False and ent["entitlements"] == [] and ent["plan"] == "free"
    # ...and the enterprise surface itself refuses them (403, not 401 — they ARE authed).
    assert client.get("/enterprise/summary", headers=hdr).status_code == 403


def test_anonymous_cannot_reach_enterprise_surface(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    assert client.get("/enterprise/summary").status_code == 401


def test_enterprise_plan_member_is_entitled(tmp_path: Path) -> None:
    client, service = _client(tmp_path)
    hdr = _login(client, service, "ent@e.com")
    # An org on the enterprise plan lifts the member's effective entitlement.
    client.post("/organizations", json={"name": "BigCo", "plan": "enterprise"}, headers=hdr)
    ent = client.get("/entitlements", headers=hdr).json()
    assert ent["enterprise"] is True and "enterprise" in ent["entitlements"]
    summary = client.get("/enterprise/summary", headers=hdr)
    assert summary.status_code == 200
    assert summary.json()["plan"] == "enterprise" and summary.json()["organizations"] == 1


def test_admin_is_entitled_without_a_plan(tmp_path: Path) -> None:
    client, service = _client(tmp_path)
    hdr = _login(client, service, "admin@e.com", role="admin")
    ent = client.get("/entitlements", headers=hdr).json()
    assert ent["enterprise"] is True and ent["role"] == "admin"
    assert client.get("/enterprise/summary", headers=hdr).status_code == 200


# ============================ Scope C — API-key scopes & expiry ============================


def test_api_key_has_no_admin_access_by_default(tmp_path: Path) -> None:
    client, service = _client(tmp_path)
    hdr = _login(client, service, "admin@e.com", role="admin")
    # An admin's DEFAULT key (no scopes) authenticates as the admin for ordinary routes
    # but is NOT authorized for /admin/* — the key is weaker than the session.
    created = client.post("/api-keys", json={"name": "default"}, headers=hdr).json()
    assert created["key"]["scopes"] == []
    key = {"X-API-Key": created["secret"]}
    assert client.get("/auth/me", headers=key).status_code == 200  # identity works
    assert client.get("/admin/customers", headers=key).status_code == 403  # admin does not


def test_api_key_with_admin_scope_reaches_admin(tmp_path: Path) -> None:
    client, service = _client(tmp_path)
    hdr = _login(client, service, "admin@e.com", role="admin")
    created = client.post("/api-keys", json={"name": "ops", "scopes": ["admin"]}, headers=hdr).json()
    key = {"X-API-Key": created["secret"]}
    assert client.get("/admin/customers", headers=key).status_code == 200


def test_analyst_key_cannot_reach_admin_even_with_scope_request(tmp_path: Path) -> None:
    client, service = _client(tmp_path)
    hdr = _login(client, service, "ana@e.com")
    # A non-admin cannot even mint an admin-scoped key.
    assert client.post("/api-keys", json={"name": "x", "scopes": ["admin"]}, headers=hdr).status_code == 403
    # A plain key owned by an analyst is refused admin on the role check.
    created = client.post("/api-keys", json={"name": "plain"}, headers=hdr).json()
    assert client.get("/admin/customers", headers={"X-API-Key": created["secret"]}).status_code == 403


def test_api_key_enterprise_scope_gates_enterprise_route(tmp_path: Path) -> None:
    client, service = _client(tmp_path)
    hdr = _login(client, service, "admin@e.com", role="admin")
    # Admin is entitled, but a key still needs the enterprise scope to use the surface.
    plain = client.post("/api-keys", json={"name": "plain"}, headers=hdr).json()
    assert client.get("/enterprise/summary", headers={"X-API-Key": plain["secret"]}).status_code == 403
    scoped = client.post(
        "/api-keys", json={"name": "ent", "scopes": ["enterprise"]}, headers=hdr
    ).json()
    assert client.get("/enterprise/summary", headers={"X-API-Key": scoped["secret"]}).status_code == 200


def test_unknown_scope_is_rejected(tmp_path: Path) -> None:
    client, service = _client(tmp_path)
    hdr = _login(client, service, "admin@e.com", role="admin")
    resp = client.post("/api-keys", json={"name": "bad", "scopes": ["superuser"]}, headers=hdr)
    assert resp.status_code == 400 and "scope" in resp.json()["detail"].lower()


def test_expired_api_key_is_rejected(tmp_path: Path) -> None:
    # Expiry is enforced at resolve time: an expired key resolves to nobody (401),
    # driven directly through the store so we can plant a past expiry.
    store = SqliteApiKeyStore(f"sqlite:///{tmp_path / 'k.db'}")
    past = (datetime.now(tz=timezone.utc) - timedelta(days=1)).isoformat()
    created = store.create("u@e.com", "old", created_at=past, expires_at=past)
    assert store.resolve_principal(created.secret) is None
    future = (datetime.now(tz=timezone.utc) + timedelta(days=1)).isoformat()
    live = store.create("u@e.com", "live", created_at=past, expires_at=future)
    principal = store.resolve_principal(live.secret)
    assert principal is not None and principal.user_email == "u@e.com"


def test_legacy_keys_deserialize_with_conservative_defaults(tmp_path: Path) -> None:
    # A database created before Phase 7 has no scopes/expires_at columns. Simulate one,
    # then open the store (which migrates in place) and confirm the legacy key resolves
    # with NO scopes and no expiry — never admin.
    db_path = tmp_path / "legacy.db"
    engine = create_engine(f"sqlite:///{db_path}", future=True)
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE api_keys (id VARCHAR PRIMARY KEY, user_email VARCHAR, name VARCHAR, "
                "key_hash VARCHAR, display VARCHAR, created_at VARCHAR)"
            )
        )
        # sha256 of the raw key 'csk_legacy' — matches _hash in the store.
        from hashlib import sha256

        conn.execute(
            text(
                "INSERT INTO api_keys VALUES ('id1', 'legacy@e.com', 'old', :h, 'csk_leg…acy', '2020-01-01')"
            ),
            {"h": sha256(b"csk_legacy").hexdigest()},
        )
    store = SqliteApiKeyStore(f"sqlite:///{db_path}")  # migrates: adds the two columns
    principal = store.resolve_principal("csk_legacy")
    assert principal is not None
    assert principal.user_email == "legacy@e.com"
    assert principal.scopes == frozenset()  # conservative: no admin, no enterprise
    listed = store.list_keys("legacy@e.com")
    assert listed[0].scopes == [] and listed[0].expires_at is None
