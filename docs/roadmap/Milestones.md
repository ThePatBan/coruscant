# Coruscant Engineering Roadmap (Milestones)

The roadmap is organized as **five engineering milestones with hard exit gates**.
Nothing advances until the previous milestone's exit criteria are fully met. This
replaces the earlier feature-progression plan: foundations first, so every future
connector, intelligence capability, and user feature inherits a robust base
instead of repeated re-engineering.

| Milestone | Goal | Priority | Exit criteria |
| --- | --- | --- | --- |
| **M1 – Foundation Hardening** | Make the platform dependable | 🔴 Highest | API surface frozen + documented; EDGAR failures explicit; deterministic parsing (stable section IDs); durable, provenance-first graph projection with deterministic dedup; comprehensive fixture + failure tests; **no swallowed exceptions; every ingestion failure observable** |
| **M2 – Source Platform** | Reusable ingestion infrastructure | 🔴 High | Common connector interface, scheduler, retry/dead-letter, shared provenance + metadata schema; IR + press-release connectors on the same pipeline with minimal custom code |
| **M3 – Intelligence Layer** | Documents → structured intelligence | 🟡 High | Event extraction, entity resolution, change detection, evidence-backed summaries, improved ranking — each output has **evidence, confidence, provenance, and is reproducible** |
| **M4 – Analyst Experience** | A compelling daily workflow | 🟡 Medium | Watchlists, timeline, saved searches, notifications, comparison, polished dashboard — an analyst completes their daily research entirely in Coruscant |
| **M5 – Scale & Commercialization** | Broader adoption | 🟢 Medium | Multi-tenancy, RBAC, observability, billing, deployment automation, backups — reliably supports paying customers |

> Note on sequencing vs. what already exists: earlier exploration built breadth
> spanning M2–M5 (additional connectors, intelligence, watchlists, RBAC). Per this
> reorganization that breadth is **paused behind the gates** — it does not count as
> "done" until the foundation it sits on satisfies M1. M1 hardens the core that all
> of it depends on.

## Status

> Reconciled 2026-06-30 against the code + test suite (268 tests green, `ruff` +
> `mypy --strict` clean). The earlier "all five complete" status overstated
> reality: M1 and M4 are genuinely met; **M2, M3, and M5 are partial** — their
> named exit criteria are implemented as structure/calculation but not yet
> enforced or proven against live data. Verdicts below trust code over status text.

- **M1 — Foundation Hardening** ✅ **met** — typed errors + no silent failures,
  dead-letter queue, deterministic section IDs, provenance-first graph, frozen
  `/version`. Caveat: graph durability is a JSON snapshot rebuilt each run (the
  Neo4j backend in ADR-0001 is not implemented); "frozen" is enforced by
  convention — there is no automated contract/OpenAPI-diff guard.
- **M2 — Source Platform** ◐ **partial** — common connector interface,
  retry/dead-letter, shared `Provenance` schema, and IR + press-release on the
  shared pipeline are met. The scheduler is now **consumed**, not advisory:
  `run_ingestion(respect_due=True)` (the worker path) and `coruscant ingest
  --due-only` ingest only sources whose cadence has elapsed, layering them onto
  the existing graph snapshot so not-due sources survive. **Remaining gap:** most
  sources are still proven only against synthetic reference connectors; the live
  EDGAR path now exists behind a switch but auto-discovery of filings is not yet
  built (see EDGAR caveat below).
- **M3 — Intelligence Layer** ◐ **partial** — event extraction, change detection,
  and evidence-backed summaries each carry evidence + bounded confidence +
  provenance and are reproducible (verified). **Gaps:** entity "resolution" is
  gazetteer slug-matching with no confidence and is not covered by the uniform
  evidence contract; hybrid-ranking tie-order depends on ingestion order (no
  `canonical_id` tiebreak, untested); confidence values are static per-category
  constants, not data-derived.
- **M4 — Analyst Experience** ✅ **met** — watchlists, timeline, saved searches,
  source-linked notifications, document comparison, and dashboard on real stores
  + real API, with a genuine end-to-end daily-workflow test. Notifications are now
  generated in the background: the worker calls `evaluate_all_watchlists` after
  each ingestion run (idempotent), so alerts appear with no user action, while the
  on-demand API evaluators remain intact.
- **M5 — Scale & Commercialization** ◐ **partial (weak)** — RBAC (binary
  admin/analyst), audit, monitoring, backup, and hardened single-host deployment
  exist and are tested. **Major gaps:** multi-tenancy is effectively missing — no
  resource carries an `organization_id` and the corpus (`/documents`,
  `/companies`) is global to all authenticated users (the org is a billing label
  only). Plan limits are now **enforced** where a tenant exists: per-day API
  calls (`/retrieve`, `/analyst`) and watchlist count return `429` past the
  effective plan's limit, surfaced via `GET /quota`; enforcement is gated on an
  organization store so single-tenant/offline use is never throttled. **Remaining
  gaps:** no payment integration; no restore command; observability has no
  metrics/tracing; horizontal scale-out is documented-only.

### EDGAR (the reference source family) — not yet production-ready

EDGAR *normalization* is production-grade and well-tested (form-aware section
templates, malformed-filing fallback, stable IDs, typed `FetchError`, provenance).
*Live ingestion* now has a real path: setting `CORUSCANT_LIVE_SOURCES=["sec_edgar"]`
swaps the synthetic `ReferenceEdgarConnector` for `EdgarHttpConnector`, which
declares the configured `edgar_user_agent` on every request and shares a
`RateLimiter` (≤`sec_rate_limit_per_second`, SEC-compliant). Live fetch/resolve
failures are explicit, observable, and dead-lettered like any other source.
**Remaining gap before "production-ready":** filing URLs are declared per company
(`sec_filings:` in config) rather than auto-discovered — wiring the CIK
submissions API (`data.sec.gov/submissions/CIK….json`) to find the latest filings
is the recommended next step. The default deployment remains fully offline.

## M1 — Foundation Hardening (details)

### Objectives
- **Architecture** — freeze the MVP API surface; separate "core platform" from
  "future platform"; define module ownership.
- **Reliability** — eliminate silent failures; structured error reporting; retry;
  dead-letter queue.
- **Graph** — durable persistence; stable identifiers; provenance-first edges;
  deterministic deduplication.
- **Testing** — real + failure EDGAR fixtures; regression suite.

### Exit criteria (M1) — met

- [x] No swallowed exceptions.
- [x] Every ingestion failure is observable (recorded + queryable).
- [x] Graph projection persists durably. *(JSON snapshot; Neo4j backend pending — see caveat above.)*
- [x] Every parsed section has a deterministic, stable ID.
- [x] Regression tests pass.
- [x] API surface documented and frozen. *(By convention; no automated contract-diff guard yet.)*

Only when these hold is EDGAR considered **production-ready**, and only then does
M2 begin.

## Product risks (tracked)

| Risk | Why it matters | Mitigation |
| --- | --- | --- |
| **Scope creep** | Every connector adds maintenance cost | Every roadmap item must map to a milestone + MVP objective; no out-of-gate work |
| **Evidence erosion** | Uncited AI output destroys trust | Provenance is non-negotiable and tested end to end |
| **Schema instability** | Churn in document/entity/graph models breaks future connectors | Freeze core domain models after M1; evolve via versioned migrations |
| **Premature intelligence** | Sophisticated reasoning on unreliable ingestion yields polished-but-wrong results | Do not advance to M3 until M1 + M2 exit criteria are met |
