// Risk concentration — where the book clusters and what makes it up. A GICS
// sector × region heat-matrix built entirely from real graph data: GICS
// classification (gics-breakdown) crossed with EX-21 legal footprints
// (jurisdiction-exposure) per region. Every cell count is a distinct-company
// count with an Exhibit-21 footprint; the drill lists the named holdings with
// their source. No weights, no fabricated numbers — a curated 53-company sample.

import { useMemo, useState } from "react";
import { api, type EntityRef, type GicsSector, type JurisdictionExposure } from "../api";
import { ErrorView, PanelHead, Skeleton } from "../components";
import { useAsync } from "../hooks";

interface Region {
  key: string;
  short: string;
  full: string;
  countries: string[];
}

// Region → member jurisdictions (all confirmed to carry EX-21 footprints in the
// graph). Geography is a static classification, not fabricated data.
const REGIONS: Region[] = [
  { key: "na", short: "N.Am", full: "North America", countries: ["United States", "Canada", "Mexico"] },
  { key: "eu", short: "Europe", full: "Europe", countries: ["United Kingdom", "Germany", "France", "Ireland", "Netherlands", "Switzerland", "Luxembourg"] },
  { key: "ea", short: "E.Asia", full: "East Asia", countries: ["China", "Japan", "Singapore"] },
  { key: "sa", short: "S.Asia", full: "South Asia", countries: ["India"] },
  { key: "la", short: "LatAm", full: "Latin America", countries: ["Brazil"] },
];

const ALL_COUNTRIES = Array.from(new Set(REGIONS.flatMap((r) => r.countries)));

interface Derived {
  sectors: GicsSector[];
  sectorOf: Map<string, string>; // company key → sector name
  sectorCompanies: Map<string, EntityRef[]>; // sector → distinct companies
  regionKeys: Map<string, Set<string>>; // region key → company keys w/ footprint
  // company key → region key → { countries where it has a footprint, EX-21 source }
  info: Map<string, Map<string, { countries: string[]; source: string | null }>>;
  matrix: number[][]; // [sectorIdx][regionIdx]
  max: number;
}

function derive(gics: GicsSector[], results: Array<readonly [string, JurisdictionExposure]>): Derived {
  const countryRegion = new Map<string, string>();
  for (const r of REGIONS) for (const c of r.countries) countryRegion.set(c, r.key);

  const sectorOf = new Map<string, string>();
  const sectorCompanies = new Map<string, EntityRef[]>();
  for (const s of gics) {
    const seen = new Set<string>();
    const list: EntityRef[] = [];
    for (const sub of s.sub_industries) {
      for (const co of sub.companies) {
        if (!sectorOf.has(co.key)) sectorOf.set(co.key, s.sector);
        if (!seen.has(co.key)) {
          seen.add(co.key);
          list.push(co);
        }
      }
    }
    sectorCompanies.set(s.sector, list);
  }

  const regionKeys = new Map<string, Set<string>>();
  for (const r of REGIONS) regionKeys.set(r.key, new Set());
  const info = new Map<string, Map<string, { countries: string[]; source: string | null }>>();

  for (const [country, expo] of results) {
    const rk = countryRegion.get(country);
    if (!rk) continue;
    for (const f of expo.direct) {
      regionKeys.get(rk)!.add(f.company.key);
      let byRegion = info.get(f.company.key);
      if (!byRegion) info.set(f.company.key, (byRegion = new Map()));
      let cell = byRegion.get(rk);
      if (!cell) byRegion.set(rk, (cell = { countries: [], source: null }));
      if (!cell.countries.includes(country)) cell.countries.push(country);
      if (!cell.source && f.source) cell.source = f.source;
    }
  }

  const matrix = gics.map((s) =>
    REGIONS.map((r) => {
      const keys = regionKeys.get(r.key)!;
      let n = 0;
      for (const co of sectorCompanies.get(s.sector) ?? []) if (keys.has(co.key)) n++;
      return n;
    }),
  );
  const max = Math.max(1, ...matrix.flat());
  return { sectors: gics, sectorOf, sectorCompanies, regionKeys, info, matrix, max };
}

