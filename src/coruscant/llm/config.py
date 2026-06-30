"""LLM router configuration — which task tier runs on which model.

The platform routes work by *tier* (cheap bulk work vs. demanding synthesis) and
the admin maps each tier to a provider + model. This keeps callers ("analyze this
with the complex tier") decoupled from the model choice, so the admin can swap a
local Gemma in for bulk classification and reserve Opus for the hard reasoning
without touching code.

Persisted as JSON under the data dir so the admin page can edit it at runtime.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

# Task tiers, cheapest → most capable. Callers pick a tier; the admin picks the
# model behind it.
TIERS: tuple[str, ...] = ("simple", "light", "complex")
TIER_HINTS: dict[str, str] = {
    "simple": "Bulk, mechanical work — classification, tagging, extraction. Favor a cheap/local model.",
    "light": "Standard summarization and short synthesis. A small hosted model.",
    "complex": "Demanding multi-step reasoning — the analyst thesis. The most capable model.",
}


class ProviderConfig(BaseModel):
    kind: str  # "openai" (OpenAI-compatible: OpenAI, Ollama, LM Studio) | "anthropic"
    base_url: str
    api_key: str = ""
    label: str = ""


class Route(BaseModel):
    provider: str  # key into LLMRouterConfig.providers
    model: str


class LLMRouterConfig(BaseModel):
    providers: dict[str, ProviderConfig] = Field(default_factory=dict)
    routes: dict[str, Route] = Field(default_factory=dict)


def default_config() -> LLMRouterConfig:
    return LLMRouterConfig(
        providers={
            "local": ProviderConfig(
                kind="openai", base_url="http://localhost:11434/v1", label="Local (Ollama / LM Studio)"
            ),
            "openai": ProviderConfig(kind="openai", base_url="https://api.openai.com/v1", label="OpenAI"),
            "anthropic": ProviderConfig(kind="anthropic", base_url="https://api.anthropic.com", label="Anthropic"),
        },
        routes={
            "simple": Route(provider="local", model="gemma2"),
            "light": Route(provider="openai", model="gpt-5.4-mini"),
            "complex": Route(provider="anthropic", model="claude-opus-4-8"),
        },
    )


def config_path(data_dir: Path) -> Path:
    return Path(data_dir) / "llm_config.json"


def load_config(data_dir: Path) -> LLMRouterConfig:
    path = config_path(data_dir)
    if path.exists():
        try:
            loaded = LLMRouterConfig.model_validate_json(path.read_text())
        except (ValueError, OSError):
            return default_config()
        # Merge defaults for any provider/tier the saved file is missing.
        base = default_config()
        for key, provider in base.providers.items():
            loaded.providers.setdefault(key, provider)
        for tier, route in base.routes.items():
            loaded.routes.setdefault(tier, route)
        return loaded
    return default_config()


def save_config(data_dir: Path, config: LLMRouterConfig) -> None:
    path = config_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(config.model_dump_json(indent=2))
