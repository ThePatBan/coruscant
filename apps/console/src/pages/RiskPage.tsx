// Risk concentration — where the book clusters and what makes it up. A GICS
// sector × region heat-matrix built entirely from real graph data: GICS
// classification (gics-breakdown) crossed with EX-21 legal footprints
// (jurisdiction-exposure) per region. The drill groups the named holdings by GICS
// sub-industry, each with its subsidiary count and Exhibit-21 source, flags cells
// that changed overnight (from the dashboard stream), and surfaces a grounded
// concentration-risk note. No weights, no fabricated numbers — a 53-company sample.

import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, type Dashboard, type EntityRef } from "../api";
import { ErrorView, PanelHead, Skeleton } from "../components";
import { useAsync } from "../hooks";
import { loadRiskMatrix, REGIONS, type RiskMatrix } from "../riskmatrix";

interface DrillRow {
  co: EntityRef;
  sub: string;
  code: string | null;
  subs: number; // EX-21 entities in scope
  countries: string[];
  source: string | null;
}
interface SubGroup {
  sub: string;
  code: string | null;
  rows: DrillRow[];
}

type Dir = "risk" | "opp" | "event";

function changedDirs(dash: Dashboard | null): Map<string, Dir> {
  const m = new Map<string, Dir>();
  if (!dash) return m;
  for (const e of dash.recent_opportunities) if (!m.has(e.company_slug)) m.set(e.company_slug, "opp");
  for (const e of dash.recent_events) if (!m.has(e.company_slug)) m.set(e.company_slug, "event");
  for (const e of dash.recent_risks) m.set(e.company_slug, "risk"); // risk wins
  return m;
}

