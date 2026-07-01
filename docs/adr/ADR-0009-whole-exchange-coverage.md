# ADR-0009: Whole-exchange coverage (the resolvable universe)

## Status

Accepted (2026-07-01). Implements the long-standing "whole-exchange coverage" item
in [docs/BUILD-STATE.md](../BUILD-STATE.md) and Phase 2 of
[docs/global-exposure-architecture.md](../global-exposure-architecture.md) §5.
US-first, built as a market-plural framework so India (NSE/BSE) and UK (FTSE/LSE)
are new providers, not rewrites.

## Context

The graph held only ~53 curated companies, so a real retail brokerage book resolved
almost nothing — the retail blocker. We need the **full universe of listed issuers**
as lightweight nodes so an uploaded portfolio lands in the graph. This is the
*universe*, deliberately **not** deep filing ingestion (10-K/Exhibit-21/officers stays
curated and on-demand): the goal is that a ticker/name resolves to a node carrying
identity + venue, onto which sector/holdings/LEI edges are attached later.

The store already scales (Kùzu serving; O(E) ingest); the missing piece was the
bulk-registry *connector*. SEC publishes `company_tickers_exchange.json` — one
request returns ~10k issuers (ticker, CIK, name, exchange), free and clean. Crucially
we must **not** fan out to the per-CIK submissions API for 10k issuers.

## Decision

**A `coverage/` module with a `CoverageProvider` seam** (mirroring `screening/` and
`anchoring/`): `list_issuers() -> list[IssuerRecord]`. `UsEdgarCoverageProvider` reads
the one SEC feed (reusing the EDGAR `RateLimiter` + contact-bearing User-Agent);
`StaticCoverageProvider` replays fixtures so CI is hermetic. Design choices:

- **Generic per-market anchors (Invariant #2).** An `IssuerRecord` carries
  `IssuerAnchor{scheme, value}` — `cik`/`ticker` for US; the model already admits
  `isin`/`sedol`/`company_number`/`figi` so India/UK drop in with no schema change.
  The surrogate node key is **never** an external ID; the anchors ride *on* it.
- **CIK-reconcile: enrich, don't duplicate.** A bulk issuer whose CIK matches an
  existing Company node **enriches** it (adds ticker/exchange/universe anchors) and
  leaves the **curated GICS/name/source authoritative**. CIK is a near-perfect
  intra-US key, so this dedup is *exact*, not fuzzy — no reversible-resolver
  judgement is needed (nothing is being merged; anchors are added to one node).
- **Stable surrogate for the rest.** A new issuer becomes `us-<cik>` (unpadded),
  deterministic across re-runs so bookmarks survive.
- **Sector honesty (Invariant #5).** Bulk issuers carry no curated GICS → labelled
  `gics_status: unresolved`, never a fabricated sector. The coarse SIC can be layered
  later, clearly lower-authority.
- **Idempotent.** Descriptive fields enrich last-write-wins; identity anchors are
  first-write-wins; the surrogate key never moves. Provenance `sec-company-tickers`
  on every node; a per-market `CoverageRun` node records provider/counts/what was
  excluded upstream.
- **Exchange filter, honest.** Keep any named venue that is not OTC (so a future
  venue like "NYSE American" is included without a code change); blank/OTC listings
  are excluded **and counted by reason** — absence is signal, not a silent drop.
- **Proof it resolves books.** `coverage/resolve.py` resolves a brokerage CSV against
  the universe by exact **ticker** (with a punctuation-folded fallback: `BRK.B`↔`BRK-B`)
  then the shared **org-name** core matcher; unmatched positions are reported
  unresolved, never fabricated. The resolve *rate* is the headline metric.
- Wired as `coruscant coverage --market us [--file|--resolve]`, `runtime.run_coverage`,
  `GET /graph/coverage` (`coverage_overview`, counted live off the graph), and a
  golden cross-backend parity case.

## Consequences

- Runs hermetically in CI (parse/filter/reconcile are pure; the live fetch is
  operator-invoked with an injected/downloaded payload). **Live-validated:** the real
  SEC feed → 7,654 real-exchange issuers in ~1.5s (2,779 OTC/blank excluded and
  labelled) → the graph grew from 53 to **6,062 US companies** (1,645 enriched incl.
  multi-share-class rows collapsing onto one CIK node; 6,009 new surrogates). A
  12-line sample retail book resolved **10/12 (83%)** — TSLA/PLTR/GME, none previously
  covered, now resolve; the misses are an ETF (not in the issuer feed) and a bogus
  symbol, both honestly unresolved.
- Serving is unchanged: `run_coverage` writes the JSON snapshot; Kùzu rematerializes
  on the next `open_synced` (mtime-gated), like every other pipeline.
- Scale: ~10k nodes is comfortable for Kùzu (columnar) and the O(E) in-memory
  intermediate; reconciliation is O(N) over a CIK dict, not O(N²).
- UI (rendering 10k nodes), user portfolio upload, and live feeds remain separate,
  out of scope here.

## Alternatives considered

- **Per-CIK submissions fan-out** — rejected: ~10k requests violates SEC fair-access
  and buys deep data we explicitly don't want in the universe pass.
- **Key nodes by CIK/ticker** — rejected: violates Invariant #2 (surrogate PK); a
  ticker is reused across delisted issuers and an external ID must be an anchor.
- **Fabricate a coarse GICS from SIC now** — rejected: SIC↔GICS is lossy; label
  unresolved and defer to a clearly lower-authority follow-up.
- **Fuzzy-merge bulk issuers into curated nodes by name** — rejected: CIK is an exact
  key; name-fuzzing 10k issuers would risk over-merge for no benefit.

## Date

2026-07-01
