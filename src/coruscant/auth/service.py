"""Authentication service: registration, login, token issuance, password reset."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
import time

from coruscant.auth.security import (
    TokenError,
    create_token,
    decode_token,
    hash_password,
    new_reset_token,
    verify_password,
)
from coruscant.auth.store import SqliteUserStore, StoredUser, UserExistsError

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD_LENGTH = 8


class AuthError(Exception):
    """Invalid credentials or input."""


@dataclass
class AuthService:
    store: SqliteUserStore
    secret: str
    token_ttl_seconds: int = 86_400
    reset_ttl_seconds: int = 3_600

    def register(self, email: str, password: str) -> StoredUser:
        email = _normalize_email(email)
        if not _EMAIL_RE.match(email):
            raise AuthError("invalid email")
        if len(password) < MIN_PASSWORD_LENGTH:
            raise AuthError(f"password must be at least {MIN_PASSWORD_LENGTH} characters")
        try:
            return self.store.create_user(
                email, hash_password(password), created_at=_now_iso()
            )
        except UserExistsError as exc:
            raise AuthError("an account with that email already exists") from exc

    def authenticate(self, email: str, password: str) -> str:
        user = self.store.get(_normalize_email(email))
        if user is None or not verify_password(password, user.password_hash):
            raise AuthError("invalid email or password")
        return self.issue_token(user.email)

    def issue_token(self, email: str) -> str:
        return create_token(email, self.secret, ttl_seconds=self.token_ttl_seconds)

    def user_from_token(self, token: str) -> StoredUser | None:
        try:
            payload = decode_token(token, self.secret)
        except TokenError:
            return None
        subject = payload.get("sub")
        if not isinstance(subject, str):
            return None
        return self.store.get(subject)

    def request_reset(self, email: str) -> str | None:
        user = self.store.get(_normalize_email(email))
        if user is None:
            return None
        token = new_reset_token()
        self.store.set_reset(user.email, token, int(time.time()) + self.reset_ttl_seconds)
        return token

    def confirm_reset(self, token: str, new_password: str) -> bool:
        if len(new_password) < MIN_PASSWORD_LENGTH:
            raise AuthError(f"password must be at least {MIN_PASSWORD_LENGTH} characters")
        user = self.store.get_by_reset_token(token)
        if user is None or user.reset_expires is None or int(time.time()) >= user.reset_expires:
            return False
        self.store.set_password(user.email, hash_password(new_password))
        return True


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()
