from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from coruscant.apps.api import create_app
from coruscant.auth.security import (
    TokenError,
    create_token,
    decode_token,
    hash_password,
    verify_password,
)
from coruscant.auth.service import AuthError, AuthService
from coruscant.auth.store import SqliteUserStore


# ---- security primitives ---------------------------------------------------


def test_password_hash_roundtrip() -> None:
    encoded = hash_password("correct horse battery staple")
    assert encoded != "correct horse battery staple"
    assert verify_password("correct horse battery staple", encoded)
    assert not verify_password("wrong", encoded)


def test_token_roundtrip_and_expiry() -> None:
    token = create_token("a@b.com", "secret", ttl_seconds=10, now=1000)
    assert decode_token(token, "secret", now=1005)["sub"] == "a@b.com"
    with pytest.raises(TokenError):
        decode_token(token, "secret", now=1011)  # expired
    with pytest.raises(TokenError):
        decode_token(token, "other-secret", now=1005)  # bad signature
    with pytest.raises(TokenError):
        decode_token("not.a.token", "secret", now=1005)


# ---- service ---------------------------------------------------------------


def _service(tmp_path: Path) -> AuthService:
    return AuthService(SqliteUserStore(f"sqlite:///{tmp_path / 'u.db'}"), secret="s", token_ttl_seconds=60)


def test_register_validations(tmp_path: Path) -> None:
    service = _service(tmp_path)
    with pytest.raises(AuthError):
        service.register("not-an-email", "password123")
    with pytest.raises(AuthError):
        service.register("a@b.com", "short")
    service.register("a@b.com", "password123")
    with pytest.raises(AuthError):  # duplicate
        service.register("a@b.com", "password123")


def test_authenticate_and_reset(tmp_path: Path) -> None:
    service = _service(tmp_path)
    service.register("user@example.com", "password123")
    assert service.authenticate("user@example.com", "password123")
    with pytest.raises(AuthError):
        service.authenticate("user@example.com", "nope")
    token = service.request_reset("user@example.com")
    assert token
    assert service.confirm_reset(token, "newpassword1")
    assert service.authenticate("user@example.com", "newpassword1")
    assert not service.confirm_reset("bogus-token", "whatever12")


# ---- API enforcement -------------------------------------------------------


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    service = AuthService(
        SqliteUserStore(f"sqlite:///{tmp_path / 'u.db'}"), secret="s", token_ttl_seconds=3600
    )
    return TestClient(create_app(auth_service=service, require_auth=True))


def test_protected_routes_require_auth(client: TestClient) -> None:
    assert client.get("/companies").status_code == 401
    assert client.get("/dashboard").status_code == 401
    assert client.get("/health").status_code == 200  # health stays public
    assert client.get("/companies", headers={"Authorization": "Bearer garbage"}).status_code == 401


def test_register_login_and_access(client: TestClient) -> None:
    token = client.post(
        "/auth/register", json={"email": "Inv@Example.com", "password": "password123"}
    ).json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    assert client.get("/companies", headers=headers).status_code == 200
    assert client.get("/auth/me", headers=headers).json()["email"] == "inv@example.com"

    assert client.post("/auth/login", json={"email": "inv@example.com", "password": "password123"}).status_code == 200
    assert client.post("/auth/login", json={"email": "inv@example.com", "password": "bad"}).status_code == 401
    assert client.post("/auth/logout").json()["ok"] is True


def test_password_reset_flow(client: TestClient) -> None:
    client.post("/auth/register", json={"email": "r@e.com", "password": "password123"})
    issued = client.post("/auth/reset/request", json={"email": "r@e.com"}).json()
    assert issued["reset_token"]
    confirm = client.post(
        "/auth/reset/confirm", json={"token": issued["reset_token"], "password": "brandnew12"}
    )
    assert confirm.json()["ok"] is True
    assert client.post("/auth/login", json={"email": "r@e.com", "password": "brandnew12"}).status_code == 200
