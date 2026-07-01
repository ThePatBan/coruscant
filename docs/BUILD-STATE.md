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
- **Entity-resolution spine + PEP/sanctions screening** (ER Phase 0→1):
  a **reversible, versioned resolver** (append-only `same`/`different`/`undecided`
  judgement log; **merge-resistant** clustering — not connected-components; pinned
  `canonical_id` stable across re-resolution) with a graph projection (`Canonical`
  node + `resolves_to` edges). A **bitemporal + `access_tier` substrate** on edges
  (valid-time/system-time + a query-time tier policy filter). **Offline screening**
  behind a **swappable provider** (one graph model, precision gate, and reversible
  resolver for both): (a) a zero-dependency **deterministic** matcher (offline,
  exact/near-exact names) and (b) **yente** (OpenSanctions' scorer at scale +
  fuzzy/cross-script recall) as a Docker sidecar over HTTP
  (`docker-compose.screening.yml`, `docs/screening-runbook.md`). Precision gate: no
  name-only auto-confirm (Form-4 insiders held higher) → confirmed `pep`/`sanctioned`
  edges vs. a `screening_candidate` review queue, never a fabricated hit. `GET
  /graph/screening` (honest `connected:false` until run) + `coruscant screen
  [--provider deterministic|yente]`. Opt-in; internal-only pending the OpenSanctions
  license (gates the live yente run, not the build). See ADR-0007.
- **GLEIF LEI anchoring** (identity/keys pillar): resolve Company/Subsidiary nodes
  to a stable **LEI anchor** (never the PK) via the same provider seam — `gleif-api`
  (free, CC0 public API) or `gleif-local` (an export file). A suffix-aware org-name
  **core matcher** (our "Apple" ↔ GLEIF "Apple Inc.") with a per-kind precision
  gate: companies confirm on an exact/core match to an *active* LEI; subsidiaries
  (thin records) also need jurisdiction↔country corroboration. Confirmed → `has_lei`
  edge + `LegalEntity` anchor node + `lei` on the node; the rest are **explicitly
  `lei_status:unresolved`**, never dropped. `GET /graph/resolution` + `coruscant
  anchor [--provider gleif-api|gleif-local]`. Recall is two-pass: the strict GLEIF
  `legalName` filter, then a `fuzzycompletions` fallback for SEC-conformed names
  ("Microsoft Corp" → "MICROSOFT CORPORATION"), still core-gated so it never
  over-merges. *Live-validated:* 35/53 real companies anchored to their LEI (rest
  honestly unresolved). See ADR-0007.
- **Portfolio front door — EDGAR 13F** (Phase 2, the holding primitive): parse a
  13F-HR information table (`portfolio/thirteenf.py`) and project `Fund -holds->
  Company` edges (`portfolio/holdings.py`) — issuer names resolved with the org
  core matcher (13F names are SEC-conformed, like our nodes), multiple share-class
  lines aggregated per company, out-of-coverage positions counted (never
  fabricated). Edges carry provenance + access_tier + valid-time (13F period).
  `GET /graph/funds` + `/graph/fund/{key}`, `coruscant portfolio --cik|--file`.
  *Live-validated:* Berkshire Hathaway's 13F (90 positions) → Apple/Amex/Coca-Cola/
  Chevron resolved into the book with real aggregated values. See ADR-0008.
