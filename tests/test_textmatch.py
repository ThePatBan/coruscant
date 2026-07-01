"""Shared text matching: org-name core matching + jurisdiction→country."""

from __future__ import annotations

from coruscant.knowledge_graph.textmatch import (
    jurisdiction_country,
    org_core,
    org_score,
)


def test_org_core_strips_corporate_designators() -> None:
    assert org_core("apple inc") == "apple"
    assert org_core("3m company") == "3m"
    assert org_core("aearo technologies llc") == "aearo technologies"


def test_org_score_matches_name_variants_but_not_lookalikes() -> None:
    # Our short label vs the registry's legal name → strong (same core).
    assert org_score("apple", "apple inc") >= 0.97
    assert org_score("3m", "3m company") >= 0.97
    # A different entity that merely shares the leading token → NOT a core match.
    assert org_score("apple", "apple ford inc") < 0.97
    # Unrelated → low.
    assert org_score("apple", "microsoft corporation") < 0.85


def test_jurisdiction_country_maps_states_and_countries() -> None:
    assert jurisdiction_country("Delaware") == "US"
    assert jurisdiction_country("New York") == "US"
    assert jurisdiction_country("England and Wales") == "GB"
    assert jurisdiction_country("Netherlands") == "NL"
    assert jurisdiction_country("Freedonia") is None  # unknown → can't corroborate
