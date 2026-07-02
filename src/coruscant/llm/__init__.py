"""LLM gateway — tiered, provider-agnostic model routing for the platform.

Boundary: PLATFORM primitive — see docs/PLATFORM.md §7.
"""

from coruscant.llm.config import (
    TIER_HINTS,
    TIERS,
    LLMRouterConfig,
    ProviderConfig,
    Route,
    default_config,
    load_config,
    save_config,
)
from coruscant.llm.gateway import LLMGateway, LLMResult
from coruscant.llm.providers import LLMError

__all__ = [
    "TIERS",
    "TIER_HINTS",
    "LLMRouterConfig",
    "ProviderConfig",
    "Route",
    "default_config",
    "load_config",
    "save_config",
    "LLMGateway",
    "LLMResult",
    "LLMError",
]
