"""Persisted last-successful-run timestamps per source (for the scheduler)."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import String, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column


class Base(DeclarativeBase):
    pass


class ScheduleRow(Base):
    __tablename__ = "schedule_runs"
    source_type: Mapped[str] = mapped_column(String, primary_key=True)
    last_run: Mapped[str] = mapped_column(String)


def _ensure_sqlite_dir(database_url: str) -> None:
    prefix = "sqlite:///"
    if database_url.startswith(prefix):
        path = Path(database_url[len(prefix) :])
        if path.parent and not path.parent.exists():
            path.parent.mkdir(parents=True, exist_ok=True)


class SqliteScheduleStore:
    def __init__(self, database_url: str = "sqlite:///data/coruscant.db") -> None:
        _ensure_sqlite_dir(database_url)
        self.engine = create_engine(database_url, future=True)
        Base.metadata.create_all(self.engine)

    def record_run(self, source_type: str, when_iso: str) -> None:
        with Session(self.engine) as session:
            session.merge(ScheduleRow(source_type=source_type, last_run=when_iso))
            session.commit()

    def last_runs(self) -> dict[str, str]:
        with Session(self.engine) as session:
            return {r.source_type: r.last_run for r in session.scalars(select(ScheduleRow)).all()}
