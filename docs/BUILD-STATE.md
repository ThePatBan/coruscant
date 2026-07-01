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

**JSON-over-SQLite** — a prototype, not Neo4j/Postgres.
- SQLite `data/coruscant.db`: catalog · intelligence · users · embeddings.
- JSON `data/graph/graph.json`: the in-process `InMemoryKnowledgeGraphStore`,
  rebuilt by ingestion.
- `docker-compose.yml` runs ingest/api/web over a named volume (SQLite); local
  dev runs on the host `./data/`. `data/` and `deploy/` are gitignored; `config/`
  is the tracked default.

## Not built yet ❌ (say it plainly)

- **Real portfolio upload** — the 53 companies are a *sample*; real upload = EDGAR
  13F (Phase 2).
- **Real ownership / UBO edges** — no parent/`owns%`/beneficial-owner edge exists;
  control is only ever an inferred, labelled proxy.
- **PEP / sanctions** screening.
- **Group / UBO contagion** exposure pathway (needs the ownership substrate).
- **Whole-exchange coverage** — only curated names; bulk SEC/Nifty/UK/Europe
  ingestion is future work and needs a real graph store first (the JSON/SQLite
  store will not scale).
- **Commodity/debt live prices in the UI** — the price client resolves their
  symbols (CL=F, GC=F, ^TNX, LQD…) but they are not surfaced yet.
- **Licensed MSCI index data** — benchmarking uses a free ETF proxy.

## Sequenced next

1. **Real graph store** (Phase 0 prerequisite; the ADR-0001 destination).
2. **Whole-exchange coverage** + auto-add on portfolio upload.
3. **Portfolio front door** (13F → holding edges, then user upload).
4. **Ownership → UBO** and **PEP/sanctions** edges (free registries first).

Full plan of record: [global-exposure-architecture.md](global-exposure-architecture.md).
