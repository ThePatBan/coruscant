from pathlib import Path

from coruscant.llm import (
    TIERS,
    LLMGateway,
    LLMRouterConfig,
    ProviderConfig,
    Route,
    default_config,
    load_config,
    save_config,
)


def test_default_config_has_a_route_per_tier() -> None:
    config = default_config()
    assert set(config.routes) == set(TIERS)
    assert config.routes["complex"].provider == "anthropic"


def test_config_roundtrips_and_merges_missing_defaults(tmp_path: Path) -> None:
    # A saved config missing a tier/provider gets the defaults merged back in.
    partial = LLMRouterConfig(
        providers={"anthropic": ProviderConfig(kind="anthropic", base_url="https://api.anthropic.com", api_key="sk")},
        routes={"complex": Route(provider="anthropic", model="claude-opus-4-8")},
    )
    save_config(tmp_path, partial)
    loaded = load_config(tmp_path)
    assert loaded.providers["anthropic"].api_key == "sk"  # preserved
    assert "local" in loaded.providers and "simple" in loaded.routes  # defaults merged


def test_gateway_availability_and_test_errors_cleanly(tmp_path: Path) -> None:
    save_config(tmp_path, default_config())
    gateway = LLMGateway(tmp_path)
    # local (no key required) is available; anthropic without a key is not.
    assert gateway.available("simple") is True
    assert gateway.available("complex") is False
    result = gateway.test("complex")
    assert result["ok"] is False and "key" in str(result["error"]).lower()
