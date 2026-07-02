// Country — the missing World → Country → Company rung. Per-country exposure and
// economic intelligence, grounded strictly in the graph: EX-21 legal footprints,
// filing co-mentions (labelled orientation, not ownership), sovereign/credit
// instruments, and change-detection for the holdings tied here. Macro and news
// are live-feed-gated: when off we show a labelled stub, never a fabricated figure.

import { useMemo, useState } from "react";
import { api, type Dashboard, type TimelineEvent } from "../api";
import { CountryMap, type CountryView } from "../CountryMap";
import { Empty, ErrorView, PanelHead, Skeleton } from "../components";
import { useAsync } from "../hooks";

interface CountryDef {
  code: string;
  name: string;
  region: string;
  view: CountryView;
  centroid: { lat: number; lon: number };
}

// Jurisdictions confirmed to carry EX-21 footprints in the graph. Geography is a
// static classification (like GICS/MSCI), not fabricated data.
const COUNTRIES: CountryDef[] = [
  { code: "US", name: "United States", region: "North America", view: { lon0: -128, lon1: -66, lat0: 24, lat1: 50 }, centroid: { lat: 39, lon: -98 } },
  { code: "UK", name: "United Kingdom", region: "Western Europe", view: { lon0: -11, lon1: 3, lat0: 49.5, lat1: 59.5 }, centroid: { lat: 54, lon: -2 } },
  { code: "DE", name: "Germany", region: "Western Europe", view: { lon0: 5, lon1: 16, lat0: 47, lat1: 55.5 }, centroid: { lat: 51, lon: 10.4 } },
  { code: "JP", name: "Japan", region: "East Asia", view: { lon0: 128, lon1: 146, lat0: 30, lat1: 46 }, centroid: { lat: 37, lon: 138 } },
  { code: "IN", name: "India", region: "South Asia", view: { lon0: 68, lon1: 90, lat0: 6, lat1: 36 }, centroid: { lat: 22, lon: 79 } },
  { code: "CN", name: "China", region: "East Asia", view: { lon0: 73, lon1: 135, lat0: 18, lat1: 53 }, centroid: { lat: 35, lon: 104 } },
];

const DIR_GLYPH: Record<string, string> = { risk: "▼", opp: "▲", event: "◍" };

type ChangeRow = TimelineEvent & { dir: "risk" | "opp" | "event" };

function collectChanges(dash: Dashboard | null, keys: Set<string>): ChangeRow[] {
  if (!dash) return [];
  const rows: ChangeRow[] = [];
  const seen = new Set<string>();
  const push = (evts: TimelineEvent[], dir: ChangeRow["dir"]) => {
    for (const e of evts) {
      if (keys.size && !keys.has(e.company_slug)) continue;
      const id = `${e.canonical_id}|${e.section_title}|${e.title}`;
      if (seen.has(id)) continue;
      seen.add(id);
      rows.push({ ...e, dir });
    }
  };
  push(dash.recent_risks, "risk");
  push(dash.recent_opportunities, "opp");
  push(dash.recent_events, "event");
  return rows;
}

const catAttr = (c: string | null | undefined) => (c ?? "").toLowerCase().replace(/\s+/g, "_");

