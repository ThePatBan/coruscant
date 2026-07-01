// Shared sector × region concentration crosstab, built from real graph data:
// GICS classification (gics-breakdown) crossed with EX-21 legal footprints
// (jurisdiction-exposure). One source of truth for the full /risk matrix and the
// compact version on the Orientation dashboard. Every count is a distinct company
// with an Exhibit-21 footprint — never a weight, never fabricated.

import { api, type EntityRef, type GicsSector, type JurisdictionExposure } from "./api";

export interface Region {
  key: string;
  short: string;
  full: string;
  countries: string[];
}

// Region → member jurisdictions (all confirmed to carry EX-21 footprints in the
// graph). Ordered E.Asia-first to match the design pack; geography is a static
// classification, not fabricated data.
export const REGIONS: Region[] = [
  { key: "ea", short: "E.Asia", full: "East Asia", countries: ["China", "Japan", "Singapore", "South Korea", "Hong Kong", "Taiwan"] },
  { key: "na", short: "N.Am", full: "North America", countries: ["United States", "Canada", "Mexico"] },
  { key: "eu", short: "Europe", full: "Europe", countries: ["United Kingdom", "Germany", "France", "Ireland", "Netherlands", "Switzerland", "Luxembourg"] },
  { key: "sa", short: "S.Asia", full: "South Asia", countries: ["India"] },
  { key: "la", short: "LatAm", full: "Latin America", countries: ["Brazil", "Argentina", "Chile"] },
];

export const ALL_COUNTRIES = Array.from(new Set(REGIONS.flatMap((r) => r.countries)));

interface CellInfo {
  countries: string[];
  subs: number; // EX-21 subsidiaries in this region
  source: string | null;
}

export interface RiskMatrix {
  sectors: GicsSector[];
  sectorOf: Map<string, string>; // company key → sector name
  subOf: Map<string, { sub: string; code: string | null }>; // company key → GICS sub-industry
  sectorCompanies: Map<string, EntityRef[]>; // sector → distinct companies
  regionKeys: Map<string, Set<string>>; // region key → company keys w/ footprint
  info: Map<string, Map<string, CellInfo>>; // company key → region key → footprint detail
  matrix: number[][]; // [sectorIdx][regionIdx]
  max: number;
}

/** Fetch gics-breakdown + jurisdiction-exposure for every region country. */
export async function loadRiskMatrix(): Promise<RiskMatrix> {
  const [gics, results] = await Promise.all([
    api.gicsBreakdown(),
    Promise.all(ALL_COUNTRIES.map((c) => api.jurisdictionExposure(c).then((r) => [c, r] as const))),
  ]);
  return derive(gics, results);
}

export function derive(gics: GicsSector[], results: Array<readonly [string, JurisdictionExposure]>): RiskMatrix {
  const countryRegion = new Map<string, string>();
  for (const r of REGIONS) for (const c of r.countries) countryRegion.set(c, r.key);

  const sectorOf = new Map<string, string>();
  const subOf = new Map<string, { sub: string; code: string | null }>();
  const sectorCompanies = new Map<string, EntityRef[]>();
  for (const s of gics) {
    const seen = new Set<string>();
    const list: EntityRef[] = [];
    for (const sub of s.sub_industries) {
      for (const co of sub.companies) {
        if (!sectorOf.has(co.key)) sectorOf.set(co.key, s.sector);
        if (!subOf.has(co.key)) subOf.set(co.key, { sub: sub.sub_industry, code: sub.code ?? null });
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
  const info = new Map<string, Map<string, CellInfo>>();

  for (const [country, expo] of results) {
    const rk = countryRegion.get(country);
    if (!rk) continue;
    for (const f of expo.direct) {
      regionKeys.get(rk)!.add(f.company.key);
      let byRegion = info.get(f.company.key);
      if (!byRegion) info.set(f.company.key, (byRegion = new Map()));
      let cell = byRegion.get(rk);
      if (!cell) byRegion.set(rk, (cell = { countries: [], subs: 0, source: null }));
      if (!cell.countries.includes(country)) cell.countries.push(country);
      cell.subs += f.subsidiaries.length;
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
  return { sectors: gics, sectorOf, subOf, sectorCompanies, regionKeys, info, matrix, max };
}

/** The single densest (sector, region) cell — used for "investigate first". */
export function densestCell(m: RiskMatrix): { sector: string; region: Region; count: number } | null {
  let best = { r: -1, c: -1, v: 0 };
  m.matrix.forEach((row, ri) => row.forEach((v, ci) => { if (v > best.v) best = { r: ri, c: ci, v }; }));
  if (best.r < 0) return null;
  return { sector: m.sectors[best.r].sector, region: REGIONS[best.c], count: best.v };
}
