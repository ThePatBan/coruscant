"""API keys for programmatic / third-party access (SQLite).

The raw key is shown once at creation; only its hash is stored. Presented keys
are verified by hashing and looking up the owner.
"""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import secrets

from pydantic import BaseModel
from sqlalchemy import String, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

_PREFIX = "csk_"


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


class ApiKey(BaseModel):
    id: str
    name: str
    display: str
    created_at: str


class ApiKeyCreated(BaseModel):
    key: ApiKey
    secret: str  # shown once


def _hash(raw: str) -> str:
    return sha256(raw.encode("utf-8")).hexdigest()


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

    def create(self, user_email: str, name: str, *, created_at: str) -> ApiKeyCreated:
        raw = _PREFIX + secrets.token_urlsafe(24)
        display = f"{raw[:10]}…{raw[-4:]}"
        key = ApiKey(id=secrets.token_hex(8), name=name, display=display, created_at=created_at)
        with Session(self.engine) as session:
            session.add(
                ApiKeyRow(
                    id=key.id,
                    user_email=user_email,
                    name=name,
                    key_hash=_hash(raw),
                    display=display,
                    created_at=created_at,
                )
            )
            session.commit()
        return ApiKeyCreated(key=key, secret=raw)

    def resolve(self, raw: str) -> str | None:
        """Return the owner email for a presented raw key, or None."""

        if not raw.startswith(_PREFIX):
            return None
        with Session(self.engine) as session:
            row = session.scalars(
                select(ApiKeyRow).where(ApiKeyRow.key_hash == _hash(raw))
            ).first()
            return row.user_email if row else None

    def list_keys(self, user_email: str) -> list[ApiKey]:
        with Session(self.engine) as session:
            rows = session.scalars(
                select(ApiKeyRow).where(ApiKeyRow.user_email == user_email).order_by(ApiKeyRow.created_at)
            ).all()
            return [
                ApiKey(id=r.id, name=r.name, display=r.display, created_at=r.created_at) for r in rows
            ]

    def revoke(self, user_email: str, key_id: str) -> bool:
        with Session(self.engine) as session:
            row = session.get(ApiKeyRow, key_id)
            if row is None or row.user_email != user_email:
                return False
            session.delete(row)
            session.commit()
            return True
