// Data adapter for the 3D force-directed Atlas. Turns the loaded company
// profiles into a {nodes, links} graph for react-force-graph-3d, with:
//   - colour by SIC sector (our community assignment — no Louvain needed)
//   - size by importance (degree)
//   - DETERMINISTIC seeded positions + per-sector anchor points, so the layout
//     is reproducible (the project's "same data → same picture" rule) and
//     companies cluster by sector rather than settling into a random hairball.

import type { Company, EntityProfile } from "./api";
import { coarseSector } from "./relations";

export interface FNode {
  id: string;
  name: string;
  kind: "Company" | "Subsidiary" | "Person";
  slug?: string; // company slug, for selection
  sector: string;
  country?: string; // for the transatlantic layer
  val: number; // node size (importance)
  tracked: boolean;
  x?: number;
  y?: number;
  z?: number;
}

// Key people (executive officers) render as a distinct "leadership" layer — one
// warm hue across all sectors, so the people stand out from the sector-coloured
// companies and their subsidiary halos.
export const PERSON_COLOR = "#ecd9a6";

export interface FLink {
  source: string;
  target: string;
  relation: string;
  crossBorder?: boolean; // a co-mention between companies in different countries
}

export interface ForceData {
  nodes: FNode[];
  links: FLink[];
  sectors: string[];
  sectorAnchor: Map<string, { x: number; y: number; z: number }>;
}

// Sector palette — distinct, calm hues that read on the near-black background.
const SECTOR_COLORS: Record<string, string> = {
  Technology: "#7c8cff",
  Financials: "#4bd6a0",
  Health: "#d782ad",
  Consumer: "#f3b94d",
  Retail: "#6aa9bd",
  Industrials: "#e0865b",
  Energy: "#7fd1a6",
  Telecom: "#b39bff",
  Other: "#8793a5",
};

export function sectorColor(sector: string): string {
  return SECTOR_COLORS[sector] ?? SECTOR_COLORS.Other;
}

// entity-to-entity relations rendered as links in 3D.
const LINK_RELATIONS = new Set(["references", "has_subsidiary", "employs", "board_member"]);

// Deterministic pseudo-random in [0,1) from a string (FNV-1a). No Math.random,
// so seeded positions are identical every load.
function hash01(seed: string): number {
  let h = 2166136261;
  for (let i = 0; i < seed.length; i++) {
    h ^= seed.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return ((h >>> 0) % 100000) / 100000;
}

export function buildForceData(companies: Company[], profiles: Map<string, EntityProfile>): ForceData {
  const sectorOf = new Map(companies.map((c) => [c.slug, coarseSector(c.industry)]));
  const countryOf = new Map(companies.map((c) => [c.slug, c.country ?? undefined]));
  const trackedSlugs = new Set(companies.map((c) => c.slug));
  const nodes = new Map<string, FNode>();
  const links: FLink[] = [];
  const seenLink = new Set<string>();
  const degree = new Map<string, number>();

  const ensure = (id: string, name: string, kind: FNode["kind"], sector: string, tracked: boolean, slug?: string) => {
    if (!nodes.has(id))
      nodes.set(id, {
        id,
        name,
        kind,
        sector,
        tracked,
        slug,
        country: slug ? countryOf.get(slug) : undefined,
        val: tracked ? 6 : 1.6,
      });
  };

  for (const c of companies) {
    ensure(`Company:${c.slug}`, c.name, "Company", sectorOf.get(c.slug) ?? "Other", true, c.slug);
  }

  for (const c of companies) {
    const prof = profiles.get(c.slug);
    if (!prof) continue;
    const sourceId = `Company:${c.slug}`;
    const sourceSector = sectorOf.get(c.slug) ?? "Other";
    for (const rel of prof.relationships) {
      if (!LINK_RELATIONS.has(rel.relation)) continue;
      const other = rel.other;
      const targetId = `${other.kind}:${other.key}`;
      if (rel.relation === "references") {
        if (!trackedSlugs.has(other.key)) continue; // company↔company only
        ensure(targetId, other.name, "Company", sectorOf.get(other.key) ?? "Other", true, other.key);
      } else if (rel.relation === "employs" || rel.relation === "board_member") {
        if (other.kind !== "Person") continue;
        // a key person / director, clustered with the company but drawn distinctly;
        // a person linked to ≥2 companies is a board interlock (a bridge)
        ensure(targetId, other.name, "Person", sourceSector, false);
      } else {
        // has_subsidiary → a Subsidiary node, coloured by its parent's sector
        ensure(targetId, other.name, "Subsidiary", sourceSector, false);
      }
      const key = [sourceId, targetId].sort().join("|") + "|" + rel.relation;
      if (seenLink.has(key)) continue;
      seenLink.add(key);
      const crossBorder =
        rel.relation === "references" &&
        !!countryOf.get(c.slug) &&
        !!countryOf.get(other.key) &&
        countryOf.get(c.slug) !== countryOf.get(other.key);
      links.push({ source: sourceId, target: targetId, relation: rel.relation, crossBorder });
      degree.set(sourceId, (degree.get(sourceId) ?? 0) + 1);
      degree.set(targetId, (degree.get(targetId) ?? 0) + 1);
    }
  }

  // Size companies by degree (importance); subsidiaries stay small. People who
  // link to ≥2 companies are board interlocks (bridges) — size them up so they
  // read as the connective tissue between clusters.
  for (const n of nodes.values()) {
    if (n.tracked) n.val = 5 + (degree.get(n.id) ?? 0) * 0.8;
    else if (n.kind === "Person") n.val = (degree.get(n.id) ?? 0) >= 2 ? 4.5 : 1.6;
  }

  // Sector anchor points distributed deterministically on a sphere.
  const sectors = [...new Set([...nodes.values()].map((n) => n.sector))].sort();
  const sectorAnchor = new Map<string, { x: number; y: number; z: number }>();
  const R = 230;
  const golden = Math.PI * (1 + Math.sqrt(5));
  sectors.forEach((sec, i) => {
    const t = (i + 0.5) / sectors.length;
    const phi = Math.acos(1 - 2 * t);
    const theta = golden * i;
    sectorAnchor.set(sec, {
      x: R * Math.sin(phi) * Math.cos(theta),
      y: R * Math.sin(phi) * Math.sin(theta),
      z: R * Math.cos(phi),
    });
  });

  // Seed each node near its sector anchor (deterministic jitter) so the sim
  // starts clustered and converges to the same reproducible shape.
  for (const n of nodes.values()) {
    const a = sectorAnchor.get(n.sector)!;
    n.x = a.x + (hash01(n.id + "x") - 0.5) * 130;
    n.y = a.y + (hash01(n.id + "y") - 0.5) * 130;
    n.z = a.z + (hash01(n.id + "z") - 0.5) * 130;
  }

  return { nodes: [...nodes.values()], links, sectors, sectorAnchor };
}
