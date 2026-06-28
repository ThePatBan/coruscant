# Coruscant

Coruscant is an AI-powered financial and corporate intelligence platform built on traceable evidence rather than scraped summaries.

This repository contains the MVP ingestion-to-intelligence platform: a config-driven pipeline that fetches source material, normalizes it into evidence-bearing documents, projects it into a knowledge graph, embeds and indexes it for hybrid search, and serves it through an API and CLI.

## What Is In Scope

The MVP ingests and normalizes seven source types:

- SEC EDGAR
- investor relations materials
- earnings call transcripts
- company press releases
- job postings
- news
- patent metadata

SEC EDGAR ships with a live HTTP connector; every source ships with an offline **reference connector** that synthesizes deterministic, evidence-bearing sample documents (marked `provenance: reference-sample`) so the full lifecycle runs without network access. New sources are added by registering a `SourceDefinition` — not by writing company-specific code.

## Lifecycle

Every source travels the same path (see [docs/architecture/Data Flow.md](docs/architecture/Data%20Flow.md)):

`fetch → store raw (immutable) → normalize → project graph → embed → index → catalog → reason`

## Repository Layout

- [src/coruscant/apps/](src/coruscant/apps/) — API, CLI, worker, and shared runtime wiring
- [src/coruscant/common/](src/coruscant/common/) — config, logging, and domain models
- [src/coruscant/connectors/](src/coruscant/connectors/) — source connectors + normalizers
- [src/coruscant/ingestion/](src/coruscant/ingestion/) — registry, generic pipeline, orchestrator
- [src/coruscant/knowledge_graph/](src/coruscant/knowledge_graph/) — graph projection, query, snapshot
- [src/coruscant/search/](src/coruscant/search/) — embeddings, vector index, hybrid retrieval, reasoning
- [src/coruscant/infrastructure/](src/coruscant/infrastructure/) — filesystem repositories + SQLite catalog
- [config/companies.yml](config/companies.yml) — company registry
- [config/sources.yml](config/sources.yml) — enabled ingestion sources
- [docs/](docs/) — architecture and governance docs
- [tests/](tests/) — verification suite

## Local Start

```bash
make setup           # editable install with dev dependencies
make test            # run the test suite
coruscant ingest     # run the full lifecycle for every company × enabled source
coruscant query "Apple risk factors and guidance"
coruscant graph apple
make api             # serve the API (also: coruscant serve)
```

### CLI

| Command | Description |
| --- | --- |
| `coruscant companies` | List configured companies |
| `coruscant sources` | List registered ingestion sources |
| `coruscant ingest` | Run the full ingestion lifecycle and persist all stores |
| `coruscant query <q>` | Answer a query against the ingested corpus, with evidence |
| `coruscant graph <slug>` | Show graph neighbors for a company |
| `coruscant serve` | Run the API server |

### API

`GET /health`, `GET /companies`, `GET /sources`, `GET /documents`,
`GET /documents/{id}`, `POST /retrieve`, `GET /answer`, and
`GET /graph/company/{slug}`. The API loads its read model from the SQLite catalog
and the graph snapshot on startup, so it serves whatever the worker last ingested.

## Design Rules

- Raw data remains immutable.
- Normalized facts are separate from documents.
- Provenance is required for every extracted claim.
- Source-specific behavior lives in connector implementations or configuration.
- New pipelines must fit the same fetch, store, normalize, extract, graph, embed, index, reason lifecycle.