- **Fund-scoped exposure — the north-star query** ("an event happens; does it touch
  *this* book, and how much?"): `portfolio_exposure(fund, pathway, term)` intersects
  a pathway exposure (sector / jurisdiction / market_tier / commodity / country)
  with a fund's `holds` edges and attaches the held value; `portfolio_profile`
  gives the book's value-weighted sector/tier shape. `GET
  /graph/fund/{key}/exposure` + `/profile`. *Live:* an Energy event → Berkshire's
  Chevron ($17.5B, 12% of book); a Taiwan event → nothing (honest empty). This is
  orientation + in-book magnitude, not a P&L estimate.
- **Whole-exchange coverage — the resolvable universe** (market-plural, US-first):
  a `coverage/` module behind a **`CoverageProvider` seam** ingests the full universe
  of listed issuers as *lightweight* Company nodes (identity + exchange, **not** deep
  filings) so an uploaded book resolves. `UsEdgarCoverageProvider` reads SEC's
  `company_tickers_exchange.json` in **one request** (~10k issuers; the per-CIK
  submissions API is *not* fanned out). Reconciliation is by **CIK** (a near-perfect
  intra-US key): a match **enriches** the curated node (adds ticker/exchange/universe
  anchors, keeps curated GICS/name authoritative), a miss creates a **stable surrogate**
  `us-<cik>`; bulk issuers get `gics_status: unresolved`, never a fabricated sector.
  Per-market **anchors are generic** (`cik` now; `isin`/`sedol`/`company_number` ready)
  so India/UK are new providers, not rewrites. Idempotent (enrich last-write-wins,
  anchors first-write-wins, keys never move). A **resolve-rate** check
  (`coverage/resolve.py`) proves a brokerage CSV lands — exact ticker (punctuation-folded,
  `BRK.B`↔`BRK-B`) then org-name fallback, unmatched reported honestly. `GET
  /graph/coverage` (`coverage_overview`, counted live) + `coruscant coverage
  --market us [--file|--resolve]`. *Live-validated:* real SEC feed → 7,654 issuers
  (2,779 OTC/blank excluded + labelled) → graph 53 → **6,062 US companies**; a 12-line
  sample book resolved **10/12 (83%)** — TSLA/PLTR/GME now covered, misses honest. See
  ADR-0009.
- **Taxonomy**: full GICS hierarchy (8-digit code) + MSCI DM/EM/FM, curated and
  verified against public MSCI/S&P sources.
- **Instrument model**: commodities + debt as first-class instruments wired into
  exposure (`config/instruments.yml`).
- **Live feeds** (free, off by default, `connected:false` when off): prices
  (Yahoo), macro (World Bank + Yahoo index), news (GDELT), sector benchmark (SPDR
  sector-ETF **proxy**, not the licensed MSCI index).
- **Intelligence**: deterministic, cited change-detection / events / summaries;
  an LLM gateway + admin console (needs an API key to light up).
- **Platform**: FastAPI API, CLI (`coruscant ingest|query|serve|screen|anchor|
  portfolio`), a worker for scheduled ingestion, auth (JWT), watchlists,
  multi-tenant quotas.

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

- **User-forwarded portfolio upload** — 13F fund holdings now ingest as `holds`
  edges (above); accepting a user's own forwarded portfolio (PDF/holdings) is the
  remaining half of the front door.
- **Real ownership / UBO edges** — no parent/`owns%`/beneficial-owner edge exists;
  control is only ever an inferred, labelled proxy. (Identity is now anchored via
  GLEIF LEI; ownership %/UBO is the next substrate — Phase 3, UK PSC first.)
- **PEP / sanctions at scale + external serving** — the screen is built (deterministic
  + yente sidecar); the *live* yente run + external demo await the OpenSanctions
  license in writing.
- **Group / UBO contagion** exposure pathway (needs the ownership substrate).
- **Whole-exchange coverage beyond the US** — the US universe now ingests (above);
  India (NSE/BSE) and UK (FTSE/LSE) are the next `CoverageProvider`s (no single free
  "all companies" feed like EDGAR — equity-list CSVs + GLEIF/OpenFIGI, ISIN/SEDOL
  anchors already modelled). The universe pass is lightweight by design; deep
  filing ingestion (10-K/Exhibit-21/officers) stays curated/on-demand.
- **Commodity/debt live prices in the UI** — the price client resolves their
  symbols (CL=F, GC=F, ^TNX, LQD…) but they are not surfaced yet.
- **Licensed MSCI index data** — benchmarking uses a free ETF proxy.

## Sequenced next

1. **Real graph store** — ✅ done (Kùzu behind the port; Neo4j/Neptune deferred).
2. **Whole-exchange coverage** — ✅ US done (ADR-0009). Next: India (NSE/BSE) + UK
   (FTSE/LSE) as new `CoverageProvider`s; then auto-add on portfolio upload.
3. **Portfolio front door** — 13F → holding edges ✅ (ADR-0008); user upload next.
4. **Ownership → UBO** and **PEP/sanctions** edges (free registries first).

Full plan of record: [global-exposure-architecture.md](global-exposure-architecture.md).
