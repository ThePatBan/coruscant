from __future__ import annotations

import pytest

from coruscant.ingestion.registry import SourceRegistry, UnknownSourceError, default_registry

EXPECTED_SOURCES = {
    "sec_edgar",
    "global_regulators",
    "court_filings",
    "sanctions",
    "government_contracts",
    "procurement_notices",
    "investor_relations",
    "earnings_call",
    "esg_reports",
    "patents",
    "press_release",
    "news",
    "job_postings",
}


def test_default_registry_has_all_in_scope_sources() -> None:
    registry = default_registry()
    assert set(registry.source_types()) == EXPECTED_SOURCES
    assert len(registry.definitions()) == len(EXPECTED_SOURCES)


def test_every_source_has_an_authority_score() -> None:
    for definition in default_registry().definitions():
        assert 0.0 <= definition.authority <= 1.0


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
