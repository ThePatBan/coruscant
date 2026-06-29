"""Dead-letter store for ingestion failures.

Every ingestion failure that exhausts its retries is recorded here (durably, in
the platform DB) so failures are observable and replayable rather than lost. The
orchestrator writes entries; the API/CLI read them.
"""

from __future__ import annotations

from pathlib import Path
import secrets

from pydantic import BaseModel
from sqlalchemy import Integer, String, Text, create_engine, func, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column


class Base(DeclarativeBase):
    pass


class DeadLetterRow(Base):
    __tablename__ = "dead_letters"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    company_slug: Mapped[str] = mapped_column(String, index=True)
    source_type: Mapped[str] = mapped_column(String, index=True)
    period: Mapped[str] = mapped_column(String)
    attempts: Mapped[int] = mapped_column(Integer)
    error: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String, index=True)


class DeadLetterEntry(BaseModel):
    id: str
    company_slug: str
    source_type: str
    period: str
    attempts: int
    error: str
    created_at: str


def _ensure_sqlite_dir(database_url: str) -> None:
    prefix = "sqlite:///"
    if database_url.startswith(prefix):
        path = Path(database_url[len(prefix) :])
        if path.parent and not path.parent.exists():
            path.parent.mkdir(parents=True, exist_ok=True)


class SqliteDeadLetterStore:
    def __init__(self, database_url: str = "sqlite:///data/coruscant.db") -> None:
        _ensure_sqlite_dir(database_url)
        self.engine = create_engine(database_url, future=True)
        Base.metadata.create_all(self.engine)

    def record(
        self,
        *,
        company_slug: str,
        source_type: str,
        period: str,
        attempts: int,
        error: str,
        created_at: str,
    ) -> None:
        with Session(self.engine) as session:
            session.add(
                DeadLetterRow(
                    id=secrets.token_hex(8),
                    company_slug=company_slug,
                    source_type=source_type,
                    period=period,
                    attempts=attempts,
                    error=error,
                    created_at=created_at,
                )
            )
            session.commit()

    def list_entries(self, *, limit: int = 200) -> list[DeadLetterEntry]:
        statement = select(DeadLetterRow).order_by(DeadLetterRow.created_at.desc()).limit(max(1, limit))
        with Session(self.engine) as session:
            return [
                DeadLetterEntry(
                    id=r.id,
                    company_slug=r.company_slug,
                    source_type=r.source_type,
                    period=r.period,
                    attempts=r.attempts,
                    error=r.error,
                    created_at=r.created_at,
                )
                for r in session.scalars(statement).all()
            ]

    def count(self) -> int:
        with Session(self.engine) as session:
            return int(session.scalar(select(func.count()).select_from(DeadLetterRow)) or 0)
