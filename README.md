# Coruscant

Coruscant is an AI-powered financial and corporate intelligence platform built on **traceable evidence** rather than scraped summaries. It continuously ingests public company information, understands **what materially changed** since the last disclosure, and presents it through a clean interface — with the source evidence behind every statement.

> Never sacrifice traceability for intelligence. Every insight links back to the exact source text that supports it.

## What it does

- **Change detection ("what changed?")** — diffs each new disclosure against the prior one and surfaces categorized, evidence-backed material changes (new/removed risks, guidance moves, executive changes, regulatory developments).
- **AI summaries** — overview, key points, risks, opportunities, management commentary, financial highlights, and events for every document. Each line is lifted verbatim from the source and cited.
- **Event timeline** — chronological, categorized events extracted per company.
- **Natural-language search** — across SEC filings, investor relations, transcripts, press releases, job postings, news, and patents, with evidence attached.
- **Knowledge graph** — companies, documents, and sections with provenance.
- **Authentication** — email/password accounts, sessions, protected routes.

The intelligence layer is **deterministic and extractive by default** (fully auditable, runs offline) behind `Protocol` ports, with a **Claude-ready adapter seam** — see [ADR-0004](docs/adr/ADR-0004-intelligence-layer.md).

## Run the full product (Docker)

```bash
docker compose up --build
# then open http://localhost:8080
```

This brings up three services sharing a data volume: `ingest` (one-shot lifecycle run that also seeds a demo account), `api` (FastAPI, health-gated), and `web` (nginx serving the SPA and reverse-proxying `/api`).

**Demo login:** `demo@coruscant.local` / `coruscant-demo` (pre-filled on the login screen).

Coverage: Apple, Microsoft, Tesla, SpaceX, Cargill, ExxonMobil.

## Run locally (without Docker)

```bash
make setup                 # editable install with dev dependencies
make test                  # full regression suite
coruscant ingest           # run the lifecycle + seed the demo user (full)
coruscant ingest --due-only # ingest only sources whose cadence has elapsed
coruscant query "Apple risk factors and guidance"
make api                   # serve the API (coruscant serve)
cd frontend && npm install && npm run dev   # SPA on :5173, proxying /api -> :8000
```

## Production modes (optional)

The default is fully offline and deterministic. Two switches turn on production
behavior (see [.env.example](.env.example) for all variables):

- **Live SEC ingestion** — `CORUSCANT_LIVE_SOURCES=["sec_edgar"]` swaps the offline
  reference connector for the live HTTP connector, which declares
  `CORUSCANT_EDGAR_USER_AGENT` on every request and rate-limits to
  `CORUSCANT_SEC_RATE_LIMIT_PER_SECOND` (SEC fair-access). It fetches the real
  filing URLs declared per company in [config/companies.yml](config/companies.yml)
  (`sec_filings:`); fetch/resolve failures are dead-lettered, never swallowed.
- **Multi-tenant quotas** — when an organization store is configured, per-plan
  daily API-call and watchlist limits are enforced (`429`), surfaced via
  `GET /quota`. Disable with `CORUSCANT_ENFORCE_QUOTAS=false`.

The **worker** (`coruscant.apps.worker`, the docker `ingest` service) runs the
scheduled lifecycle: due-aware ingestion, then a background watchlist evaluation
so notifications are generated without any user action.

## Architecture

```
React SPA (nginx)  ──/api──▶  FastAPI  ──▶  hybrid search · knowledge graph · intelligence
        │                        │                 ▲
   auth (JWT)              auth · intelligence      │
                                 ▼                  │
   worker / `coruscant ingest` ──▶ orchestrator ──▶ connectors → normalize → graph → embed → index
                                       │                              → summarize → events → change-detect
                                       ▼
                       SQLite (catalog + intelligence + users) · graph snapshot · raw/normalized artifacts
```

- `src/coruscant/connectors` — source connectors + normalizers (SEC live + reference; reference connectors for the other six sources)
- `src/coruscant/ingestion` — registry, generic pipeline, orchestrator (multi-period)
- `src/coruscant/intelligence` — summarizer, event extractor, change detector (cited)
- `src/coruscant/search` — embeddings, vector index, hybrid retrieval
- `src/coruscant/knowledge_graph` — projection, query, snapshot
- `src/coruscant/infrastructure` — filesystem repos, SQLite catalog + intelligence store, run status
- `src/coruscant/auth` — password hashing, signed tokens, user store, auth service
- `src/coruscant/apps` — API, CLI, worker, shared runtime
- `frontend/` — React + TypeScript SPA

See [docs/Architecture](docs/Architecture/) and the ADRs in [docs/adr](docs/adr/).

## API

Public: `GET /health`, `POST /auth/register`, `POST /auth/login`, `POST /auth/reset/{request,confirm}`.
Authenticated (bearer token): `GET /auth/me`, `/companies`, `/sources`, `/documents`, `/documents/{id}`,
`/documents/{id}/summary`, `/companies/{slug}/timeline`, `/companies/{slug}/changes`,
`/graph/company/{slug}`, `POST /retrieve`, `GET /answer`, `GET /dashboard`, `GET /status`.

## Roadmap

Development follows five engineering milestones with hard exit gates — foundations
first, so every future connector and capability inherits a robust base. See
[docs/roadmap/Milestones.md](docs/roadmap/Milestones.md). The current milestone is
**M1 — Foundation Hardening** (reliability, deterministic parsing, durable
provenance-first graph, frozen API surface); the API contract is in
[docs/api/Contract.md](docs/api/Contract.md).

## Design rules

- Raw data remains immutable; normalized facts are separate from raw documents.
- Provenance is required for every extracted claim and every AI statement.
- Source-specific behavior lives in connectors/config; all sources share one lifecycle.
- New sources are added by registering a `SourceDefinition`, not by changing core code.
