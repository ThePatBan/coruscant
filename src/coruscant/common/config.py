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
    # Phase 6 (public launch): expose a safe, read-only, evidence-backed public
    # surface (entity search, profiles, relationships, timelines, evidence) to
    # unauthenticated visitors — no forced demo sign-in. Curated allow-list only
    # (see apps/api.py PUBLIC_READ); user-owned, write, admin, and costly LLM
    # routes stay authenticated. Set false to fall back to fully-gated behaviour.
    public_read: bool = True
    # Anonymous requests/minute per client IP against the public surface. Signed-in
    # callers are exempt (they have per-plan quotas instead). Fixed-window, in-proc.
    public_read_rate_limit: int = 120
    # Assert go-live safety at startup. When true, the app REFUSES to boot with an
    # unsafe production config (wildcard CORS, missing secret) instead of silently
    # degrading. Off by default so dev/test/offline use is never blocked.
    production: bool = False

    def config_warnings(self) -> list[str]:
        """Go-live safety issues in the current settings (empty == launch-safe).

        Surfaced (logged) on every boot; treated as fatal when ``production`` is on.
        Keep this the single source of truth for "is this config safe to serve?"."""
        warnings: list[str] = []
        if "*" in self.cors_origins:
            warnings.append(
                "CORS is wildcard ('*'): set CORUSCANT_CORS_ORIGINS to your exact "
                "web origin(s) before serving to real users."
            )
        if not self.secret_key.strip():
            warnings.append(
                "CORUSCANT_SECRET_KEY is unset: tokens use a per-process ephemeral "
                "secret and are invalidated on every restart. Set a strong, stable secret."
            )
        if self.expose_reset_token:
            warnings.append(
                "CORUSCANT_EXPOSE_RESET_TOKEN is on: password-reset tokens are returned "
                "in API responses — a dev/offline convenience, never for production."
            )
        if self.seed_demo_user:
            warnings.append(
                "CORUSCANT_SEED_DEMO_USER is on: a known demo account is auto-created — "
                "disable it before a public launch."
            )
        return warnings

    def ensure_launch_safe(self) -> None:
        """Fail closed when serving with an unsafe production config; no-op otherwise.

        ``config_warnings`` are advisory (logged) in dev/offline use, but fatal when
        ``production`` is set — the app refuses to boot rather than silently serve
        with wildcard CORS or ephemeral tokens."""
        warnings = self.config_warnings()
        if self.production and warnings:
            raise RuntimeError("unsafe production config: " + "; ".join(warnings))

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
