# Coruscant — Design Handoff Brief

Paste this into your design session so mockups are **implementation-ready and
honest**. Two hard rules govern every screen:

1. **Never fabricate.** No number, price, or relationship that the API/feed did
   not return. When a live feed is off, show a *labelled stub* (not a placeholder
   value). Empty and "no exposure" states are first-class — design them.
2. **Reconcile to the existing design system** (tokens below). Evolve it on
   purpose if you want, but don't invent a parallel style by accident.

The product is **portfolio-exposure intelligence** ("an event happens somewhere;
does it touch my book, and how?") — orientation over reading. Two tabs:
`/world` (below) and `/atlas` (the 3D company graph). Coverage today is a
**53-company sample** (30 US · 15 UK · 8 India) + 8 commodities + 7 debt
instruments — treat it as a sample, not a real user portfolio.

---

## Design tokens (from `apps/console/src/index.css`)

**Aesthetic:** near-black "intelligence terminal", single **indigo** accent,
**amber reserved for provenance/evidence only**. Dark is earned (long focused
sessions). Dense, legible, editorial — not a padded SaaS dashboard.

**Color**
- Surfaces: `--bg #090b0f` · `--bg-elev #11141a` · `--bg-elev-2 #161a22` · `--bg-hover #1b2029`
- Borders: `--border #232a35` · `--border-strong #313a48`
- Text: `--text #e8ebef` · `--text-muted #9aa4b2` · `--text-faint #7e8a9b`
- Accent (indigo — structure/links/primary): `--accent #7c8cff` · `--accent-strong #5b6cff` · `--accent-soft rgba(124,140,255,.12)` · `--accent-border rgba(124,140,255,.35)`
- **Evidence (amber — provenance ONLY, keep rare):** `--evidence #f3b94d` · soft `rgba(243,185,77,.12)` · border `rgba(243,185,77,.3)`
- Semantic: `--good #4bd6a0` (up/gain/added) · `--danger #ff6b6b` (removed/risk); price-down uses `#ff7a7a`
- Market tiers: DM = indigo `--accent` · EM = amber `#f3b94d` · FM = violet `#b388ff`

**Type:** system sans (`--font`); **mono** (`--mono`) for ids, tickers, codes,
timestamps, source paths. H1 28 / H2 19 / H3 15, weight 650, letter-spacing
−0.02em; body 15/1.55; keep prose ≤72ch. Hierarchy from weight + scale + the
mono/sans split, **not color alone**.

**Shape/space:** radius `--radius 12` / `--radius-sm 8` / pill `999`. Cards exist
but are **not** the default container — prefer rails, dividers, spatial grouping;
**never nest cards**. Motion: subtle, ease-out, fast (0.13–0.16s), no bounce,
respect `prefers-reduced-motion`, never animate layout.

**Evidence affordance:** a `↗ evidence` / `↳ source` mono link is a system
signature — every *derived* statement carries one; amber marks provenance and
stays rare so it stays meaningful.

---

## `/world` — element-by-element data contract

Layout today (top → bottom): a 4-tile **portfolio summary** row; a **globe +
news** row; a **portfolio composition / country insight** panel below. You may
re-lay-out freely — but each element can only show the fields listed.

### 1. Portfolio summary (4 tiles)
- **Portfolio** — `GET /companies` count → `"{n} holdings"`, sub `"tracking the {n}-company universe"`. Badge: **sample**.
- **Since yesterday** — `GET /portfolio/prices` → `{connected, avg_change_pct, gainers, losers, priced, total, as_of, holdings[]}`. Connected: `±X.XX%` (green/red) + `"{gainers}↑ {losers}↓ · equal-weight, {priced} priced"` + a **"Yahoo"** source chip. **Off:** `"—"` + `"Yahoo Finance — not connected"` (stub). ⚠️ It is **equal-weighted across the sample — NOT a position-weighted return** (no holdings/weights exist). Never show a $ P&L or a portfolio-level % as if weighted.
- **Markets open now** — `{openCount} / {total}`, computed live from each exchange's local trading hours (always live, no stub).
- **Company intelligence** — a CTA button → `/atlas`.

### 2. Markets globe (react-globe.gl)
15 exchanges, each lit **open/closed** (computed from local trading hours — a real, free signal). No index values on the globe (we don't fetch per-exchange intraday). Click a market → focuses its **country** (drives the news rail + the country-insight panel below). Movement/% is deliberately **not** shown here.

### 3. News rail — `GET /news[?country=]`
`{connected, scope: "global"|"country", country, articles:[{title, url, domain, published_at, source_country}], note}`. States: **loading**; **not connected** (stub); **connected but empty** (show `note`, e.g. "rate-limited — try again"); **list** (title · domain · time-ago, links out). Global by default; **country-scoped** when a market is selected. GDELT is rate-limited, so empty is common — design the empty state well.

### 4. Portfolio composition (shown when NO market is selected)
- **Market-tier bar** — `GET /graph/market-tiers` → `[{tier: "DM"|"EM"|"FM", label, companies}]`. Stacked bar + legend %. Today: ~45 DM / 8 EM / **0 FM** (so FM may be absent — handle a missing tier).
- **Today's movers** — top 3 gainers / 3 losers from `/portfolio/prices` `holdings[]` (`{symbol, name, change_pct}`). Only when prices connected.
- **Sector vs index** — `GET /portfolio/benchmark` → `{connected, sectors:[{sector, holdings, weight_pct, portfolio_change_pct, benchmark_symbol, benchmark_name, benchmark_change_pct, delta_pct}], note}`. Table: Sector · Wt · You · Index · Δ. ⚠️ "Index" is a **SPDR sector-ETF proxy, NOT the licensed MSCI index** — label it. Equal-weight caveat applies.
- **Commodity exposure** — `GET /instruments/commodities` → `[{slug, name, category, symbol, affects_sectors[]}]` as chips; on click `GET /graph/commodity-exposure?commodity={slug}` → `{commodity, category, affects_sectors[], holdings:[{name}]}` → "drives {sectors} → {holdings}" or "no holdings in these sectors — itself the insight".
- **GICS tree** — `GET /graph/gics-breakdown` → `[{sector, companies, sub_industries:[{sub_industry, industry, code, companies:[{name}]}]}]`. Drillable **sector → sub-industry → holdings**; the sub-industry carries an **8-digit GICS code** (render mono). 10 of 11 sectors present (no Real Estate).

### 5. Country insight (shown when a market IS selected)
- **Header** — flag, country, tier label (`Developed/Emerging/Frontier market`), exchange short code + local time, an **open/closed** pill.
- **Tier context** — from `/graph/market-tiers`: "{Emerging market} is **X%** of your book ({n} of {m} holdings)".
- **Macro tiles (3)** — `GET /macro?country=` → `{connected, metrics:[{label:"GDP growth"|"Inflation (CPI)", value, unit:"%", period}], index:{name, change_pct}}`. Tiles: **GDP growth**, **Inflation**, **Index today** (index move colored). Values are annual (World Bank) — show the year; index is today (Yahoo). Stub each tile when off.
- **Holdings with a footprint here** — `GET /graph/jurisdiction-exposure?jurisdiction=` → `{direct:[{company:{name,key}, subsidiaries[], source}], network:[...]}`. Each direct row: company · "{n} legal entities" · **`↗ evidence`** link (the Exhibit-21 filing URL — amber provenance). Empty state: "No direct footprint in {country}. An event here barely touches this book — itself the insight." Network line: "+N peers name an exposed company (**network proximity, not magnitude**)".
- **Debt issued here** — `GET /graph/country-debt?country=` → `[{name, debt_type, issuer_country, symbol}]` (e.g. "US 10-Year Treasury · US Investment-Grade Corporate …").

---

## `/atlas` — the company graph (if you touch it)
A 3D force graph (react-force-graph-3d): Company / Person (officers, directors) /
Subsidiary nodes; edges for employment, board membership, subsidiaries, and
cross-company co-mentions (board interlocks bridge companies). It's spatial
orientation, not a list. Node hover shows a flag + role; cross-border co-mention
links render in a distinct teal.

---

## What does NOT exist yet (do not design around these as if live)
- Real portfolio **upload** or **weights** → no position-weighted return, no $ P&L, no allocation-vs-target.
- Real **ownership / UBO / parent** edges; **PEP / sanctions**; group-contagion exposure.
- **Licensed MSCI index** data (we proxy with sector ETFs).
- **Commodity/debt live prices** in the UI (resolvable but not surfaced yet — fair game to design *if* labelled).
- Any intraday chart / historical time-series (we have last-vs-prior-close only).

When in doubt, prefer an **honest empty/stub state** over an invented number — it
is the product's signature, not a gap to hide.
