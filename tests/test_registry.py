from __future__ import annotations

import pytest

from coruscant.ingestion.registry import SourceRegistry, UnknownSourceError, default_registry

EXPECTED_SOURCES = {
    "sec_edgar",
    "investor_relations",
    "earnings_call",
    "press_release",
    "job_postings",
    "news",
    "patents",
}


def test_default_registry_has_all_in_scope_sources() -> None:
    registry = default_registry()
    assert set(registry.source_types()) == EXPECTED_SOURCES
    assert len(registry.definitions()) == len(EXPECTED_SOURCES)


def test_registry_get_and_has() -> None:
    registry = default_registry()
    assert registry.has("news")
    definition = registry.get("news")
    assert definition.document_type == "news_article"
    assert callable(definition.connector_factory)
    assert callable(definition.normalizer)


def test_registry_unknown_source_raises() -> None:
    registry = SourceRegistry()
    assert not registry.has("nope")
    with pytest.raises(UnknownSourceError):
        registry.get("nope")
