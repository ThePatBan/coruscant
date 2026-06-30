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
import { api, type GicsSector, type MarketTierCount } from "../api";
import { useAsync } from "../hooks";

// The globe pulls in three.js — lazy-load it so it lands in its own chunk (and
// shares three with the Atlas) instead of bloating the app shell.
const MarketsGlobe = lazy(() => import("../MarketsGlobe").then((m) => ({ default: m.MarketsGlobe })));

const TIER_CLASS: Record<string, string> = { DM: "tier-dm", EM: "tier-em", FM: "tier-fm" };

function pct(n: number, total: number): number {
  return total > 0 ? Math.round((n / total) * 100) : 0;
}

function StubBadge({ label }: { label: string }) {
  return <span className="stub-badge" title="Not yet connected to a live source">{label}</span>;
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

function PortfolioComposition({ tiers, sectors }: { tiers: MarketTierCount[]; sectors: GicsSector[] }) {
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
      <GicsTree sectors={sectors} />
    </div>
  );
}

function CountryInsight({ exchange, tiers }: { exchange: Exchange; tiers: MarketTierCount[] }) {
  const { data, loading, error } = useAsync(
    () => api.jurisdictionExposure(exchange.country),
    [exchange.country],
  );
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
        {["GDP growth", "Inflation", "Index today"].map((m) => (
          <div key={m} className="ci-metric">
            <div className="ci-metric-val">—</div>
            <div className="ci-metric-label">{m} <StubBadge label="feed" /></div>
          </div>
        ))}
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
          <div className="wp-label">Since yesterday <StubBadge label="prices" /></div>
          <div className="wp-value">—</div>
          <div className="wp-sub muted">Yahoo / Google Finance — not connected</div>
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

        <aside className="world-news">
          <div className="wn-head">
            {selected ? `${selected.flag} ${selected.country} — business news` : "Business news"}
            <StubBadge label="feed" />
          </div>
          <div className="wn-empty muted">
            {selected
              ? `A country-specific news stream for ${selected.country} mounts here once a news source is connected.`
              : "A global business-news stream mounts here once a news source is connected. Click a market to scope it to a country."}
          </div>
        </aside>
      </section>

      <section className="world-insights">
        {selected ? (
          <CountryInsight exchange={selected} tiers={tierList} />
        ) : (
          <PortfolioComposition tiers={tierList} sectors={sectors ?? []} />
        )}
      </section>
    </div>
  );
}
