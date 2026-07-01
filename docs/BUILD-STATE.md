# Coruscant — Build State (what is actually built)

**The honest, current snapshot.** 2026-07-01. When another doc (an ADR, an
architecture diagram, a milestone) disagrees with this file about what *exists
today*, this file wins. Aspirational docs describe a destination; this one
describes the shipping system.

## Product

Portfolio-exposure intelligence — *"an event happens somewhere; does it touch my
portfolio, and how?"* Orientation over reading. **#1 rule: never fabricate** —
every relationship/number is evidence-backed; a feed that is off shows a labelled
stub (`connected: false`), never a placeholder.

Two tabs: **`/world`** (Home/World — the exposure surface) and **`/atlas`** (the
3D company graph).

## Built ✅

- **Two-tab SPA** (React + Vite + TS): World tab + Atlas 3D force graph.
- **Knowledge graph** (JSON snapshot): 53 companies (30 US · 15 UK · 8 India),
  661 Person, 152 Subsidiary, 58 Filing; GICS Industry/Sector, MarketTier,
  8 Commodity, 7 DebtInstrument, Country. Provenance on every edge.
- **Exposure engine** — 5 pathways: geographic (Exhibit-21), sector (GICS, any
  hierarchy level), market tier (MSCI DM/EM/FM), commodity (→ sector → holdings),
  debt (→ country). Network proximity via co-mention = orientation only.
- **Multi-hop traversal** — `reachable()` on the store port (native variable-length
  `SHORTEST` Cypher on Kùzu; BFS default elsewhere) powers `/graph/company-network`:
  the co-mention neighbourhood of a company out to N hops, each reached company with
  a shortest **evidence chain** (per-hop filing citation). The traversal the flat
  store couldn't do at scale; the shape the future `owns*`/`supplies*` will take.
- **Entity-resolution spine + PEP/sanctions screening** (ER Phase 0→1, PR 1 of 2):
  a **reversible, versioned resolver** (append-only `same`/`different`/`undecided`
  judgement log; **merge-resistant** clustering — not connected-components; pinned
  `canonical_id` stable across re-resolution) with a graph projection (`Canonical`
  node + `resolves_to` edges). A **bitemporal + `access_tier` substrate** on edges
  (valid-time/system-time + a query-time tier policy filter). **Offline screening**
  behind a swappable provider: a zero-dependency deterministic matcher screens the
  graph's people against an OpenSanctions export under a precision gate (no
  name-only auto-confirm; Form-4 insiders held to a higher bar) → confirmed
  `pep`/`sanctioned` edges vs. a `screening_candidate` review queue, never a
  fabricated hit. `GET /graph/screening` (honest `connected:false` until run) +
  `coruscant screen --dataset`. Opt-in; internal-only pending the OpenSanctions
  license. See ADR-0007.
- **Taxonomy**: full GICS hierarchy (8-digit code) + MSCI DM/EM/FM, curated and
  verified against public MSCI/S&P sources.
- **Instrument model**: commodities + debt as first-class instruments wired into
  exposure (`config/instruments.yml`).
- **Live feeds** (free, off by default, `connected:false` when off): prices
  (Yahoo), macro (World Bank + Yahoo index), news (GDELT), sector benchmark (SPDR
  sector-ETF **proxy**, not the licensed MSCI index).
- **Intelligence**: deterministic, cited change-detection / events / summaries;
  an LLM gateway + admin console (needs an API key to light up).
- **Platform**: FastAPI API, CLI (`coruscant ingest|query|serve`), a worker for
  scheduled ingestion, auth (JWT), watchlists, multi-tenant quotas.

## Storage (as-is)

**SQLite catalog + a Kùzu graph store behind the `KnowledgeGraphStore` port.**
- SQLite `data/coruscant.db`: catalog · intelligence · users · embeddings.
- Graph: **Kùzu** (`graph_backend="kuzu"`, the default) — an embedded, disk-based,
  Cypher-native property-graph DB (free/MIT, no server). The exposure engine + API
  query it through the port. It is the Cypher on-ramp to a future Neo4j/Neptune:
  the same queries repoint with a driver change, not a rewrite (see ADR-0001).
- `data/graph/graph.json`: the portable snapshot **ingestion writes** (via the
  in-process `InMemoryKnowledgeGraphStore`, still the ingest-side store + the
  `memory` backend / golden-parity comparator). Serving materializes the Kùzu DB
  `data/graph/graph.kz` from that snapshot, rebuilt only when the snapshot changes.
  A golden test asserts the two backends return byte-identical exposure results.
- `docker-compose.yml` runs ingest/api/web over a named volume (SQLite); local
  dev runs on the host `./data/`. `data/` and `deploy/` are gitignored; `config/`
  is the tracked default.
- *Ingest is now O(E):* the in-memory store dedups edges via an identity index
  (was O(E²) — 10k companies fell from ~110s to ~0.2s), then bulk-loads Kùzu in one
  transaction. The remaining scale ceiling is only the in-memory intermediate;
  direct-to-Kùzu `COPY` projection is the far-future step for it.

## Not built yet ❌ (say it plainly)

- **Real portfolio upload** — the 53 companies are a *sample*; real upload = EDGAR
  13F (Phase 2).
- **Real ownership / UBO edges** — no parent/`owns%`/beneficial-owner edge exists;
  control is only ever an inferred, labelled proxy.
- **PEP / sanctions** screening.
- **Group / UBO contagion** exposure pathway (needs the ownership substrate).
- **Whole-exchange coverage** — only curated names; bulk SEC/Nifty/UK/Europe
  ingestion is future work. The store now scales (Kùzu serving; O(E) ingest); the
  remaining blocker is the *connectors* (bulk registry pulls), not the store.
- **Commodity/debt live prices in the UI** — the price client resolves their
  symbols (CL=F, GC=F, ^TNX, LQD…) but they are not surfaced yet.
- **Licensed MSCI index data** — benchmarking uses a free ETF proxy.

## Sequenced next

1. **Real graph store** — ✅ done (Kùzu behind the port; Neo4j/Neptune deferred).
2. **Whole-exchange coverage** + auto-add on portfolio upload (store scales now;
   the work is the bulk-registry connectors).
3. **Portfolio front door** (13F → holding edges, then user upload).
4. **Ownership → UBO** and **PEP/sanctions** edges (free registries first).

Full plan of record: [global-exposure-architecture.md](global-exposure-architecture.md).
