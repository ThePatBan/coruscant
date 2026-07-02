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

This product is **one workspace** on the Coruscant Intelligence Platform (the shared
substrate). What is platform vs what is this workspace is defined in
[PLATFORM.md](PLATFORM.md); the boundary is drawn in docs and code organization but not
yet enforced by module structure (that is later, deliberate work).

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
- **India coverage — NSE + BSE, ISIN-unified** (the seam's second market, proving it):
  `IndiaCoverageProvider` unions the NSE `EQUITY_L.csv` + BSE active-equity scrip list
  into one Company node **per ISIN** — a company dual-listed on both exchanges shares
  one ISIN, so ISIN is the intra-India dedup key *and* the NSE↔BSE unifier. One node
  carries **both** exchange symbols as anchors (NSE symbol → the `ticker` anchor so
  `resolve.py` works unchanged; numeric BSE code → a `bse_code` anchor); `exchange` ∈
  {NSE, BSE, `NSE & BSE`} makes the dual-listed overlap a first-class bucket, not a
  hidden merge. `_MARKET_IDENTITY_SCHEME["IN"]="isin"`; surrogate `in-<isin>`, stable
  across re-runs. The curated US-listed **ADRs** (`infy`, `wit`, `rdy`, …) are *not*
  merged with the domestic listing — exact-ISIN dedup can't touch them and ADR↔domestic
  reconciliation flows through the shared GLEIF LEI, never a coverage merge. **Nifty 50
  / BSE Sensex** are represented as `Index` nodes + provenance-backed `constituent_of`
  edges (Company → Index) — the "event on the Nifty → which of my holdings are in it"
  pathway (ADR-0010). ISIN resolution added to `resolve.py` (Zerodha/Groww exports key
  by ISIN or NSE symbol). `coruscant coverage --market in [--nse --bse --nifty --sensex]`.
  *Live-validated:* real NSE + BSE (JSON API) + Nifty lists → **5,035 India issuers**
  (2,223 dual-listed NSE∩BSE, 130 NSE-only, 2,682 BSE-only; 32 non-equity/blank-ISIN
  excluded + labelled) → graph 53 → **5,088 companies**; all 50 Nifty constituents
  linked; a 12-line sample book resolved **9/12 (75%)** — misses honest (a mutual fund,
  a bogus symbol, and the post-demerger-retired `TATAMOTORS` symbol, present as
  TMCV/TMPV and resolvable by ISIN). See ADR-0009 + ADR-0010.
- **UK coverage — LSE, ISIN-identified** (the third and last market on the seam):
  `UkLseCoverageProvider` parses the LSE "List of all companies" CSV into one Company
  node **per ISIN** (`gb-<isin>`), with `exchange` reflecting the segment (LSE Main
  Market vs LSE AIM). The handoff's **ISIN / SEDOL / company-number** identity set rides
  as anchors: ISIN is the identity + dedup key, the TIDM becomes the `ticker` anchor,
  and SEDOL + the Companies House number are attached **when the export carries them**,
  never fabricated. `_MARKET_IDENTITY_SCHEME["GB"]="isin"`. The curated UK **ADRs**
  (`bp`, `hsbc`, `shel`, `azn`, …, US-listed, keyed by US ticker) are *not* merged with
  the domestic LSE listing — reconciliation flows through the shared GLEIF LEI.
  **FTSE 100 / FTSE 250** are `Index` nodes + `constituent_of` edges (ADR-0010, same
  generic shape as Nifty/Sensex). **SEDOL resolution** added to `resolve.py` (UK exports
  — HL / AJ Bell — often key by SEDOL); order ticker → ISIN → SEDOL → org-name.
  `coruscant coverage --market gb [--lse --ftse100 --ftse250]` (`uk` accepted as an
  alias). The LSE site is JS-heavy (no scriptable CSV — confirmed), so the operator
  `--lse` download is the primary path, exactly like NSE's 403. *Live-validated* (mechanics
  on verified-real FTSE mega-cap identifiers; full-universe ingest is operator `--file`):
  15 real LSE issuers → all 15 FTSE 100-linked; BP carries the full isin/ticker/sedol/
  company-number anchor set while Shell carries only isin/ticker (SEDOL/reg-no absent →
  not fabricated); the `bp`/`shel`/`vod`/`azn` ADRs verified **distinct** from their
  domestic `gb-<isin>` nodes; a sample book resolved 5/7 by ticker/ISIN/SEDOL (2 honest
  misses: a unit trust and a bogus symbol). See ADR-0009 + ADR-0010.
