# ADR-0012: Live ownership sources, UBO chains, group contagion, GLEIF-L2 consolidation

## Status

Accepted (2026-07-02). Builds directly on [ADR-0011](ADR-0011-ownership-substrate.md)
(the three distinct ownership edge types) and reuses the edge substrate from
[ADR-0007](ADR-0007-entity-resolution-spine.md) (`access_tier` + bitemporal stamping)
verbatim. Where ADR-0011 was the *foundation* (edge classes + a BODS/static ingest
seam), this is the first **live** national source, the **traversals** on top, and an
**auxiliary** consolidation signal — all additive, no substrate change.

## Context

ADR-0011 landed the ownership edge classes but left the substrate fed only by an
operator-supplied BODS/OpenOwnership file, with no traversal and no consolidation
data. The product needs four things to make ownership *useful* without ever
compromising the honesty bar (declared ≠ beneficial ≠ consolidation; nothing
fabricated; restricted stays labelled):

1. a **live** register, not just a file drop;
2. the ability to **follow** ownership up a chain to an owner;
3. a **group/UBO contagion** view — "an event on a company in my holding's control
   group" — kept distinct from a direct holding;
4. **consolidation** ("who owns whom") coverage as a control signal.

## Decision

### 1. Live ownership — UK Companies House PSC (the highest-priority live source)

A new `CompaniesHousePscProvider` on the existing `OwnershipProvider` seam. The UK
PSC register is **public** — unlike EU member-state registers, which CJEU C-37/20
closed to the public — so an individual PSC edge is stamped `AccessTier.PUBLIC` via
the record-level `access_tier` override (a documented, per-source policy distinct
from the BODS/EU default of legitimate-interest). The load-bearing honesty rules:

- **kind → basis, never guessed**: individual → `beneficial_owner`; corporate /
  legal-person → `declared_shareholding` (the BODS person/entity split); a PSC
  *statement* ("no PSC identified") is **not** an edge (counted, never emitted).
- **super-secure PSC → withheld, not fabricated**: identity is legally protected, so
  the edge is emitted with the identity redacted and stamped `restricted-authority` —
  its existence is transparent, its content gated.
- **disclosed bands, never a fabricated exact %**: `natures_of_control` map to a
  `percentage_band` verbatim (`25%-50%`), with the `-as-firm`/`-as-trust` holding-
  vehicle suffix folded to the base band.
- **live-first**: the Public Data API (needs a free API key,
  `CORUSCANT_COMPANIES_HOUSE_API_KEY`) is the primary path and is **scoped to the
  GB-covered universe** (fetch only company numbers we can resolve against). A bulk
  PSC-snapshot NDJSON file is the operator fallback, not the default.

### 2. UBO chain-following (`GET /graph/company/{key}/ownership-chain`)

A depth-first walk over *incoming* ownership edges, in a new
`knowledge_graph.ownership_graph` module (mirrors the ownership vocab locally, like
`queries.py` mirrors screening/anchoring — the graph layer stays independent of the
ingestion layer). Each hop keeps its **own** `relation`/`basis`; a chain is a **path
of distinct sourced claims, not a derived conclusion**. The terminal is:

- `beneficial_owner` only where the top hop is *literally* a `beneficial_owner_of`
  edge — we never promote a shareholding chain to an ultimate owner;
- else `root` (a declared owner with none above), `unresolved` (an unanchored
  surrogate — we don't know who they are), `cycle` (a circular holding, detected and
  stopped), `max_depth`, or `restricted` (the next hop is above the caller's
  clearance — truncated and counted).

Access-tier + as-of aware throughout.

### 3. Group / UBO contagion (`GET /graph/company/{key}/contagion`) — a *separate* path

An undirected BFS over ownership edges from a directly-exposed seed. Reached
companies **inherit** exposure (shared control), classified `parent` / `subsidiary`
/ `shares-owner` (two companies under one beneficial owner) with the ownership
evidence chain back to the seed. Direct (`[seed]`) and inherited are kept **visibly
distinct** and this is a read-only query — it never rewrites or collapses the
underlying edges. Beneficial-owner ties are withheld-and-counted for unprivileged
callers (so a shared-person link is invisible at the public tier — honest, since you
cannot see the person).

### 4. GLEIF Level-2 consolidation (`--provider gleif-l2`) — auxiliary, not ownership

GLEIF relationship records (direct/ultimate consolidating parent) become
`consolidates` edges **only** — an accounting-consolidation claim, explicitly not a
%-ownership figure and never a beneficial-owner edge. It flows through the *same*
`ingest_ownership` pipeline, so it reconciles by LEI onto already-anchored nodes
(enrich, don't duplicate), dedups direct/ultimate duplicates, and — because it is a
distinct relation — **coexists with, and never overwrites**, a declared `owns` edge
for the same pair. Live CC0 API (scoped to anchored LEIs) or a relationship-record
file. It reconciles *with* existing anchors, it does not replace them.

### Seam + UI

- The `OwnershipProvider` protocol gains a `market` attribute (ISO-3166 alpha-2, or
  `*` for market-agnostic BODS/LEI) — mirroring `CoverageProvider`. New national
  registers drop in as market-tagged providers with **no change** to the pipeline,
  which resolves purely by anchor. No market logic lives in the core graph or UI.
- The CompanyDetailPage gains an "Ownership & control" section (owners, UBO chains,
  group contagion) with explicit **resolved / unresolved / restricted** states and
  honest empty rendering (the section is hidden when a company has no ownership
  data — surface only where it aids orientation); the World tab gains an ownership-
  overview tile.

## Consequences

- The three relations remain distinct at every layer — ingest, traversal, contagion,
  and UI — so the "sum shareholding + beneficial control together" mistake stays
  impossible to make by accident.
- Live UK PSC is a genuine feed, but coverage is a *labelled* subset (the GB-covered
  universe with an API key); absence is counted, never hidden.
- Contagion is a first-class, separate exposure path — inherited exposure is a
  control-group signal, never silently merged into a holding.
- GLEIF-L2 gives consolidation reach without pretending it is ownership.

## Alternatives considered

- **Derive an ultimate beneficial owner from the chain** — rejected (again, per
  ADR-0011): a chain terminal is `beneficial_owner` only where the data states it.
  Chain-derived UBO is deliberate future work with real false-positive risk.
- **A `contagion` edge written into the graph** — rejected: contagion is a *query*
  over ownership edges, not new substrate; materializing it would invite the
  direct/inherited conflation the product must avoid.
- **GLEIF-L2 as an `owns`/`has_lei` enrichment** — rejected: consolidation is its own
  claim; folding it into ownership or identity would blur three distinct concepts.
- **PSC beneficial owners at the EU legitimate-interest tier** — rejected for the UK:
  the UK register is public; using the record-level `access_tier` override is exactly
  the designed mechanism, and it keeps the EU/BODS default correctly restricted.

## Date

2026-07-02
