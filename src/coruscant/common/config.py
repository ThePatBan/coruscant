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


class SourceSetting(BaseModel):
    type: str
    enabled: bool = True
    period: str | None = None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CORUSCANT_", env_file=".env", extra="ignore")

    data_dir: Path = Path("data")
    config_dir: Path = Path("config")
    database_url: str = "sqlite:///data/coruscant.db"
    neo4j_url: str | None = None
    edgar_user_agent: str = "Coruscant/0.1.0 contact@coruscant.local"
    cors_origins: list[str] = Field(default_factory=lambda: ["*"])

    @property
    def graph_snapshot_path(self) -> Path:
        return self.data_dir / "graph" / "graph.json"


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