- **US coverage hardening — multi-class tickers.** A single CIK lists several share
  classes (GOOG/GOOGL under CIK 1652044, FOX/FOXA, UA/UAA). CIK dedup collapsed them to
  one node but kept only the *first* ticker, so a book holding the second class went
  unresolved — a fabricated "unresolved", the dishonest kind. Fix: `ticker`/`figi` are
  now **multi-valued anchors** (`pipeline._merge_anchors`) that accumulate every distinct
  value while identity anchors (cik/isin/…) stay first-write-wins; `build_ticker_index`
  indexes the primary ticker **and** every ticker anchor, so each share class resolves to
  its issuer. Idempotent across re-runs. `CoverageMarketCount` now also surfaces per-market
  `created`/`enriched`/`indices` from the last run for inspection via `GET /graph/coverage`.
- **User portfolio upload — the retail front door.** `POST /portfolios/resolve` (dry-run
  preview) and `POST /portfolios/upload` (resolve + persist) accept a brokerage holdings
  CSV (JSON-transported so no new multipart dep), run it through the existing deterministic
  `resolve.py` (ticker → ISIN → SEDOL → org-name), and persist **only resolved** positions
  as a user-scoped portfolio — two share classes of one issuer collapse to one holding,
  unmatched rows are surfaced in the report (labelled, never fabricated into a holding).
  A light upload panel on the Portfolio page reads the file and shows the match breakdown +
  the unresolved list.
