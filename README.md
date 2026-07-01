# Coruscant

Coruscant is a **portfolio-exposure intelligence** platform. It answers one question for a portfolio holder:

> *A random event happens somewhere in the world. **Does it touch my portfolio — and how?***

It optimizes for **orientation, not reading**: *what changed, who it hits, why we believe it, what to investigate* — every relationship and number backed by its source.

> **The first rule: never fabricate.** No relationship or number on screen that the data does not support. When a live feed is off, the UI shows a labelled stub (`connected: false`), never a placeholder value. Inferred links are labelled as inferences, with the proxy they rest on.

## The product — two tabs

**Tab 1 — Home / World (`/world`).** An event → blast-radius → your book surface:

- **Portfolio summary** with live *"since yesterday"* prices (free Yahoo, gated).
- An oscillating **markets globe** (react-globe.gl) — each exchange lit **open/closed**, computed from its local trading hours (a real, free signal).
- A **business-news rail** (free GDELT), global and scoped to a country on drill-in.
- **Portfolio composition**: an **MSCI DM/EM/FM** market-tier bar, a drillable **GICS sector → sub-industry → holdings** tree, a **sector-vs-index benchmark** table (SPDR sector-ETF proxy — *not* the licensed MSCI index), and **commodity-exposure** chips (event → sector → your holdings).
- Click a market to focus its **country**: Exhibit-21 legal footprint, **GDP / inflation / index** macro (World Bank + Yahoo), and the **sovereign / corporate debt** issued there.

**Tab 2 — Company graph (`/atlas`).** The 3D force graph (react-force-graph-3d): companies, officers/directors, subsidiaries, cross-company co-mentions, and board interlocks — spatial orientation, not a list.

## The exposure engine

Pathways that trace an event to the holdings it touches, each on **evidence-backed edges**:

| Pathway | Event → who is exposed | Evidence |
|---|---|---|
| **Geographic** | a jurisdiction → holdings with a legal entity there | Exhibit-21 filing |
| **Sector (GICS)** | a sector/sub-industry (e.g. *Semiconductors*) → holdings in it | curated GICS, verified |
| **Market tier (MSCI)** | Developed/Emerging/Frontier weight of the book | MSCI classification |
| **Commodity** | a commodity → the GICS sectors it drives → holdings | curated linkage |
| **Debt** | a country → its sovereign/corporate debt | issuer inventory |

"No exposure" is a first-class answer. **Network proximity** (co-mention) is an orientation hint, *not* dollar magnitude. Group/UBO contagion and PEP/sanctions are **not built yet** (they need ownership edges — see the roadmap).

## Coverage (the honest starting substrate)

A knowledge graph over **53 companies** — 30 US (Dow), 15 UK (cross-listed 20-F filers), 8 India (ADRs) — plus **8 commodities** and **7 debt instruments**. Nodes: Company, Person (661), Subsidiary (152), Filing (58), GICS Industry/Sector, MarketTier, Commodity, DebtInstrument, Country. Edges carry provenance: `insider_holding`, `references` (co-mention), `has_subsidiary`, `employs`, `board_member`, `in_sector`, `in_market_tier`, `affects_sector`, `issued_by`.

The 53 companies stand in as a **sample portfolio** until real upload lands (Phase 2 / EDGAR 13F). Taxonomy is the **full GICS hierarchy** (sector → industry group → industry → sub-industry, keyed by the 8-digit code) plus **MSCI DM/EM/FM**, curated and verified against public MSCI/S&P sources.

## Live data feeds (all free, off by default)

| Feed | Source | Flag |
|---|---|---|
| Prices ("since yesterday", movers, benchmark) | Yahoo Finance (unofficial) | `CORUSCANT_ENABLE_LIVE_PRICES` |
| Country macro (GDP, inflation) + index | World Bank + Yahoo | `CORUSCANT_ENABLE_LIVE_MACRO` |
| Business news | GDELT DOC 2.0 | `CORUSCANT_ENABLE_LIVE_NEWS` |

Off by default so the offline/test path never touches the network; each endpoint returns `connected: false` when its feed is off. Sector benchmarking reuses the prices flag and proxies the sector index with SPDR Select Sector ETFs (the licensed MSCI index is a later paid feed).

