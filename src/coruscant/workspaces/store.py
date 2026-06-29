"""SQLite-backed workspace store with membership-based access control."""

from __future__ import annotations

from pathlib import Path
import secrets

from sqlalchemy import String, Text, create_engine, delete, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from coruscant.workspaces.models import Workspace, WorkspaceItem


class Base(DeclarativeBase):
    pass


class WorkspaceRow(Base):
    __tablename__ = "workspaces"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    owner_email: Mapped[str] = mapped_column(String, index=True)
    name: Mapped[str] = mapped_column(String)
    created_at: Mapped[str] = mapped_column(String)


class MemberRow(Base):
    __tablename__ = "workspace_members"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    workspace_id: Mapped[str] = mapped_column(String, index=True)
    email: Mapped[str] = mapped_column(String, index=True)


class ItemRow(Base):
    __tablename__ = "workspace_items"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String, index=True)
    type: Mapped[str] = mapped_column(String)
    title: Mapped[str] = mapped_column(String)
    body: Mapped[str] = mapped_column(Text, default="")
    ref: Mapped[str | None] = mapped_column(String, nullable=True)
    author_email: Mapped[str] = mapped_column(String)
    created_at: Mapped[str] = mapped_column(String)


def _ensure_sqlite_dir(database_url: str) -> None:
    prefix = "sqlite:///"
    if database_url.startswith(prefix):
        path = Path(database_url[len(prefix) :])
        if path.parent and not path.parent.exists():
            path.parent.mkdir(parents=True, exist_ok=True)


class SqliteWorkspaceStore:
    def __init__(self, database_url: str = "sqlite:///data/coruscant.db") -> None:
        _ensure_sqlite_dir(database_url)
        self.engine = create_engine(database_url, future=True)
        Base.metadata.create_all(self.engine)

    def _members(self, session: Session, workspace_id: str) -> list[str]:
        rows = session.scalars(
            select(MemberRow).where(MemberRow.workspace_id == workspace_id)
        ).all()
        return sorted({r.email for r in rows})

    def _items(self, session: Session, workspace_id: str) -> list[WorkspaceItem]:
        rows = session.scalars(
            select(ItemRow).where(ItemRow.workspace_id == workspace_id).order_by(ItemRow.created_at)
        ).all()
        return [
            WorkspaceItem(
                id=r.id,
                type=r.type,
                title=r.title,
                body=r.body,
                ref=r.ref,
                author_email=r.author_email,
                created_at=r.created_at,
            )
            for r in rows
        ]

    def _to_workspace(self, session: Session, row: WorkspaceRow, *, with_items: bool) -> Workspace:
        return Workspace(
            id=row.id,
            name=row.name,
            owner_email=row.owner_email,
            members=self._members(session, row.id),
            created_at=row.created_at,
            items=self._items(session, row.id) if with_items else [],
        )

    def _can_access(self, session: Session, row: WorkspaceRow, email: str) -> bool:
        return row.owner_email == email or email in self._members(session, row.id)

    def create_workspace(
        self, owner_email: str, name: str, members: list[str], *, created_at: str
    ) -> Workspace:
        workspace_id = secrets.token_hex(8)
        with Session(self.engine) as session:
            session.add(
                WorkspaceRow(id=workspace_id, owner_email=owner_email, name=name, created_at=created_at)
            )
            for member in {owner_email, *members}:
                session.add(MemberRow(workspace_id=workspace_id, email=member))
            session.commit()
            row = session.get(WorkspaceRow, workspace_id)
            assert row is not None
            return self._to_workspace(session, row, with_items=True)

    def list_workspaces(self, email: str) -> list[Workspace]:
        with Session(self.engine) as session:
            member_ids = set(
                session.scalars(
                    select(MemberRow.workspace_id).where(MemberRow.email == email)
                ).all()
            )
            rows = session.scalars(select(WorkspaceRow).order_by(WorkspaceRow.created_at)).all()
            return [
                self._to_workspace(session, r, with_items=False)
                for r in rows
                if r.owner_email == email or r.id in member_ids
            ]

    def get_workspace(self, email: str, workspace_id: str) -> Workspace | None:
        with Session(self.engine) as session:
            row = session.get(WorkspaceRow, workspace_id)
            if row is None or not self._can_access(session, row, email):
                return None
            return self._to_workspace(session, row, with_items=True)

    def add_member(self, email: str, workspace_id: str, member_email: str) -> bool:
        with Session(self.engine) as session:
            row = session.get(WorkspaceRow, workspace_id)
            if row is None or row.owner_email != email:  # only the owner adds members
                return False
            if member_email not in self._members(session, workspace_id):
                session.add(MemberRow(workspace_id=workspace_id, email=member_email))
                session.commit()
            return True

    def add_item(self, email: str, workspace_id: str, item: WorkspaceItem) -> WorkspaceItem | None:
        with Session(self.engine) as session:
            row = session.get(WorkspaceRow, workspace_id)
            if row is None or not self._can_access(session, row, email):
                return None
            session.add(
                ItemRow(
                    id=item.id,
                    workspace_id=workspace_id,
                    type=item.type,
                    title=item.title,
                    body=item.body,
                    ref=item.ref,
                    author_email=item.author_email,
                    created_at=item.created_at,
                )
            )
            session.commit()
            return item

    def delete_item(self, email: str, workspace_id: str, item_id: str) -> bool:
        with Session(self.engine) as session:
            row = session.get(WorkspaceRow, workspace_id)
            if row is None or not self._can_access(session, row, email):
                return False
            item = session.get(ItemRow, item_id)
            if item is None or item.workspace_id != workspace_id:
                return False
            session.delete(item)
            session.commit()
            return True

    def delete_workspace(self, email: str, workspace_id: str) -> bool:
        with Session(self.engine) as session:
            row = session.get(WorkspaceRow, workspace_id)
            if row is None or row.owner_email != email:  # only the owner deletes
                return False
            session.delete(row)
            session.execute(delete(MemberRow).where(MemberRow.workspace_id == workspace_id))
            session.execute(delete(ItemRow).where(ItemRow.workspace_id == workspace_id))
            session.commit()
            return True
