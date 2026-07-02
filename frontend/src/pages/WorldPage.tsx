// Tab 1 — Home / World. Portfolio summary on top, the oscillating markets globe
// in the centre, a business-news rail on the right, and portfolio insights below.
// With nothing selected the insight panel shows the portfolio's *composition* —
// MSCI market tiers (DM/EM/FM) and the GICS sector→sub-industry tree, both real
// data. Click a market to focus its country: the rail switches to country news
// and the panel shows your real exposure there (Exhibit-21 footprint) plus how
// that market's tier weighs in your book. Pieces that need a feed we haven't wired
// (live prices, news, macro) are stubbed and labelled as such — never faked.

import { lazy, Suspense, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { EXCHANGES, marketStatus, localTime, TIER_LABEL, type Exchange } from "../world/exchanges";
import {
  api,
  type GicsSector,
  type IndexQuote,
  type MacroMetric,
  type MarketTierCount,
  type PortfolioBenchmark,
  type PortfolioPrices,
} from "../api";
import { useAsync } from "../hooks";

// The globe pulls in three.js — lazy-load it so it lands in its own chunk (and
// shares three with the Atlas) instead of bloating the app shell.
const MarketsGlobe = lazy(() => import("../MarketsGlobe").then((m) => ({ default: m.MarketsGlobe })));

const TIER_CLASS: Record<string, string> = { DM: "tier-dm", EM: "tier-em", FM: "tier-fm" };

function pct(n: number, total: number): number {
  return total > 0 ? Math.round((n / total) * 100) : 0;
}

function signedPct(n: number): string {
  return `${n >= 0 ? "+" : ""}${n.toFixed(2)}%`;
}

// Top gainers / losers since yesterday (free Yahoo quotes).
function Movers({ prices }: { prices: PortfolioPrices }) {
  if (!prices.connected || prices.holdings.length === 0) return null;
  const gainers = prices.holdings.slice(0, 3);
  const losers = prices.holdings.slice(-3).reverse();
  const Row = ({ h }: { h: PortfolioPrices["holdings"][number] }) => (
    <span className="mover">
      <span className="mover-sym">{h.symbol}</span>
      <span className={h.change_pct >= 0 ? "up" : "down"}>{signedPct(h.change_pct)}</span>
    </span>
  );
  return (
    <div className="pc-block">
      <div className="ci-section-label">Today's movers <span className="muted">· since prior close</span></div>
      <div className="movers">
        <div className="movers-col">
          {gainers.map((h) => <Row key={h.slug} h={h} />)}
        </div>
        <div className="movers-col">
          {losers.map((h) => <Row key={h.slug} h={h} />)}
        </div>
      </div>
    </div>
  );
}

function StubBadge({ label }: { label: string }) {
  return <span className="stub-badge" title="Not yet connected to a live source">{label}</span>;
}

function timeAgo(iso?: string | null): string {
  if (!iso) return "";
  const mins = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

// Business-news rail: global, or scoped to the selected market's country (GDELT).
function NewsRail({ selected }: { selected: Exchange | null }) {
  const country = selected?.country;
  const { data, loading } = useAsync(() => api.news(country), [country ?? ""]);
  return (
    <aside className="world-news">
      <div className="wn-head">
        {selected ? `${selected.flag} ${selected.country} — business news` : "Business news"}
        {data && !data.connected ? <StubBadge label="feed" /> : null}
      </div>
      {loading ? (
        <div className="wn-empty muted">Loading headlines…</div>
      ) : !data || !data.connected ? (
        <div className="wn-empty muted">
          {selected
            ? `Country news for ${selected.country} mounts here once the news feed is connected.`
            : "A global business-news stream mounts here once the news feed is connected. Click a market to scope it to a country."}
        </div>
      ) : data.articles.length === 0 ? (
        <div className="wn-empty muted">{data.note ?? "No headlines right now."}</div>
      ) : (
        <ul className="wn-list">
          {data.articles.map((a) => (
            <li key={a.url}>
              <a href={a.url} target="_blank" rel="noreferrer" className="wn-item">
                <div className="wn-title">{a.title}</div>
                <div className="wn-meta muted">
                  {a.domain}
                  {a.published_at ? ` · ${timeAgo(a.published_at)}` : ""}
                </div>
              </a>
            </li>
          ))}
        </ul>
      )}
    </aside>
  );
}

// MSCI market-tier composition (pathway 4): a stacked DM/EM/FM bar + legend.
function MarketTierBar({ tiers }: { tiers: MarketTierCount[] }) {
  const total = tiers.reduce((s, t) => s + t.companies, 0);
  if (!total) return null;
  return (
    <div className="pc-block">
      <div className="ci-section-label">Market exposure — MSCI classification</div>
      <div className="tier-bar">
        {tiers.map((t) => (
          <div
            key={t.tier}
            className={`tier-seg ${TIER_CLASS[t.tier] ?? ""}`}
            style={{ width: `${pct(t.companies, total)}%` }}
            title={`${t.label}: ${t.companies} (${pct(t.companies, total)}%)`}
          />
        ))}
      </div>
      <div className="tier-legend">
        {tiers.map((t) => (
          <span key={t.tier} className="tier-leg">
            <span className={`tdot ${TIER_CLASS[t.tier] ?? ""}`} />
            {t.label.replace(" market", "")} <strong>{pct(t.companies, total)}%</strong>
            <span className="muted"> · {t.companies}</span>
          </span>
        ))}
      </div>
    </div>
  );
}

// GICS sector → sub-industry → holdings, drillable. The whole tree comes from one
// call, so drilling is instant and never invents an edge.
function GicsTree({ sectors }: { sectors: GicsSector[] }) {
  const [openSector, setOpenSector] = useState<string | null>(null);
  const [openSub, setOpenSub] = useState<string | null>(null);
  const total = sectors.reduce((s, x) => s + x.companies, 0);
  const max = sectors.reduce((m, x) => Math.max(m, x.companies), 0);
  return (
    <div className="pc-block">
      <div className="ci-section-label">Sectors — GICS ({sectors.length} of 11)</div>
      <ul className="gics-list">
        {sectors.map((s) => {
          const active = openSector === s.sector;
          return (
            <li key={s.sector}>
              <button
                className={`gics-row ${active ? "active" : ""}`}
                onClick={() => {
                  setOpenSector(active ? null : s.sector);
                  setOpenSub(null);
                }}
              >
                <span className="gics-caret">{active ? "▾" : "▸"}</span>
                <span className="gics-name">{s.sector}</span>
                <span className="gics-bar">
                  <span className="gics-fill" style={{ width: `${pct(s.companies, max)}%` }} />
                </span>
                <span className="gics-count">{s.companies}</span>
                <span className="gics-pct muted">{pct(s.companies, total)}%</span>
              </button>
              {active ? (
                <ul className="gics-sublist">
                  {s.sub_industries.map((sub) => {
                    const subActive = openSub === sub.sub_industry;
                    return (
                      <li key={sub.sub_industry}>
                        <button
                          className={`gics-subrow ${subActive ? "active" : ""}`}
                          onClick={() => setOpenSub(subActive ? null : sub.sub_industry)}
                          title={sub.code ? `GICS ${sub.code} · ${sub.industry}` : sub.industry}
                        >
                          <span className="gics-subname">{sub.sub_industry}</span>
                          <span className="gics-subcount muted">{sub.companies.length}</span>
                        </button>
                        {subActive ? (
                          <div className="gics-holdings">
                            {sub.companies.map((c) => c.name).join(" · ")}
                            {sub.code ? <span className="gics-code muted"> · GICS {sub.code}</span> : null}
                          </div>
                        ) : null}
                      </li>
                    );
                  })}
                </ul>
              ) : null}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

// Each GICS sector's holdings vs its sector-index (ETF) proxy, today.
function BenchmarkTable({ data }: { data: PortfolioBenchmark }) {
  if (!data.connected || data.sectors.length === 0) return null;
  const fmt = (v?: number | null) => (v == null ? "—" : signedPct(v));
  const cls = (v?: number | null) => (v == null ? "" : v >= 0 ? "up" : "down");
  return (
    <div className="pc-block">
      <div className="ci-section-label">
        Sector vs index <span className="muted">· you vs SPDR sector-ETF proxy, equal-weight</span>
      </div>
      <div className="bench">
        <div className="bench-row bench-head muted">
          <span>Sector</span><span>Wt</span><span>You</span><span>Index</span><span>Δ</span>
        </div>
        {data.sectors.map((s) => (
          <div key={s.sector} className="bench-row" title={s.benchmark_name ?? undefined}>
            <span className="bench-sector">{s.sector}</span>
            <span className="muted">{Math.round(s.weight_pct)}%</span>
            <span className={cls(s.portfolio_change_pct)}>{fmt(s.portfolio_change_pct)}</span>
            <span className={cls(s.benchmark_change_pct)}>{fmt(s.benchmark_change_pct)}</span>
            <span className={cls(s.delta_pct)}>{fmt(s.delta_pct)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// Commodity event → the GICS sectors it drives → your equity holdings there.
function CommoditiesBlock() {
  const { data } = useAsync(() => api.commodities(), []);
  const [open, setOpen] = useState<string | null>(null);
  const { data: exposure } = useAsync(
    () => (open ? api.commodityExposure(open) : Promise.resolve(null)),
    [open ?? ""],
  );
  if (!data || data.length === 0) return null;
  return (
    <div className="pc-block">
      <div className="ci-section-label">
        Commodity exposure <span className="muted">· event → sector → your holdings</span>
      </div>
      <ul className="chip-list">
        {data.map((c) => (
          <li key={c.slug}>
            <button
              className={`chip ${open === c.slug ? "active" : ""}`}
              onClick={() => setOpen(open === c.slug ? null : c.slug)}
            >
              {c.name}
            </button>
          </li>
        ))}
      </ul>
      {open && exposure ? (
        <div className="commodity-exposure small">
          <strong>{exposure.commodity}</strong> drives {exposure.affects_sectors.join(" · ")} →{" "}
          {exposure.holdings.length ? (
            exposure.holdings.map((h) => h.name).join(", ")
          ) : (
            <span className="muted">no holdings in these sectors — itself the insight</span>
          )}
        </div>
      ) : null}
    </div>
  );
}

function ScreeningPanel() {
  const { data, loading } = useAsync(() => api.screening(), []);
  return (
    <div className="pc-block">
      <div className="ci-section-label">
        PEP / sanctions screening <span className="muted">· people in the graph vs. OpenSanctions</span>
      </div>
      {loading ? (
        <div className="muted small">Screening…</div>
      ) : !data || !data.connected ? (
        <div className="muted small">
          Not screened yet — no watchlist dataset is wired. Run <code>coruscant screen</code> with an
          OpenSanctions export to populate this. No placeholder is shown until it runs.
        </div>
      ) : (
        <>
          <div className="small">
            <strong>{data.screened}</strong> screened · <strong>{data.confirmed.length}</strong> confirmed
            ({data.pep} PEP · {data.sanctioned} sanctioned) · <strong>{data.needs_review.length}</strong> in
            review
          </div>
          {data.confirmed.length === 0 ? (
            <div className="muted small">
              No corroborated hits — expected for public-company officers, itself the insight.
            </div>
          ) : (
            <ul className="ci-list">
              {data.confirmed.map((h, i) => (
                <li key={`${h.person.key}-${h.relation}-${i}`}>
                  <strong>{h.person.name}</strong>{" "}
                  <span className={`chip ${h.relation === "sanctioned" ? "active" : ""}`}>{h.relation}</span>{" "}
                  <span className="muted">
                    {h.matched_name}
                    {h.score != null ? ` · ${Math.round(h.score * 100)}%` : ""}
                    {h.valid_from ? ` · since ${h.valid_from}` : ""}
                  </span>
                  {h.source_url ? (
                    <>
                      {" · "}
                      <a href={h.source_url} target="_blank" rel="noreferrer">
                        source
                      </a>
                    </>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
          {data.needs_review.length > 0 ? (
            <div className="muted small">
              {data.needs_review.length} candidate{data.needs_review.length === 1 ? "" : "s"} awaiting review —
              name-only and unconfirmed, a candidate not a determination.
            </div>
          ) : null}
        </>
      )}
    </div>
  );
}

function PortfolioComposition({
  tiers,
  sectors,
  prices,
  benchmark,
}: {
  tiers: MarketTierCount[];
  sectors: GicsSector[];
  prices: PortfolioPrices | null;
  benchmark: PortfolioBenchmark | null;
}) {
  const total = tiers.reduce((s, t) => s + t.companies, 0);
  return (
    <div className="portfolio-composition">
      <div className="pc-head">
        <div className="wi-title">Portfolio composition</div>
        <div className="muted small">
          How the {total}-holding sample sits across markets and GICS sectors — every classification
          public &amp; source-verified. Drill a sector to its sub-industries; select a market on the globe
          to trace an event into this book.
        </div>
      </div>
      <MarketTierBar tiers={tiers} />
      {prices ? <Movers prices={prices} /> : null}
      {benchmark ? <BenchmarkTable data={benchmark} /> : null}
      <CommoditiesBlock />
      <GicsTree sectors={sectors} />
      <ScreeningPanel />
      <OwnershipPanel />
    </div>
  );
}

function OwnershipPanel() {
  const { data, loading } = useAsync(() => api.ownershipOverview(), []);
  const source = data?.provider ? data.provider.replace(/-/g, " ") : null;
  return (
    <div className="pc-block">
      <div className="ci-section-label">
        Ownership &amp; control{" "}
        <span className="muted">· declared shareholding · beneficial ownership · consolidation</span>
      </div>
      {loading ? (
        <div className="muted small">Loading ownership substrate…</div>
      ) : !data || !data.connected ? (
        <div className="muted small">
          No ownership ingested yet. Run <code>coruscant ownership --provider psc</code> (live UK
          Companies House PSC), <code>--provider gleif-l2</code> (accounting consolidation), or{" "}
          <code>--file</code> with a BODS export. Nothing is shown until it runs.
        </div>
      ) : (
        <>
          <div className="small">
            <strong>{data.provider ?? "unknown source"}</strong>
            {data.market ? <span className="muted"> · market {data.market}</span> : null}
            {data.observed_at ? <span className="muted"> · run {data.observed_at}</span> : null}
          </div>
          <div className="small">
            <strong>{data.owns}</strong> declared · <strong>{data.beneficial_owner_of}</strong> beneficial
            · <strong>{data.consolidates}</strong> consolidation
            {data.restricted > 0 ? (
              <>
                {" "}
                · <strong>{data.restricted}</strong> restricted
              </>
            ) : null}
          </div>
          <div className="muted small">
            Three distinct claim types, never merged — percentages appear only where sourced.
            {data.holders_unresolved > 0 || data.subjects_unresolved > 0 ? (
              <>
                {" "}
                {data.holders_unresolved + data.subjects_unresolved} unresolved part
                {data.holders_unresolved + data.subjects_unresolved === 1 ? "y" : "ies"} left labelled,
                not fabricated.
              </>
            ) : null}
            {data.restricted > 0
              ? " Restricted edges are counted, not shown (e.g. an EU beneficial owner)."
              : ""}
            {source ? ` Live source: ${source}.` : ""}
          </div>
        </>
      )}
    </div>
  );
}

function MacroTile({ label, metric, connected }: { label: string; metric?: MacroMetric; connected: boolean }) {
  const has = connected && metric && metric.value != null;
  return (
    <div className="ci-metric">
      <div className="ci-metric-val">{has ? `${metric!.value!.toFixed(1)}${metric!.unit}` : "—"}</div>
      <div className="ci-metric-label">
        {label} {has ? <span className="muted">{metric!.period} · WB</span> : <StubBadge label="feed" />}
      </div>
    </div>
  );
}

function IndexTile({ index, connected }: { index?: IndexQuote | null; connected: boolean }) {
  const has = connected && index != null;
  return (
    <div className="ci-metric">
      <div className={`ci-metric-val ${has ? (index!.change_pct >= 0 ? "up" : "down") : ""}`}>
        {has ? signedPct(index!.change_pct) : "—"}
      </div>
      <div className="ci-metric-label">{has ? index!.name : <>Index today <StubBadge label="feed" /></>}</div>
    </div>
  );
}

function CountryInsight({ exchange, tiers }: { exchange: Exchange; tiers: MarketTierCount[] }) {
  const { data, loading, error } = useAsync(
    () => api.jurisdictionExposure(exchange.country),
    [exchange.country],
  );
  const { data: macro } = useAsync(() => api.macro(exchange.country), [exchange.country]);
  const { data: debt } = useAsync(() => api.countryDebt(exchange.country), [exchange.country]);
  const direct = data?.direct ?? [];
  const network = data?.network ?? [];
  const total = tiers.reduce((s, t) => s + t.companies, 0);
  const tierRow = tiers.find((t) => t.tier === exchange.msci);
  return (
    <div className="country-insight">
      <div className="ci-head">
        <div>
          <div className="ci-title">{exchange.flag} {exchange.country}</div>
          <div className="ci-sub">{TIER_LABEL[exchange.msci]} · {exchange.short} {localTime(exchange)} local</div>
        </div>
        <span className={`pill ${marketStatus(exchange) === "open" ? "" : "muted"}`}>
          <span className={`dot ${marketStatus(exchange) === "open" ? "" : "off"}`} />
          {marketStatus(exchange) === "open" ? "Market open" : "Market closed"}
        </span>
      </div>

      {tierRow && total ? (
        <div className="ci-tier">
          <span className={`tdot ${TIER_CLASS[exchange.msci] ?? ""}`} />
          {TIER_LABEL[exchange.msci]} is <strong>{pct(tierRow.companies, total)}%</strong> of your book
          <span className="muted"> ({tierRow.companies} of {total} holdings)</span>
        </div>
      ) : null}

      <div className="ci-macro">
        <MacroTile label="GDP growth" connected={!!macro?.connected} metric={macro?.metrics.find((m) => m.label === "GDP growth")} />
        <MacroTile label="Inflation" connected={!!macro?.connected} metric={macro?.metrics.find((m) => m.label === "Inflation (CPI)")} />
        <IndexTile connected={!!macro?.connected} index={macro?.index} />
      </div>

      <div className="ci-exposure">
        <div className="ci-section-label">Your holdings with a footprint here</div>
        {loading ? (
          <div className="muted small">Tracing exposure…</div>
        ) : error ? (
          <div className="muted small">Exposure unavailable.</div>
        ) : direct.length === 0 ? (
          <div className="ci-none">
            No direct footprint in {exchange.country}. <span className="muted">An event here barely touches this book — itself the insight.</span>
          </div>
        ) : (
          <ul className="ci-list">
            {direct.map((fp) => (
              <li key={fp.company.key}>
                <strong>{fp.company.name}</strong>
                <span className="muted"> — {fp.subsidiaries.length} legal entit{fp.subsidiaries.length === 1 ? "y" : "ies"}</span>
                {fp.source ? (
                  <a className="ci-cite" href={fp.source} target="_blank" rel="noreferrer" title="Exhibit 21 source filing">↗ evidence</a>
                ) : null}
                <div className="ci-subs">{fp.subsidiaries.slice(0, 3).join(" · ")}{fp.subsidiaries.length > 3 ? " · …" : ""}</div>
              </li>
            ))}
          </ul>
        )}
        {network.length > 0 ? (
          <div className="ci-network muted small">
            +{network.length} peer{network.length === 1 ? "" : "s"} name an exposed company (network proximity, not magnitude).
          </div>
        ) : null}
      </div>

      {debt && debt.length > 0 ? (
        <div className="ci-debt">
          <div className="ci-section-label">Debt issued here</div>
          <div className="small">{debt.map((d) => d.name).join(" · ")}</div>
        </div>
      ) : null}
    </div>
  );
}

export function WorldPage() {
  const navigate = useNavigate();
  const [selected, setSelected] = useState<Exchange | null>(null);
  const [now, setNow] = useState(() => new Date());
  const { data: companies } = useAsync(() => api.companies(), []);
  const { data: tiers } = useAsync(() => api.marketTiers(), []);
  const { data: sectors } = useAsync(() => api.gicsBreakdown(), []);
  const { data: prices } = useAsync(() => api.portfolioPrices(), []);
  const { data: benchmark } = useAsync(() => api.portfolioBenchmark(), []);

  // Re-evaluate open/closed each minute.
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 60_000);
    return () => clearInterval(id);
  }, []);

  const openCount = useMemo(() => EXCHANGES.filter((e) => marketStatus(e, now) === "open").length, [now]);
  const sampleSize = companies?.length ?? 0;
  const tierList = tiers ?? [];

  return (
    <div className="world-page">
      {/* Portfolio summary — sample until upload is wired (Phase 2 / 13F). */}
      <section className="world-portfolio">
        <div className="wp-tile">
          <div className="wp-label">Portfolio <StubBadge label="sample" /></div>
          <div className="wp-value">{sampleSize} holdings</div>
          <div className="wp-sub muted">tracking the {sampleSize}-company universe</div>
        </div>
        <div className="wp-tile">
          {prices?.connected && prices.avg_change_pct != null ? (
            <>
              <div className="wp-label">Since yesterday <span className="stub-badge" title="Free Yahoo Finance quotes, not real-time">Yahoo</span></div>
              <div className={`wp-value ${prices.avg_change_pct >= 0 ? "up" : "down"}`}>{signedPct(prices.avg_change_pct)}</div>
              <div className="wp-sub muted">{prices.gainers}↑ {prices.losers}↓ · equal-weight, {prices.priced} priced</div>
            </>
          ) : (
            <>
              <div className="wp-label">Since yesterday <StubBadge label="prices" /></div>
              <div className="wp-value">—</div>
              <div className="wp-sub muted">Yahoo Finance — not connected</div>
            </>
          )}
        </div>
        <div className="wp-tile">
          <div className="wp-label">Markets open now</div>
          <div className="wp-value">{openCount}<span className="muted" style={{ fontSize: 16 }}> / {EXCHANGES.length}</span></div>
          <div className="wp-sub muted">live, by local trading hours</div>
        </div>
        <button className="wp-tile wp-cta" onClick={() => navigate("/atlas")}>
          <div className="wp-label">Company intelligence</div>
          <div className="wp-value" style={{ fontSize: 18 }}>Open the graph →</div>
          <div className="wp-sub muted">directors · suppliers · subsidiaries</div>
        </button>
      </section>

      <section className="world-main">
        <div className="world-globe-col">
          <Suspense fallback={<div className="markets-globe" style={{ display: "grid", placeItems: "center" }}><span className="spinner" style={{ width: 24, height: 24 }} /></div>}>
            <MarketsGlobe now={now} selectedId={selected?.id} onSelect={setSelected} />
          </Suspense>
          <div className="globe-legend">
            <span><span className="ldot open" /> open</span>
            <span><span className="ldot closed" /> closed</span>
            <span className="muted">click a market to focus its country</span>
          </div>
        </div>

        <NewsRail selected={selected} />
      </section>

      <section className="world-insights">
        {selected ? (
          <CountryInsight exchange={selected} tiers={tierList} />
        ) : (
          <PortfolioComposition
            tiers={tierList}
            sectors={sectors ?? []}
            prices={prices ?? null}
            benchmark={benchmark ?? null}
          />
        )}
      </section>
    </div>
  );
}
