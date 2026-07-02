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
from fastapi.routing import APIRoute
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


# ---- Closed-world guards on the auth boundary ------------------------------------
#
# The tests above spot-check a curated list. These two assert a CLOSED WORLD over the
# actual route table, so accidental over-exposure (a new `dependencies=public` route,
# or a route with NO auth gate at all) fails CI instead of shipping silently. They are
# the automated backstop for the manual "keep this in sync" note above.

# Paths intentionally reachable with no auth gate: liveness/readiness and the
# unauthenticated auth endpoints themselves. Everything else MUST carry a gate.
OPEN_ROUTES = {
    "/health",
    "/livez",
    "/readyz",
    "/version",
    "/auth/register",
    "/auth/login",
    "/auth/logout",
    "/auth/reset/request",
    "/auth/reset/confirm",
}

# The COMPLETE anonymous public-read surface — every (method, path) reachable through
# the `public_read` gate. This set IS the public boundary: making a route public (or
# un-publishing one) must be a conscious edit here, or the drift guard below fails.
EXPECTED_PUBLIC_ROUTES = {
    ("POST", "/retrieve"),
    ("GET", "/answer"),
    ("GET", "/companies"),
    ("GET", "/sources"),
    ("GET", "/documents"),
    ("GET", "/documents/{canonical_id}"),
    ("GET", "/documents/{canonical_id}/summary"),
    ("GET", "/compare"),
    ("GET", "/entities"),
    ("GET", "/entities/{kind}/{key}"),
    ("GET", "/dashboard"),
    ("GET", "/companies/{slug}/timeline"),
    ("GET", "/companies/{slug}/changes"),
    ("GET", "/graph/company/{slug}"),
    ("GET", "/graph/company-network"),
    ("GET", "/graph/company/{company_key}/owners"),
    ("GET", "/graph/company/{company_key}/ownership-chain"),
    ("GET", "/graph/company/{company_key}/contagion"),
    ("GET", "/graph/co-executives"),
    ("GET", "/graph/screening"),
    ("GET", "/graph/resolution"),
    ("GET", "/graph/coverage"),
    ("GET", "/graph/exposure"),
    ("GET", "/graph/ownership"),
}

# The auth-gate dependency callables. A route is "gated" iff one of these is reachable
# from its dependant tree. (anon_rate_limit throttles but does NOT authenticate, so it
# is deliberately excluded — auth routes carry it yet remain in OPEN_ROUTES.)
_AUTH_GATES = {"require_user", "public_read", "require_admin"}


def _api_routes(app: object) -> list[APIRoute]:
    # Version-robust: routes appear either flattened (APIRoute with `.path`) or, on
    # Starlette 1.x, under an `_IncludedRouter` wrapper exposing `.original_router`.
    routes: list[APIRoute] = []
    for r in getattr(app, "routes", []):
        if isinstance(r, APIRoute):
            routes.append(r)
        elif hasattr(r, "original_router"):
            routes.extend(s for s in r.original_router.routes if isinstance(s, APIRoute))
    return routes


def _gate_names(route: APIRoute) -> set[str]:
    names: set[str] = set()
    stack = list(route.dependant.dependencies)
    while stack:
        dep = stack.pop()
        name = getattr(dep.call, "__name__", "")
        if name:
            names.add(name)
        stack.extend(dep.dependencies)
    return names


def test_every_route_is_gated_or_explicitly_open(tmp_path: Path) -> None:
    app = _client(tmp_path).app
    routes = _api_routes(app)
    assert routes, "route introspection found no APIRoutes — the FastAPI wrapper changed"
    unguarded = sorted(
        {
            route.path
            for route in routes
            if not (_AUTH_GATES & _gate_names(route)) and route.path not in OPEN_ROUTES
        }
    )
    assert not unguarded, (
        "these routes carry no auth gate — add require_user/public_read/require_admin, "
        f"or add the path to OPEN_ROUTES if it is intentionally open: {unguarded}"
    )


def test_public_read_surface_matches_the_allow_list(tmp_path: Path) -> None:
    app = _client(tmp_path).app
    actual = {
        (method, route.path)
        for route in _api_routes(app)
        if "public_read" in _gate_names(route)
        for method in route.methods - {"HEAD", "OPTIONS"}
    }
    assert actual == EXPECTED_PUBLIC_ROUTES, (
        f"public surface drifted — newly exposed: {sorted(actual - EXPECTED_PUBLIC_ROUTES)}; "
        f"no longer public: {sorted(EXPECTED_PUBLIC_ROUTES - actual)}"
    )


def test_auth_endpoints_are_rate_limited(tmp_path: Path, monkeypatch) -> None:
    # Unauthenticated auth endpoints are PBKDF2-heavy; a per-IP fixed window blunts
    # brute-force and CPU-amplification. Bad credentials still 401 until the window
    # fills, then further attempts are throttled with 429.
    from coruscant.apps import api as api_module

    settings = api_module.get_settings()
    monkeypatch.setattr(settings, "auth_rate_limit", 3)
    client = _client(tmp_path)
    statuses = [
        client.post(
            "/auth/login", json={"email": "nobody@example.com", "password": "password123"}
        ).status_code
        for _ in range(5)
    ]
    assert statuses.count(401) == 3  # first three attempts reach the (failing) login
    assert statuses.count(429) == 2  # the 4th and 5th are throttled before hashing
