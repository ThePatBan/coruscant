"""UBO chain-following over the ownership substrate: multi-hop traversal, cycles,
partial (unresolved) chains, access-tier truncation, bitemporal as-of, and the
honesty invariant that a chain is never a *derived* ultimate owner — a beneficial-
owner terminal appears only where the data literally states a person's control.

Hermetic; edges built directly on the in-memory store via the ownership pipeline."""

from __future__ import annotations

from coruscant.common.types import GraphNode
from coruscant.knowledge_graph import substrate
from coruscant.knowledge_graph.memory import InMemoryKnowledgeGraphStore
from coruscant.exposure.ownership_graph import ownership_chains
from coruscant.ownership import (
    OwnershipBasis,
    OwnershipParty,
    OwnershipRecord,
    PartyAnchor,
    StaticOwnershipProvider,
    ingest_ownership,
)


def _co(store: InMemoryKnowledgeGraphStore, key: str, name: str, **props: object) -> None:
    store.upsert_node(GraphNode(kind="Company", key=key, properties={"name": name, **props}))


def _rec(holder: OwnershipParty, subject: OwnershipParty, basis: OwnershipBasis,
         **kw: object) -> OwnershipRecord:
    return OwnershipRecord(holder=holder, subject=subject, basis=basis,
                           source=str(kw.pop("source", "test")), **kw)  # type: ignore[arg-type]


def _party(key: str, name: str, kind: str = "Company") -> OwnershipParty:
    return OwnershipParty(name=name, kind=kind, key=key)


def _ingest(store: InMemoryKnowledgeGraphStore, records: list[OwnershipRecord]) -> None:
    ingest_ownership(store, StaticOwnershipProvider(records), observed_at="2026-07-02")


# -- multi-hop resolved chain terminating at a beneficial owner ----------------

def test_multi_hop_chain_reaches_beneficial_owner_without_inference() -> None:
    # target ← (owns 60%) mid ← (owns 100%) top ← (beneficial_owner) Jane.
    store = InMemoryKnowledgeGraphStore()
    for key, name in [("target", "Target Co"), ("mid", "Mid Co"), ("top", "Top Co")]:
        _co(store, key, name)
    store.upsert_node(GraphNode(kind="Person", key="jane", properties={"name": "Jane Owner"}))
    _ingest(store, [
        _rec(_party("mid", "Mid Co"), _party("target", "Target Co"),
             OwnershipBasis.DECLARED_SHAREHOLDING, percentage=60.0),
        _rec(_party("top", "Top Co"), _party("mid", "Mid Co"),
             OwnershipBasis.DECLARED_SHAREHOLDING, percentage=100.0),
        _rec(_party("jane", "Jane Owner", "Person"), _party("top", "Top Co"),
             OwnershipBasis.BENEFICIAL_OWNER, interest="voting-rights"),
    ])
    # Query at legitimate-interest clearance so the beneficial-owner hop is visible
    # (a BODS-style beneficial owner defaults to the restricted tier — see the tier
    # test below for the public-caller truncation).
    result = ownership_chains(store, "target", clearance=substrate.AccessTier.LEGITIMATE_INTEREST)
    assert len(result.chains) == 1
    chain = result.chains[0]
    assert chain.terminal == "beneficial_owner" and chain.complete is True
    assert result.resolved_chains == 1 and result.partial_chains == 0
    # Three hops, each keeping its OWN basis — no collapse of shareholding into
    # beneficial ownership.
    assert [hop.relation for hop in chain.links] == ["owns", "owns", "beneficial_owner_of"]
    assert [hop.basis for hop in chain.links] == [
        "declared_shareholding", "declared_shareholding", "beneficial_owner"]
    # Evidence carried: the declared percentages appear only where sourced.
    assert chain.links[0].percentage == 60.0 and chain.links[2].percentage is None
    assert chain.terminal_holder is not None and chain.terminal_holder.name == "Jane Owner"


def test_declared_only_chain_terminates_at_root_not_beneficial() -> None:
    # A chain of declared shareholdings with no beneficial-owner disclosure ends at a
    # declared ROOT — never silently promoted to a beneficial owner.
    store = InMemoryKnowledgeGraphStore()
    _co(store, "sub", "Sub Co")
    _co(store, "parent", "Parent Co")
    _ingest(store, [
        _rec(_party("parent", "Parent Co"), _party("sub", "Sub Co"),
             OwnershipBasis.DECLARED_SHAREHOLDING, percentage=80.0),
    ])
    result = ownership_chains(store, "sub")
    assert len(result.chains) == 1
    assert result.chains[0].terminal == "root" and result.chains[0].complete is True
    assert all(hop.relation == "owns" for hop in result.chains[0].links)