- **Ownership substrate — the missing edge class (Phase 3 foundation).** New
  `coruscant.ownership` package: three **distinct** relations, never conflated — `owns`
  (declared %-shareholding, public), `beneficial_owner_of` (a natural person's ultimate
  ownership/control, legitimate-interest tier), `consolidates` (accounting consolidation,
  GLEIF-L2, public). `OwnershipProvider` seam + a **BODS** (OpenOwnership / UK-PSC-shaped)
  parser + `StaticOwnershipProvider`; `ingest_ownership` resolves parties to existing nodes
  by anchor (enrich, don't duplicate), labels the rest `unresolved` (counted), and
  substrate-stamps every edge with `source` + `access_tier` (**enforced at query time** —
  a public caller sees beneficial-owner edges only as a `restricted` count) + bitemporal
  validity. No fabricated magnitude (exact `percentage` only when sourced; PSC/BODS ranges
  kept verbatim as `percentage_band`); no derivation of beneficial ownership from
  shareholding (deliberate future work). `GET /graph/ownership` + `GET
  /graph/company/{key}/owners` (as-of aware); `coruscant ownership --file <bods.json>`.
  See ADR-0011.
- **Live ownership sources + UBO chains + contagion + L2 consolidation (ADR-0012).**
  Building on the ADR-0011 substrate, all additive:
  - **UK Companies House PSC** — the first *live* national beneficial-ownership source
    (`--provider psc`). PSC is a **public** register (unlike EU registers post-CJEU
    C-37/20), so individual PSCs are stamped `public` via the record's `access_tier`
    override; a *super-secure* PSC is emitted but withheld (`restricted-authority`,
    identity legally protected). Kind → basis (individual = beneficial owner, corporate/
    legal-person = declared shareholding); `natures_of_control` → disclosed band verbatim
    (never a fabricated exact %); statements counted, never edges. Live Public Data API
    (needs `CORUSCANT_COMPANIES_HOUSE_API_KEY`, scoped to the GB-covered universe) or a
    bulk PSC-snapshot file fallback. Corporate PSCs anchor by company number → resolve
    onto LSE-covered nodes.
  - **UBO chain-following** — `GET /graph/company/{key}/ownership-chain` walks incoming
    ownership edges upward into evidence-carrying chains. Each hop keeps its **own** basis
    (no collapse of shareholding into beneficial ownership); terminal is `beneficial_owner`
    only where the data states it, else `root`/`unresolved`/`cycle`/`max_depth`/`restricted`.
    Access-tier + as-of aware; cycles detected, partials labelled.
  - **Group / UBO contagion** — `GET /graph/company/{key}/contagion` is a **separate**
    inherited-exposure path: undirected BFS over ownership edges surfaces group members
    (parent / subsidiary / shares-owner) that inherit exposure, each with the evidence
    chain back to the seed. Direct vs inherited kept visibly distinct; never collapsed into
    ordinary edges; beneficial-owner ties withheld-and-counted for unprivileged callers.
  - **GLEIF Level-2 consolidation** — `--provider gleif-l2` turns GLEIF relationship
    records (direct/ultimate consolidating parent) into `consolidates` edges only — an
    auxiliary control signal, never %-ownership. Reconciles by LEI onto anchored nodes,
    dedups direct/ultimate, coexists with (never overwrites) a declared `owns` edge for the
    same pair. Live CC0 API (scoped to anchored LEIs) or a relationship-record file.
  - **UI** — CompanyDetailPage gains an "Ownership & control" section (owners, UBO chains,
    group contagion) with explicit resolved / unresolved / restricted states; the World tab
    gains an ownership-overview tile. Honest empty states; no clutter (per-company section
    renders only when there is data). The `OwnershipProvider` seam is now market-tagged
    (`market`), so new national registers drop in as providers with no core-graph change.
- **Taxonomy**: full GICS hierarchy (8-digit code) + MSCI DM/EM/FM, curated and
  verified against public MSCI/S&P sources.
- **Instrument model**: commodities + debt as first-class instruments wired into
  exposure (`config/instruments.yml`).
- **Live feeds** (free, off by default, `connected:false` when off): prices
  (Yahoo), macro (World Bank + Yahoo index), news (GDELT), sector benchmark (SPDR
  sector-ETF **proxy**, not the licensed MSCI index).
- **Intelligence**: deterministic, cited change-detection / events / summaries;
  an LLM gateway + admin console (needs an API key to light up).
- **Runtime & serving** (the platform assembly layer): FastAPI API, CLI (`coruscant
  ingest|query|serve|screen|anchor|portfolio|coverage|ownership`), a worker for
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

- **Ownership breadth + magnitude** — the substrate, live UK PSC, UBO chains,
  contagion, and GLEIF-L2 consolidation exist (above). Still open, and honestly so:
  *live* national registers beyond UK PSC (EU/other BODS sources are file-only, not
  live APIs); **no derived ultimate beneficial owner** — chains are paths of distinct
  sourced claims, and promoting a shareholding chain to a UBO stays a deliberate,
  evidence-carrying step we have *not* taken; aggregate "control %" math over disclosed
  *bands* (a range, not a point); and a bulk GLEIF-L2 ingest (the live path is scoped to
  already-anchored LEIs, not the whole L2 file).
- **PEP / sanctions at scale + external serving** — the screen is built (deterministic
  + yente sidecar); the *live* yente run + external demo await the OpenSanctions
  license in writing.
- **Whole-exchange coverage** — all three target markets now ingest as `CoverageProvider`s:
  **US** (EDGAR/CIK), **India** (NSE+BSE/ISIN), **UK** (LSE/ISIN) — see above. The universe
  pass is lightweight by design; deep filing ingestion (10-K/Exhibit-21/officers) stays
  curated/on-demand. Further markets (EU/JP/…) drop in as new providers on the same seam;
  the operator-`--file` path covers registries that block scripted bulk downloads.
- **Commodity/debt live prices in the UI** — the price client resolves their
  symbols (CL=F, GC=F, ^TNX, LQD…) but they are not surfaced yet.
- **Licensed MSCI index data** — benchmarking uses a free ETF proxy.

## Sequenced next

1. **Real graph store** — ✅ done (Kùzu behind the port; Neo4j/Neptune deferred).
2. **Whole-exchange coverage** — ✅ US + India + UK (ADR-0009/0010). Next: further
   markets (EU/JP/…) as new `CoverageProvider`s on the same seam.
3. **Portfolio front door** — 13F → holding edges ✅ (ADR-0008); user upload ✅.
4. **Ownership → UBO** — ✅ substrate (ADR-0011) + live UK PSC, UBO chains, group
   contagion, GLEIF-L2 (ADR-0012). Next: more live registers, aggregate control-%
   magnitude over bands, and (deliberately, with evidence) chain-derived UBO.
5. **PEP/sanctions** live serving (OpenSanctions license in writing).

Full plan of record: [global-exposure-architecture.md](global-exposure-architecture.md).
