"""UBO chain-following and group/UBO contagion over the ownership substrate.

Two traversals built *on top of* the three distinct ownership edge types
(``owns`` / ``beneficial_owner_of`` / ``consolidates``) laid down by
:mod:`coruscant.ownership.pipeline` — never new substrate, and never a silent
inference (ADR-0011 was explicit that turning shareholding into beneficial ownership
must be a deliberate, evidence-carrying step):

* **Ownership chains** (:func:`ownership_chains`) — follow the *incoming* ownership
  edges upward from a company to its owners, and their owners, producing evidence-
  carrying chains. Each hop keeps its own ``relation``/``basis``: a chain does NOT
  collapse a declared shareholding into beneficial ownership. A chain is only
  ``terminal="beneficial_owner"`` when the top hop is *literally* a
  ``beneficial_owner_of`` edge (the data says a natural person controls) — otherwise
  it is a declared ``root``, an ``unresolved`` link, a ``cycle``, a depth cutoff, or
  ``restricted`` (a hop the caller's clearance withholds). We never assert an
  *ultimate* beneficial owner the data does not state; a chain is a path of distinct
  claims, not a derived conclusion.

* **Group / UBO contagion** (:func:`group_contagion`) — a *separate* exposure path
  from ordinary ownership edges: given a directly-exposed company, the other
  companies in its ownership group (reachable *undirected* through owns/consolidates/
  beneficial-owner edges — e.g. two companies sharing one beneficial owner) inherit
  exposure. Direct and inherited exposure are kept visibly distinct, and every
  inherited hit carries the ownership evidence chain that links it back to the seed.
  This never rewrites or collapses the underlying edges.

Everything is access-tier and as-of aware, reusing :mod:`coruscant.knowledge_graph.substrate`.
"""

from __future__ import annotations

from collections import deque
from datetime import date

from pydantic import BaseModel

from coruscant.common.types import GraphEdge
from coruscant.knowledge_graph import substrate
from coruscant.exposure.queries import EntityRef
from coruscant.knowledge_graph.store import KnowledgeGraphStore

# Mirrors coruscant.ownership.pipeline (kept local so this layer stays independent of
# the ingestion layer, exactly as queries.py mirrors the screening/anchoring vocab).
OWNS = "owns"
BENEFICIAL_OWNER_OF = "beneficial_owner_of"
CONSOLIDATES = "consolidates"
_OWNERSHIP_RELATIONS = (OWNS, BENEFICIAL_OWNER_OF, CONSOLIDATES)
_OWNERSHIP_STATUS = "ownership_status"  # "unresolved" on a surrogate we could not anchor

# Chain terminal classes. resolved = a natural end (a stated beneficial owner, or a
# declared root with no owner above); the rest are honest incompletenesses.
_T_BENEFICIAL = "beneficial_owner"
_T_ROOT = "root"
_T_UNRESOLVED = "unresolved"
_T_CYCLE = "cycle"
_T_MAX_DEPTH = "max_depth"
_T_RESTRICTED = "restricted"
_RESOLVED_TERMINALS = (_T_BENEFICIAL, _T_ROOT)


def _name(store: KnowledgeGraphStore, kind: str, key: str) -> str:
    node = store.get_node(kind, key)
    if node is not None and isinstance(node.properties.get("name"), str):
        return str(node.properties["name"])
    return key


def _ref(store: KnowledgeGraphStore, kind: str, key: str) -> EntityRef:
    return EntityRef(kind=kind, key=key, name=_name(store, kind, key))


def _str(props: dict[str, object], key: str) -> str | None:
    value = props.get(key)
    return value if isinstance(value, str) else None


def _is_unresolved(store: KnowledgeGraphStore, kind: str, key: str) -> bool:
    node = store.get_node(kind, key)
    return node is not None and node.properties.get(_OWNERSHIP_STATUS) == "unresolved"


# -- UBO chain-following -------------------------------------------------------


class ChainLink(BaseModel):
    """One hop of an ownership chain: ``holder`` has an interest of ``relation`` in
    ``subject``, with the sourced evidence. Each hop keeps its own basis — the chain
    never conflates the three claim types."""

    holder: EntityRef
    subject: EntityRef
    relation: str  # owns | beneficial_owner_of | consolidates
    basis: str | None = None
    percentage: float | None = None
    percentage_band: str | None = None
    interest: str | None = None
    source: str | None = None
    source_url: str | None = None
    valid_from: str | None = None
    valid_to: str | None = None
    holder_resolved: bool | None = None
    access_tier: str | None = None


