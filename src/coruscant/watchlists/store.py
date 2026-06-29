"""SQLite-backed watchlist and notification store (shares the platform DB)."""

from __future__ import annotations

from pathlib import Path
import secrets

from sqlalchemy import Boolean, Integer, String, Text, create_engine, delete, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from coruscant.watchlists.models import Notification, Watchlist, WatchItem


class Base(DeclarativeBase):
    pass


class WatchlistRow(Base):
    __tablename__ = "watchlists"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_email: Mapped[str] = mapped_column(String, index=True)
    name: Mapped[str] = mapped_column(String)
    created_at: Mapped[str] = mapped_column(String)


class WatchItemRow(Base):
    __tablename__ = "watch_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    watchlist_id: Mapped[str] = mapped_column(String, index=True)
    type: Mapped[str] = mapped_column(String)
    value: Mapped[str] = mapped_column(String)


class NotificationRow(Base):
    __tablename__ = "notifications"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_email: Mapped[str] = mapped_column(String, index=True)
    watchlist_id: Mapped[str] = mapped_column(String, index=True)
    watch_type: Mapped[str] = mapped_column(String)
    watch_value: Mapped[str] = mapped_column(String)
    kind: Mapped[str] = mapped_column(String)
    title: Mapped[str] = mapped_column(String)
    detail: Mapped[str] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String, nullable=True)
    source_uri: Mapped[str | None] = mapped_column(String, nullable=True)
    canonical_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[str] = mapped_column(String)
    read: Mapped[bool] = mapped_column(Boolean, default=False)


def _ensure_sqlite_dir(database_url: str) -> None:
    prefix = "sqlite:///"
    if database_url.startswith(prefix):
        path = Path(database_url[len(prefix) :])
        if path.parent and not path.parent.exists():
            path.parent.mkdir(parents=True, exist_ok=True)


class SqliteWatchlistStore:
    def __init__(self, database_url: str = "sqlite:///data/coruscant.db") -> None:
        _ensure_sqlite_dir(database_url)
        self.engine = create_engine(database_url, future=True)
        Base.metadata.create_all(self.engine)

    def create_watchlist(
        self, user_email: str, name: str, items: list[WatchItem], *, created_at: str
    ) -> Watchlist:
        watchlist_id = secrets.token_hex(8)
        with Session(self.engine) as session:
            session.add(
                WatchlistRow(id=watchlist_id, user_email=user_email, name=name, created_at=created_at)
            )
            for item in items:
                session.add(
                    WatchItemRow(watchlist_id=watchlist_id, type=item.type, value=item.value)
                )
            session.commit()
        return Watchlist(id=watchlist_id, name=name, items=items, created_at=created_at)

    def _items(self, session: Session, watchlist_id: str) -> list[WatchItem]:
        rows = session.scalars(
            select(WatchItemRow).where(WatchItemRow.watchlist_id == watchlist_id)
        ).all()
        return [WatchItem(type=r.type, value=r.value) for r in rows]

    def get_watchlist(self, user_email: str, watchlist_id: str) -> Watchlist | None:
        with Session(self.engine) as session:
            row = session.get(WatchlistRow, watchlist_id)
            if row is None or row.user_email != user_email:
                return None
            return Watchlist(
                id=row.id, name=row.name, items=self._items(session, row.id), created_at=row.created_at
            )

    def list_watchlists(self, user_email: str) -> list[Watchlist]:
        with Session(self.engine) as session:
            rows = session.scalars(
                select(WatchlistRow)
                .where(WatchlistRow.user_email == user_email)
                .order_by(WatchlistRow.created_at)
            ).all()
            return [
                Watchlist(
                    id=r.id, name=r.name, items=self._items(session, r.id), created_at=r.created_at
                )
                for r in rows
            ]

    def delete_watchlist(self, user_email: str, watchlist_id: str) -> bool:
        with Session(self.engine) as session:
            row = session.get(WatchlistRow, watchlist_id)
            if row is None or row.user_email != user_email:
                return False
            session.delete(row)
            session.execute(delete(WatchItemRow).where(WatchItemRow.watchlist_id == watchlist_id))
            session.execute(delete(NotificationRow).where(NotificationRow.watchlist_id == watchlist_id))
            session.commit()
            return True

    def add_notifications(
        self, user_email: str, watchlist_id: str, notifications: list[Notification]
    ) -> int:
        added = 0
        with Session(self.engine) as session:
            for n in notifications:
                stored_id = f"{watchlist_id}:{n.id}"
                if session.get(NotificationRow, stored_id) is not None:
                    continue  # idempotent: preserve existing (incl. read state)
                session.add(
                    NotificationRow(
                        id=stored_id,
                        user_email=user_email,
                        watchlist_id=watchlist_id,
                        watch_type=n.watch_type,
                        watch_value=n.watch_value,
                        kind=n.kind,
                        title=n.title,
                        detail=n.detail,
                        category=n.category,
                        source_uri=n.source_uri,
                        canonical_id=n.canonical_id,
                        created_at=n.created_at,
                        read=False,
                    )
                )
                added += 1
            session.commit()
        return added

    def list_notifications(
        self, user_email: str, *, unread_only: bool = False, limit: int = 200
    ) -> list[Notification]:
        statement = select(NotificationRow).where(NotificationRow.user_email == user_email)
        if unread_only:
            statement = statement.where(NotificationRow.read.is_(False))
        statement = statement.order_by(NotificationRow.created_at.desc()).limit(max(1, limit))
        with Session(self.engine) as session:
            return [
                Notification(
                    id=r.id,
                    watchlist_id=r.watchlist_id,
                    watch_type=r.watch_type,
                    watch_value=r.watch_value,
                    kind=r.kind,
                    title=r.title,
                    detail=r.detail,
                    category=r.category,
                    source_uri=r.source_uri,
                    canonical_id=r.canonical_id,
                    created_at=r.created_at,
                    read=r.read,
                )
                for r in session.scalars(statement).all()
            ]

    def mark_read(self, user_email: str, notification_id: str) -> bool:
        with Session(self.engine) as session:
            row = session.get(NotificationRow, notification_id)
            if row is None or row.user_email != user_email:
                return False
            row.read = True
            session.commit()
            return True
