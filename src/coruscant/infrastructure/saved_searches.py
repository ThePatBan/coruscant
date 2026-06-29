"""User-scoped saved searches (SQLite)."""

from __future__ import annotations

from pathlib import Path
import secrets

from pydantic import BaseModel
from sqlalchemy import String, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column


class Base(DeclarativeBase):
    pass


class SavedSearchRow(Base):
    __tablename__ = "saved_searches"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_email: Mapped[str] = mapped_column(String, index=True)
    name: Mapped[str] = mapped_column(String)
    query: Mapped[str] = mapped_column(String)
    source_type: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[str] = mapped_column(String)


class SavedSearch(BaseModel):
    id: str
    name: str
    query: str
    source_type: str | None = None
    created_at: str


def _ensure_sqlite_dir(database_url: str) -> None:
    prefix = "sqlite:///"
    if database_url.startswith(prefix):
        path = Path(database_url[len(prefix) :])
        if path.parent and not path.parent.exists():
            path.parent.mkdir(parents=True, exist_ok=True)


class SqliteSavedSearchStore:
    def __init__(self, database_url: str = "sqlite:///data/coruscant.db") -> None:
        _ensure_sqlite_dir(database_url)
        self.engine = create_engine(database_url, future=True)
        Base.metadata.create_all(self.engine)

    def create(
        self, user_email: str, name: str, query: str, source_type: str | None, *, created_at: str
    ) -> SavedSearch:
        search = SavedSearch(
            id=secrets.token_hex(8),
            name=name,
            query=query,
            source_type=source_type,
            created_at=created_at,
        )
        with Session(self.engine) as session:
            session.add(
                SavedSearchRow(
                    id=search.id,
                    user_email=user_email,
                    name=name,
                    query=query,
                    source_type=source_type,
                    created_at=created_at,
                )
            )
            session.commit()
        return search

    def list_searches(self, user_email: str) -> list[SavedSearch]:
        statement = (
            select(SavedSearchRow)
            .where(SavedSearchRow.user_email == user_email)
            .order_by(SavedSearchRow.created_at)
        )
        with Session(self.engine) as session:
            return [
                SavedSearch(
                    id=r.id,
                    name=r.name,
                    query=r.query,
                    source_type=r.source_type,
                    created_at=r.created_at,
                )
                for r in session.scalars(statement).all()
            ]

    def delete(self, user_email: str, search_id: str) -> bool:
        with Session(self.engine) as session:
            row = session.get(SavedSearchRow, search_id)
            if row is None or row.user_email != user_email:
                return False
            session.delete(row)
            session.commit()
            return True
