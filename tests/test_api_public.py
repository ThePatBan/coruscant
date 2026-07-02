"""Phase 6 — public launch readiness: the unauthenticated read surface.

Guards the promise that Public is truly public: an anonymous visitor can browse the
curated discovery surface (entity search, profiles, relationships, timelines,
evidence) with no forced sign-in, while user-owned/write/admin routes stay locked;
the open surface is rate-limited; and go-live health/readiness/config-safety hold.
"""

from __future__ import annotations

from pathlib import Path

from coruscant.apps.api import create_app
from coruscant.auth.service import AuthService
from coruscant.auth.store import SqliteUserStore
from coruscant.common.config import Settings
from fastapi.testclient import TestClient


def _client(tmp_path: Path, **kwargs: object) -> TestClient:
    service = AuthService(
        SqliteUserStore(f"sqlite:///{tmp_path / 'u.db'}"), secret="s", token_ttl_seconds=3600
    )
    return TestClient(create_app(auth_service=service, require_auth=True, **kwargs))


# Every route an anonymous visitor is allowed to read (mirrors the PUBLIC_READ
# allow-list in apps/api.py). If a route is added/removed there, update this too.
PUBLIC_GET_ROUTES = [
    "/health",
    "/livez",
    "/version",
    "/companies",
    "/sources",
    "/documents",
    "/entities",
    "/graph/co-executives",
    "/graph/screening",
    "/graph/resolution",
    "/graph/ownership",
    "/graph/coverage",
    "/dashboard",
    "/companies/apple/timeline",
    "/companies/apple/changes",
    "/graph/company/apple",
    "/graph/company-network?company=apple",
    "/graph/exposure?country=US",
]

# User-owned, write, admin, or costly-LLM routes that MUST stay authenticated.
PROTECTED_ROUTES = [
    "/portfolios",
    "/watchlists",
    "/saved-searches",
    "/workspaces",
    "/api-keys",
    "/organizations",
    "/quota",
    "/usage",
    "/notifications",
    "/monitoring",
    "/admin/customers",
    "/signals/apple",
]


def test_public_read_surface_is_open_unauthenticated(tmp_path: Path) -> None:
    client = _client(tmp_path)
    for route in PUBLIC_GET_ROUTES:
        resp = client.get(route)
        assert resp.status_code == 200, f"{route} should be public, got {resp.status_code}"


def test_retrieve_is_public_and_evidence_backed(tmp_path: Path) -> None:
    client = _client(tmp_path)
    resp = client.post("/retrieve", json={"query": "market", "top_k": 3})
    assert resp.status_code == 200
    body = resp.json()
    assert "results" in body and "answer" in body  # evidence-shaped, no auth needed


def test_private_routes_still_require_auth(tmp_path: Path) -> None:
    client = _client(tmp_path)
    for route in PROTECTED_ROUTES:
        assert client.get(route).status_code == 401, f"{route} must require auth"
    # A bogus bearer token is treated as anonymous, not a valid session.
    assert client.get("/portfolios", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_public_read_can_be_disabled(tmp_path: Path, monkeypatch) -> None:
    # With the public surface off, discovery re-locks to authenticated-only — the
    # single flag flips behaviour with no per-route changes.
    from coruscant.apps import api as api_module

    settings = api_module.get_settings()
    monkeypatch.setattr(settings, "public_read", False)
    client = _client(tmp_path)
    assert client.get("/companies").status_code == 401
    assert client.get("/health").status_code == 200  # health is never gated


def test_public_surface_is_rate_limited(tmp_path: Path, monkeypatch) -> None:
    from coruscant.apps import api as api_module

    settings = api_module.get_settings()
    monkeypatch.setattr(settings, "public_read_rate_limit", 3)
    client = _client(tmp_path)
    statuses = [client.get("/companies").status_code for _ in range(5)]
    assert statuses.count(200) == 3
    assert statuses.count(429) == 2  # the 4th and 5th anonymous hits are throttled


def test_authenticated_calls_bypass_the_anonymous_rate_limit(tmp_path: Path, monkeypatch) -> None:
    from coruscant.apps import api as api_module

    settings = api_module.get_settings()
    monkeypatch.setattr(settings, "public_read_rate_limit", 2)
    service = AuthService(
        SqliteUserStore(f"sqlite:///{tmp_path / 'u.db'}"), secret="s", token_ttl_seconds=3600
    )
    client = TestClient(create_app(auth_service=service, require_auth=True))
    token = client.post(
        "/auth/register", json={"email": "a@b.com", "password": "password123"}
    ).json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    # Well past the anonymous limit of 2 — signed-in callers are never throttled here.
    for _ in range(6):
        assert client.get("/companies", headers=headers).status_code == 200


def test_readyz_reports_ready_when_dependencies_answer(tmp_path: Path) -> None:
    client = _client(tmp_path)
    resp = client.get("/readyz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ready"
    assert body["checks"]["graph"] and body["checks"]["corpus"] and body["checks"]["auth"]


def test_config_warnings_flag_unsafe_defaults() -> None:
    unsafe = Settings(cors_origins=["*"], secret_key="", expose_reset_token=True)
    warnings = unsafe.config_warnings()
    assert any("CORS" in w for w in warnings)
    assert any("SECRET_KEY" in w for w in warnings)
    # A locked-down config is launch-safe (no warnings).
    safe = Settings(cors_origins=["https://app.example.com"], secret_key="a-strong-secret")
    assert safe.config_warnings() == []


def test_production_fails_closed_on_unsafe_config() -> None:
    unsafe = Settings(production=True, cors_origins=["*"], secret_key="")
    try:
        unsafe.ensure_launch_safe()
    except RuntimeError as exc:
        assert "unsafe production config" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("ensure_launch_safe must raise on unsafe production config")
    # Non-production only warns; it never blocks a boot.
    Settings(production=False, cors_origins=["*"], secret_key="").ensure_launch_safe()
    # A safe production config boots fine.
    Settings(production=True, cors_origins=["https://x"], secret_key="strong").ensure_launch_safe()
