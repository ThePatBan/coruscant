// Geo lookup for the Live Signals globe. Company → HQ country is public fact (a
// static classification, like GICS/MSCI), not fabricated data. Coordinates are
// country centroids; per-company pins are deterministically jittered around the
// centroid so a country's holdings spread into a legible cluster rather than
// stacking on one point.

export const COUNTRY_CENTROID: Record<string, { lat: number; lon: number }> = {
  "United States": { lat: 39, lon: -98 },
  "United Kingdom": { lat: 54, lon: -2 },
  India: { lat: 22, lon: 79 },
  Germany: { lat: 51, lon: 10.4 },
  Japan: { lat: 37, lon: 138 },
  China: { lat: 35, lon: 104 },
  Netherlands: { lat: 52.2, lon: 5.3 },
  France: { lat: 46.5, lon: 2.5 },
  Switzerland: { lat: 46.8, lon: 8.2 },
  Ireland: { lat: 53.2, lon: -8 },
  Brazil: { lat: -10, lon: -52 },
  Singapore: { lat: 1.35, lon: 103.8 },
  Canada: { lat: 56, lon: -106 },
};

// HQ / primary-listing country for the 53-company graph (30 US Dow · 15 UK 20-F ·
// 8 India ADRs). Keyed by graph slug.
export const CO_COUNTRY: Record<string, string> = {
  // United States
  aapl: "United States", amgn: "United States", amzn: "United States", axp: "United States",
  ba: "United States", cat: "United States", crm: "United States", csco: "United States",
  cvx: "United States", dis: "United States", gs: "United States", hd: "United States",
  hon: "United States", ibm: "United States", jnj: "United States", jpm: "United States",
  ko: "United States", mcd: "United States", mmm: "United States", mrk: "United States",
  msft: "United States", nke: "United States", nvda: "United States", pg: "United States",
  shw: "United States", trv: "United States", unh: "United States", v: "United States",
  vz: "United States", wmt: "United States",
  // United Kingdom
  azn: "United Kingdom", bcs: "United Kingdom", bp: "United Kingdom", bti: "United Kingdom",
  deo: "United Kingdom", gsk: "United Kingdom", hsbc: "United Kingdom", ngg: "United Kingdom",
  nwg: "United Kingdom", puk: "United Kingdom", relx: "United Kingdom", rio: "United Kingdom",
  shel: "United Kingdom", ul: "United Kingdom", vod: "United Kingdom",
  // India
  hdb: "India", ibn: "India", infy: "India", mmyt: "India", rdy: "India", sify: "India",
  wit: "India", ytra: "India",
};

// simple deterministic hash → [-1, 1]
function jitter(seed: string, salt: number): number {
  let h = 2166136261 ^ salt;
  for (let i = 0; i < seed.length; i++) {
    h ^= seed.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return ((h >>> 0) % 1000) / 500 - 1; // -1..1
}

/** Located coordinate for a company: HQ centroid + deterministic spread. */
export function coordForCompany(slug: string): { lat: number; lon: number; country: string } | null {
  const country = CO_COUNTRY[slug];
  if (!country) return null;
  const c = COUNTRY_CENTROID[country];
  if (!c) return null;
  const spread = country === "United States" ? 11 : country === "India" ? 6 : 4;
  return {
    country,
    lat: c.lat + jitter(slug, 7) * spread * 0.7,
    lon: c.lon + jitter(slug, 13) * spread,
  };
}
