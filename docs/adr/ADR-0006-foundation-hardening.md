# ADR-0006: Foundation Hardening (M1) — Frozen Surface, Core/Future Split, Schema Policy

## Status

Accepted

## Context

A staged review found the architecture beginning to drift: silent failures in the
EDGAR HTTP path, section identifiers derived only from titles (collidable), and an
API/domain surface that kept growing as features were added. Continuing to add
connectors on this base would multiply technical debt across every pipeline.

## Decision

Adopt the five-milestone roadmap (see docs/roadmap/Milestones.md) and treat M1 —
Foundation Hardening — as a hard gate. As part of M1:

**Reliability**
- No swallowed exceptions. Connectors raise typed errors
  (`coruscant.common.errors`); the orchestrator records every failure to a
  durable dead-letter store and the run report. Optional/best-effort fetches log
  explicitly rather than returning silently.
- Retry with bounded attempts; exhausted attempts become dead-letter records that
  can be inspected and replayed.

**Graph**
- Stable, deterministic identifiers: documents by `canonical_id`
  (sha256 of source URI), sections by a deterministic `section_id`, entities by a
  slug key. Edges are deduplicated deterministically and carry provenance
  (`source` + `source_uri`). Projection persists to a durable snapshot.

**Core vs. future platform**
The **core platform** (frozen at M1) is the dependable base every future capability
inherits:
- `common` (config, types, errors), `connectors` (interface + SEC EDGAR),
  `ingestion` (registry, generic pipeline, orchestrator), `knowledge_graph`,
  `infrastructure` (repositories, catalog, dead-letter, status), `apps` (API/CLI/
  worker/runtime), `auth`.

The **future platform** (evolves behind M2+ gates) layers on top:
- additional `connectors`, `intelligence`, `watchlists`, `portfolio`,
  `workspaces`, `enterprise`.

**API freeze**
- The MVP API surface is documented in docs/api/Contract.md and considered stable.
  Breaking changes require a new version. The app exposes `api_version`
  (`GET /version`).

**Schema-stability policy**
- Core domain models (`SourceDocument`, `NormalizedDocument`, `DocumentSection`,
  `GraphNode`, `GraphEdge`, `Claim`) carry a `SCHEMA_VERSION` and are frozen after
  M1; they evolve only through versioned, documented migrations.

## Consequences

- New connectors become incremental work, not re-engineering.
- Failures are observable and replayable instead of silent.
- Parsing and graph projection are reproducible (deterministic IDs + dedup).
- The cost is up-front hardening time before M2 — accepted, because it compounds.

## Date

2026-06-29
