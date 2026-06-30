"""The LLM gateway — route a task tier to its configured provider + model.

Callers ask for work at a tier ("complex"); the gateway resolves the route from
the admin's config and runs it. One seam for every model call in the platform, so
swapping models is an admin action, not a code change.
"""

from __future__ import annotations

import time
from pathlib import Path

from pydantic import BaseModel

from coruscant.llm import config as cfg
from coruscant.llm import providers


class LLMResult(BaseModel):
    text: str
    tier: str
    provider: str
    model: str
    latency_ms: int


class LLMGateway:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = Path(data_dir)

    def config(self) -> cfg.LLMRouterConfig:
        return cfg.load_config(self.data_dir)

    def _resolve(self, tier: str) -> tuple[cfg.ProviderConfig, str, str]:
        config = self.config()
        route = config.routes.get(tier)
        if route is None:
            raise providers.LLMError(f"No model is routed for the '{tier}' tier.")
        provider = config.providers.get(route.provider)
        if provider is None:
            raise providers.LLMError(f"Route '{tier}' points at unknown provider '{route.provider}'.")
        return provider, route.provider, route.model

    def complete(self, *, tier: str, system: str, user: str, max_tokens: int = 1024) -> LLMResult:
        provider, provider_id, model = self._resolve(tier)
        started = time.monotonic()
        text = providers.complete(provider, model, system=system, user=user, max_tokens=max_tokens)
        return LLMResult(
            text=text,
            tier=tier,
            provider=provider_id,
            model=model,
            latency_ms=int((time.monotonic() - started) * 1000),
        )

    def test(self, tier: str) -> dict[str, object]:
        """Send a trivial prompt to verify a tier's route is reachable."""
        try:
            result = self.complete(
                tier=tier,
                system="You are a connectivity health check. Reply with one word.",
                user="Reply with the single word: ok",
                max_tokens=16,
            )
        except providers.LLMError as exc:
            provider = self.config().routes.get(tier)
            return {"ok": False, "tier": tier, "error": str(exc), "model": provider.model if provider else None}
        return {
            "ok": True,
            "tier": tier,
            "provider": result.provider,
            "model": result.model,
            "latency_ms": result.latency_ms,
            "sample": result.text.strip()[:80],
        }

    def available(self, tier: str) -> bool:
        """Whether the tier's route is usable: a key is set, or it's a local
        (self-hosted) endpoint that needs none."""
        try:
            provider, _, _ = self._resolve(tier)
        except providers.LLMError:
            return False
        if provider.api_key:
            return True
        return "localhost" in provider.base_url or "127.0.0.1" in provider.base_url
