from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    # Graph-store backend for the SERVING/query path (the exposure engine + API).
    # "kuzu" (default): an embedded, disk-based, Cypher-native graph DB built from
    # the JSON snapshot — the scalable store and the Cypher on-ramp to a future
    # Neo4j/Neptune. "memory": the in-process JSON-over-dict prototype, kept as the
    # lightweight test double and golden-parity comparator. Ingestion always
    # materializes the JSON snapshot regardless of backend.
    graph_backend: str = "kuzu"
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
    # Path to an OpenSanctions export (bulk `targets.nested.json` or a JSON array)
    # for PEP/sanctions screening. Unset by default so the offline/test path never
    # depends on it and the screening panel honestly reports `connected: false`
    # until an operator wires a dataset (see `coruscant screen`).
    screening_dataset_path: Path | None = None
    # Which screening matcher to use: "deterministic" (zero-dep, offline, exact/
    # near-exact names) or "yente" (OpenSanctions' scorer at scale + fuzzy/cross-
    # script recall, run as a Docker sidecar over HTTP — see docker-compose.screening.yml).
    screening_provider: str = "deterministic"
    yente_url: str = "http://localhost:8000"
    yente_dataset: str = "default"  # yente collection ("default" | "sanctions" | "peps")
    yente_cutoff: float = 0.7  # minimum score for yente to return a candidate
    yente_limit: int = 5  # max candidates per person
    # GLEIF LEI anchoring: "gleif-api" (free, CC0 public API) or "gleif-local"
    # (an operator-supplied GLEIF export at gleif_dataset_path).
    anchor_provider: str = "gleif-api"
    gleif_dataset_path: Path | None = None
    # UK Companies House PSC (Persons with Significant Control) — a free, live,
    # PUBLIC beneficial-ownership register. The Public Data API needs a free API key
    # (register at developer.company-information.service.gov.uk); unset by default so
    # the offline/test path never depends on it and `coruscant ownership --provider
    # psc` reports an honest error until a key or a bulk snapshot file is supplied.
    companies_house_api_key: str | None = None
    companies_house_api_url: str = "https://api.company-information.service.gov.uk"
    # Enforce per-plan daily API + watchlist quotas. Only takes effect in a
    # multi-tenant deployment (when an organization store is configured); single
    # -tenant/offline use is never throttled. Set false to disable enforcement.
    enforce_quotas: bool = True

    @property
    def graph_snapshot_path(self) -> Path:
        return self.data_dir / "graph" / "graph.json"

    @property
    def graph_kuzu_path(self) -> Path:
        """On-disk Kùzu database file (materialized from the JSON snapshot)."""
        return self.data_dir / "graph" / "graph.kz"

    @property
    def resolver_snapshot_path(self) -> Path:
        """Append-only entity-resolution judgement log (reversible + versioned)."""
        return self.data_dir / "graph" / "resolver.json"

    @property
    def status_path(self) -> Path:
        return self.data_dir / "status.json"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def load_sources(config_dir: Path | None = None) -> list[SourceSetting]:
    base = config_dir or get_settings().config_dir
    path = base / "sources.yml"
    data = yaml.safe_load(path.read_text()) if path.exists() else {}
    sources = data.get("sources", []) if isinstance(data, dict) else []
    return [SourceSetting.model_validate(source) for source in sources]