class OwnershipChain(BaseModel):
    """A path of ownership hops from the queried company *up* toward an owner, plus
    an honest ``terminal`` describing why it stopped. ``complete`` is true only for a
    natural terminal (a stated beneficial owner, or a declared root) — never for a
    truncation."""

    links: list[ChainLink] = []  # nearest owner first, ultimate owner last
    terminal: str  # beneficial_owner | root | unresolved | cycle | max_depth | restricted
    terminal_holder: EntityRef | None = None
    depth: int = 0
    complete: bool = False


class CompanyOwnershipChains(BaseModel):
    """Every ownership chain leading up to a company, access-tier + as-of aware.
    Counts separate resolved chains from the honest incompletenesses so the UI can
    label resolved / unresolved / restricted without inventing certainty."""

    company: EntityRef
    chains: list[OwnershipChain] = []
    resolved_chains: int = 0  # reached a stated beneficial owner or a declared root
    partial_chains: int = 0  # cut short: unresolved link, depth cap, or restricted hop
    cyclic_chains: int = 0  # a circular holding was detected and stopped
    restricted: int = 0  # chains truncated because the next hop is above the clearance
    note: str = (
        "Ownership chains are paths of distinct sourced claims (declared shareholding, "
        "beneficial ownership, consolidation), not a derived ultimate owner. A chain is "
        "labelled beneficial only where the data literally states a person's control."
    )


def _link(store: KnowledgeGraphStore, edge: GraphEdge) -> ChainLink:
    props = edge.properties
    pct = props.get("percentage")
    resolved = props.get("holder_resolved")
    return ChainLink(
        holder=_ref(store, edge.source_kind, edge.source_key),
        subject=_ref(store, edge.target_kind, edge.target_key),
        relation=edge.relation,
        basis=_str(props, "basis"),
        percentage=float(pct) if isinstance(pct, (int, float)) else None,
        percentage_band=_str(props, "percentage_band"),
        interest=_str(props, "interest"),
        source=_str(props, substrate.SOURCE),
        source_url=_str(props, "source_url"),
        valid_from=_str(props, substrate.VALID_FROM),
        valid_to=_str(props, substrate.VALID_TO),
        holder_resolved=resolved if isinstance(resolved, bool) else None,
        access_tier=substrate.tier_of(props).value,
    )


def _owner_edges(
    store: KnowledgeGraphStore,
    kind: str,
    key: str,
    *,
    clearance: substrate.AccessTier | str,
    as_of: date | str | None,
) -> tuple[list[GraphEdge], int]:
    """The ownership edges pointing *at* ``(kind, key)`` — its owners — as-of and
    tier filtered. Returns ``(visible_edges, withheld_count)`` so a chain truncated by
    access tier stays transparent (its existence counted, its content withheld)."""

    incoming = [e for e in store.incoming(kind, key) if e.relation in _OWNERSHIP_RELATIONS]
    if as_of is not None:
        incoming = substrate.as_of(incoming, on=as_of)
    visible = substrate.visible(incoming, clearance=clearance)
    return visible, len(incoming) - len(visible)


def _terminal_for(store: KnowledgeGraphStore, kind: str, key: str, last_relation: str | None) -> str:
    """Why a chain stopped at a node with no further visible owners."""

    if last_relation == BENEFICIAL_OWNER_OF or kind == "Person":
        return _T_BENEFICIAL  # a natural person's stated control — the top of a UBO chain
    if _is_unresolved(store, kind, key):
        return _T_UNRESOLVED  # a surrogate we could not anchor — we don't know who they are
    return _T_ROOT  # a resolved entity with no disclosed owner above it


