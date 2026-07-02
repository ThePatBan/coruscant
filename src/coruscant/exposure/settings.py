"""Portfolio-Exposure workspace runtime settings.

Boundary: WORKSPACE (Portfolio-Exposure) — see docs/PLATFORM.md §7, §9 (seam 1).

The product-specific runtime flags — live feeds, PEP/sanctions screening, GLEIF anchoring,
UK PSC ownership, and the finance SEC-EDGAR connector config — that used to sit on the
platform ``common.config.Settings``. Phase 5 splits them out so the platform ``Settings``
carries only genuinely platform-level configuration.

This class reads the same ``CORUSCANT_`` env prefix / ``.env`` file as the platform
``Settings`` (each owns a disjoint set of fields, ``extra="ignore"``), so environment- and
``.env``-driven configuration is unchanged — a ``CORUSCANT_ENABLE_LIVE_PRICES`` etc. still
works exactly as before.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class WorkspaceSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CORUSCANT_", env_file=".env", extra="ignore")

    # --- Finance ingestion / SEC EDGAR connector ---
    edgar_user_agent: str = "Coruscant/0.1.0 contact@coruscant.local"
    # Sources that use their live (network) connector instead of the offline reference
    # connector. Empty by default so dev/test stays fully offline.
    live_sources: list[str] = Field(default_factory=list)
    # SEC fair-access cap (requests/second); applies to every live EDGAR request.
    sec_rate_limit_per_second: float = 8.0

    # --- Live feeds (World tab); OFF by default so the offline/test path never hits the network ---
    enable_live_prices: bool = False
    enable_live_macro: bool = False
    enable_live_news: bool = False

    # --- PEP / sanctions screening ---
    # OpenSanctions export path (deterministic provider); unset => panel reports connected:false.
    screening_dataset_path: Path | None = None
    # "deterministic" (offline) or "yente" (OpenSanctions scorer sidecar over HTTP).
    screening_provider: str = "deterministic"
    yente_url: str = "http://localhost:8000"
    yente_dataset: str = "default"  # yente collection ("default" | "sanctions" | "peps")
    yente_cutoff: float = 0.7  # minimum score for yente to return a candidate
    yente_limit: int = 5  # max candidates per person

    # --- GLEIF LEI anchoring: "gleif-api" (free CC0) or "gleif-local" (operator export) ---
    anchor_provider: str = "gleif-api"
    gleif_dataset_path: Path | None = None

    # --- UK Companies House PSC (public beneficial-ownership register; needs a free key) ---
    companies_house_api_key: str | None = None
    companies_house_api_url: str = "https://api.company-information.service.gov.uk"


@lru_cache(maxsize=1)
def get_workspace_settings() -> WorkspaceSettings:
    return WorkspaceSettings()
