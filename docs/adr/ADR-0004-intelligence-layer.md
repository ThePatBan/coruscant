# ADR-0004: Traceability-First Intelligence Layer

## Status

Accepted

## Context

Coruscant's value is auditable, trustworthy financial intelligence — summaries,
event extraction, and especially change detection ("what changed since the last
disclosure?"). The product mandate is explicit: *never sacrifice traceability for
intelligence; every insight must link back to the exact source text that supports
it.* The MVP must also run and be tested offline, deterministically, without a
mandatory dependency on an external LLM or API key.

## Decision

Implement the intelligence layer as **deterministic, extractive** reference
implementations behind `Protocol` ports (`Summarizer`, `EventExtractor`,
`ChangeDetector`):

- Summaries, events, and changes are built from sentences lifted **verbatim** from
  the source. Every output is a `Claim` carrying its source URI and section, so it
  is auditable by construction — there is no free-text generation that could
  assert something unsupported.
- Change detection diffs the current disclosure against the previous one of the
  same (company, source), categorizes each added/removed statement, and attaches
  the source span on the side it came from.
- A **Claude-backed adapter** can implement the same Protocols (activated when an
  API key is present) for richer language, with the same citation contract
  enforced — without changing any caller.

To make change detection meaningful, periodic sources (SEC, investor relations,
earnings calls) ingest a prior and a current disclosure; reference connectors vary
content across revisions.

## Consequences

- Every AI statement is traceable; nothing is asserted without a citation.
- The system runs and is fully tested offline and deterministically.
- Intelligence is computed during ingestion and persisted (SQLite) so the API
  serves it without recomputation.
- Upgrading to LLM-backed intelligence is an adapter swap, not a rewrite.
- Extractive output is less fluent than an LLM's; this is an accepted trade-off
  for auditability in the MVP.

## Alternatives Considered

- LLM-only summaries/change detection (richer, but non-deterministic, needs keys
  and network, and traceability must be re-imposed on free text).
- No change detection (summaries only) — fails the core product thesis.

## Date

2026-06-29
