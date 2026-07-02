"""Workspace-domain configuration schemas (the investment universe).

Boundary: WORKSPACE (Portfolio-Exposure) — see docs/PLATFORM.md §7, §9 (seam 1).

Phase 2 of the platform/workspace split (ADR-0013) isolates these investment-domain
config models out of the platform ``common/config.py`` — which now keeps only the
platform ``Settings`` and generic source config. These are **re-exported** from
``coruscant.common.config`` for backward compatibility, so existing imports keep working;
new code should import them from here. Their eventual home is a dedicated workspace
package (docs/PLATFORM.md §9) — this module is the first structural move.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class CompanyConfig(BaseModel):
    slug: str
    name: str
    aliases: list[str] = Field(default_factory=list)
    industry: str | None = None
    country: str | None = None
    # SEC central index key (identity; optional — private companies have none).
    cik: str | None = None
    # Exchange ticker for live quotes. Optional: for our universe the slug is the
    # lowercased ticker (aapl→AAPL, the UK/India names are US-listed ADRs), so this
    # defaults to slug.upper(); set it when a slug and ticker diverge (e.g. BRK.B).
    ticker: str | None = None
    # Explicit SEC filing document/index URLs (oldest → newest) used by the live
    # EDGAR path. Ignored in reference/offline mode. Empty for private companies.
    sec_filings: list[str] = Field(default_factory=list)

    @property
    def ticker_symbol(self) -> str:
        return (self.ticker or self.slug).upper()


class CommodityConfig(BaseModel):
    slug: str
    name: str
    category: str  # Energy | Metals | Agriculture
    # Yahoo futures symbol for the free live price (optional).
    symbol: str | None = None
    # GICS sectors whose holdings this commodity drives (curated, evidence-backed
    # linkage — e.g. Crude Oil -> Energy). The exposure engine traverses these.
    affects_sectors: list[str] = Field(default_factory=list)


class DebtConfig(BaseModel):
    slug: str
    name: str
    debt_type: str  # sovereign | corporate | aggregate
    issuer_country: str  # links the instrument to a Country
    # Yahoo yield-index or bond-ETF proxy symbol (optional).
    symbol: str | None = None


class InstrumentsConfig(BaseModel):
    """Non-equity instruments in the inventory. Equities are the tracked
    companies; commodities and debt are first-class instruments the exposure
    engine reasons about (a commodity event reaches equity holdings via sector; a
    country event reaches its sovereign/corporate debt)."""

    commodities: list[CommodityConfig] = Field(default_factory=list)
    debt: list[DebtConfig] = Field(default_factory=list)


class PersonConfig(BaseModel):
    name: str
    role: str | None = None
    previously: list[str] = Field(default_factory=list)


class SupplierConfig(BaseModel):
    name: str
    country: str | None = None


class CompanyEntities(BaseModel):
    people: list[PersonConfig] = Field(default_factory=list)
    suppliers: list[SupplierConfig] = Field(default_factory=list)
    customers: list[str] = Field(default_factory=list)
    competitors: list[str] = Field(default_factory=list)
    partners: list[str] = Field(default_factory=list)
    countries: list[str] = Field(default_factory=list)
    products: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)
    agencies: list[str] = Field(default_factory=list)
