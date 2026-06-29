"""SQLite stores for organizations/membership and usage analytics."""

from __future__ import annotations

from pathlib import Path
import secrets

from sqlalchemy import Integer, String, create_engine, func, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from coruscant.commercial.models import DEFAULT_PLAN, Organization, UsageSummary


class Base(DeclarativeBase):
    pass


class OrgRow(Base):
    __tablename__ = "organizations"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    owner_email: Mapped[str] = mapped_column(String, index=True)
    plan: Mapped[str] = mapped_column(String, default=DEFAULT_PLAN)
    created_at: Mapped[str] = mapped_column(String)


class OrgMemberRow(Base):
    __tablename__ = "organization_members"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    organization_id: Mapped[str] = mapped_column(String, index=True)
    email: Mapped[str] = mapped_column(String, index=True)


class UsageRow(Base):
    __tablename__ = "usage_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String, index=True)
    action: Mapped[str] = mapped_column(String, index=True)
    created_at: Mapped[str] = mapped_column(String)


def _ensure_sqlite_dir(database_url: str) -> None:
    prefix = "sqlite:///"
    if database_url.startswith(prefix):
        path = Path(database_url[len(prefix) :])
        if path.parent and not path.parent.exists():
            path.parent.mkdir(parents=True, exist_ok=True)


class SqliteOrgStore:
    def __init__(self, database_url: str = "sqlite:///data/coruscant.db") -> None:
        _ensure_sqlite_dir(database_url)
        self.engine = create_engine(database_url, future=True)
        Base.metadata.create_all(self.engine)

    def _members(self, session: Session, org_id: str) -> list[str]:
        rows = session.scalars(
            select(OrgMemberRow).where(OrgMemberRow.organization_id == org_id)
        ).all()
        return sorted({r.email for r in rows})

    def _to_org(self, session: Session, row: OrgRow) -> Organization:
        return Organization(
            id=row.id,
            name=row.name,
            owner_email=row.owner_email,
            plan=row.plan,
            members=self._members(session, row.id),
            created_at=row.created_at,
        )

    def create_org(
        self, owner_email: str, name: str, plan: str, members: list[str], *, created_at: str
    ) -> Organization:
        org_id = secrets.token_hex(8)
        with Session(self.engine) as session:
            session.add(
                OrgRow(id=org_id, name=name, owner_email=owner_email, plan=plan, created_at=created_at)
            )
            for member in {owner_email, *members}:
                session.add(OrgMemberRow(organization_id=org_id, email=member))
            session.commit()
            row = session.get(OrgRow, org_id)
            assert row is not None
            return self._to_org(session, row)

    def list_orgs(self, email: str) -> list[Organization]:
        with Session(self.engine) as session:
            org_ids = set(
                session.scalars(
                    select(OrgMemberRow.organization_id).where(OrgMemberRow.email == email)
                ).all()
            )
            if not org_ids:
                return []
            rows = session.scalars(
                select(OrgRow).where(OrgRow.id.in_(org_ids)).order_by(OrgRow.created_at)
            ).all()
            return [self._to_org(session, r) for r in rows]

    def get_org(self, email: str, org_id: str) -> Organization | None:
        with Session(self.engine) as session:
            row = session.get(OrgRow, org_id)
            if row is None or email not in self._members(session, org_id):
                return None
            return self._to_org(session, row)

    def set_plan(self, email: str, org_id: str, plan: str) -> bool:
        with Session(self.engine) as session:
            row = session.get(OrgRow, org_id)
            if row is None or row.owner_email != email:  # only the owner changes the plan
                return False
            row.plan = plan
            session.commit()
            return True


class SqliteUsageStore:
    def __init__(self, database_url: str = "sqlite:///data/coruscant.db") -> None:
        _ensure_sqlite_dir(database_url)
        self.engine = create_engine(database_url, future=True)
        Base.metadata.create_all(self.engine)

    def record(self, email: str, action: str, *, created_at: str) -> None:
        with Session(self.engine) as session:
            session.add(UsageRow(email=email, action=action, created_at=created_at))
            session.commit()

    def summary(self, emails: list[str]) -> UsageSummary:
        if not emails:
            return UsageSummary()
        with Session(self.engine) as session:
            rows = session.execute(
                select(UsageRow.action, func.count())
                .where(UsageRow.email.in_(emails))
                .group_by(UsageRow.action)
            ).all()
        actions = {action: int(count) for action, count in rows}
        return UsageSummary(actions=actions, total=sum(actions.values()))
