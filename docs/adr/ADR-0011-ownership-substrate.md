# ADR-0011: Ownership substrate (owns / beneficial_owner_of / consolidates)

## Status

Accepted (2026-07-02). The first realization of Phase 3 in
[global-exposure-architecture.md](../global-exposure-architecture.md) — "real ownership
edges, the missing substrate." Rides on the edge substrate from
[ADR-0007](ADR-0007-entity-resolution-spine.md) (`access_tier` + bitemporal stamping),
reusing it verbatim. This is a **foundation**, not a completeness claim: it introduces
the ownership edge classes the graph has never had and the ingestion seam for them; it
does **not** yet fold shareholding into beneficial ownership, nor fetch live national
registers.

## Context

The graph had no ownership primitive. `has_subsidiary` (Exhibit 21) is a bare list of
subsidiary *names* — no holder, no percentage, no direction (architecture §1). 13F gave
us `Fund -holds-> Company` (a portfolio primitive), but not who *controls* a company.
Closing the exposure loop ("an event on an owner → my holding two hops down") needs an
ownership class, and the product's honesty bar makes *how* we model it load-bearing.

The single most dangerous mistake here is **conflation**: treating a declared
%-shareholding, a natural person's ultimate beneficial ownership, and accounting
consolidation as the same edge. They are different claims, from different sources, with
different access rules (architecture §2.4, §2.7):

- **Declared shareholding** — a disclosed %-stake (SEC 13D/G, a BODS entity interest).
  Public.
- **Beneficial ownership** — the natural person who ultimately owns/controls (UK PSC,
  a BODS person statement). Access-restricted post-CJEU C-37/20 (EU public BO access
  collapsed; AMLR restores only legitimate-interest access).
- **Accounting consolidation** — a parent consolidates a subsidiary (GLEIF L2 "ultimate
  parent"). Public, and explicitly **not** a %-ownership figure.

## Decision

Model ownership as **three distinct edge relations**, selected by an explicit
`OwnershipBasis`, `holder --relation--> subject` (owner/parent → owned/subsidiary):

| basis | relation | default access tier |
|---|---|---|
| `declared_shareholding` | `owns` | `public` |
| `beneficial_owner` | `beneficial_owner_of` | `legitimate-interest` |
| `accounting_consolidation` | `consolidates` | `public` |

- **A provider seam** (`OwnershipProvider`) mirrors coverage/screening/anchoring:
  `list_ownership() -> list[OwnershipRecord]`. `BodsOwnershipProvider` parses the
  **Beneficial Ownership Data Standard** (OpenOwnership; UK PSC exports map to it) — a
  natively statement-based format, the reference implementation of "no edge without
  evidence." `StaticOwnershipProvider` is the hermetic test double and the carrier for
  non-BODS records (e.g. a GLEIF-L2 consolidation seed).
- **Every edge is substrate-stamped** (`coruscant.knowledge_graph.substrate`): `source`
  (Invariant #1), `access_tier` **enforced at query time** (a public caller does not see
  `beneficial_owner_of`; it is reported only as a `restricted` count — existence is
  transparent, content is gated), and bitemporal validity (`valid_from`/`valid_to`) so
  "who controlled it *on date D*?" is answerable.
- **No fabricated magnitude.** `percentage` is set only when the source states an exact
  figure; a disclosed range becomes a `percentage_band` (`"25%-50%"`) verbatim; a
  statement with neither carries no percentage. Never invented.
- **Enrich, don't duplicate.** Parties resolve to existing nodes by external anchor
  (LEI/CIK/ISIN), reusing the covered/curated node; the rest get a stable surrogate
  labelled `ownership_status: unresolved` and are **counted** (`subjects_unresolved` /
  `holders_unresolved`) — a labelled gap, never a fabricated identity.
- **No derivation.** A 75%-shareholding is recorded as `owns`, not silently promoted to
  `beneficial_owner_of`. Turning a chain of shareholdings into an ultimate beneficial
  owner is deliberate future work, not a hidden inference here.
- Idempotent: edges dedup on identity (the store's edge contract); an `OwnershipRun`
  node records the per-run summary. Exposed via `GET /graph/ownership` (overview) and
  `GET /graph/company/{key}/owners` (as-of aware), plus `coruscant ownership --file`.

## Consequences

- The three relations round-trip through the generic JSON→Kùzu store with no schema
  migration (single `Node`/`Edge` tables), like every other edge.
- Beneficial ownership is enforced-restricted from day one, so the 2025–26 access shock
  (CTA/EU BO lockdown) is a policy the query gate already honors — a compliance asset,
  not a retrofit.
- Sets up UBO/contagion: "owner of my holding" is now a graph traversal away; the
  chain-following inference can be added *on top of* these edges without new substrate.
- The percentage/band split means aggregate "control %" math must treat bands honestly
  (a range, not a point) — pushed to the future magnitude work, not faked now.

## Alternatives considered

- **One `owns` edge with an `ownership_type` property** — rejected: conflation risk is
  the whole hazard; a single relation invites a query that sums shareholding and
  beneficial control together. Distinct relations make the wrong query impossible to
  write by accident.
- **Derive beneficial ownership from shareholding at ingest** — rejected: that is an
  inference with real false-positive risk (nominee/intermediary chains); it must be an
  explicit, evidence-carrying step, not a silent equation.
- **Percentage as a single nullable float** — rejected: PSC/BODS disclose *bands*;
  coercing a 25–50% band to a point fabricates precision. Keep the band verbatim.
- **Public beneficial-owner edges** — rejected: violates §2.7 and the post-CJEU access
  regime; default the tier to legitimate-interest and enforce it.

## Date

2026-07-02