export function RiskPage() {
  const load = useAsync(() => Promise.all([loadRiskMatrix(), api.dashboard()]), []);
  const d: RiskMatrix | null = load.data ? load.data[0] : null;
  const changed = useMemo(() => changedDirs(load.data ? load.data[1] : null), [load.data]);

  // selected {r,c}; -1 means "whole row/column". Default to the densest cell.
  const [sel, setSel] = useState<{ r: number; c: number } | null>(null);
  const cur = useMemo(() => {
    if (sel) return sel;
    if (!d) return { r: 0, c: 0 };
    let best = { r: 0, c: 0, v: -1 };
    d.matrix.forEach((row, ri) => row.forEach((v, ci) => { if (v > best.v) best = { r: ri, c: ci, v }; }));
    return { r: best.r, c: best.c };
  }, [sel, d]);

  const drill = useMemo(() => {
    if (!d) return null;
    const { r, c } = cur;
    const region = c >= 0 ? REGIONS[c] : null;
    const sectorName = r >= 0 ? d.sectors[r]?.sector : null;
    const rows: DrillRow[] = [];
    const consider = (co: EntityRef) => {
      const byRegion = d.info.get(co.key);
      const meta = d.subOf.get(co.key) ?? { sub: "—", code: null };
      if (region) {
        const cell = byRegion?.get(region.key);
        if (!cell) return;
        rows.push({ co, sub: meta.sub, code: meta.code, subs: cell.subs, countries: cell.countries, source: cell.source });
      } else {
        const countries: string[] = [];
        let subs = 0;
        let source: string | null = null;
        byRegion?.forEach((cell) => {
          for (const cc of cell.countries) if (!countries.includes(cc)) countries.push(cc);
          subs += cell.subs;
          if (!source) source = cell.source;
        });
        if (countries.length) rows.push({ co, sub: meta.sub, code: meta.code, subs, countries, source });
      }
    };
    if (sectorName) {
      for (const co of d.sectorCompanies.get(sectorName) ?? []) consider(co);
    } else {
      for (const s of d.sectors) for (const co of d.sectorCompanies.get(s.sector) ?? []) consider(co);
    }
    rows.sort((a, b) => a.co.name.localeCompare(b.co.name));

    // group by GICS sub-industry, preserving first-seen order
    const groupMap = new Map<string, SubGroup>();
    for (const row of rows) {
      const key = row.code || row.sub;
      let g = groupMap.get(key);
      if (!g) groupMap.set(key, (g = { sub: row.sub, code: row.code, rows: [] }));
      g.rows.push(row);
    }
    const groups = [...groupMap.values()];

    const title = (sectorName ?? "All sectors") + (region ? ` × ${region.full}` : r >= 0 ? " — all regions" : "");
    const sectorTotal = d.sectors[r]?.companies;
    const more = sectorName && typeof sectorTotal === "number" ? Math.max(0, sectorTotal - rows.length) : 0;

    // changed-overnight pill: dominant dir among the drilled holdings
    let pill: Dir | null = null;
    for (const row of rows) {
      const dir = changed.get(row.co.key);
      if (dir === "risk") { pill = "risk"; break; }
      if (dir && !pill) pill = dir;
    }
    return { rows, groups, title, region, sectorName, sectorTotal, more, pill };
  }, [d, cur, changed]);

  const ranked = useMemo(() => {
    if (!d) return [];
    const cells: Array<{ r: number; c: number; v: number }> = [];
    d.matrix.forEach((row, ri) => row.forEach((v, ci) => { if (v > 0) cells.push({ r: ri, c: ci, v }); }));
    cells.sort((a, b) => b.v - a.v);
    return cells.slice(0, 6);
  }, [d]);

  const PILL_LABEL: Record<Dir, string> = { risk: "changed overnight · risk", opp: "changed overnight · opportunity", event: "changed overnight" };

  return (
    <div className="risk-page spatial-page">
      <div className="page-head">
        <div className="kicker">
          <span className="idx">01</span> Risk concentration
        </div>
        <h1 style={{ marginTop: 6 }}>Where the book clusters — and what makes it up</h1>
        <div className="muted small" style={{ marginTop: 6 }}>
          GICS sector × region, by count of holdings with an Exhibit-21 legal footprint. Click a cell, a
          sector, or a region to drill in. A curated 53-company sample — counts and share, never weights.
        </div>
      </div>

      {load.error ? (
        <ErrorView error={load.error} />
      ) : (
        <div className="risk-split">
          {/* LEFT: matrix + deepest concentrations */}
          <section className="risk-left">
            {load.loading || !d ? (
              <Skeleton h={300} />
            ) : (
              <>
                <div className="risk-matrix">
                  <div className="risk-mrow risk-mhead">
                    <div className="risk-rowlabel" />
                    {REGIONS.map((r, ci) => (
                      <button
                        key={r.key}
                        className={`risk-colh${cur.c === ci && cur.r < 0 ? " active" : ""}`}
                        onClick={() => setSel({ r: -1, c: ci })}
                        title={r.full}
                      >
                        {r.short}
                      </button>
                    ))}
                    <div className="risk-sig">Σ</div>
                  </div>
                  {d.sectors.map((s, ri) => (
                    <div className="risk-mrow" key={s.sector}>
                      <button
                        className={`risk-rowlabel risk-rowh${cur.r === ri && cur.c < 0 ? " active" : ""}`}
                        onClick={() => setSel({ r: ri, c: -1 })}
                        title={s.sector}
                      >
                        {s.sector}
                      </button>
                      {d.matrix[ri].map((v, ci) => {
                        const hot =
                          (cur.r === ri && cur.c === ci) ||
                          (cur.r === ri && cur.c < 0) ||
                          (cur.c === ci && cur.r < 0);
                        const pct = v > 0 ? Math.round(12 + (v / d.max) * 68) : 0;
                        return (
                          <button
                            key={ci}
                            className={`risk-cell${hot ? " hot" : ""}`}
                            onClick={() => setSel({ r: ri, c: ci })}
                            title={`${s.sector} × ${REGIONS[ci].full} — ${v} holding${v === 1 ? "" : "s"} with a footprint`}
                            style={{
                              background: v > 0 ? `color-mix(in oklab, var(--accent) ${pct}%, transparent)` : "var(--bg-elev-2)",
                            }}
                          >
                            {v > 0 ? <span className="risk-cell-v">{v}</span> : null}
                          </button>
                        );
                      })}
                      <div className="risk-sig mono">{s.companies}</div>
                    </div>
                  ))}
                  <div className="risk-mrow risk-mfoot">
                    <div className="risk-rowlabel">Region Σ</div>
                    {REGIONS.map((r) => (
                      <div className="risk-sig mono" key={r.key}>{d.regionKeys.get(r.key)!.size}</div>
                    ))}
                    <div className="risk-sig" />
                  </div>
                </div>

                <div className="risk-legend">
                  <span className="risk-legend-scale">
                    less
                    <span className="sw" style={{ background: "color-mix(in oklab, var(--accent) 12%, transparent)", border: "1px solid var(--border)" }} />
                    <span className="sw" style={{ background: "color-mix(in oklab, var(--accent) 42%, transparent)" }} />
                    <span className="sw" style={{ background: "color-mix(in oklab, var(--accent) 80%, transparent)" }} />
                    more holdings
                  </span>
                  <span className="src-link"><span className="arrow">↳</span> Exhibit-21</span>
                </div>

                <div style={{ marginTop: 22 }}>
                  <PanelHead idx="02" kicker="Deepest concentrations" title="" />
                  <div className="stack">
                    {ranked.map((cell, i) => {
                      const on = cur.r === cell.r && cur.c === cell.c;
                      return (
                        <button
                          key={`${cell.r}-${cell.c}`}
                          className={`risk-rank${on ? " active" : ""}`}
                          onClick={() => setSel({ r: cell.r, c: cell.c })}
                        >
                          <span className="mono muted risk-rank-i">0{i + 1}</span>
                          <span className="risk-rank-l">
                            {d.sectors[cell.r].sector} × {REGIONS[cell.c].full}
                          </span>
                          <span className="mono muted risk-rank-n">{cell.v} hldgs</span>
                        </button>
                      );
                    })}
                  </div>
                </div>
              </>
            )}
          </section>

          {/* RIGHT: drill */}
          <section className="risk-right">
            {load.loading || !drill ? (
              <Skeleton h={200} />
            ) : (
              <>
                <div className="risk-drill-head">
                  <div style={{ minWidth: 0 }}>
                    <div className="kicker">Drill-down</div>
                    <h2 style={{ marginTop: 6 }}>{drill.title}</h2>
                    <div className="mono muted" style={{ marginTop: 7 }}>
                      {drill.rows.length} holding{drill.rows.length === 1 ? "" : "s"} with a legal footprint
                      {drill.region ? ` in ${drill.region.full}` : ""}
                    </div>
                  </div>
                  {drill.pill ? <span className={`risk-changed-pill ${drill.pill}`}>{PILL_LABEL[drill.pill]}</span> : null}
                </div>

                {drill.region && drill.rows.length >= 2 ? (
                  <div className="risk-callout">
                    <span className="risk-callout-l">Concentration risk</span>
                    <span className="risk-callout-t">
                      {drill.rows.length} holdings share a legal footprint in {drill.region.full} — a correlated{" "}
                      {drill.sectorName ? drill.sectorName.toLowerCase() : ""} cluster; a shock here reaches them together.
                    </span>
                  </div>
                ) : null}

                <div className="dp-section">
                  <div className="dp-section-head">
                    <span className="kicker">By GICS sub-industry</span>
                    <span className="src-link"><span className="arrow">↳</span> EX-21 / 10-K</span>
                  </div>
                  {drill.rows.length === 0 ? (
                    <div className="muted small">
                      No Exhibit-21 footprint recorded for this{drill.region ? " sector in this region" : " sector"}.
                    </div>
                  ) : (
                    <div className="stack gap">
                      {drill.groups.map((g) => (
                        <div className="risk-subgroup" key={g.code || g.sub}>
                          <div className="risk-subhead">
                            <span className="risk-subdot" />
                            <span className="risk-subname">{g.sub}</span>
                            {g.code ? <span className="mono muted small">{g.code}</span> : null}
                            <span style={{ flex: 1 }} />
                            <span className="mono muted small">
                              {g.rows.length} holding{g.rows.length === 1 ? "" : "s"}
                            </span>
                          </div>
                          <div className="risk-holdings">
                            {g.rows.map((row) => (
                              <div className="risk-hrow" key={row.co.key}>
                                <div style={{ flex: 1, minWidth: 0 }}>
                                  <div className="risk-hname">{row.co.name}</div>
                                  {row.countries.length ? (
                                    <div className="mono muted small">{row.countries.join(", ")}</div>
                                  ) : null}
                                </div>
                                <span className="mono muted small risk-entities">
                                  {row.subs} {row.subs === 1 ? "entity" : "entities"} here
                                </span>
                                {row.source ? (
                                  <a className="src-link" href={row.source} target="_blank" rel="noreferrer" title="Open EX-21 / 10-K source">
                                    <span className="arrow">↳</span> EX-21 / 10-K
                                  </a>
                                ) : null}
                              </div>
                            ))}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                  {drill.more > 0 ? (
                    <div className="mono muted small" style={{ marginTop: 12 }}>
                      + {drill.more} more in the 53-company sample (named holdings shown)
                    </div>
                  ) : null}
                </div>

                <div className="risk-actions">
                  {drill.pill ? (
                    <Link className="btn ghost" to="/changes">See what changed here →</Link>
                  ) : null}
                  <span style={{ flex: 1 }} />
                  <Link className="btn" to="/atlas">Open these in Atlas ✦ →</Link>
                </div>
              </>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
