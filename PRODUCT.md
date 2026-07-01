# Coruscant — Product Context

> Source of truth for design work. Grounded in `README.md`, `docs/`, and the
> shipping codebase, not in any single feature prompt.

## Register

**product** — the design serves a portfolio holder orienting under time pressure.
This is an allocator's/analyst's instrument, not a marketing surface. Craft shows
through density, legibility, and trustworthiness, not decoration.

## Product purpose

Coruscant is a **portfolio-exposure intelligence** platform. It answers one
question: *a random event happens somewhere — does it touch my portfolio, and
how?* It trades pages of reading for **orientation**: what changed, who it hits,
why we believe it, what to investigate — always with the source behind every
statement.

The job to be done:
- Trace an event → its blast radius → the holdings it actually touches
  (geography, GICS sector, MSCI market tier, commodity, debt).
- See the shape of the book at a glance (tier + sector composition, movers,
  sector-vs-index).
- Defend every edge back to the disclosure or public classification behind it.

It is **orientation over reading** — not a news feed, not a flat blog of summaries.

## Users

Family offices, fund managers, allocators, and the analysts around them. They scan
for signal under time pressure, distrust unsourced claims, and must defend every
conclusion. Desktop-first (wide monitors), dense panels, long sessions.

## Non-negotiable principle

**Never fabricate; never sacrifice traceability for intelligence.** Every insight
links back to the exact source (a filing, or a public GICS/MSCI classification).
Therefore the UI must:
- Never present an inference as a fact — label derived/proxy links (e.g. control
  implied by leadership overlap; network proximity from co-mention, which is
  *orientation, not dollar magnitude*).
- Never fabricate a relationship or number the data does not hold. When a live
  feed is off, show a labelled stub (`connected: false`), never a placeholder.
- Keep a source link reachable from every claim.

## Data the graph actually holds

**53 companies** (30 US Dow · 15 UK 20-F · 8 India ADRs), 661 Person, 152
Subsidiary, 58 Filing, plus GICS Industry/Sector, MarketTier (DM/EM), 8 Commodity
and 7 DebtInstrument, and Country nodes.

Edges (each with provenance): `insider_holding`, `references` (co-mention),
`has_subsidiary`, `employs`, `board_member`, `in_sector` (GICS), `in_market_tier`
(MSCI), `affects_sector` (commodity → sector), `issued_by` (debt → country).

There is **no ownership / parent / beneficial-owner edge yet.** Control questions
are answered with labelled *proxies* — leadership overlap (a person leading ≥2
companies), shared dependency, co-mention. Group/UBO and PEP/sanctions pathways
are on the roadmap, not built.

## Anti-references (what to avoid)

- A flat "blog of summaries" or social feed of cards.
- Identical card grids; the hero-metric template.
- Generic SaaS dashboards. Coverage is a curated **sample** (53 names +
  commodities/debt), so the design can be dense and editorial, not padded.
- Any visual that implies a relationship, a price, or an exposure the data /
  live feed did not return.

## Tone

Precise, editorial, investigative. Confident but evidence-bound. No hype copy.