def ownership_chains(
    store: KnowledgeGraphStore,
    company_key: str,
    *,
    company_kind: str = "Company",
    clearance: substrate.AccessTier | str = substrate.AccessTier.PUBLIC,
    as_of: date | str | None = None,
    max_depth: int = 8,
) -> CompanyOwnershipChains:
    """Follow ownership edges upward from a company to build evidence-carrying chains.

    A depth-first walk over *incoming* ownership edges. Cycles are detected (a holder
    already on the path stops that branch, terminal ``cycle``); an unanchored holder
    stops the branch (``unresolved``); a hop above the caller's clearance truncates
    the branch (``restricted``). No inference: the terminal is ``beneficial_owner``
    only when the top hop is a beneficial-owner edge."""

    result = CompanyOwnershipChains(company=_ref(store, company_kind, company_key))
    if store.get_node(company_kind, company_key) is None:
        return result
    max_depth = max(1, min(max_depth, 12))
    chains: list[OwnershipChain] = []

    # DFS stack: (kind, key, prefix_links, visited_keys, last_relation, depth).
    stack: list[tuple[str, str, list[ChainLink], frozenset[str], str | None, int]] = [
        (company_kind, company_key, [], frozenset({company_key}), None, 0)
    ]
    while stack:
        kind, key, prefix, visited, last_relation, depth = stack.pop()
        visible, withheld = _owner_edges(store, kind, key, clearance=clearance, as_of=as_of)
        if not visible:
            # A leaf. If this is the queried company itself (no owners at all), that is
            # the honest empty state — no chain, never a fabricated "root" edge.
            if not prefix:
                continue
            # Otherwise classify why we stopped (restricted trumps — a hidden owner exists).
            terminal = _T_RESTRICTED if withheld else _terminal_for(store, kind, key, last_relation)
            chains.append(OwnershipChain(
                links=list(prefix), terminal=terminal, terminal_holder=prefix[-1].holder,
                depth=len(prefix), complete=terminal in _RESOLVED_TERMINALS,
            ))
            continue
        for edge in visible:
            link = _link(store, edge)
            new_prefix = prefix + [link]
            holder_key = edge.source_key
            if holder_key in visited:  # circular holding — stop, labelled
                chains.append(OwnershipChain(
                    links=new_prefix, terminal=_T_CYCLE, terminal_holder=link.holder,
                    depth=len(new_prefix), complete=False,
                ))
                continue
            if depth + 1 >= max_depth:
                chains.append(OwnershipChain(
                    links=new_prefix, terminal=_T_MAX_DEPTH, terminal_holder=link.holder,
                    depth=len(new_prefix), complete=False,
                ))
                continue
            stack.append((
                edge.source_kind, holder_key, new_prefix, visited | {holder_key},
                edge.relation, depth + 1,
            ))

    # Deterministic order: shorter chains first, then by terminal, then holder name.
    chains.sort(key=lambda c: (c.depth, c.terminal, c.terminal_holder.name if c.terminal_holder else ""))
    result.chains = chains
    result.resolved_chains = sum(1 for c in chains if c.terminal in _RESOLVED_TERMINALS)
    result.cyclic_chains = sum(1 for c in chains if c.terminal == _T_CYCLE)
    result.restricted = sum(1 for c in chains if c.terminal == _T_RESTRICTED)
    result.partial_chains = sum(
        1 for c in chains if c.terminal in (_T_UNRESOLVED, _T_MAX_DEPTH, _T_RESTRICTED)
    )
    return result


# -- Group / UBO contagion -----------------------------------------------------


class ContagionHop(BaseModel):
    """One undirected step of a contagion path: from one entity to an adjacent one
    along an ownership edge, with the direction taken and the sourced evidence."""

    from_entity: EntityRef
    to_entity: EntityRef
    relation: str
    direction: str  # "up" (to an owner) | "down" (to an owned entity)
    basis: str | None = None
    source: str | None = None
    source_url: str | None = None
    access_tier: str | None = None


class ContagionMember(BaseModel):
    """A company that inherits exposure from the seed through the ownership group,
    with the evidence path back to the seed and the shared connection that links
    them (a common owner, a parent, or a subsidiary)."""

    company: EntityRef
    hops: int  # ownership hops from the seed (shortest)
    link: str  # "parent" | "subsidiary" | "shares-owner" | "group" — how it connects
    shared_owner: EntityRef | None = None  # the common holder, when the tie is a shared owner
    path: list[ContagionHop] = []  # the ownership evidence chain seed → member


class GroupContagion(BaseModel):
    """Group/UBO contagion for a directly-exposed company: the *separate* inherited-
    exposure path. ``direct`` is the seed itself; ``inherited`` are the group members
    that inherit exposure, each with its ownership evidence chain. Kept distinct from
    ordinary exposure — inherited exposure is a control-group signal, not a holding."""

    seed: EntityRef
    direct: list[EntityRef] = []  # the directly-exposed company (the seed)
    inherited: list[ContagionMember] = []  # group members with inherited exposure
    restricted: int = 0  # adjacent hops withheld by access tier (transparency)
    note: str = (
        "Inherited (group/UBO) exposure is a distinct path from a direct holding: it "
        "means shared control, traced through owns/consolidates/beneficial-owner edges. "
        "Beneficial-owner ties are withheld from unprivileged callers and only counted."
    )


