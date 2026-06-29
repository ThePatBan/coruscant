"""Password hashing (PBKDF2-SHA256) and HS256 signed tokens, stdlib only."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time

_PBKDF2_ITERATIONS = 240_000
_PBKDF2_ALGO = "pbkdf2_sha256"


class TokenError(Exception):
    """Raised when a token is malformed, tampered with, or expired."""


# ---- Password hashing ------------------------------------------------------


def hash_password(password: str, *, iterations: int = _PBKDF2_ITERATIONS) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"{_PBKDF2_ALGO}${iterations}${_b64encode(salt)}${_b64encode(digest)}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algo, iter_str, salt_b64, hash_b64 = encoded.split("$")
        if algo != _PBKDF2_ALGO:
            return False
        iterations = int(iter_str)
        salt = _b64decode(salt_b64)
        expected = _b64decode(hash_b64)
    except (ValueError, TypeError):
        return False
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(candidate, expected)


# ---- Signed tokens (compact JWT, HS256) ------------------------------------


def create_token(subject: str, secret: str, *, ttl_seconds: int, now: int | None = None) -> str:
    issued = now if now is not None else int(time.time())
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {"sub": subject, "iat": issued, "exp": issued + ttl_seconds}
    header_segment = _b64encode(json.dumps(header, separators=(",", ":")).encode())
    payload_segment = _b64encode(json.dumps(payload, separators=(",", ":")).encode())
    signing_input = f"{header_segment}.{payload_segment}".encode()
    signature = _b64encode(hmac.new(secret.encode(), signing_input, hashlib.sha256).digest())
    return f"{header_segment}.{payload_segment}.{signature}"


def decode_token(token: str, secret: str, *, now: int | None = None) -> dict[str, object]:
    try:
        header_segment, payload_segment, signature = token.split(".")
    except ValueError as exc:
        raise TokenError("malformed token") from exc
    signing_input = f"{header_segment}.{payload_segment}".encode()
    expected = _b64encode(hmac.new(secret.encode(), signing_input, hashlib.sha256).digest())
    if not hmac.compare_digest(expected, signature):
        raise TokenError("bad signature")
    try:
        payload = json.loads(_b64decode(payload_segment))
    except (ValueError, TypeError) as exc:
        raise TokenError("malformed payload") from exc
    expiry = payload.get("exp")
    current = now if now is not None else int(time.time())
    if not isinstance(expiry, int) or current >= expiry:
        raise TokenError("expired token")
    return payload  # type: ignore[no-any-return]


def new_reset_token() -> str:
    return secrets.token_urlsafe(24)


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)
