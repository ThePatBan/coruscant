"""PEP/sanctions screening: matching, the precision gate, and no fabrication."""

from __future__ import annotations

import json
from pathlib import Path

from coruscant.common.types import GraphNode
from coruscant.exposure import queries as Q
from coruscant.knowledge_graph.memory import InMemoryKnowledgeGraphStore
from coruscant.knowledge_graph.resolution import Resolver, Verdict
from coruscant.knowledge_graph.substrate import AccessTier
from coruscant.screening.pipeline import (
    CANDIDATE,
    SANCTIONED,
    WATCHLIST_KIND,
    screen_people,
)
from coruscant.screening.provider import (
    DeterministicScreeningProvider,
    ScreeningQuery,
    WatchlistRecord,
    load_opensanctions,
    normalize_name,
)


def _person(store: InMemoryKnowledgeGraphStore, key: str, name: str, **props: object) -> None:
    store.upsert_node(GraphNode(kind="Person", key=key, properties={"name": name, **props}))


def _record(rid: str, name: str, **kw: object) -> WatchlistRecord:
    return WatchlistRecord(id=rid, name=name, **kw)  # type: ignore[arg-type]


def test_normalize_name_folds_case_and_diacritics() -> None:
    assert normalize_name("Nicolás Maduro Moros") == "nicolas maduro moros"
    assert normalize_name("SBERBANK  of  Russia, PJSC") == "sberbank of russia pjsc"


def test_scorer_is_order_insensitive_but_not_reckless() -> None:
    provider = DeterministicScreeningProvider([_record("r1", "John Smith", topics=["sanction"])])
    # Same tokens, reversed order → strong candidate.
    reversed_order = provider.screen([ScreeningQuery(kind="Person", key="p", name="Smith John")])
    assert reversed_order and reversed_order[0].score >= 0.95
    # A merely-similar different name is not surfaced above the floor.
    unrelated = provider.screen([ScreeningQuery(kind="Person", key="p", name="Jane Doe")])
    assert unrelated == []


def test_name_only_match_never_auto_confirms() -> None:
    # The "Wang Wei" problem: a perfect name match with no corroboration must NOT
    # become a sanctioned/pep edge — it goes to human review instead.
    store = InMemoryKnowledgeGraphStore()
    _person(store, "wang-wei", "Wang Wei")
    provider = DeterministicScreeningProvider([_record("os-1", "Wang Wei", topics=["sanction"])])
    resolver = Resolver()

    summary = screen_people(store, provider, resolver, observed_at="2026-07-01")
    assert summary.confirmed == 0 and summary.needs_review == 1
    assert store.edges_by_relation(SANCTIONED) == []  # no fabricated hit
    candidates = store.edges_by_relation(CANDIDATE)
    assert len(candidates) == 1 and candidates[0].properties["review_status"] == "needs-review"
    # The judgement is recorded reversibly, as undecided.
    assert list(resolver.current().values())[0].verdict is Verdict.UNDECIDED


def test_corroborated_match_confirms_and_writes_typed_edge() -> None:
    store = InMemoryKnowledgeGraphStore()
    _person(store, "nicolas-maduro", "Nicolás Maduro", country="Venezuela")
    provider = DeterministicScreeningProvider(
        [_record("os-9", "Nicolas Maduro", topics=["sanction", "role.pep"],
                 countries=["Venezuela"], first_seen="2017-08-01T00:00:00")]
    )
    resolver = Resolver()

    summary = screen_people(store, provider, resolver, observed_at="2026-07-01")
    assert summary.confirmed == 1
    assert summary.sanctioned == 1 and summary.pep == 1  # both topics → both edges
    sanctioned = store.edges_by_relation(SANCTIONED)[0]
    assert sanctioned.properties["review_status"] == "confirmed"
    assert sanctioned.properties["access_tier"] == AccessTier.PUBLIC.value
    assert sanctioned.properties["valid_from"] == "2017-08-01"  # bitemporal from first_seen
    assert store.get_node(WATCHLIST_KIND, sanctioned.target_key) is not None
    assert list(resolver.current().values())[0].verdict is Verdict.SAME


def test_form4_insider_needs_higher_bar() -> None:
    # A reversed-order corroborated match (score 0.98) auto-confirms for an officer
    # but is held for review for a Form-4 insider — a different base rate (§4.3).
    provider = DeterministicScreeningProvider(
        [_record("os-2", "Smith John", topics=["sanction"], countries=["US"])]
    )
    officer = InMemoryKnowledgeGraphStore()
    _person(officer, "john-smith", "John Smith", country="US", source="sec-10k-officers")
    assert screen_people(officer, provider, Resolver(), observed_at="2026-07-01").confirmed == 1

    insider = InMemoryKnowledgeGraphStore()
    _person(insider, "john-smith", "John Smith", country="US", source="sec-form4")
    insider_summary = screen_people(insider, provider, Resolver(), observed_at="2026-07-01")
    assert insider_summary.confirmed == 0 and insider_summary.needs_review == 1


def test_screening_overview_honest_states_and_tier_and_asof() -> None:
    store = InMemoryKnowledgeGraphStore()
    # Before any run: connected is false, never a placeholder.
    assert Q.screening_overview(store).connected is False

    _person(store, "nicolas-maduro", "Nicolás Maduro", country="Venezuela")
    _person(store, "wang-wei", "Wang Wei")
    provider = DeterministicScreeningProvider([
        _record("os-9", "Nicolas Maduro", topics=["sanction"], countries=["Venezuela"],
                first_seen="2017-08-01T00:00:00"),
        _record("os-1", "Wang Wei", topics=["sanction"]),
    ])
    screen_people(store, provider, Resolver(), observed_at="2026-07-01")

    overview = Q.screening_overview(store)
    assert overview.connected is True and overview.screened == 2
    assert overview.sanctioned == 1 and len(overview.confirmed) == 1
    assert len(overview.needs_review) == 1

    # Bitemporal: before the listing began, the confirmed hit does not apply.
    earlier = Q.screening_overview(store, as_of="2016-01-01")
    assert earlier.sanctioned == 0
    # Access tier: a caller below the edge's tier sees nothing (all screening data
    # is public here, so public sees it; a hypothetical stricter tier would hide it).
    assert Q.screening_overview(store, clearance=AccessTier.PUBLIC).sanctioned == 1


def test_load_opensanctions_parses_ftm_shapes(tmp_path: Path) -> None:
    # A JSON array (fixture shape) and JSON-lines (bulk shape) both parse.
    rows = [
        {"id": "Q1", "schema": "Person", "caption": "Ada Lovelace",
         "properties": {"name": ["Ada Lovelace", "Augusta Ada King"], "topics": ["role.pep"],
                        "country": ["gb"], "birthDate": ["1815-12-10"]},
         "datasets": ["everypolitician"], "first_seen": "2020-01-01T00:00:00"},
    ]
    array_path = tmp_path / "a.json"
    array_path.write_text(json.dumps(rows))
    lines_path = tmp_path / "b.jsonl"
    lines_path.write_text("\n".join(json.dumps(r) for r in rows))

    for path in (array_path, lines_path):
        records = load_opensanctions(path)
        assert len(records) == 1
        rec = records[0]
        assert rec.name == "Ada Lovelace" and "Augusta Ada King" in rec.aliases
        assert rec.is_pep() and not rec.is_sanctioned()
        assert rec.countries == ["gb"] and rec.birth_date == "1815-12-10"
        assert rec.source_url == "https://www.opensanctions.org/entities/Q1/"


def test_empty_dataset_provider_is_disconnected() -> None:
    assert DeterministicScreeningProvider([]).connected() is False
