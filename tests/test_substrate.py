"""The edge substrate: access-tier policy enforcement + bitemporal filtering."""

from __future__ import annotations

from datetime import date

from coruscant.common.types import GraphEdge
from coruscant.knowledge_graph import substrate as S
from coruscant.knowledge_graph.substrate import AccessTier


def _edge(**props: object) -> GraphEdge:
    return GraphEdge(source_kind="Person", source_key="p", relation="pep",
                     target_kind="WatchlistEntity", target_key="w", properties=dict(props))


def test_stamp_writes_substrate_fields_and_omits_empty_bounds() -> None:
    props = S.stamp({"score": 0.9}, source="opensanctions", access_tier=AccessTier.PUBLIC,
                    observed_at=date(2026, 7, 1))
    assert props["score"] == 0.9
    assert props[S.SOURCE] == "opensanctions"
    assert props[S.ACCESS_TIER] == "public"
    assert props[S.OBSERVED_AT] == "2026-07-01"
    assert S.VALID_FROM not in props and S.VALID_TO not in props  # open-ended omitted


def test_stamp_records_valid_time_interval() -> None:
    props = S.stamp(source="ofac", access_tier="restricted-authority",
                    observed_at="2026-07-01", valid_from=date(2022, 3, 1), valid_to="2026-01-01")
    assert props[S.VALID_FROM] == "2022-03-01"
    assert props[S.VALID_TO] == "2026-01-01"
    assert props[S.ACCESS_TIER] == "restricted-authority"


def test_tier_of_defaults_public_and_fails_closed_on_unknown() -> None:
    assert S.tier_of({}) is AccessTier.PUBLIC  # unlabelled reference edge is public
    assert S.tier_of({S.ACCESS_TIER: "legitimate-interest"}) is AccessTier.LEGITIMATE_INTEREST
    assert S.tier_of({S.ACCESS_TIER: "who-knows"}) is AccessTier.AGGREGATOR_LICENSED  # fail closed


def test_visibility_is_ordered_by_clearance() -> None:
    public = _edge(access_tier="public")
    legit = _edge(access_tier="legitimate-interest")
    restricted = _edge(access_tier="restricted-authority")
    licensed = _edge(access_tier="aggregator-licensed")
    edges = [public, legit, restricted, licensed]

    # A public caller sees only public data.
    assert S.visible(edges, clearance=AccessTier.PUBLIC) == [public]
    # Higher clearance sees its tier and everything less restrictive.
    assert S.visible(edges, clearance="restricted-authority") == [public, legit, restricted]
    assert S.visible(edges, clearance=AccessTier.AGGREGATOR_LICENSED) == edges
    assert not S.can_see({"access_tier": "aggregator-licensed"}, AccessTier.PUBLIC)


def test_bitemporal_as_of_selects_facts_true_on_the_date() -> None:
    listed = _edge(valid_from="2022-03-01", valid_to="2025-12-31")  # delisted end of 2025
    still_open = _edge(valid_from="2020-01-01")  # open-ended
    edges = [listed, still_open]

    # On the transaction date inside the window, both apply.
    assert S.as_of(edges, on=date(2024, 6, 1)) == [listed, still_open]
    # After the delisting, only the open-ended fact survives.
    assert S.as_of(edges, on="2026-06-01") == [still_open]
    # Before it was listed, the closed fact does not yet apply.
    assert S.as_of(edges, on="2021-01-01") == [still_open]
