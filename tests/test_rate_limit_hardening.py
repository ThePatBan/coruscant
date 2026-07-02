"""Phase 7, Scope D — rate-limit deployment hardening.

Proves: (1) the client-IP for rate limiting trusts X-Forwarded-For ONLY when explicitly
configured — an untrusted deployment cannot be bypassed by spoofing the header, a
trusted one partitions per forwarded IP; (2) the limiter abstraction seam selects the
in-process backend by default and fails closed on an unimplemented one; (3) config
surfaces an unsafe open-surface-without-limit and documents the active trust posture.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from coruscant.apps.api import create_app
from coruscant.apps.ratelimit import (
    InProcessFixedWindowRateLimiter,
    build_rate_limiter,
)
from coruscant.auth.service import AuthService
from coruscant.auth.store import SqliteUserStore
from coruscant.common.config import Settings


def _client(tmp_path: Path) -> TestClient:
    service = AuthService(
        SqliteUserStore(f"sqlite:///{tmp_path / 'u.db'}"), secret="s", token_ttl_seconds=3600
    )
    return TestClient(create_app(auth_service=service, require_auth=True))


# ---- Trusted vs untrusted forwarded headers ---------------------------------------


def test_untrusted_forwarded_header_cannot_bypass_the_limit(tmp_path: Path, monkeypatch) -> None:
    from coruscant.apps import api as api_module

    settings = api_module.get_settings()
    monkeypatch.setattr(settings, "public_read_rate_limit", 3)
    monkeypatch.setattr(settings, "trust_forwarded_for", False)  # default posture
    client = _client(tmp_path)
    # Every request forges a DIFFERENT X-Forwarded-For. Because the header is not
    # trusted, all collapse onto the socket peer's single bucket — spoofing buys nothing.
    statuses = [
        client.get("/companies", headers={"X-Forwarded-For": f"9.9.9.{i}"}).status_code
        for i in range(5)
    ]
    assert statuses.count(200) == 3 and statuses.count(429) == 2


def test_trusted_forwarded_header_partitions_per_client(tmp_path: Path, monkeypatch) -> None:
    from coruscant.apps import api as api_module

    settings = api_module.get_settings()
    monkeypatch.setattr(settings, "public_read_rate_limit", 2)
    monkeypatch.setattr(settings, "trust_forwarded_for", True)
    client = _client(tmp_path)
    a = {"X-Forwarded-For": "10.0.0.1"}
    b = {"X-Forwarded-For": "10.0.0.2"}
    # Client A burns its budget...
    assert [client.get("/companies", headers=a).status_code for _ in range(3)] == [200, 200, 429]
    # ...but client B has its own untouched bucket.
    assert client.get("/companies", headers=b).status_code == 200


# ---- The limiter abstraction seam -------------------------------------------------


def test_build_rate_limiter_defaults_to_in_process() -> None:
    limiter = build_rate_limiter(5)
    assert isinstance(limiter, InProcessFixedWindowRateLimiter)


def test_build_rate_limiter_fails_closed_on_unimplemented_backend() -> None:
    with pytest.raises(ValueError, match="rate-limit backend"):
        build_rate_limiter(5, backend="redis")


def test_in_process_limiter_enforces_the_window() -> None:
    limiter = InProcessFixedWindowRateLimiter(2)
    assert [limiter.allow("k") for _ in range(3)] == [True, True, False]
    assert limiter.allow("other") is True  # distinct keys are independent
    # A non-positive limit disables limiting entirely.
    assert all(InProcessFixedWindowRateLimiter(0).allow("k") for _ in range(10))


# ---- Config safety / posture ------------------------------------------------------


def test_open_surface_without_limit_is_flagged_and_fatal_in_production() -> None:
    unsafe = Settings(
        public_read=True, public_read_rate_limit=0, cors_origins=["https://x"], secret_key="strong"
    )
    assert any("RATE_LIMIT" in w or "anti-abuse" in w for w in unsafe.config_warnings())
    with pytest.raises(RuntimeError, match="unsafe production config"):
        Settings(
            production=True,
            public_read=True,
            public_read_rate_limit=0,
            cors_origins=["https://x"],
            secret_key="strong",
        ).ensure_launch_safe()
    # A positive limit is safe — the default production config still boots.
    Settings(production=True, cors_origins=["https://x"], secret_key="strong").ensure_launch_safe()


def test_client_ip_notes_document_the_trust_mode() -> None:
    on = Settings(trust_forwarded_for=True).client_ip_notes()
    assert any("X-Forwarded-For" in n for n in on)
    off = Settings(trust_forwarded_for=False).client_ip_notes()
    assert any("socket peer" in n for n in off)
