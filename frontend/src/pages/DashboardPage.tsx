// Orientation — the post-login World view (design-pack Screen 1). In one screen:
// what the book is, what changed, where the risk concentrates, what to do first.
// Hybrid data policy: the layout is faithful to the pack, but every figure is
// real or clearly labelled. The portfolio value is an explicit equal-weight
// SAMPLE (a stated assumption until a portfolio is uploaded); "Today's read" is
// computed from the real change stream + concentration matrix, not written by
// hand; the % move is live only when the price feed is connected, else a stub.

import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, type Dashboard, type PortfolioPrices, type TimelineEvent } from "../api";
import { ErrorView, Skeleton } from "../components";
import { useAsync } from "../hooks";
import { densestCell, loadRiskMatrix, REGIONS, type RiskMatrix } from "../riskmatrix";
import { SignalGlobe } from "../SignalGlobe";

type Dir = "risk" | "opp" | "event";
const DIR_GLYPH: Record<Dir, string> = { risk: "▼", opp: "▲", event: "◍" };
const catAttr = (c: string | null | undefined) => (c ?? "").toLowerCase().replace(/\s+/g, "_");

// Transparent equal-weight assumption used only for the labelled SAMPLE hero.
// Stated on screen; replaced the moment a real portfolio + price feed connect.
const ASSUMED_PER_HOLDING = 250_000_000;

interface Row extends TimelineEvent {
  dir: Dir;
  id: string;
}

interface OrientData {
  dash: Dashboard;
  prices: PortfolioPrices;
  matrix: RiskMatrix;
  rows: Row[];
}

async function loadOrientation(): Promise<OrientData> {
  const [dash, prices, matrix] = await Promise.all([
    api.dashboard(),
    api.portfolioPrices().catch(
      () => ({ connected: false, priced: 0, total: 0, gainers: 0, losers: 0, holdings: [] }) as PortfolioPrices,
    ),
    loadRiskMatrix(),
  ]);
  const rows: Row[] = [];
  const seen = new Set<string>();
  const add = (evts: TimelineEvent[], dir: Dir) => {
    for (const e of evts) {
      const id = `${e.canonical_id}|${e.section_title}|${e.title}`;
      if (seen.has(id)) continue;
      seen.add(id);
      rows.push({ ...e, dir, id });
    }
  };
  add(dash.recent_risks, "risk");
  add(dash.recent_opportunities, "opp");
  add(dash.recent_events, "event");
  return { dash, prices, matrix, rows };
}

type Period = "yesterday" | "mtd" | "ytd";

