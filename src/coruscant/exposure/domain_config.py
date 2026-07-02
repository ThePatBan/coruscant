"""Workspace-domain configuration schemas + loaders (the investment universe).

Boundary: WORKSPACE (Portfolio-Exposure) — see docs/PLATFORM.md §7, §9 (seam 1).

Phase 4 of the platform/workspace split (ADR-0013) relocates these investment-domain
config schemas and their loaders out of the platform ``common`` package into the
Portfolio-Exposure workspace. The platform ``common/config.py`` now keeps only the
generic ``Settings``, ``SourceSetting``, ``get_settings``, and ``load_sources`` — it no
longer imports or re-exports any workspace-domain schema. This module reaches back to the
platform only for ``get_settings`` (workspace -> platform, the allowed direction).
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from coruscant.common.config import get_settings


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


def load_companies(config_dir: Path | None = None) -> list[CompanyConfig]:
    base = config_dir or get_settings().config_dir
    path = base / "companies.yml"
    data = yaml.safe_load(path.read_text()) if path.exists() else {}
    companies = data.get("companies", [])
    return [CompanyConfig.model_validate(company) for company in companies]


def load_instruments(config_dir: Path | None = None) -> InstrumentsConfig:
    base = config_dir or get_settings().config_dir
    path = base / "instruments.yml"
    data = yaml.safe_load(path.read_text()) if path.exists() else {}
    return InstrumentsConfig.model_validate(data or {})


def load_entities(config_dir: Path | None = None) -> dict[str, CompanyEntities]:
    base = config_dir or get_settings().config_dir
    path = base / "entities.yml"
    data = yaml.safe_load(path.read_text()) if path.exists() else {}
    companies = data.get("companies", {}) if isinstance(data, dict) else {}
    return {slug: CompanyEntities.model_validate(value) for slug, value in companies.items()}
