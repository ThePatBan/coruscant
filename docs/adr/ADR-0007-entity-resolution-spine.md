# ADR-0007: The entity-resolution spine + PEP/sanctions screening

## Status

Accepted (2026-07-01). Implements Phase 0 (substrate & keys) → Phase 1 (screen
the people we already have) of
[docs/global-exposure-architecture.md](../global-exposure-architecture.md) §5, now
that the graph store (ADR-0001) is built.

**Update (PR 3, 2026-07-01):** GLEIF **LEI anchoring** landed (the identity/keys
pillar, §3). The `anchoring/` module mirrors the screening seam: `LeiProvider` with
a live `GleifApiProvider` (GLEIF's free CC0 API — no licence gate, so it runs live)
and an offline `LocalGleifProvider`. A shared `knowledge_graph/textmatch.py` adds a
suffix-aware **org-name core matcher** (our "Apple" ↔ GLEIF "Apple Inc.", while
rejecting "Apple Ford, Inc.") — the thin-record precision problem (§4.2) in
miniature. Per-kind gate: companies confirm on an exact/core match to an *active*
LEI; subsidiaries also require jurisdiction↔country corroboration. Confirmed →
`has_lei` + a `LegalEntity` anchor node + `lei` on the node + a reversible `same`
judgement; unmatched nodes are `lei_status:unresolved`, never dropped. `GET
/graph/resolution`, `coruscant anchor`. Live-validated: 27/53 real companies
anchored. The LEI is an **anchor, never the PK** (§2.2).

**Update (PR 2, 2026-07-01):** the `yente` provider is now implemented —
`YenteScreeningProvider` (a stdlib-HTTP client for yente's `/match` contract) +
`docker-compose.screening.yml` (yente + OpenSearch sidecar) + `docs/screening-runbook.md`,
selectable via `CORUSCANT_SCREENING_PROVIDER=yente`. Hermetic mock tests lock the
contract; the *live* run stays operator-executed (heavy index + the OpenSanctions
data licence gate, below). The pipeline, precision gate, resolver, and graph model
are unchanged — only the scorer improves.

## Context

Entity resolution is the load-bearing wall under every later pillar (§4): the
event→entity join, UBO traversal, and portfolio matching all fail silently
without it. The store leaves room for the substrate it needs but did not build it:
bitemporal + `access_tier` edge columns, and a reversible resolver table.

Two forces shaped the *how*:

1. **The store's model is already statement-based and generic.** Nodes/edges carry
   a free-form `properties` JSON, round-tripped verbatim through the JSON snapshot
   → Kùzu and guarded by the golden parity test. So the substrate fields are
   **property keys, not a schema migration.**
2. **`nomenklatura`/`yente` is the chosen ER spine (§4), but the library is heavy.**
   `pip install nomenklatura` pulls 21 transitive packages including `pyicu` (needs
   the ICU C library — a CI build hazard) and `scikit-learn`. This repo's entire
   runtime dependency list is six packages, and PR 1 must stay hermetic and
   Docker-free.

## Decision

**1. Reversible resolver as an append-only, versioned judgement log**
(`knowledge_graph/resolution.py`). Adopts nomenklatura's Resolver *shape* — a graph
of `same`/`different`/`undecided` judgements — but as an append-only log
(`resolver.json`): you never mutate or delete a judgement, you append a superseding
one (a merge you cannot undo is a bug, §4.4). Clustering is **merge-resistant, not
connected-components** (§4.1): `same` edges union greedily by score, but a `different`
judgement between two components refuses the union (bridge-breaking). Canonical ids
are **pinned** — a cluster reuses an id already assigned to a member, so a customer's
bookmark survives re-resolution (§4.4). The graph gets the *projection* (a
`Canonical` node + `resolves_to` edges + `canonical_id` on members); the log is the
source of truth it recomputes from. Internal surrogate id is the PK; LEI/CIK/DIN are
anchors (§2.2).

**2. Bitemporal + access-tier substrate** (`knowledge_graph/substrate.py`). Every
sensitive edge is stamped with `access_tier` (enforced by a query-time policy
filter — a tag nobody enforces is worse than none, §2.7) and valid-time +
system-time (`valid_from`/`valid_to`/`observed_at`), so "was this counterparty
sanctioned *on the transaction date*?" is answerable (§2.6). These ride as
`properties` keys — no storage migration.

**3. Screening behind a swappable provider** (`screening/`). PR 1 ships a
zero-dependency `DeterministicScreeningProvider` (stdlib name normalization →
token blocking → a conservative, precision-first score). A strict precision gate
(§4.3): **nothing auto-confirms on a name alone** — confirmation needs a
corroborating attribute (country/birth-year), and Form-4 insiders (a different PEP
base rate) clear a higher bar. Confirmed matches project typed `pep`/`sanctioned`
edges; everything else routes to human review as a labelled `screening_candidate`
edge — never a fabricated hit. `YenteScreeningProvider` marks the PR-2 seam:
OpenSanctions' `yente` (nomenklatura's scorer at scale) as a **Docker sidecar over
HTTP**, so its heavy deps live in the container, not this process.

## Consequences

- The spine runs end-to-end in CI with no service, no network, no Docker; a golden
  parity case covers every new edge type across both backends.
- Screening is opt-in (needs an OpenSanctions dataset); the panel honestly reports
  `connected: false` until one is wired, and a low/empty hit list is a real answer.
- OpenSanctions is CC-BY-NC → paid Reseller/OEM for commercial use; this gates
  *external* demo, not building. Screening is internal-only until the license is
  clarified in writing (§6).
- Full correlation clustering is NP-hard; the greedy constrained approximation is
  honest for PR 1 and is upgraded to yente's solver in PR 2.

## Alternatives considered

- **Vendor `nomenklatura` in-process** — rejected for PR 1: 21 deps incl. `pyicu`
  + `scikit-learn` breaks the hermetic, six-dependency, Docker-free CI the phase
  requires. Deferred to the yente *service* in PR 2.
- **Connected-components clustering** — rejected: transitively over-merges unrelated
  entities on one bad bridge, fabricating links no source asserts (violates §2.1).
- **A sidecar resolver store (SQLite table)** — rejected: the graph is already a
  reversible, provenance-carrying, parity-guarded statement store; modelling the
  projection as nodes/edges reuses it and the multi-hop primitive.
- **Senzing as the ER spine** — rejected (per §4): closed-box scorer, per-record
  pricing; kept only as a commercial fallback.

## Date

2026-07-01