export function DashboardPage() {
  const { data, error, loading } = useAsync(loadOrientation, []);
  const [period, setPeriod] = useState<Period>("yesterday");
  const [filter, setFilter] = useState<"all" | Dir>("all");
  const [openId, setOpenId] = useState<string | null>(null);

  const holdings = data ? data.matrix.sectors.reduce((a, s) => a + s.companies, 0) : 0;
  const assumedAum = holdings * ASSUMED_PER_HOLDING;

  const counts = useMemo(() => {
    const r = data?.rows ?? [];
    return {
      all: r.length,
      risk: r.filter((x) => x.dir === "risk").length,
      opp: r.filter((x) => x.dir === "opp").length,
      event: r.filter((x) => x.dir === "event").length,
    };
  }, [data]);

  const dense = data ? densestCell(data.matrix) : null;

  // "Today's read" — grounded synthesis, not hand-written copy.
  const todaysRead = useMemo(() => {
    if (!data) return null;
    const total = counts.all;
    const risks = counts.risk;
    const clusterPart = dense ? ` your deepest cluster is ${dense.sector} in ${dense.region.full} (${dense.count} holding${dense.count === 1 ? "" : "s"})` : "";
    return { risks, total, clusterPart, sector: dense?.sector };
  }, [data, counts, dense]);

  const list = data ? (filter === "all" ? data.rows : data.rows.filter((r) => r.dir === filter)) : [];

  const move =
    period === "yesterday" && data?.prices.connected && typeof data.prices.avg_change_pct === "number"
      ? data.prices.avg_change_pct
      : null;

  return (
    <div className="orient spatial-page">
      {error ? <ErrorView error={error} /> : null}
      {loading ? <OrientSkeleton /> : null}

      {data ? (
        <>
          {/* HERO */}
          <div className="orient-hero">
            <div className="orient-hero-left">
              <div className="orient-hero-kick">
                Portfolio value <span className="stub-badge">sample</span>
              </div>
              <div className="orient-hero-val">
                ${(assumedAum / 1e9).toFixed(2)}B <span className="orient-hero-cur">USD</span>
              </div>
              <div className="orient-hero-sub mono">
                {holdings} holdings · equal-weight · assumes ${(ASSUMED_PER_HOLDING / 1e6).toFixed(0)}M/holding until portfolio upload
              </div>
            </div>
            <div className="orient-hero-right">
              <div className="segmented">
                {(["yesterday", "mtd", "ytd"] as Period[]).map((p) => (
                  <button key={p} className={period === p ? "active" : ""} onClick={() => setPeriod(p)}>
                    {p === "yesterday" ? "Yesterday" : p.toUpperCase()}
                  </button>
                ))}
              </div>
              {move !== null ? (
                <div className={`orient-hero-pct ${move >= 0 ? "up" : "down"}`}>
                  {move >= 0 ? "+" : ""}
                  {move.toFixed(2)}%
                </div>
              ) : (
                <div className="orient-hero-pct pending">pending price feed</div>
              )}
              <div className="orient-hero-prov mono">
                <span className={`dot ${data.prices.connected ? "" : "off"}`} />
                {period === "yesterday"
                  ? data.prices.connected
                    ? "equal-weight · Yahoo · live"
                    : "equal-weight · price feed off"
                  : "sample · pending price history"}
              </div>
            </div>
          </div>

          {/* TODAY'S READ */}
          {todaysRead ? (
            <div className="orient-read">
              <span className="orient-read-tag">Today's read —</span>
              <span>
                {todaysRead.total > 0 ? (
                  <>
                    <span className="danger-em">
                      {todaysRead.risks} of {todaysRead.total} recent changes raise risk;
                    </span>
                    {todaysRead.clusterPart ? (
                      <>
                        {todaysRead.clusterPart}.{" "}
                        <Link to="/risk" className="accent-em">
                          Start with {todaysRead.sector}.
                        </Link>
                      </>
                    ) : (
                      " review the change stream below."
                    )}
                  </>
                ) : (
                  "No material changes in the current window — the book is quiet. Scan concentrations while it lasts."
                )}
              </span>
            </div>
          ) : null}

          {/* GRID */}
          <div className="orient-grid">
            {/* 01 WHAT CHANGED */}
            <section className="orient-01">
              <div className="orient-panel-head">
                <Link to="/changes" className="orient-panel-link">
                  <span className="idx">01</span> What changed <span className="arr">→</span>
                </Link>
                <Link to="/changes" className="orient-panel-all">
                  all insights →
                </Link>
              </div>
              <div className="segmented orient-filters">
                {([["all", "All"], ["risk", "Risk"], ["opp", "Opportunity"], ["event", "Events"]] as const).map(
                  ([k, label]) => (
                    <button key={k} className={filter === k ? "active" : ""} onClick={() => setFilter(k)}>
                      {label} <span className="ct">{counts[k]}</span>
                    </button>
                  ),
                )}
              </div>
              <div className="orient-triage">
                {list.length === 0 ? (
                  <div className="muted small" style={{ padding: "14px 4px" }}>
                    Nothing in this filter.
                  </div>
                ) : (
                  list.map((c) => {
                    const on = openId === c.id;
                    return (
                      <div key={c.id} className={`orient-trow${on ? " open" : ""}`}>
                        <button className="orient-trow-main" onClick={() => setOpenId(on ? null : c.id)}>
                          <span className="mono orient-trow-when">
                            {c.occurred_at ? c.occurred_at.slice(0, 10) : "—"}
                          </span>
                          <span className={`dir-${c.dir} orient-trow-glyph`}>{DIR_GLYPH[c.dir]}</span>
                          <span className="orient-trow-hl">{c.title || c.description}</span>
                          <span className="dp-cat" data-c={catAttr(c.category)}>
                            {(c.category || "general").replace(/_/g, " ")}
                          </span>
                          <span className="mono orient-trow-co">{c.company_slug.toUpperCase()}</span>
                        </button>
                        {on ? (
                          <div className="orient-trow-ev">
                            <div className="orient-trow-ev-line">
                              <span className="mono arrow" style={{ color: "var(--evidence)" }}>
                                {c.dir === "opp" ? "+" : c.dir === "risk" ? "–" : "·"}
                              </span>
                              {c.description || c.title}
                            </div>
                            <div className="orient-trow-ev-foot">
                              {c.source_uri ? (
                                <a className="src-link" href={c.source_uri} target="_blank" rel="noreferrer">
                                  <span className="arrow">↳</span> {c.section_title || "source"}
                                </a>
                              ) : null}
                              <span style={{ flex: 1 }} />
                              <Link className="btn ghost" to="/changes">
                                Trace evidence ↳
                              </Link>
                            </div>
                          </div>
                        ) : null}
                      </div>
                    );
                  })
                )}
              </div>
              <div className="orient-hints mono">
                <span>↑↓ move</span>
                <span>↵ open</span>
                <span>↳ evidence</span>
              </div>
            </section>

            {/* SIDE: 02 globe · 03 matrix · investigate */}
            <aside className="orient-side">
              <div>
                <div className="orient-panel-head">
                  <Link to="/world" className="orient-panel-link">
                    <span className="idx">02</span> Live signals <span className="arr">→</span>
                  </Link>
                  <span className="orient-feedbadge mono">
                    <span className="dot off" /> GDELT · RSS <span className="stub-badge">soon</span>
                  </span>
                </div>
                <Link to="/world" className="orient-globe">
                  <SignalGlobe />
                  <span className="orient-globe-cap mono">news + flagged changes · open World →</span>
                </Link>
              </div>

              <div>
                <div className="orient-panel-head">
                  <Link to="/risk" className="orient-panel-link">
                    <span className="idx">03</span> Where your risk concentrates <span className="arr">→</span>
                  </Link>
                  <span className="src-link">
                    <span className="arrow">↳</span> Exhibit-21
                  </span>
                </div>
                <MiniMatrix m={data.matrix} />
              </div>

              {dense ? (
                <div className="orient-investigate">
                  <div style={{ flex: 1 }}>
                    <div className="orient-investigate-kick">Investigate first</div>
                    <div className="orient-investigate-body">
                      {dense.sector} exposure — {dense.count} holding{dense.count === 1 ? "" : "s"} concentrated in{" "}
                      {dense.region.full}.
                    </div>
                  </div>
                  <Link to="/risk" className="btn">
                    Open thread →
                  </Link>
                </div>
              ) : null}
            </aside>
          </div>
        </>
      ) : null}
    </div>
  );
}

