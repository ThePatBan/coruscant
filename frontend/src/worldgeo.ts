// Shared world geometry for the focused canvas maps (Country page, and any
// future flat map). We reuse the app's existing `world-atlas` dependency rather
// than the design pack's bespoke `world-110m.json` — same Natural Earth 110m
// source, one map layer for the whole app.

import { feature } from "topojson-client";
import landTopo from "world-atlas/countries-110m.json";

/** A polygon ring as [lon, lat] pairs. */
export type Ring = [number, number][];

interface GeoFeature {
  geometry: { type: string; coordinates: unknown } | null;
}

const collection = feature(
  landTopo as never,
  (landTopo as never as { objects: { countries: never } }).objects.countries,
) as never as { features: GeoFeature[] };

/**
 * Every country polygon flattened to a flat list of rings — the cheap form for
 * canvas stroking (coastlines + shared borders both come out of the outlines).
 * Computed once at module load.
 */
export const WORLD_RINGS: Ring[] = (() => {
  const rings: Ring[] = [];
  for (const f of collection.features) {
    const g = f.geometry;
    if (!g) continue;
    if (g.type === "Polygon") {
      for (const r of g.coordinates as Ring[]) rings.push(r);
    } else if (g.type === "MultiPolygon") {
      for (const poly of g.coordinates as Ring[][]) for (const r of poly) rings.push(r);
    }
  }
  return rings;
})();
