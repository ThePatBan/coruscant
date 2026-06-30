from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class CompanyConfig(BaseModel):
    slug: str
    name: str
    aliases: list[str] = Field(default_factory=list)
    industry: str | None = None
    country: str | None = None
    # SEC central index key (identity; optional — private companies have none).
    cik: str | None = None
    # Explicit SEC filing document/index URLs (oldest → newest) used by the live
    # EDGAR path. Ignored in reference/offline mode. Empty for private companies.
    sec_filings: list[str] = Field(default_factory=list)


class SourceSetting(BaseModel):
    type: str
    enabled: bool = True
    period: str | None = None


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


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CORUSCANT_", env_file=".env", extra="ignore")

    data_dir: Path = Path("data")
    config_dir: Path = Path("config")
    database_url: str = "sqlite:///data/coruscant.db"
    neo4j_url: str | None = None
    edgar_user_agent: str = "Coruscant/0.1.0 contact@coruscant.local"
    # Sources that use their live (network) connector instead of the offline
    # reference connector. Empty by default so dev/test stays fully offline. In
    # production set e.g. CORUSCANT_LIVE_SOURCES=["sec_edgar"].
    live_sources: list[str] = Field(default_factory=list)
    # SEC fair-access cap (requests/second). SEC permits ~10/s with a declared
    # User-Agent; default keeps headroom. Applies to every live EDGAR request.
    sec_rate_limit_per_second: float = 8.0
    cors_origins: list[str] = Field(default_factory=lambda: ["*"])
    # Empty by default: build_auth_service falls back to a per-process ephemeral
    # secret (never a committed constant). Set CORUSCANT_SECRET_KEY for stable,
    # secure tokens in any real deployment.
    secret_key: str = ""
    token_ttl_seconds: int = 86_400
    # Demo seeding is OFF by default; the docker stack opts in explicitly. A real
    # deployment never auto-creates a known account.
    seed_demo_user: bool = False
    demo_email: str = "demo@coruscant.local"
    demo_password: str = ""
    # Returning the reset token in the API response is a dev/offline convenience
    # only (no email delivery); never expose it on an untrusted deployment.
    expose_reset_token: bool = False
    ingest_max_attempts: int = 3
    # Enforce per-plan daily API + watchlist quotas. Only takes effect in a
    # multi-tenant deployment (when an organization store is configured); single
    # -tenant/offline use is never throttled. Set false to disable enforcement.
    enforce_quotas: bool = True

    @property
    def graph_snapshot_path(self) -> Path:
        return self.data_dir / "graph" / "graph.json"

    @property
    def status_path(self) -> Path:
        return self.data_dir / "status.json"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def load_companies(config_dir: Path | None = None) -> list[CompanyConfig]:
    base = config_dir or get_settings().config_dir
    path = base / "companies.yml"
    data = yaml.safe_load(path.read_text()) if path.exists() else {}
    companies = data.get("companies", [])
    return [CompanyConfig.model_validate(company) for company in companies]


def load_sources(config_dir: Path | None = None) -> list[SourceSetting]:
    base = config_dir or get_settings().config_dir
    path = base / "sources.yml"
    data = yaml.safe_load(path.read_text()) if path.exists() else {}
    sources = data.get("sources", []) if isinstance(data, dict) else []
    return [SourceSetting.model_validate(source) for source in sources]


def load_entities(config_dir: Path | None = None) -> dict[str, CompanyEntities]:
    base = config_dir or get_settings().config_dir
    path = base / "entities.yml"
    data = yaml.safe_load(path.read_text()) if path.exists() else {}
    companies = data.get("companies", {}) if isinstance(data, dict) else {}
    return {slug: CompanyEntities.model_validate(value) for slug, value in companies.items()}