/** Compact sector × region heatmap (top sectors) — links out to full /risk. */
function MiniMatrix({ m }: { m: RiskMatrix }) {
  // show sectors that have any footprint first, capped, so the panel stays tight
  const order = m.sectors
    .map((s, ri) => ({ s, ri, tot: m.matrix[ri].reduce((a, b) => a + b, 0) }))
    .sort((a, b) => b.tot - a.tot)
    .slice(0, 5);
  const colTotals = REGIONS.map((_, ci) => m.regionKeys.get(REGIONS[ci].key)!.size);
  return (
    <div className="orient-matrix">
      <div className="orient-mrow orient-mhead">
        <div className="orient-mlabel" />
        {REGIONS.map((r) => (
          <div key={r.key} className="orient-mcolh">
            {r.short}
          </div>
        ))}
        <div className="orient-msig">hold</div>
      </div>
      {order.map(({ s, ri, tot }) => (
        <div className="orient-mrow" key={s.sector}>
          <div className="orient-mlabel" title={s.sector}>
            {s.sector}
          </div>
          {m.matrix[ri].map((v, ci) => {
            const pct = v > 0 ? Math.round(12 + (v / m.max) * 68) : 0;
            return (
              <div
                key={ci}
                className="orient-mcell"
                title={`${s.sector} × ${REGIONS[ci].full} — ${v} holding${v === 1 ? "" : "s"}`}
                style={{ background: v > 0 ? `color-mix(in oklab, var(--accent) ${pct}%, transparent)` : "var(--bg-elev-2)" }}
              />
            );
          })}
          <div className="orient-msig mono">{tot}</div>
        </div>
      ))}
      <div className="orient-mrow orient-mfoot">
        <div className="orient-mlabel">Region Σ</div>
        {colTotals.map((n, i) => (
          <div className="orient-msig mono" key={i}>
            {n}
          </div>
        ))}
        <div className="orient-msig" />
      </div>
    </div>
  );
}

function OrientSkeleton() {
  return (
    <div aria-hidden="true">
      <Skeleton h={92} />
      <div style={{ height: 16 }} />
      <Skeleton h={28} w="70%" />
      <div style={{ height: 20 }} />
      <div className="orient-grid">
        <Skeleton h={420} />
        <div className="stack gap">
          <Skeleton h={190} />
          <Skeleton h={190} />
        </div>
      </div>
    </div>
  );
}
