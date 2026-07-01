# ADR-0008: The portfolio front door (EDGAR 13F)

## Status

Accepted (2026-07-01). Implements Phase 2 of
[docs/global-exposure-architecture.md](../global-exposure-architecture.md) §5 —
"the portfolio front door" — now that the identity substrate (ADR-0007) exists.
This is the input the product has been missing: a real institutional book to trace
events into.

## Context

The exposure engine treated the 53 sample companies *as* the portfolio. There was
no **holding** primitive — no way to say "this fund holds this company, as of this
quarter, this much." EDGAR **13F-HR** filings are the free, statutory source of
institutional holdings (a quarterly information table of issuer / CUSIP / value /
shares), so they are the honest first input before user-forwarded portfolios.

Resolving a 13F line to one of our nodes is an ER problem — but a favourable one:
13F issuer names are **SEC-conformed** ("APPLE INC", "CHEVRON CORPORATION"), the
same convention as our Company node names, so the org-name **core matcher** from
ADR-0007 resolves them with high precision and no new machinery.

## Decision

**A `Fund` node + `holds` edges** (`portfolio/holdings.py`), populated from a 13F
information table parsed by `portfolio/thirteenf.py` (a pure, fixture-tested
function; plus a live `fetch_latest_13f(cik)` that navigates EDGAR's submissions →
accession → info-table document). Design choices:

- **Resolution is name-based and conservative.** Each issuer resolves to the
  best-scoring Company at the exact/core floor (0.97); a look-alike ("Apple Ford,
  Inc.") never attaches. CUSIP is carried on the edge as a future anchor.
- **Aggregate share-class lines per company.** A filer reports one issuer across
  many rows (subsidiary managers, multiple classes); these sum into a single
  `holds` edge, so the value is the manager's true position.
- **Out-of-coverage is counted, never fabricated.** Positions with no Company node
  are tallied (`out_of_coverage`); we do not invent nodes to make the book look
  complete — the honest gap that whole-exchange coverage later closes.
- **Substrate on every edge:** provenance (`sec-13f`), `access_tier`, and
  valid-time = the 13F report period, so "what did they hold *on that quarter*?"
  is a bitemporal query.
- Reuses the store, the golden parity harness, `GET /graph/funds` +
  `/graph/fund/{key}`, and `coruscant portfolio --cik|--file`.

## Consequences

- Runs hermetically in CI (parser + projection are pure); the live fetch is
  operator-invoked. Live-validated: Berkshire Hathaway's 13F (90 positions) →
  Apple / American Express / Coca-Cola / Chevron resolved with real aggregated
  values, 61 positions honestly out of coverage.
- The exposure queries can now be scoped to a *fund's* holdings (the next step),
  turning "an event happened — does it touch my book?" from sample into real.
- Value-unit caveat: 13F historically reports values in USD thousands, whole
  dollars since 2023; we store the reported integer and do not reinterpret it.
- User-forwarded portfolios (PDF/holdings) are the other half of the front door,
  still to come.

## Alternatives considered

- **Treat the sample companies as the portfolio (status quo)** — rejected: no real
  input, no per-book exposure.
- **Match holdings by CUSIP→CIK** — rejected for now: no clean free CUSIP↔CIK map;
  SEC-conformed name matching is high-precision here. CUSIP is retained on the edge
  for a future anchor.
- **A separate portfolio store (the existing SQLite `PortfolioStore`)** — that
  models a *user's* hand-picked slug list (a different feature); the graph needs a
  first-class, provenance-carrying, bitemporal holding edge.

## Date

2026-07-01