export function CountryPage() {
  const [code, setCode] = useState("US");
  const def = COUNTRIES.find((c) => c.code === code) ?? COUNTRIES[0];

  const dash = useAsync(() => api.dashboard(), []);
  const data = useAsync(
    () =>
      Promise.all([
        api.jurisdictionExposure(def.name),
        api.macro(def.name),
        api.news(def.name),
        api.countryDebt(def.name),
      ]),
    [def.name],
  );

  const [expo, macro, news, debt] = data.data ?? [null, null, null, null];

  const footprintKeys = useMemo(() => {
    const s = new Set<string>();
    if (expo) {
      for (const d of expo.direct) s.add(d.company.key);
      for (const n of expo.network) s.add(n.company.key);
    }
    return s;
  }, [expo]);

  const changes = useMemo(() => collectChanges(dash.data, footprintKeys), [dash.data, footprintKeys]);

  const directN = expo?.direct.length ?? 0;
  const networkN = expo?.network.length ?? 0;
  const reason = !expo
    ? "Loading the book's footprint here…"
    : directN === 0 && networkN === 0
      ? `No tracked holding lists a legal footprint in ${def.name} yet.`
      : `${directN} holding${directN === 1 ? "" : "s"} carry a legal footprint in ${def.name} (Exhibit-21)` +
        (networkN ? `, and ${networkN} more are referenced in filings here.` : ".");

  return (
    <div className="country-page spatial-page">
      <div className="page-head row-between" style={{ display: "flex", alignItems: "flex-end", gap: 16 }}>
        <div>
          <div className="kicker">Country · exposure &amp; economic intelligence</div>
          <h1 style={{ marginTop: 6 }}>{def.name}</h1>
          <div className="mono muted" style={{ marginTop: 4 }}>{def.region}</div>
        </div>
        <div className="segmented" role="tablist" aria-label="Country">
          {COUNTRIES.map((c) => (
            <button
              key={c.code}
              className={c.code === code ? "active" : ""}
              onClick={() => setCode(c.code)}
              aria-selected={c.code === code}
            >
              {c.code}
            </button>
          ))}
        </div>
      </div>

      <div className="dp-ribbon">
        <span className="why">Why you're here</span>
        <span className="reason">{reason}</span>
      </div>

      {data.error ? (
        <ErrorView error={data.error} />
      ) : (
        <div className="dp-split">
          {/* DOSSIER */}
          <aside className="dp-dossier">
            <div className="country-statgrid">
              <div className="stat">
                <div className="country-stat-v">{data.loading ? <Skeleton w={40} h={26} /> : directN}</div>
                <div className="country-stat-l">holdings with a footprint</div>
              </div>
              <div className="stat">
                <div className="country-stat-v">{data.loading ? <Skeleton w={40} h={26} /> : networkN}</div>
                <div className="country-stat-l">also referenced here</div>
              </div>
            </div>

            <div className="dp-section">
              <div className="dp-section-head">
                <span className="kicker">Your exposure here</span>
                <span className="src-link"><span className="arrow">↳</span> EX-21</span>
              </div>
              {data.loading ? (
                <Skeleton h={80} />
              ) : directN === 0 ? (
                <div className="muted small">No EX-21 legal footprint recorded for {def.name}.</div>
              ) : (
                <div className="stack">
                  {expo!.direct.map((f) => (
                    <div className="country-holding" key={f.company.key}>
                      <span className="country-holding-dot" />
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div className="country-holding-nm">{f.company.name}</div>
                        <div className="mono muted small">
                          {f.subsidiaries.length} subsidiar{f.subsidiaries.length === 1 ? "y" : "ies"} in {def.name}
                        </div>
                      </div>
                      {f.source ? (
                        <a className="src-link" href={f.source} target="_blank" rel="noreferrer" title="Open EX-21 source">
                          <span className="arrow">↳</span> source
                        </a>
                      ) : null}
                    </div>
                  ))}
                </div>
              )}
            </div>

            {networkN > 0 && (
              <div className="dp-section">
                <div className="dp-section-head">
                  <span className="kicker">Referenced in filings here</span>
                </div>
                <div className="muted small" style={{ marginBottom: 8 }}>
                  Orientation, not ownership — a filing filed here names them.
                </div>
                <div className="country-chips">
                  {expo!.network.slice(0, 12).map((n, i) => (
                    <span className="chip" key={`${n.company.key}-${i}`} style={{ cursor: "default" }}>
                      {n.company.name}
                    </span>
                  ))}
                  {networkN > 12 ? <span className="mono muted small">+{networkN - 12} more</span> : null}
                </div>
              </div>
            )}

            {debt && debt.length > 0 && (
              <div className="dp-section">
                <div className="dp-section-head">
                  <span className="kicker">Sovereign &amp; credit</span>
                </div>
                <div className="stack">
                  {debt.map((d) => (
                    <div className="country-debt" key={d.slug}>
                      <span>{d.name}</span>
                      <span className="mono muted small">
                        {d.debt_type}
                        {d.symbol ? ` · ${d.symbol}` : ""}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className="dp-section">
              <div className="dp-section-head">
                <span className="kicker" style={{ color: "var(--text-faint)" }}>Macro indicators</span>
                {macro && !macro.connected ? <span className="stub-badge">pending feed</span> : null}
              </div>
              {macro && macro.connected && macro.metrics.length ? (
                <div className="stack">
                  {macro.metrics.map((m, i) => (
                    <div className="country-debt" key={i}>
                      <span>{m.label}</span>
                      <span className="mono">{m.value ?? "—"}{m.unit ? ` ${m.unit}` : ""}</span>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="muted small">
                  GDP, rates, FX and trade balances attach when a macro feed is connected. Coruscant does not
                  fabricate figures.
                </div>
              )}
            </div>
          </aside>

          {/* MAIN */}
          <section className="dp-main">
            <div className="country-mapwrap">
              <CountryMap view={def.view} centroid={def.centroid} redrawKey={def.code} />
              <div className="country-map-label">{def.name} · legal footprint</div>
              <div className="country-map-attr mono">Natural Earth · 110m</div>
            </div>

            <div className="country-body">
              <PanelHead
                idx="01"
                kicker="What changed among holdings here"
                title={<span className="mono" style={{ fontSize: 13, color: "var(--text-faint)" }}>{changes.length}</span>}
              />
              {dash.loading || data.loading ? (
                <div className="stack gap"><Skeleton h={54} /><Skeleton h={54} /></div>
              ) : changes.length === 0 ? (
                <Empty
                  icon="◍"
                  title="No overnight changes tied to holdings here"
                  hint="Change-detection runs over periodic disclosures; nothing surfaced for this country's holdings."
                />
              ) : (
                <div className="stack">
                  {changes.map((c, i) => (
                    <div className="country-change" key={`${c.canonical_id}-${i}`}>
                      <div className={`dp-glyph sm dir-${c.dir}`}>{DIR_GLYPH[c.dir]}</div>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div className="country-change-top">
                          <span className="country-change-co">{c.company_slug.toUpperCase()}</span>
                          <span className="dp-cat" data-c={catAttr(c.category)}>{(c.category || "general").replace(/_/g, " ")}</span>
                        </div>
                        <div className="country-change-stmt">{c.title || c.description}</div>
                      </div>
                      {c.source_uri ? (
                        <a className="src-link" href={c.source_uri} target="_blank" rel="noreferrer">
                          <span className="arrow">↳</span> source
                        </a>
                      ) : null}
                    </div>
                  ))}
                </div>
              )}

              <div style={{ marginTop: 22 }}>
                <PanelHead
                  idx="02"
                  kicker="Headlines"
                  title=""
                  right={news && !news.connected ? <span className="stub-badge">pending feed</span> : null}
                />
                {news && news.connected && news.articles.length ? (
                  <div className="stack">
                    {news.articles.slice(0, 8).map((a, i) => (
                      <a className="country-news" key={i} href={a.url} target="_blank" rel="noreferrer">
                        <span className="country-news-t">{a.title}</span>
                        <span className="mono muted small">{a.domain}</span>
                      </a>
                    ))}
                  </div>
                ) : (
                  <div className="muted small">
                    Business-news headlines for {def.name} attach when the GDELT feed is connected — never fabricated.
                  </div>
                )}
              </div>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
