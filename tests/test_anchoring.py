"""GLEIF LEI anchoring: the precision gate, no over-merge, honest unresolved."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from coruscant.anchoring.pipeline import (
    HAS_LEI,
    LEGAL_ENTITY_KIND,
    anchor_entities,
)
from coruscant.anchoring.provider import (
    AnchorQuery,
    GleifApiProvider,
    LeiRecord,
    LocalGleifProvider,
    load_gleif,
)
from coruscant.common.types import GraphNode
from coruscant.exposure import queries as Q
from coruscant.knowledge_graph.memory import InMemoryKnowledgeGraphStore
from coruscant.knowledge_graph.resolution import Resolver, Verdict


def _lei(lei: str, name: str, **kw: object) -> LeiRecord:
    kw.setdefault("status", "ACTIVE")
    return LeiRecord(lei=lei, name=name, **kw)  # type: ignore[arg-type]


def _company(store: InMemoryKnowledgeGraphStore, key: str, name: str) -> None:
    store.upsert_node(GraphNode(kind="Company", key=key, properties={"name": name}))


def _subsidiary(store: InMemoryKnowledgeGraphStore, key: str, name: str, jurisdiction: str) -> None:
    store.upsert_node(GraphNode(kind="Subsidiary", key=key,
                                properties={"name": name, "jurisdiction": jurisdiction}))


def test_company_core_name_match_confirms_and_enriches() -> None:
    store = InMemoryKnowledgeGraphStore()
    _company(store, "apple", "Apple")  # our label vs the legal name
    provider = LocalGleifProvider([
        _lei("HWUPKR0MPOU8FGXBT394", "Apple Inc.", country="US", registered_at="2012-06-06"),
        _lei("OTHER0000000000000000", "Apple Ford, Inc.", country="US"),  # look-alike, must lose
    ])
    resolver = Resolver()

    summary = anchor_entities(store, provider, resolver, observed_at="2026-07-01")
    assert summary.resolved == 1 and summary.companies_resolved == 1
    node = store.get_node("Company", "apple")
    assert node is not None and node.properties["lei"] == "HWUPKR0MPOU8FGXBT394"
    assert node.properties["lei_status"] == "resolved"
    edge = store.edges_by_relation(HAS_LEI)[0]
    assert edge.target_key == "HWUPKR0MPOU8FGXBT394"
    assert edge.properties["valid_from"] == "2012-06-06"  # bitemporal from LEI registration
    assert edge.properties["access_tier"] == "public"
    assert store.get_node(LEGAL_ENTITY_KIND, "HWUPKR0MPOU8FGXBT394") is not None
    assert list(resolver.current().values())[0].verdict is Verdict.SAME


def test_lookalike_never_over_merges() -> None:
    # "Apple" must not anchor to "Apple Ford, Inc." — the core differs.
    store = InMemoryKnowledgeGraphStore()
    _company(store, "apple", "Apple")
    provider = LocalGleifProvider([_lei("FORD00000000000000000", "Apple Ford, Inc.", country="US")])
    summary = anchor_entities(store, provider, Resolver(), observed_at="2026-07-01")
    assert summary.resolved == 0  # subset (0.90) is below the confirm floor
    assert store.edges_by_relation(HAS_LEI) == []


def test_inactive_lei_is_not_confirmed() -> None:
    store = InMemoryKnowledgeGraphStore()
    _company(store, "apple", "Apple")
    provider = LocalGleifProvider([_lei("DEAD0000000000000000", "Apple Inc.", status="LAPSED", country="US")])
    summary = anchor_entities(store, provider, Resolver(), observed_at="2026-07-01")
    assert summary.resolved == 0 and summary.review == 1  # candidate, not a confirmation


def test_subsidiary_needs_jurisdiction_corroboration() -> None:
    provider = LocalGleifProvider([_lei("SUB000000000000000AE", "Aearo Technologies LLC", country="US")])

    # Jurisdiction agrees (Delaware → US) → confirmed.
    ok = InMemoryKnowledgeGraphStore()
    _subsidiary(ok, "aearo", "Aearo Technologies LLC", "Delaware")
    assert anchor_entities(ok, provider, Resolver(), observed_at="2026-07-01").subsidiaries_resolved == 1

    # Same name, wrong country (record is US, sub says Germany) → held for review.
    bad = InMemoryKnowledgeGraphStore()
    _subsidiary(bad, "aearo", "Aearo Technologies LLC", "Germany")
    summary = anchor_entities(bad, provider, Resolver(), observed_at="2026-07-01")
    assert summary.resolved == 0 and summary.review == 1


def test_unmatched_node_is_labelled_unresolved_not_dropped() -> None:
    store = InMemoryKnowledgeGraphStore()
    _company(store, "obscure", "Totally Unlisted Private Co")
    summary = anchor_entities(store, LocalGleifProvider([]), Resolver(), observed_at="2026-07-01")
    assert summary.unresolved == 1
    node = store.get_node("Company", "obscure")
    assert node is not None and node.properties["lei_status"] == "unresolved"  # labelled, still present


def test_resolution_overview_states_and_asof() -> None:
    store = InMemoryKnowledgeGraphStore()
    assert Q.resolution_overview(store).connected is False  # honest, before any run

    _company(store, "apple", "Apple")
    _subsidiary(store, "obscure-sub", "Obscure Holdings LLC", "Nowhere")
    provider = LocalGleifProvider([_lei("HWUPKR0MPOU8FGXBT394", "Apple Inc.", country="US",
                                        registered_at="2012-06-06")])
    anchor_entities(store, provider, Resolver(), observed_at="2026-07-01")

    ov = Q.resolution_overview(store)
    assert ov.connected and ov.considered == 2 and ov.resolved == 1 and ov.unresolved == 1
    assert len(ov.anchors) == 1 and ov.anchors[0].lei == "HWUPKR0MPOU8FGXBT394"
    # Bitemporal: before the LEI existed, the anchor edge does not apply.
    assert Q.resolution_overview(store, as_of="2010-01-01").resolved == 0


def test_load_gleif_parses_api_envelope_and_record_list(tmp_path: Path) -> None:
    api_shape = {"data": [{
        "type": "lei-records", "id": "HWUPKR0MPOU8FGXBT394",
        "attributes": {"lei": "HWUPKR0MPOU8FGXBT394",
                       "entity": {"legalName": {"name": "Apple Inc."},
                                  "legalAddress": {"country": "US"}, "jurisdiction": "US-CA",
                                  "status": "ACTIVE"},
                       "registration": {"initialRegistrationDate": "2012-06-06T00:00:00Z"}}}]}
    env = tmp_path / "api.json"
    env.write_text(json.dumps(api_shape))
    records = load_gleif(env)
    assert len(records) == 1 and records[0].lei == "HWUPKR0MPOU8FGXBT394"
    assert records[0].name == "Apple Inc." and records[0].country == "US"
    assert records[0].registered_at == "2012-06-06" and records[0].is_active()

    simple = tmp_path / "list.json"
    simple.write_text(json.dumps([{"lei": "X", "name": "Beta Ltd", "country": "GB"}]))
    assert load_gleif(simple)[0].name == "Beta Ltd"


def test_gleif_api_provider_builds_request_and_parses(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    captured: dict[str, str] = {}
    payload = {"data": [{"attributes": {"lei": "HWUPKR0MPOU8FGXBT394",
               "entity": {"legalName": {"name": "Apple Inc."}, "legalAddress": {"country": "US"},
                          "status": "ACTIVE"},
               "registration": {"initialRegistrationDate": "2012-06-06T00:00:00Z"}}}]}

    class _Resp:
        def read(self) -> bytes:
            return json.dumps(payload).encode()

        def __enter__(self) -> "_Resp":
            return self

        def __exit__(self, *exc: object) -> bool:
            return False

    def fake_urlopen(req, timeout=None):  # type: ignore[no-untyped-def]
        captured["url"] = req.full_url
        return _Resp()

    with patch("coruscant.anchoring.provider.urlopen", fake_urlopen):
        matches = GleifApiProvider(fuzzy=False).resolve(
            [AnchorQuery(kind="Company", key="apple", name="Apple")]
        )
    assert "filter%5Bentity.legalName%5D=Apple" in captured["url"] or "legalName" in captured["url"]
    assert len(matches) == 1 and matches[0].record.lei == "HWUPKR0MPOU8FGXBT394"


def test_gleif_fuzzy_fallback_resolves_sec_conformed_name() -> None:
    # Our SEC-conformed "Microsoft Corp" misses the strict legalName filter, but
    # fuzzycompletions surfaces "MICROSOFT CORPORATION" (core-match) → confirmed.
    lei = "INR2EJN1ERAN0W5ZP974"

    def route(req, timeout=None):  # type: ignore[no-untyped-def]
        url = req.full_url
        if "fuzzycompletions" in url:
            payload = {"data": [
                {"attributes": {"value": "MICROSOFT CORPORATION"},
                 "relationships": {"lei-records": {"data": {"id": lei}}}},
                {"attributes": {"value": "MICROSOFT CORPORATION (INDIA) PRIVATE LIMITED"},
                 "relationships": {"lei-records": {"data": {"id": "OTHER000000000000000"}}}},
            ]}
        elif f"lei-records/{lei}" in url:
            payload = {"data": {"attributes": {"lei": lei,
                       "entity": {"legalName": {"name": "MICROSOFT CORPORATION"},
                                  "legalAddress": {"country": "US"}, "status": "ACTIVE"},
                       "registration": {"initialRegistrationDate": "2012-08-08T00:00:00Z"}}}}
        else:  # strict legalName filter finds nothing for the conformed name
            payload = {"data": []}

        class _R:
            def read(self) -> bytes:
                return json.dumps(payload).encode()

            def __enter__(self):  # type: ignore[no-untyped-def]
                return self

            def __exit__(self, *e: object) -> bool:
                return False

        return _R()

    with patch("coruscant.anchoring.provider.urlopen", route):
        matches = GleifApiProvider().resolve(
            [AnchorQuery(kind="Company", key="msft", name="Microsoft Corp")]
        )
    # Only the core-matching completion is fetched + confirmed; the India sub is dropped.
    assert len(matches) == 1 and matches[0].record.lei == lei
    assert matches[0].score >= 0.97