interface DrillRow {
  co: EntityRef;
  sector: string;
  countries: string[];
  source: string | null;
}

export function RiskPage() {
  const load = useAsync(
    () =>
      Promise.all([
        api.gicsBreakdown(),
        Promise.all(ALL_COUNTRIES.map((c) => api.jurisdictionExposure(c).then((r) => [c, r] as const))),
      ]),
    [],
  );

  const d = useMemo<Derived | null>(() => {
    if (!load.data) return null;
    return derive(load.data[0], load.data[1]);
  }, [load.data]);

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
      if (region) {
        const cell = byRegion?.get(region.key);
        if (!cell) return;
        rows.push({ co, sector: d.sectorOf.get(co.key) ?? "—", countries: cell.countries, source: cell.source });
      } else {
        // whole row: any region footprint
        const countries: string[] = [];
        let source: string | null = null;
        byRegion?.forEach((cell) => {
          for (const cc of cell.countries) if (!countries.includes(cc)) countries.push(cc);
          if (!source) source = cell.source;
        });
        if (countries.length) rows.push({ co, sector: d.sectorOf.get(co.key) ?? "—", countries, source });
      }
    };
    if (sectorName) {
      for (const co of d.sectorCompanies.get(sectorName) ?? []) consider(co);
    } else {
      // whole column: every company with a footprint in the region, any sector
      for (const s of d.sectors) for (const co of d.sectorCompanies.get(s.sector) ?? []) consider(co);
    }
    rows.sort((a, b) => a.co.name.localeCompare(b.co.name));
    const title =
      (sectorName ?? "All sectors") + (region ? ` × ${region.full}` : r >= 0 ? " — all regions" : "");
    const total = d.sectors[r]?.companies;
    return { rows, title, region, sectorName, sectorTotal: total };
  }, [d, cur]);

  // ranked "deepest concentrations"
  const ranked = useMemo(() => {
    if (!d) return [];
    const cells: Array<{ r: number; c: number; v: number }> = [];
    d.matrix.forEach((row, ri) => row.forEach((v, ci) => { if (v > 0) cells.push({ r: ri, c: ci, v }); }));
    cells.sort((a, b) => b.v - a.v);
    return cells.slice(0, 6);
  }, [d]);

  return (
    <div className="risk-page">
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
                <div className="kicker">Drill-down</div>
                <h2 style={{ marginTop: 6 }}>{drill.title}</h2>
                <div className="mono muted" style={{ marginTop: 7 }}>
                  {drill.rows.length} holding{drill.rows.length === 1 ? "" : "s"} with a legal footprint
                  {drill.region ? ` in ${drill.region.full}` : ""}
                  {typeof drill.sectorTotal === "number" && drill.sectorName
                    ? ` · ${drill.sectorTotal} in sector`
                    : ""}
                </div>

                <div className="dp-section">
                  <div className="dp-section-head">
                    <span className="kicker">Named holdings</span>
                    <span className="src-link"><span className="arrow">↳</span> EX-21</span>
                  </div>
                  {drill.rows.length === 0 ? (
                    <div className="muted small">
                      No Exhibit-21 footprint recorded for this{drill.region ? " sector in this region" : " sector"}.
                    </div>
                  ) : (
                    <div className="risk-holdings">
                      {drill.rows.map((row) => (
                        <div className="risk-hrow" key={row.co.key}>
                          <div style={{ flex: 1, minWidth: 0 }}>
                            <div className="risk-hname">{row.co.name}</div>
                            <div className="mono muted small">
                              {row.sector}
                              {row.countries.length ? ` · ${row.countries.join(", ")}` : ""}
                            </div>
                          </div>
                          {row.source ? (
                            <a className="src-link" href={row.source} target="_blank" rel="noreferrer" title="Open EX-21 source">
                              <span className="arrow">↳</span> source
                            </a>
                          ) : null}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
