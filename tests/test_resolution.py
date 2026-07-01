"""The reversible resolver: merge-resistant clustering, reversibility, stable ids."""

from __future__ import annotations

from coruscant.knowledge_graph.memory import InMemoryKnowledgeGraphStore
from coruscant.knowledge_graph.resolution import (
    CANONICAL_ID,
    CANONICAL_KIND,
    RESOLVES_TO,
    Resolver,
    Verdict,
    cluster,
    pinned_from_store,
    project_canonical,
)

A = ("Company", "a")
B = ("Company", "b")
C = ("Company", "c")
D = ("Company", "d")


def _clusters_of(result) -> list[frozenset]:  # type: ignore[no-untyped-def]
    return sorted((c for c in result.clusters if len(c) >= 2), key=lambda c: sorted(c))


def test_current_supersedes_earlier_judgement() -> None:
    r = Resolver()
    r.decide(A, B, Verdict.SAME, decided_at="2026-01-01", score=0.95)
    r.decide(A, B, Verdict.DIFFERENT, decided_at="2026-06-01", note="reviewer split them")
    effective = list(r.current().values())
    assert len(effective) == 1
    assert effective[0].verdict is Verdict.DIFFERENT  # latest wins


def test_clustering_is_merge_resistant_not_connected_components() -> None:
    # A~B and B~C at 0.9 each, but A is explicitly DIFFERENT from C. Connected
    # components would fuse all three; we must not fabricate an A~C link.
    r = Resolver()
    r.decide(A, B, Verdict.SAME, decided_at="2026-01-01", score=0.9)
    r.decide(B, C, Verdict.SAME, decided_at="2026-01-01", score=0.9)
    r.decide(A, C, Verdict.DIFFERENT, decided_at="2026-01-02")
    result = cluster(r)
    clusters = _clusters_of(result)
    assert clusters == [frozenset({A, B})]  # C is held out; the bridge is broken
    assert C not in result.canonical_id or result.canonical_id.get(C) != result.canonical_id[A]
    assert (B, C) in result.blocked or (C, B) in result.blocked


def test_retraction_reverses_a_merge() -> None:
    r = Resolver()
    r.decide(A, B, Verdict.SAME, decided_at="2026-01-01", score=0.99)
    assert _clusters_of(cluster(r)) == [frozenset({A, B})]
    r.retract(A, B, decided_at="2026-02-01")  # never a delete — a superseding judgement
    assert _clusters_of(cluster(r)) == []
    assert len(r.log) == 2  # the audit trail keeps both


def test_canonical_id_is_stable_across_re_resolution() -> None:
    r = Resolver()
    r.decide(A, B, Verdict.SAME, decided_at="2026-01-01", score=0.95)
    first = cluster(r)
    pinned_id = first.canonical_id[A]
    assert first.canonical_id[B] == pinned_id

    # Registries update: a new member D joins the cluster overnight.
    r.decide(A, D, Verdict.SAME, decided_at="2026-06-01", score=0.9)
    second = cluster(r, pinned={A: pinned_id, B: pinned_id})
    assert second.canonical_id[A] == pinned_id  # the bookmark did not move
    assert second.canonical_id[D] == pinned_id  # the newcomer joins the existing id


def test_manual_same_without_score_is_full_confidence() -> None:
    r = Resolver()
    r.decide(A, B, Verdict.SAME, decided_at="2026-01-01")  # no score
    assert _clusters_of(cluster(r, min_score=0.8)) == [frozenset({A, B})]


def test_persistence_roundtrip() -> None:
    r = Resolver()
    r.decide(A, B, Verdict.SAME, decided_at="2026-01-01", score=0.9, method="deterministic-name-v1")
    restored = Resolver.from_list(r.to_list())
    assert restored.to_list() == r.to_list()
    assert list(restored.current().values())[0].method == "deterministic-name-v1"


def test_project_canonical_writes_cluster_node_and_stamps_members() -> None:
    store = InMemoryKnowledgeGraphStore()
    for kind, key in (A, B, C):
        from coruscant.common.types import GraphNode
        store.upsert_node(GraphNode(kind=kind, key=key, properties={"name": key.upper()}))
    r = Resolver()
    r.decide(A, B, Verdict.SAME, decided_at="2026-01-01", score=0.95)
    result = cluster(r)

    projected = project_canonical(store, result, observed_at="2026-07-01")
    assert projected == 1
    cid = result.canonical_id[A]
    assert store.get_node(CANONICAL_KIND, cid) is not None
    assert store.get_node(*A).properties[CANONICAL_ID] == cid  # type: ignore[union-attr]
    assert store.get_node(*C).properties.get(CANONICAL_ID) is None  # singleton untouched
    resolves = store.edges_by_relation(RESOLVES_TO)
    assert {(e.source_kind, e.source_key) for e in resolves} == {A, B}

    # Re-reading the stamped ids reproduces the pin, so the next run is stable.
    assert pinned_from_store(store) == {A: cid, B: cid}