## Storage (what it actually is)

**JSON-over-SQLite**, not Neo4j (ADR-0001's "why Neo4j" is aspirational — see its status note):

- **SQLite** `data/coruscant.db` — catalog, intelligence (change-sets/events/summaries), users, embeddings.
- A **JSON graph snapshot** `data/graph/graph.json` — an in-process `InMemoryKnowledgeGraphStore`, rebuilt by ingestion.

`docker-compose.yml` exists (ingest / api / web sharing a named volume, also SQLite), but local dev runs on the host `./data/`. `data/` and `deploy/` are gitignored; `config/` is the tracked default config. A real graph store is the next foundational step before whole-exchange ingestion.

## Run it

**Docker (full stack):**
```bash
docker compose up --build      # then open http://localhost:8080
```
Brings up `ingest` (one-shot lifecycle + demo seed), `api` (FastAPI, health-gated), and `web` (nginx serving the SPA, proxying `/api`). Demo login: `demo@coruscant.local` / `coruscant-demo`.

**Local (no Docker):**
```bash
make setup                                   # editable install + dev deps
make test                                    # full regression suite
coruscant ingest                             # run the lifecycle (offline/reference by default)
make api                                     # serve the API on :8000
cd frontend && npm install && npm run dev    # SPA on :5173, proxying /api -> :8000
```

**Production switches** (see [.env.example](.env.example)): `CORUSCANT_LIVE_SOURCES=["sec_edgar"]` for live EDGAR ingestion (declares a contact User-Agent, rate-limited); the live-feed flags above; multi-tenant quotas when an org store is configured.

## API surface (selected)

Public: `GET /health`, `POST /auth/{register,login}`, `POST /auth/reset/{request,confirm}`.
Authenticated (bearer): `/companies`, `/documents`, `/graph/company/{slug}`, `/dashboard`;
exposure — `/graph/{jurisdictions,jurisdiction-exposure,sectors,sector-exposure,gics-breakdown,market-tiers,market-tier-exposure,commodity-exposure,country-debt}`, `/instruments/{commodities,debt}`;
feeds — `/portfolio/{prices,benchmark}`, `/macro`, `/news`.

## Architecture

```
React SPA (nginx) ──/api──▶ FastAPI ──▶ knowledge graph · exposure engine · hybrid search · intelligence
       │                       │                    ▲
  auth (JWT)          live feeds: prices · macro · news (free, gated)
                               ▼
  worker / `coruscant ingest` ──▶ orchestrator ──▶ connectors → normalize → graph (GICS/MSCI/instruments) → embed
                                     │                                     → summarize → events → change-detect
                                     ▼
                     SQLite (catalog · intelligence · users) · JSON graph snapshot · raw/normalized artifacts
```

- `src/coruscant/connectors` — source connectors + normalizers (SEC live + reference)
- `src/coruscant/ingestion` — registry, pipeline, orchestrator
- `src/coruscant/knowledge_graph` — projection, GICS/MSCI **taxonomy**, **instruments**, query engine, snapshot
- `src/coruscant/pricing` · `macro` · `news` — the free, gated live feeds
- `src/coruscant/intelligence` · `search` · `auth` · `apps` — cited intelligence, hybrid retrieval, auth, API/CLI/worker
- `frontend/` — React + TypeScript SPA

See [docs/global-exposure-architecture.md](docs/global-exposure-architecture.md) (the plan of record) and the [ADRs](docs/adr/).

## Roadmap

Built: the two-tab product, the exposure engine (5 pathways), full GICS/MSCI taxonomy, the free live feeds, the instrument model (commodities + debt). Next, in order: a **real graph store** (the prototype won't scale), **whole-exchange coverage** (SEC / Nifty / UK / Europe) with **auto-add on portfolio upload**, real **portfolio upload** (13F), then real **ownership → UBO** and **PEP/sanctions** edges — free-first at every tier. See [docs/roadmap/Milestones.md](docs/roadmap/Milestones.md).

## Design rules

- Raw data stays immutable; normalized facts are separate from raw documents.
- Provenance is required for every extracted claim and every AI statement.
- Source-specific behavior lives in connectors/config; all sources share one lifecycle.
- New sources register a `SourceDefinition`; they do not change core code.
