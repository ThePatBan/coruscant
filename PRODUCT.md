# Coruscant — Product Context

> Source of truth for design work. Grounded in `README.md`, `docs/`, and the
> shipping codebase, not in any single feature prompt.

## Register

**product** — the design serves the work of investigation. This is an analyst's
tool, not a marketing surface. Craft shows through density, legibility, and
trustworthiness, not decoration.

## Product purpose

Coruscant is an AI-powered corporate-intelligence platform built on **traceable
evidence** rather than scraped summaries. It ingests public company disclosures,
detects **what materially changed** since the last filing, and connects companies,
people, suppliers, countries, products, and technologies into a knowledge graph —
always with the source text behind every statement.

It is an **investigation workspace**, not a news feed. The job to be done:
- Follow ownership / control / influence between entities.
- Reason about a company's **progression over time** (a history, not a stream).
- Trace any claim back to the disclosure that supports it.

## Users

Analysts, investigators, and researchers (financial, diligence, risk, journalism).
They scan for signal under time pressure, distrust unsourced claims, and need to
defend every conclusion. They read on desktop (wide monitors) and tablet.

## Non-negotiable principle

**Never sacrifice traceability for intelligence.** Every insight links back to the
exact source text that supports it. The intelligence layer is deterministic and
extractive by default — fully auditable. Therefore the UI must:
- Never present an inference as a fact. When a conclusion is derived (e.g. control
  implied by leadership overlap, not a declared ownership filing), **label it as
  inferential** and show the proxy it rests on.
- Never fabricate ownership, financials, or relationships the graph does not hold.
- Keep a source link reachable from every claim.

## Data the graph actually holds

Entities: Company, Person, Country, Product, Technology, Agency, Document.
Relations: `employs`, `previously_at`, `relies_on_supplier`, `operates_in`,
`supplies_to`, `competes_with`, `partners_with`, `produces`, `uses_technology`,
`engaged_with`, `mentions`.

There is **no ownership / parent / subsidiary / beneficial-owner edge.** Control and
ownership questions must be answered with the strongest available *proxies*, clearly
labelled: leadership overlap (a person who leads ≥2 companies), and shared critical
dependency (companies relying on the same supplier / exposed to the same country).

## Anti-references (what to avoid)

- A flat "blog of summaries" or social feed of cards.
- Identical card grids; the hero-metric template.
- Generic SaaS dashboards. Coverage is small and high-value (6 marquee companies),
  so the design can be dense and editorial, not padded.
- Any visual that implies a relationship the data does not contain.

## Tone

Precise, editorial, investigative. Confident but evidence-bound. No hype copy.