# -- partial chains: unresolved link -------------------------------------------

def test_unresolved_holder_yields_partial_chain() -> None:
    # target's owner is an unanchored entity (no pre-existing node) → a surrogate,
    # labelled unresolved; the chain is partial, not fabricated further.
    store = InMemoryKnowledgeGraphStore()
    _co(store, "target", "Target Co")
    _ingest(store, [
        _rec(OwnershipParty(name="Mystery Holdings", kind="Company",
                            anchor=PartyAnchor(scheme="lei", value="ZZUNKNOWN0000000000")),
             _party("target", "Target Co"), OwnershipBasis.DECLARED_SHAREHOLDING),
    ])
    result = ownership_chains(store, "target")
    assert len(result.chains) == 1
    chain = result.chains[0]
    assert chain.terminal == "unresolved" and chain.complete is False
    assert result.partial_chains == 1 and result.resolved_chains == 0
    assert chain.links[0].holder_resolved is False


# -- cycles --------------------------------------------------------------------

def test_cycle_is_detected_and_labelled() -> None:
    # A ← B ← A (a circular cross-holding). The chain stops at the repeat, labelled.
    store = InMemoryKnowledgeGraphStore()
    _co(store, "a", "A Co")
    _co(store, "b", "B Co")
    _ingest(store, [
        _rec(_party("b", "B Co"), _party("a", "A Co"), OwnershipBasis.DECLARED_SHAREHOLDING),
        _rec(_party("a", "A Co"), _party("b", "B Co"), OwnershipBasis.DECLARED_SHAREHOLDING),
    ])
    result = ownership_chains(store, "a")
    assert result.cyclic_chains >= 1
    cyclic = [c for c in result.chains if c.terminal == "cycle"]
    assert cyclic and not cyclic[0].complete
    # It terminates rather than looping forever.
    assert all(len(c.links) <= 3 for c in result.chains)


# -- access-tier truncation ----------------------------------------------------

def test_beneficial_owner_hop_truncates_chain_for_public_caller() -> None:
    # target ← (owns) mid ← (beneficial_owner, legitimate-interest) Jane.
    store = InMemoryKnowledgeGraphStore()
    _co(store, "target", "Target Co")
    _co(store, "mid", "Mid Co")
    store.upsert_node(GraphNode(kind="Person", key="jane", properties={"name": "Jane"}))
    _ingest(store, [
        _rec(_party("mid", "Mid Co"), _party("target", "Target Co"),
             OwnershipBasis.DECLARED_SHAREHOLDING),
        _rec(_party("jane", "Jane", "Person"), _party("mid", "Mid Co"),
             OwnershipBasis.BENEFICIAL_OWNER),  # defaults to legitimate-interest tier
    ])
    # Public caller: the beneficial-owner hop above Mid is withheld → chain truncated.
    public = ownership_chains(store, "target")
    assert public.restricted == 1
    truncated = [c for c in public.chains if c.terminal == "restricted"]
    # The chain reaches Mid (a declared owner of Target) but Mid's beneficial owner
    # is withheld, so it stops there — labelled restricted, not fabricated further.
    assert truncated and truncated[0].links[-1].holder.key == "mid"

    # Privileged caller sees through to Jane.
    privileged = ownership_chains(store, "target",
                                  clearance=substrate.AccessTier.LEGITIMATE_INTEREST)
    assert privileged.restricted == 0
    assert any(c.terminal == "beneficial_owner" for c in privileged.chains)


# -- bitemporal ----------------------------------------------------------------

def test_as_of_excludes_not_yet_in_force_hop() -> None:
    store = InMemoryKnowledgeGraphStore()
    _co(store, "target", "Target Co")
    _co(store, "parent", "Parent Co")
    _ingest(store, [
        _rec(_party("parent", "Parent Co"), _party("target", "Target Co"),
             OwnershipBasis.DECLARED_SHAREHOLDING, valid_from="2020-01-01"),
    ])
    # Before the interest began, there is no chain.
    early = ownership_chains(store, "target", as_of="2019-01-01")
    assert early.chains == []
    later = ownership_chains(store, "target", as_of="2021-01-01")
    assert len(later.chains) == 1


# -- honest empty --------------------------------------------------------------

def test_no_owners_is_honest_empty() -> None:
    store = InMemoryKnowledgeGraphStore()
    _co(store, "solo", "Solo Co")
    result = ownership_chains(store, "solo")
    assert result.chains == [] and result.resolved_chains == 0


def test_missing_company_returns_empty_not_error() -> None:
    store = InMemoryKnowledgeGraphStore()
    result = ownership_chains(store, "ghost")
    assert result.chains == [] and result.company.key == "ghost"
