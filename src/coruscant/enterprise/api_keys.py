"""API keys for programmatic / third-party access (SQLite).

The raw key is shown once at creation; only its hash is stored. Presented keys are
verified by hashing and looking up the owner.

Keys carry two pieces of least-privilege metadata (Phase 7, Scope C):

* ``scopes`` — the ELEVATED capabilities the key is allowed to exercise. The vocabulary
  is intentionally tiny: ``admin`` and ``enterprise``. A key with **neither** (the
  default, and what every pre-Phase-7 key deserializes to) still authenticates as its
  owner for ordinary read/own-data routes, but the sensitive admin/enterprise surfaces
  additionally require the matching scope *and* the owner's role/entitlement — so an
  admin's key cannot reach ``/admin/*`` unless that key was explicitly granted ``admin``.
* ``expires_at`` — an optional ISO-8601 expiry. ``None`` (the default and the legacy
  value) means the key never expires; an expired key resolves to nobody.

Both columns are added to pre-existing databases in-place (``_migrate``), so existing
keys deserialize safely with the conservative defaults above — no admin, no expiry loss.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import secrets

from pydantic import BaseModel, Field
from sqlalchemy import String, create_engine, select, text
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

_PREFIX = "csk_"

# Elevated capabilities a key may carry. Ordinary read/own-data access needs no scope;
# these gate ONLY the sensitive surfaces (see apps/api.py route checks). Keep in sync
# with the frontend scope picker and docs.
SCOPE_ADMIN = "admin"
SCOPE_ENTERPRISE = "enterprise"
KNOWN_SCOPES: frozenset[str] = frozenset({SCOPE_ADMIN, SCOPE_ENTERPRISE})


class Base(DeclarativeBase):
    pass


class ApiKeyRow(Base):
    __tablename__ = "api_keys"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_email: Mapped[str] = mapped_column(String, index=True)
    name: Mapped[str] = mapped_column(String)
    key_hash: Mapped[str] = mapped_column(String, unique=True, index=True)
    display: Mapped[str] = mapped_column(String)  # masked, e.g. csk_ab12…
    created_at: Mapped[str] = mapped_column(String)
    # Added in Phase 7; NULL on legacy rows -> conservative defaults (no scopes, no expiry).
    scopes: Mapped[str | None] = mapped_column(String, nullable=True)
    expires_at: Mapped[str | None] = mapped_column(String, nullable=True)


class ApiKey(BaseModel):
    id: str
    name: str
    display: str
    created_at: str
    scopes: list[str] = Field(default_factory=list)
    expires_at: str | None = None


class ApiKeyCreated(BaseModel):
    key: ApiKey
    secret: str  # shown once


@dataclass
class ApiKeyPrincipal:
    """A resolved, non-expired API key: who owns it and what it may do."""

    user_email: str
    scopes: frozenset[str] = field(default_factory=frozenset)


def _hash(raw: str) -> str:
    return sha256(raw.encode("utf-8")).hexdigest()


def _dump_scopes(scopes: list[str] | frozenset[str] | None) -> str:
    return json.dumps(sorted(set(scopes or ())))


def _load_scopes(raw: str | None) -> frozenset[str]:
    if not raw:
        return frozenset()
    try:
        values = json.loads(raw)
    except (ValueError, TypeError):
        return frozenset()
    return frozenset(str(v) for v in values) if isinstance(values, list) else frozenset()


def _is_expired(expires_at: str | None) -> bool:
    if not expires_at:
        return False
    try:
        moment = datetime.fromisoformat(expires_at)
    except ValueError:
        return True  # unparseable expiry -> fail closed (treat as expired)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return datetime.now(tz=timezone.utc) >= moment


def _ensure_sqlite_dir(database_url: str) -> None:
    prefix = "sqlite:///"
    if database_url.startswith(prefix):
        path = Path(database_url[len(prefix) :])
        if path.parent and not path.parent.exists():
            path.parent.mkdir(parents=True, exist_ok=True)


class SqliteApiKeyStore:
    def __init__(self, database_url: str = "sqlite:///data/coruscant.db") -> None:
        _ensure_sqlite_dir(database_url)
        self.engine = create_engine(database_url, future=True)
        Base.metadata.create_all(self.engine)
        self._migrate()

    def _migrate(self) -> None:
        """Add the Phase-7 columns to a pre-existing table, in place. SQLite's
        ``create_all`` never alters an existing table, so a database created before
        this phase is missing ``scopes``/``expires_at``; add them idempotently. Rows
        keep NULL, which deserializes to the conservative defaults."""
        with self.engine.begin() as conn:
            existing = {row[1] for row in conn.execute(text("PRAGMA table_info(api_keys)"))}
            if "scopes" not in existing:
                conn.execute(text("ALTER TABLE api_keys ADD COLUMN scopes VARCHAR"))
            if "expires_at" not in existing:
                conn.execute(text("ALTER TABLE api_keys ADD COLUMN expires_at VARCHAR"))

    def create(
        self,
        user_email: str,
        name: str,
        *,
        created_at: str,
        scopes: list[str] | None = None,
        expires_at: str | None = None,
    ) -> ApiKeyCreated:
        # Default to NO elevated scopes — a key never inherits admin/enterprise access
        # implicitly. Unknown scopes are dropped (validated at the route for a 400).
        granted = sorted(set(scopes or ()) & KNOWN_SCOPES)
        raw = _PREFIX + secrets.token_urlsafe(24)
        display = f"{raw[:10]}…{raw[-4:]}"
        key = ApiKey(
            id=secrets.token_hex(8),
            name=name,
            display=display,
            created_at=created_at,
            scopes=granted,
            expires_at=expires_at,
        )
        with Session(self.engine) as session:
            session.add(
                ApiKeyRow(
                    id=key.id,
                    user_email=user_email,
                    name=name,
                    key_hash=_hash(raw),
                    display=display,
                    created_at=created_at,
                    scopes=_dump_scopes(granted),
                    expires_at=expires_at,
                )
            )
            session.commit()
        return ApiKeyCreated(key=key, secret=raw)

    def resolve_principal(self, raw: str) -> ApiKeyPrincipal | None:
        """The owner + scopes for a presented raw key, or None when it is unknown or
        expired. This is the authority-bearing resolve; prefer it over :meth:`resolve`."""
        if not raw.startswith(_PREFIX):
            return None
        with Session(self.engine) as session:
            row = session.scalars(
                select(ApiKeyRow).where(ApiKeyRow.key_hash == _hash(raw))
            ).first()
            if row is None or _is_expired(row.expires_at):
                return None
            return ApiKeyPrincipal(user_email=row.user_email, scopes=_load_scopes(row.scopes))

    def resolve(self, raw: str) -> str | None:
        """Return the owner email for a presented raw key, or None (expiry-aware)."""
        principal = self.resolve_principal(raw)
        return principal.user_email if principal else None

    def list_keys(self, user_email: str) -> list[ApiKey]:
        with Session(self.engine) as session:
            rows = session.scalars(
                select(ApiKeyRow).where(ApiKeyRow.user_email == user_email).order_by(ApiKeyRow.created_at)
            ).all()
            return [
                ApiKey(
                    id=r.id,
                    name=r.name,
                    display=r.display,
                    created_at=r.created_at,
                    scopes=sorted(_load_scopes(r.scopes)),
                    expires_at=r.expires_at,
                )
                for r in rows
            ]

    def revoke(self, user_email: str, key_id: str) -> bool:
        with Session(self.engine) as session:
            row = session.get(ApiKeyRow, key_id)
            if row is None or row.user_email != user_email:
                return False
            session.delete(row)
            session.commit()
            return True
