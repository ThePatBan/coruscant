# ADR-0010: Market-index membership (Index nodes + constituent_of edges)

## Status

Accepted (2026-07-01). Rides on the whole-exchange coverage seam
([ADR-0009](ADR-0009-whole-exchange-coverage.md)); first realized for India
(Nifty 50 / BSE Sensex) and immediately reused for the UK (FTSE 100 / FTSE 250) — the
same generic `Index` node + `constituent_of` edge, no per-market schema. Market-agnostic
by construction.

## Context

Coverage ingests the **full** NSE + BSE universe (ADR-0009). A market index — Nifty 50,
BSE Sensex, and later the S&P 500, FTSE 100 — is **not** an exchange and **not** the
coverage set; it is a curated basket *on top of* the universe. Two things made it worth
modelling now rather than later:

1. It is a natural, provenance-backed **exposure pathway**: "an event hits the Nifty →
   which of my holdings are constituents?" is a first-class question a portfolio user
   asks, structurally identical to the sector/country/tier pathways already in the
   engine.
2. It introduces a new node kind and a new relation, which the store and the golden
   cross-backend parity test must round-trip — cheaper to lock in with coverage than to
   retrofit.

An index constituent is an *identity* claim about a company already in the universe, so
it must reuse the same surrogate node, never create a parallel one.

## Decision

Represent a market index as an **`Index` node** (stable key: `nifty-50`, `bse-sensex`)
carrying `name`, `market`, `provider`, a live constituent count, and a count of
constituents that fell **outside** the ingested universe (honest — absence is counted).
Membership is a **`constituent_of` edge** `Company → Index`, provenance on the edge
(`source`, `source_url`, `index_name`, `observed_at`).

- **Providers opt in.** A `CoverageProvider` may expose `list_index_memberships() ->
  list[IndexMembership]`; the pipeline duck-types it (like `last_drops`), so the US
  provider — which has no index feed here — is untouched. `IndexMembership` carries the
  constituent's `isin` and/or `symbol`.
- **Link to the real node, never fabricate.** During ingest the pipeline builds
  ISIN→key and ticker→key maps over the nodes it touches, then links each constituent by
  **ISIN (exact)** then **symbol**. A constituent absent from the universe is counted as
  `constituents_unresolved` on the `Index` node and gets **no edge** — never a stub or
  a fabricated company.
- **Idempotent.** The `Index` node is upserted (last-write-wins on the counts);
  `constituent_of` edges are first-write-wins (the store's edge contract), so re-runs
  neither duplicate edges nor drift provenance.
- Reported through the existing coverage plumbing: `CoverageSummary.indices` /
  `CoverageRun.indices` = `{index name → constituents linked}`; the CLI prints it.

## Consequences

- The `Index`/`constituent_of` pair round-trips through the generic JSON→Kùzu store with
  no schema migration (single `Node`/`Edge` tables), and the golden parity suite gains a
  case asserting both backends agree (`test_parity_constituent_of_index`).
- The "event on an index → exposed holdings" query is now a graph traversal away, not a
  data-model change — a future exposure pathway with zero new substrate.
- *Live-validated:* the real Nifty 50 list linked all **50** constituents to the
  `nifty-50` node against the freshly-ingested NSE/BSE universe; a constituent whose
  ISIN/symbol is absent from the universe is counted unresolved, not fabricated (unit
  test `test_index_constituent_outside_universe_is_counted_not_fabricated`).

## Alternatives considered

- **Model the index as an `Exchange`/venue** — rejected: an index is a basket, not a
  listing venue; conflating them would corrupt the `by_exchange` coverage counts.
- **A property list of index names on each Company** — rejected: not queryable as a
  traversal, no per-membership provenance, and no home for index-level metadata
  (constituent count, as-of date).
- **Create placeholder company nodes for out-of-universe constituents** — rejected:
  violates the no-fabrication invariant; count the gap instead.

## Date

2026-07-01
