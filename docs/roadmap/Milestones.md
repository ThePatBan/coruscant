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

## Current milestone: M1 — Foundation Hardening

### Objectives
- **Architecture** — freeze the MVP API surface; separate "core platform" from
  "future platform"; define module ownership.
- **Reliability** — eliminate silent failures; structured error reporting; retry;
  dead-letter queue.
- **Graph** — durable persistence; stable identifiers; provenance-first edges;
  deterministic deduplication.
- **Testing** — real + failure EDGAR fixtures; regression suite.

### Exit criteria (M1)
- [ ] No swallowed exceptions.
- [ ] Every ingestion failure is observable (recorded + queryable).
- [ ] Graph projection persists durably.
- [ ] Every parsed section has a deterministic, stable ID.
- [ ] Regression tests pass.
- [ ] API surface documented and frozen.

Only when these hold is EDGAR considered **production-ready**, and only then does
M2 begin.

## Product risks (tracked)

| Risk | Why it matters | Mitigation |
| --- | --- | --- |
| **Scope creep** | Every connector adds maintenance cost | Every roadmap item must map to a milestone + MVP objective; no out-of-gate work |
| **Evidence erosion** | Uncited AI output destroys trust | Provenance is non-negotiable and tested end to end |
| **Schema instability** | Churn in document/entity/graph models breaks future connectors | Freeze core domain models after M1; evolve via versioned migrations |
| **Premature intelligence** | Sophisticated reasoning on unreliable ingestion yields polished-but-wrong results | Do not advance to M3 until M1 + M2 exit criteria are met |
