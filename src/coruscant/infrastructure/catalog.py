"""SQLite-backed catalog of normalized documents.

Filesystem repositories keep immutable raw and normalized artifacts; this catalog
is the queryable index the API and CLI read from. It stores indexed metadata
columns plus the full normalized document payload so a document can be rebuilt
without touching the filesystem. Backed by SQLAlchemy so the same code targets
SQLite today and PostgreSQL later by changing ``database_url``.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import String, Text, create_engine, func, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from coruscant.common.types import NormalizedDocument


class Base(DeclarativeBase):
    pass


class DocumentRecord(Base):
    __tablename__ = "documents"

    canonical_id: Mapped[str] = mapped_column(String, primary_key=True)
    company_slug: Mapped[str] = mapped_column(String, index=True)
    source_type: Mapped[str] = mapped_column(String, index=True)
    document_type: Mapped[str] = mapped_column(String, index=True)
    title: Mapped[str | None] = mapped_column(String, nullable=True)
    source_uri: Mapped[str] = mapped_column(String)
    published_at: Mapped[str | None] = mapped_column(String, nullable=True)
    payload: Mapped[str] = mapped_column(Text)


def _ensure_sqlite_dir(database_url: str) -> None:
    prefix = "sqlite:///"
    if database_url.startswith(prefix):
        path = Path(database_url[len(prefix) :])
        if path.parent and not path.parent.exists():
            path.parent.mkdir(parents=True, exist_ok=True)


class SqliteDocumentCatalog:
    def __init__(self, database_url: str = "sqlite:///data/coruscant.db") -> None:
        _ensure_sqlite_dir(database_url)
        self.engine = create_engine(database_url, future=True)
        Base.metadata.create_all(self.engine)

    def upsert(self, document: NormalizedDocument, *, company_slug: str, source_type: str) -> None:
        record = DocumentRecord(
            canonical_id=document.canonical_id,
            company_slug=company_slug,
            source_type=source_type,
            document_type=document.document_type,
            title=document.title,
            source_uri=document.source_uri,
            published_at=str(document.published_at) if document.published_at is not None else None,
            payload=document.model_dump_json(),
        )
        with Session(self.engine) as session:
            session.merge(record)
            session.commit()

    def get(self, canonical_id: str) -> NormalizedDocument | None:
        with Session(self.engine) as session:
            record = session.get(DocumentRecord, canonical_id)
            if record is None:
                return None
            return NormalizedDocument.model_validate_json(record.payload)

    def list_documents(
        self, *, company_slug: str | None = None, source_type: str | None = None
    ) -> list[NormalizedDocument]:
        statement = select(DocumentRecord)
        if company_slug is not None:
            statement = statement.where(DocumentRecord.company_slug == company_slug)
        if source_type is not None:
            statement = statement.where(DocumentRecord.source_type == source_type)
        statement = statement.order_by(DocumentRecord.company_slug, DocumentRecord.source_type)
        with Session(self.engine) as session:
            records = session.scalars(statement).all()
            return [NormalizedDocument.model_validate_json(record.payload) for record in records]

    def companies(self) -> list[str]:
        statement = select(DocumentRecord.company_slug).distinct().order_by(DocumentRecord.company_slug)
        with Session(self.engine) as session:
            return list(session.scalars(statement).all())

    def count(self) -> int:
        with Session(self.engine) as session:
            total = session.scalar(select(func.count()).select_from(DocumentRecord))
            return int(total or 0)
