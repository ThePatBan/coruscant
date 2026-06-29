"""SQLite persistence for intelligence outputs (summaries, events, change sets).

Shares the same ``database_url`` as the document catalog (a separate set of
tables in the same file) so the API can serve AI-derived intelligence without
re-running the pipeline. Payloads are stored as JSON; indexed columns support the
dashboard and company queries.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import Integer, String, Text, create_engine, delete, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from coruscant.intelligence.models import ChangeSet, DocumentSummary, ExtractedEvent


class Base(DeclarativeBase):
    pass


class SummaryRecord(Base):
    __tablename__ = "summaries"

    canonical_id: Mapped[str] = mapped_column(String, primary_key=True)
    company_slug: Mapped[str] = mapped_column(String, index=True)
    source_type: Mapped[str] = mapped_column(String, index=True)
    payload: Mapped[str] = mapped_column(Text)


class EventRecord(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    canonical_id: Mapped[str] = mapped_column(String, index=True)
    company_slug: Mapped[str] = mapped_column(String, index=True)
    category: Mapped[str] = mapped_column(String, index=True)
    occurred_at: Mapped[str | None] = mapped_column(String, nullable=True)
    payload: Mapped[str] = mapped_column(Text)


class ChangeSetRecord(Base):
    __tablename__ = "change_sets"

    current_canonical_id: Mapped[str] = mapped_column(String, primary_key=True)
    company_slug: Mapped[str] = mapped_column(String, index=True)
    source_type: Mapped[str] = mapped_column(String, index=True)
    payload: Mapped[str] = mapped_column(Text)


def _ensure_sqlite_dir(database_url: str) -> None:
    prefix = "sqlite:///"
    if database_url.startswith(prefix):
        path = Path(database_url[len(prefix) :])
        if path.parent and not path.parent.exists():
            path.parent.mkdir(parents=True, exist_ok=True)


class SqliteIntelligenceStore:
    def __init__(self, database_url: str = "sqlite:///data/coruscant.db") -> None:
        _ensure_sqlite_dir(database_url)
        self.engine = create_engine(database_url, future=True)
        Base.metadata.create_all(self.engine)

    # -- summaries -------------------------------------------------------------

    def save_summary(self, summary: DocumentSummary) -> None:
        with Session(self.engine) as session:
            session.merge(
                SummaryRecord(
                    canonical_id=summary.canonical_id,
                    company_slug=summary.company_slug,
                    source_type=summary.source_type,
                    payload=summary.model_dump_json(),
                )
            )
            session.commit()

    def get_summary(self, canonical_id: str) -> DocumentSummary | None:
        with Session(self.engine) as session:
            record = session.get(SummaryRecord, canonical_id)
            return DocumentSummary.model_validate_json(record.payload) if record else None

    # -- events ----------------------------------------------------------------

    def replace_events(self, canonical_id: str, events: list[ExtractedEvent]) -> None:
        with Session(self.engine) as session:
            session.execute(delete(EventRecord).where(EventRecord.canonical_id == canonical_id))
            for event in events:
                session.add(
                    EventRecord(
                        canonical_id=event.canonical_id,
                        company_slug=event.company_slug,
                        category=event.category,
                        occurred_at=event.occurred_at,
                        payload=event.model_dump_json(),
                    )
                )
            session.commit()

    def list_events(
        self, *, company_slug: str | None = None, limit: int | None = None
    ) -> list[ExtractedEvent]:
        statement = select(EventRecord)
        if company_slug is not None:
            statement = statement.where(EventRecord.company_slug == company_slug)
        statement = statement.order_by(EventRecord.occurred_at.desc())
        if limit is not None:
            statement = statement.limit(limit)
        with Session(self.engine) as session:
            return [
                ExtractedEvent.model_validate_json(r.payload)
                for r in session.scalars(statement).all()
            ]

    # -- change sets -----------------------------------------------------------

    def save_change_set(self, change_set: ChangeSet) -> None:
        with Session(self.engine) as session:
            session.merge(
                ChangeSetRecord(
                    current_canonical_id=change_set.current_canonical_id,
                    company_slug=change_set.company_slug,
                    source_type=change_set.source_type,
                    payload=change_set.model_dump_json(),
                )
            )
            session.commit()

    def list_change_sets(self, *, company_slug: str | None = None) -> list[ChangeSet]:
        statement = select(ChangeSetRecord)
        if company_slug is not None:
            statement = statement.where(ChangeSetRecord.company_slug == company_slug)
        with Session(self.engine) as session:
            return [
                ChangeSet.model_validate_json(r.payload)
                for r in session.scalars(statement).all()
            ]
