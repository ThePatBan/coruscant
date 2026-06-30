"""SQLite-backed user store (shares the platform database)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import Integer, String, create_engine, func, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column


class Base(DeclarativeBase):
    pass


class UserRow(Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String, primary_key=True)
    password_hash: Mapped[str] = mapped_column(String)
    created_at: Mapped[str] = mapped_column(String)
    role: Mapped[str] = mapped_column(String, default="analyst")
    reset_token: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    reset_expires: Mapped[int | None] = mapped_column(Integer, nullable=True)


@dataclass
class StoredUser:
    email: str
    password_hash: str
    created_at: str
    role: str = "analyst"
    reset_token: str | None = None
    reset_expires: int | None = None


class UserExistsError(Exception):
    """Raised when registering an email that already exists."""


def _ensure_sqlite_dir(database_url: str) -> None:
    prefix = "sqlite:///"
    if database_url.startswith(prefix):
        path = Path(database_url[len(prefix) :])
        if path.parent and not path.parent.exists():
            path.parent.mkdir(parents=True, exist_ok=True)


def _to_user(row: UserRow) -> StoredUser:
    return StoredUser(
        email=row.email,
        password_hash=row.password_hash,
        created_at=row.created_at,
        role=row.role,
        reset_token=row.reset_token,
        reset_expires=row.reset_expires,
    )


class SqliteUserStore:
    def __init__(self, database_url: str = "sqlite:///data/coruscant.db") -> None:
        _ensure_sqlite_dir(database_url)
        self.engine = create_engine(database_url, future=True)
        Base.metadata.create_all(self.engine)

    def create_user(
        self, email: str, password_hash: str, *, created_at: str, role: str = "analyst"
    ) -> StoredUser:
        with Session(self.engine) as session:
            if session.get(UserRow, email) is not None:
                raise UserExistsError(email)
            row = UserRow(email=email, password_hash=password_hash, created_at=created_at, role=role)
            session.add(row)
            session.commit()
            return _to_user(row)

    def get(self, email: str) -> StoredUser | None:
        with Session(self.engine) as session:
            row = session.get(UserRow, email)
            return _to_user(row) if row else None

    def set_password(self, email: str, password_hash: str) -> None:
        with Session(self.engine) as session:
            row = session.get(UserRow, email)
            if row is None:
                return
            row.password_hash = password_hash
            row.reset_token = None
            row.reset_expires = None
            session.commit()

    def set_reset(self, email: str, token: str, expires: int) -> None:
        with Session(self.engine) as session:
            row = session.get(UserRow, email)
            if row is None:
                return
            row.reset_token = token
            row.reset_expires = expires
            session.commit()

    def get_by_reset_token(self, token: str) -> StoredUser | None:
        with Session(self.engine) as session:
            row = session.scalars(select(UserRow).where(UserRow.reset_token == token)).first()
            return _to_user(row) if row else None

    def count(self) -> int:
        with Session(self.engine) as session:
            total = session.scalar(select(func.count()).select_from(UserRow))
            return int(total or 0)

    def list_users(self) -> list[StoredUser]:
        with Session(self.engine) as session:
            rows = session.scalars(select(UserRow).order_by(UserRow.created_at)).all()
            return [_to_user(row) for row in rows]
