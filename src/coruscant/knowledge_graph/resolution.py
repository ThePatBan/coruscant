"""Reversible, versioned entity resolution — the ER spine's core.

Adapts the shape of OpenSanctions' ``nomenklatura`` Resolver to our store: an
**append-only, versioned log** of ``same`` / ``different`` / ``undecided``
judgements between two graph entities. It is append-only because a merge you
cannot undo is a bug (§4.4): you never mutate or delete a judgement, you append a
superseding one, so the log is a full audit trail and :meth:`Resolver.current`
derives the effective state.

Two hard requirements the architecture doc calls out (§4):

* **Merge-resistant clustering, NOT connected-components.** ``A~B`` and ``B~C`` at
  0.9 does *not* imply ``A~C``; naive union would fuse unrelated entities on one
  bad bridge. :func:`cluster` unions ``same`` edges greedily by score but refuses
  any union that a ``different`` judgement forbids — a persisted ``different``
  breaks the bridge. (Optimal correlation clustering is NP-hard; this
  score-ordered constrained greedy is the honest approximation, upgraded to
  ``yente``'s solver later.)
* **Stable canonical ids across re-resolution.** A customer's bookmark cannot
  change because registries updated overnight, so a cluster reuses any
  canonical id already assigned to one of its members (:func:`cluster` takes a
  ``pinned`` map, typically :func:`pinned_from_store`); only genuinely new
  clusters mint a fresh id, deterministically from their lowest member.

The graph gets the *projection* (a ``Canonical`` node + ``resolves_to`` edges +
``canonical_id`` stamped on members via :func:`project_canonical`); the log is the
reversible source of truth it is recomputed from.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from hashlib import sha256
from typing import Any

from pydantic import BaseModel

from coruscant.knowledge_graph import substrate
from coruscant.knowledge_graph.store import KnowledgeGraphStore

EntityId = tuple[str, str]  # (kind, key)

CANONICAL_KIND = "Canonical"
RESOLVES_TO = "resolves_to"
CANONICAL_ID = "canonical_id"


class Verdict(str, Enum):
    SAME = "same"
    DIFFERENT = "different"
    UNDECIDED = "undecided"


class Judgement(BaseModel):
    """One dated assertion that two entities are/aren't the same. Immutable: to
    change your mind, append a later judgement about the same pair."""

    left_kind: str
    left_key: str
    right_kind: str
    right_key: str
    verdict: Verdict
    score: float | None = None
    method: str = "manual"
    decided_by: str = "system"
    decided_at: str  # ISO date/datetime — the version key (later supersedes earlier)
    note: str | None = None

    def endpoints(self) -> tuple[EntityId, EntityId]:
        return (self.left_kind, self.left_key), (self.right_kind, self.right_key)

    def pair(self) -> frozenset[EntityId]:
        return frozenset(self.endpoints())


def _iso(value: date | str) -> str:
    return value.isoformat() if isinstance(value, date) else value


class Resolver:
    """The append-only judgement log plus the derived, effective view."""

    def __init__(self, judgements: list[Judgement] | None = None) -> None:
        self._log: list[Judgement] = list(judgements or [])

    @property
    def log(self) -> list[Judgement]:
        return list(self._log)

    def decide(
        self,
        left: EntityId,
        right: EntityId,
        verdict: Verdict,
        *,
        decided_at: date | str,
        score: float | None = None,
        method: str = "manual",
        decided_by: str = "system",
        note: str | None = None,
    ) -> Judgement:
        if left == right:
            raise ValueError("cannot judge an entity against itself")
        judgement = Judgement(
            left_kind=left[0], left_key=left[1],
            right_kind=right[0], right_key=right[1],
            verdict=verdict, score=score, method=method,
            decided_by=decided_by, decided_at=_iso(decided_at), note=note,
        )
        self._log.append(judgement)
        return judgement

    def retract(self, left: EntityId, right: EntityId, *, decided_at: date | str,
                decided_by: str = "system", note: str | None = None) -> Judgement:
        """Undo a prior judgement by superseding it with ``undecided`` — the
        reversible-merge guarantee (§4.4), never a delete."""

        return self.decide(left, right, Verdict.UNDECIDED, decided_at=decided_at,
                            method="retraction", decided_by=decided_by, note=note)

    def current(self) -> dict[frozenset[EntityId], Judgement]:
        """The effective judgement per pair: the latest by ``decided_at`` (ties
        broken by log order, so a later append wins)."""

        effective: dict[frozenset[EntityId], Judgement] = {}
        for judgement in self._log:
            pair = judgement.pair()
            prior = effective.get(pair)
            if prior is None or judgement.decided_at >= prior.decided_at:
                effective[pair] = judgement
        return effective

    # -- persistence ----------------------------------------------------------

    def to_list(self) -> list[dict[str, Any]]:
        return [j.model_dump() for j in self._log]

    @classmethod
    def from_list(cls, data: list[dict[str, Any]]) -> "Resolver":
        return cls([Judgement.model_validate(row) for row in data])


@dataclass
class ClusterResult:
    """The merge-resistant clustering of the resolver's ``same``/``different``
    judgements, plus the stable canonical id assigned to each clustered node and
    the ``same`` edges a ``different`` constraint refused to merge."""

    clusters: list[frozenset[EntityId]] = field(default_factory=list)
    canonical_id: dict[EntityId, str] = field(default_factory=dict)
    blocked: list[tuple[EntityId, EntityId]] = field(default_factory=list)


def _mint(members: frozenset[EntityId], pinned: dict[EntityId, str]) -> str:
    existing = sorted({pinned[m] for m in members if m in pinned})
    if existing:
        return existing[0]  # reuse a pinned id → a bookmark survives re-clustering
    kind, key = min(members)
    return "cid-" + sha256(f"{kind}\x1f{key}".encode("utf-8")).hexdigest()[:12]


def cluster(
    resolver: Resolver, *, min_score: float = 0.0, pinned: dict[EntityId, str] | None = None
) -> ClusterResult:
    """Merge-resistant clusters from the resolver's current judgements.

    ``same`` edges (score ≥ ``min_score``; a manual judgement with no score counts
    as a full-confidence 1.0) are unioned in descending-score order, but a union
    is refused whenever a ``different`` judgement stands between the two
    components — the bridge-breaking that stops transitive over-merge."""

    pinned = pinned or {}
    same_edges: list[tuple[float, EntityId, EntityId]] = []
    forbidden: dict[EntityId, set[EntityId]] = {}
    for pair, judgement in resolver.current().items():
        a, b = sorted(pair)
        if judgement.verdict is Verdict.DIFFERENT:
            forbidden.setdefault(a, set()).add(b)
            forbidden.setdefault(b, set()).add(a)
        elif judgement.verdict is Verdict.SAME:
            score = 1.0 if judgement.score is None else judgement.score
            if score >= min_score:
                same_edges.append((score, a, b))
    # Descending score; deterministic endpoint tie-break so results are backend-stable.
    same_edges.sort(key=lambda e: (-e[0], e[1], e[2]))

    members: dict[EntityId, frozenset[EntityId]] = {}
    barred: dict[EntityId, set[EntityId]] = {}

    def component(node: EntityId) -> tuple[frozenset[EntityId], set[EntityId]]:
        return (members.get(node, frozenset({node})),
                barred.get(node, set(forbidden.get(node, set()))))

    blocked: list[tuple[EntityId, EntityId]] = []
    for _score, a, b in same_edges:
        ma, ba = component(a)
        mb, bb = component(b)
        if ma is mb and a in ma and b in ma:
            continue
        if (ma & bb) or (mb & ba):  # a different-constraint spans the two components
            blocked.append((a, b))
            continue
        merged = ma | mb
        merged_bar = ba | bb
        for node in merged:
            members[node] = merged
            barred[node] = merged_bar

    seen: set[frozenset[EntityId]] = set()
    result = ClusterResult(blocked=blocked)
    # Only clustered nodes (those appearing in some judgement) get an id here;
    # singletons default to being their own canonical entity.
    all_nodes: set[EntityId] = set(forbidden)
    for _s, a, b in same_edges:
        all_nodes.add(a)
        all_nodes.add(b)
    for node in sorted(all_nodes):
        comp = members.get(node, frozenset({node}))
        if comp in seen:
            continue
        seen.add(comp)
        cid = _mint(comp, pinned)
        result.clusters.append(comp)
        for member in comp:
            result.canonical_id[member] = cid
    return result


def pinned_from_store(store: KnowledgeGraphStore) -> dict[EntityId, str]:
    """Read the canonical ids already stamped on graph nodes, so re-resolution
    keeps them stable."""

    pinned: dict[EntityId, str] = {}
    for node in store.all_nodes():
        cid = node.properties.get(CANONICAL_ID)
        if isinstance(cid, str) and cid:
            pinned[(node.kind, node.key)] = cid
    return pinned


def project_canonical(
    store: KnowledgeGraphStore, result: ClusterResult, *, observed_at: date | str
) -> int:
    """Project multi-member clusters into the graph: a ``Canonical`` cluster node,
    ``resolves_to`` edges from each member, and the ``canonical_id`` stamped on the
    member nodes. Runs on the ingest-side in-memory store; the snapshot then
    carries it to the serving backend. Returns the number of clusters projected."""

    from coruscant.common.types import GraphEdge, GraphNode

    projected = 0
    for comp in result.clusters:
        if len(comp) < 2:
            continue
        cid = result.canonical_id[next(iter(comp))]
        store.upsert_node(
            GraphNode(kind=CANONICAL_KIND, key=cid,
                      properties={"name": cid, "source": "resolver", "members": len(comp)})
        )
        for kind, key in sorted(comp):
            node = store.get_node(kind, key)
            if node is not None:
                props = dict(node.properties)
                props[CANONICAL_ID] = cid
                store.upsert_node(GraphNode(kind=kind, key=key, properties=props))
            store.upsert_edge(
                GraphEdge(
                    source_kind=kind, source_key=key,
                    relation=RESOLVES_TO, target_kind=CANONICAL_KIND, target_key=cid,
                    properties=substrate.stamp(source="resolver", observed_at=observed_at),
                )
            )
        projected += 1
    return projected
