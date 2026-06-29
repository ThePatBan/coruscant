"""SQLite-backed, user-scoped portfolio store (shares the platform DB)."""

from __future__ import annotations

from pathlib import Path
import secrets

from sqlalchemy import Integer, String, create_engine, delete, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from coruscant.portfolio.models import Holding, Portfolio


class Base(DeclarativeBase):
    pass


class PortfolioRow(Base):
    __tablename__ = "portfolios"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_email: Mapped[str] = mapped_column(String, index=True)
    name: Mapped[str] = mapped_column(String)
    created_at: Mapped[str] = mapped_column(String)


class HoldingRow(Base):
    __tablename__ = "holdings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    portfolio_id: Mapped[str] = mapped_column(String, index=True)
    company_slug: Mapped[str] = mapped_column(String)
    label: Mapped[str | None] = mapped_column(String, nullable=True)


def _ensure_sqlite_dir(database_url: str) -> None:
    prefix = "sqlite:///"
    if database_url.startswith(prefix):
        path = Path(database_url[len(prefix) :])
        if path.parent and not path.parent.exists():
            path.parent.mkdir(parents=True, exist_ok=True)


class SqlitePortfolioStore:
    def __init__(self, database_url: str = "sqlite:///data/coruscant.db") -> None:
        _ensure_sqlite_dir(database_url)
        self.engine = create_engine(database_url, future=True)
        Base.metadata.create_all(self.engine)

    def create_portfolio(
        self, user_email: str, name: str, holdings: list[Holding], *, created_at: str
    ) -> Portfolio:
        portfolio_id = secrets.token_hex(8)
        with Session(self.engine) as session:
            session.add(
                PortfolioRow(id=portfolio_id, user_email=user_email, name=name, created_at=created_at)
            )
            for holding in holdings:
                session.add(
                    HoldingRow(
                        portfolio_id=portfolio_id,
                        company_slug=holding.company_slug,
                        label=holding.label,
                    )
                )
            session.commit()
        return Portfolio(id=portfolio_id, name=name, holdings=holdings, created_at=created_at)

    def _holdings(self, session: Session, portfolio_id: str) -> list[Holding]:
        rows = session.scalars(
            select(HoldingRow).where(HoldingRow.portfolio_id == portfolio_id)
        ).all()
        return [Holding(company_slug=r.company_slug, label=r.label) for r in rows]

    def get_portfolio(self, user_email: str, portfolio_id: str) -> Portfolio | None:
        with Session(self.engine) as session:
            row = session.get(PortfolioRow, portfolio_id)
            if row is None or row.user_email != user_email:
                return None
            return Portfolio(
                id=row.id, name=row.name, holdings=self._holdings(session, row.id), created_at=row.created_at
            )

    def list_portfolios(self, user_email: str) -> list[Portfolio]:
        with Session(self.engine) as session:
            rows = session.scalars(
                select(PortfolioRow)
                .where(PortfolioRow.user_email == user_email)
                .order_by(PortfolioRow.created_at)
            ).all()
            return [
                Portfolio(
                    id=r.id, name=r.name, holdings=self._holdings(session, r.id), created_at=r.created_at
                )
                for r in rows
            ]

    def delete_portfolio(self, user_email: str, portfolio_id: str) -> bool:
        with Session(self.engine) as session:
            row = session.get(PortfolioRow, portfolio_id)
            if row is None or row.user_email != user_email:
                return False
            session.delete(row)
            session.execute(delete(HoldingRow).where(HoldingRow.portfolio_id == portfolio_id))
            session.commit()
            return True