def _adjacent(
    store: KnowledgeGraphStore,
    kind: str,
    key: str,
    *,
    clearance: substrate.AccessTier | str,
    as_of: date | str | None,
) -> tuple[list[tuple[str, str, ContagionHop]], int]:
    """Undirected ownership neighbours of a node: owners (``up``) and owned entities
    (``down``), tier + as-of filtered. Returns ``(neighbours, withheld)`` where each
    neighbour is ``(kind, key, hop)`` — the evidence for that step."""

    neighbours: list[tuple[str, str, ContagionHop]] = []
    withheld = 0
    incoming = [e for e in store.incoming(kind, key) if e.relation in _OWNERSHIP_RELATIONS]
    outgoing = [e for e in store.outgoing(kind, key) if e.relation in _OWNERSHIP_RELATIONS]
    if as_of is not None:
        incoming = substrate.as_of(incoming, on=as_of)
        outgoing = substrate.as_of(outgoing, on=as_of)
    withheld += len(incoming) - len(substrate.visible(incoming, clearance=clearance))
    withheld += len(outgoing) - len(substrate.visible(outgoing, clearance=clearance))
    for edge in substrate.visible(incoming, clearance=clearance):  # an owner (go up)
        neighbours.append((edge.source_kind, edge.source_key, ContagionHop(
            from_entity=_ref(store, kind, key),
            to_entity=_ref(store, edge.source_kind, edge.source_key),
            relation=edge.relation, direction="up",
            basis=_str(edge.properties, "basis"), source=_str(edge.properties, substrate.SOURCE),
            source_url=_str(edge.properties, "source_url"),
            access_tier=substrate.tier_of(edge.properties).value,
        )))
    for edge in substrate.visible(outgoing, clearance=clearance):  # an owned entity (go down)
        neighbours.append((edge.target_kind, edge.target_key, ContagionHop(
            from_entity=_ref(store, kind, key),
            to_entity=_ref(store, edge.target_kind, edge.target_key),
            relation=edge.relation, direction="down",
            basis=_str(edge.properties, "basis"), source=_str(edge.properties, substrate.SOURCE),
            source_url=_str(edge.properties, "source_url"),
            access_tier=substrate.tier_of(edge.properties).value,
        )))
    return neighbours, withheld


def _classify_link(path: list[ContagionHop]) -> tuple[str, EntityRef | None]:
    """Describe how a member connects to the seed from its evidence path: a pure
    upward path is a ``parent``, a pure downward path a ``subsidiary``, an up-then-
    down path a sibling (``shares-owner``, naming the pivot), anything else ``group``."""

    if not path:
        return "group", None
    directions = [h.direction for h in path]
    if all(d == "up" for d in directions):
        return "parent", None
    if all(d == "down" for d in directions):
        return "subsidiary", None
    # up* then down* → the pivot (last "up" target) is the shared owner.
    pivot_index = max((i for i, d in enumerate(directions) if d == "up"), default=-1)
    if pivot_index >= 0 and all(d == "down" for d in directions[pivot_index + 1:]):
        return "shares-owner", path[pivot_index].to_entity
    return "group", None


def group_contagion(
    store: KnowledgeGraphStore,
    seed_key: str,
    *,
    seed_kind: str = "Company",
    clearance: substrate.AccessTier | str = substrate.AccessTier.PUBLIC,
    as_of: date | str | None = None,
    max_hops: int = 4,
) -> GroupContagion:
    """The ownership group a directly-exposed company belongs to — its inherited-
    exposure set. Undirected BFS over ownership edges from the seed; each reached
    *company* inherits exposure and carries the shortest evidence path back. Company-
    to-company only for the inherited set (people are traversed as pivots but a person
    is not itself an exposed holding)."""

    result = GroupContagion(seed=_ref(store, seed_kind, seed_key))
    if store.get_node(seed_kind, seed_key) is None:
        return result
    result.direct = [result.seed]
    max_hops = max(1, min(max_hops, 8))

    seen: set[tuple[str, str]] = {(seed_kind, seed_key)}
    # BFS queue carries the evidence path so far.
    queue: deque[tuple[str, str, list[ContagionHop]]] = deque([(seed_kind, seed_key, [])])
    members: list[ContagionMember] = []
    total_withheld = 0
    while queue:
        kind, key, path = queue.popleft()
        if len(path) >= max_hops:
            continue
        neighbours, withheld = _adjacent(store, kind, key, clearance=clearance, as_of=as_of)
        total_withheld += withheld
        for n_kind, n_key, hop in neighbours:
            if (n_kind, n_key) in seen:
                continue
            seen.add((n_kind, n_key))
            new_path = path + [hop]
            if n_kind == "Company":  # an exposed peer in the group
                link, shared = _classify_link(new_path)
                members.append(ContagionMember(
                    company=_ref(store, n_kind, n_key), hops=len(new_path),
                    link=link, shared_owner=shared, path=new_path,
                ))
            queue.append((n_kind, n_key, new_path))

    members.sort(key=lambda m: (m.hops, m.company.name))
    result.inherited = members
    result.restricted = total_withheld
    return result
