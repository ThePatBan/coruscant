"""Append-only audit log (SQLite)."""

from __future__ import annotations

from pathlib import Path
import secrets

from pydantic import BaseModel
from sqlalchemy import String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column


class Base(DeclarativeBase):
    pass


class AuditRow(Base):
    __tablename__ = "audit_log"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_email: Mapped[str] = mapped_column(String, index=True)
    action: Mapped[str] = mapped_column(String, index=True)
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[str] = mapped_column(String, index=True)


class AuditEntry(BaseModel):
    id: str
    user_email: str
    action: str
    detail: str = ""
    created_at: str


def _ensure_sqlite_dir(database_url: str) -> None:
    prefix = "sqlite:///"
    if database_url.startswith(prefix):
        path = Path(database_url[len(prefix) :])
        if path.parent and not path.parent.exists():
            path.parent.mkdir(parents=True, exist_ok=True)


class SqliteAuditStore:
    def __init__(self, database_url: str = "sqlite:///data/coruscant.db") -> None:
        _ensure_sqlite_dir(database_url)
        self.engine = create_engine(database_url, future=True)
        Base.metadata.create_all(self.engine)

    def record(self, user_email: str, action: str, detail: str, *, created_at: str) -> None:
        with Session(self.engine) as session:
            session.add(
                AuditRow(
                    id=secrets.token_hex(8),
                    user_email=user_email,
                    action=action,
                    detail=detail,
                    created_at=created_at,
                )
            )
            session.commit()

    def list_entries(self, *, limit: int = 200) -> list[AuditEntry]:
        statement = select(AuditRow).order_by(AuditRow.created_at.desc()).limit(max(1, limit))
        with Session(self.engine) as session:
            return [
                AuditEntry(
                    id=r.id,
                    user_email=r.user_email,
                    action=r.action,
                    detail=r.detail,
                    created_at=r.created_at,
                )
                for r in session.scalars(statement).all()
            ]
