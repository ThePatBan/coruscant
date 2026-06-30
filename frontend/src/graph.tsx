// Relationship map — a deterministic SVG node-link view of the knowledge graph.
//
// No layout library and no animation jitter: positions are computed analytically
// so the same data always draws the same picture. Tracked companies sit on a
// ring; the *bridges* that connect them (a shared executive, a shared supplier,
// a shared technology) are pulled toward the centre, which is exactly where the
// cross-company story lives. Everything is colored by the relation tier
// (relations.ts) so control, proxy-control, and supply exposure read at a glance.

import { useMemo, useState, type KeyboardEvent } from "react";
import { useNavigate } from "react-router-dom";
import { api, type Company, type EntityProfile } from "./api";
import { useAsync } from "./hooks";
import { coarseSector, isEntityRelation, kindGlyph, relationTier, relationVerb, tierLabel, TIERS, type RelationTier } from "./relations";

export interface GNode {
  id: string;
  kind: string;
  key: string;
  name: string;
  tracked: boolean;
  /** tracked-company keys this node connects (≥2 ⇒ a bridge). */
  bridges: string[];
  /** SEC SIC industry of a tracked company; drives sector clustering on the ring. */
  sector?: string;
}

export interface GEdge {
  id: string;
  source: string;
  target: string;
  relation: string;
  tier: RelationTier;
}

export interface RelGraph {
  nodes: GNode[];
  edges: GEdge[];
}

const nodeId = (kind: string, key: string) => `${kind}:${key}`;

/** Build a relationship graph from the entity profiles of the tracked companies.
 *  `sectorBySlug` (optional) attaches each tracked company's industry for sector
 *  clustering; omit it to keep the plain alphabetical ring (e.g. the dashboard). */
export function buildGraph(
  profiles: EntityProfile[],
  trackedKeys: Iterable<string>,
  sectorBySlug?: Map<string, string>,
): RelGraph {
  const tracked = new Set(trackedKeys);
  const nodes = new Map<string, GNode>();
  const edges = new Map<string, GEdge>();

  const ensure = (kind: string, key: string, name: string): string => {
    const id = nodeId(kind, key);
    const existing = nodes.get(id);
    if (existing) {
      if (!existing.name && name) existing.name = name;
      return id;
    }
    const isTracked = kind === "Company" && tracked.has(key);
    nodes.set(id, {
      id,
      kind,
      key,
      name: name || key,
      tracked: isTracked,
      bridges: [],
      sector: isTracked ? sectorBySlug?.get(key) : undefined,
    });
    return id;
  };

  for (const profile of profiles) {
    const cid = ensure("Company", profile.entity.key, profile.entity.name);
    for (const rel of profile.relationships) {
      if (!isEntityRelation(rel.relation)) continue;
      // Country/Industry are low-signal hubs; Subsidiary nodes are numerous
      // (a company can declare hundreds in Exhibit 21) and per-company, so they
      // would swamp the overview. All three stay out of the map but remain in the
      // rail's typed relationship lists; cross-company structure on the map comes
      // from company↔company edges.
      if (rel.other.kind === "Country" || rel.other.kind === "Industry" || rel.other.kind === "Subsidiary") continue;
      const oid = ensure(rel.other.kind, rel.other.key, rel.other.name);
      const [a, b] = [cid, oid].sort();
      const ek = `${a}|${b}|${rel.relation}`;
      if (!edges.has(ek)) {
        edges.set(ek, { id: ek, source: cid, target: oid, relation: rel.relation, tier: relationTier(rel.relation) });
      }
    }
  }

  // A non-tracked node bridges every tracked company it touches.
  for (const e of edges.values()) {
    const s = nodes.get(e.source)!;
    const t = nodes.get(e.target)!;
    if (s.tracked && !t.tracked && !t.bridges.includes(s.key)) t.bridges.push(s.key);
    if (t.tracked && !s.tracked && !s.bridges.includes(t.key)) s.bridges.push(t.key);
  }

  return { nodes: [...nodes.values()], edges: [...edges.values()] };
}

export interface LoadedGraph {
  graph: RelGraph;
  trackedKeys: Set<string>;
  companies: Company[];
  /** raw entity profiles keyed by company slug, for typed relationship views. */
  profiles: Map<string, EntityProfile>;
  /** companies whose profile failed to load — the graph is incomplete by this many. */
  failed: number;
}

/** Load the tracked companies and their entity profiles, then build the graph. */
export function useRelGraph() {
  return useAsync<LoadedGraph>(async () => {
    const companies = await api.companies();
    const trackedKeys = new Set(companies.map((c) => c.slug));
    const sectorBySlug = new Map(companies.map((c) => [c.slug, c.industry ?? ""]));
    const loaded = await Promise.all(companies.map((c) => api.entity("Company", c.slug).catch(() => null)));
    const profiles = new Map<string, EntityProfile>();
    let failed = 0;
    companies.forEach((c, i) => {
      const p = loaded[i];
      if (p) profiles.set(c.slug, p);
      else failed += 1;
    });
    const graph = buildGraph([...profiles.values()], trackedKeys, sectorBySlug);
    return { graph, trackedKeys, companies, profiles, failed };
  }, []);
}

/** A small inline notice when part of the graph could not be loaded, so an empty
 *  region reads as "load failure" rather than "no relationships exist". */
export function GraphIncompleteNote({ failed }: { failed: number }) {
  if (failed <= 0) return null;
  return (
    <div className="errbox" role="status" style={{ marginTop: 4 }}>
      Relationships for {failed} {failed === 1 ? "company" : "companies"} could not be loaded — the map
      may be incomplete. Reload to retry.
    </div>
  );
}

export interface GraphStats {
  companies: number;
  links: number;
  bridges: number;
}

export function graphStats(graph: RelGraph): GraphStats {
  return {
    companies: graph.nodes.filter((n) => n.tracked).length,
    links: graph.edges.length,
    bridges: graph.nodes.filter((n) => !n.tracked && n.bridges.length >= 2).length,
  };
}

// ---- layout ----------------------------------------------------------------

interface Pt {
  x: number;
  y: number;
}

export type Mode = "core" | "full" | "ego";

interface Dims {
  w: number;
  h: number;
  cx: number;
  cy: number;
  Rc: number; // company-ring radius
  leafR: number; // radius for full-mode leaf nodes
}

// Each mode gets a viewBox sized to hold everything it draws, so nodes and
// labels never clip. The SVG scales to its container width regardless.
function dimsFor(mode: Mode): Dims {
  if (mode === "full") {
    const w = 1160;
    const h = 820;
    return { w, h, cx: w / 2, cy: h / 2, Rc: 235, leafR: 352 };
  }
  if (mode === "ego") {
    const w = 780;
    const h = 560;
    return { w, h, cx: w / 2, cy: h / 2, Rc: Math.min(780, 560) * 0.36, leafR: 0 };
  }
  const w = 820;
  const h = 540;
  return { w, h, cx: w / 2, cy: h / 2, Rc: 172, leafR: 0 };
}

export interface Layout {
  pos: Map<string, Pt>;
  visible: Set<string>;
  w: number;
  h: number;
  sectorLabels: SectorLabel[];
}

export interface SectorLabel {
  label: string;
  x: number;
  y: number;
}

/** Place tracked companies on the ring, grouped into adjacent sector arcs with a
 *  gap between sectors, so same-sector companies cluster. Returns a label anchor
 *  per sector (at the arc midpoint, just outside the ring). Deterministic; with
 *  one sector (or no sector data) it degrades to a plain evenly-spaced ring. */
function placeTrackedRing(
  tracked: GNode[],
  pos: Map<string, Pt>,
  visible: Set<string>,
  cx: number,
  cy: number,
  Rc: number,
): SectorLabel[] {
  const groups = new Map<string, GNode[]>();
  for (const n of tracked) {
    const sec = coarseSector(n.sector);
    (groups.get(sec) ?? groups.set(sec, []).get(sec)!).push(n);
  }
  const sectors = [...groups.keys()].sort();
  const GAP = 1.4; // inter-sector gap, in company-slot units
  type Slot = { node?: GNode; sector?: string; w: number };
  const seq: Slot[] = [];
  let total = 0;
  sectors.forEach((sec, gi) => {
    if (gi > 0) {
      seq.push({ w: GAP });
      total += GAP;
    }
    for (const n of groups.get(sec)!.slice().sort((a, b) => a.key.localeCompare(b.key))) {
      seq.push({ node: n, sector: sec, w: 1 });
      total += 1;
    }
  });
  if (sectors.length > 1) {
    seq.push({ w: GAP }); // close the ring with a gap between last and first sector
    total += GAP;
  }
  total = Math.max(total, 1);
  const sectorAngles = new Map<string, number[]>();
  let acc = 0;
  for (const slot of seq) {
    if (slot.node) {
      const ang = -Math.PI / 2 + ((acc + slot.w / 2) / total) * 2 * Math.PI;
      pos.set(slot.node.id, { x: cx + Rc * Math.cos(ang), y: cy + Rc * Math.sin(ang) });
      visible.add(slot.node.id);
      (sectorAngles.get(slot.sector!) ?? sectorAngles.set(slot.sector!, []).get(slot.sector!)!).push(ang);
    }
    acc += slot.w;
  }
  if (sectors.length <= 1) return [];
  const Rlabel = Rc + 54;
  const labels: SectorLabel[] = [];
  for (const [sec, angs] of sectorAngles) {
    const mid = angs.reduce((s, a) => s + a, 0) / angs.length;
    labels.push({ label: sec, x: cx + Rlabel * Math.cos(mid), y: cy + Rlabel * Math.sin(mid) });
  }
  return labels;
}

export function computeLayout(graph: RelGraph, mode: Mode, focusKey?: string): Layout {
  const { w, h, cx, cy, Rc, leafR } = dimsFor(mode);
  const pos = new Map<string, Pt>();
  const visible = new Set<string>();

  if (mode === "ego" && focusKey) {
    const centerId = nodeId("Company", focusKey);
    pos.set(centerId, { x: cx, y: cy });
    visible.add(centerId);
    const neighbours = graph.edges
      .filter((e) => e.source === centerId || e.target === centerId)
      .map((e) => (e.source === centerId ? e.target : e.source));
    const uniq = [...new Set(neighbours)];
    // Cluster by kind so related neighbours sit together on the ring.
    uniq.sort((a, b) => {
      const ta = graph.nodes.find((n) => n.id === a)?.kind ?? "";
      const tb = graph.nodes.find((n) => n.id === b)?.kind ?? "";
      return ta.localeCompare(tb) || a.localeCompare(b);
    });
    uniq.forEach((id, i) => {
      const ang = -Math.PI / 2 + (i * 2 * Math.PI) / Math.max(uniq.length, 1);
      pos.set(id, { x: cx + Rc * Math.cos(ang), y: cy + Rc * Math.sin(ang) });
      visible.add(id);
    });
    return { pos, visible, w, h, sectorLabels: [] };
  }

  const trackedNodes = graph.nodes.filter((n) => n.tracked);
  const sectorLabels = placeTrackedRing(trackedNodes, pos, visible, cx, cy, Rc);

  const isShown = (n: GNode) =>
    n.tracked || (mode === "full" ? n.bridges.length >= 1 : n.bridges.length >= 2);

  // Bridges (≥2 tracked companies): place between the companies they connect.
  const bridges = graph.nodes.filter((n) => !n.tracked && n.bridges.length >= 2);
  const groups = new Map<string, GNode[]>();
  for (const b of bridges) {
    const sig = [...b.bridges].sort().join(",");
    (groups.get(sig) ?? groups.set(sig, []).get(sig)!).push(b);
  }
  for (const [, members] of groups) {
    const comps = members[0].bridges
      .map((k) => pos.get(nodeId("Company", k)))
      .filter((p): p is Pt => Boolean(p));
    if (comps.length === 0) continue;
    const mid = { x: avg(comps.map((p) => p.x)), y: avg(comps.map((p) => p.y)) };
    const base = { x: cx + (mid.x - cx) * 0.5, y: cy + (mid.y - cy) * 0.5 };
    // Spread same-pair bridges along the perpendicular of the company chord.
    const dx = comps.length >= 2 ? comps[1].x - comps[0].x : mid.y - cy;
    const dy = comps.length >= 2 ? comps[1].y - comps[0].y : -(mid.x - cx);
    const len = Math.hypot(dx, dy);
    // Degenerate (single company at centre): fall back to a horizontal spread.
    const px = len < 0.01 ? 1 : -dy / len;
    const py = len < 0.01 ? 0 : dx / len;
    const spacing = 64;
    members.forEach((m, k) => {
      const off = (k - (members.length - 1) / 2) * spacing;
      pos.set(m.id, { x: base.x + px * off, y: base.y + py * off });
      visible.add(m.id);
    });
  }

  if (mode === "full") {
    // Leaves (one tracked company): fan out on an arc beyond their company.
    const leaves = graph.nodes.filter((n) => !n.tracked && n.bridges.length === 1);
    const byOwner = new Map<string, GNode[]>();
    for (const l of leaves) {
      const owner = l.bridges[0];
      (byOwner.get(owner) ?? byOwner.set(owner, []).get(owner)!).push(l);
    }
    for (const [owner, members] of byOwner) {
      const cp = pos.get(nodeId("Company", owner));
      if (!cp) continue;
      const baseAng = Math.atan2(cp.y - cy, cp.x - cx);
      const spread = Math.min(0.16 + members.length * 0.07, 1.05);
      members.forEach((m, k) => {
        const a = baseAng + (members.length === 1 ? 0 : (k / (members.length - 1) - 0.5) * spread);
        pos.set(m.id, { x: cx + leafR * Math.cos(a), y: cy + leafR * Math.sin(a) });
        visible.add(m.id);
      });
    }
  }

  for (const n of graph.nodes) if (isShown(n) && pos.has(n.id)) visible.add(n.id);

  // Deterministic de-overlap: push the central bridge nodes apart from each other
  // and away from the company ring so labels never collide. No randomness, so the
  // same graph always settles to the same picture.
  const bridgePts = graph.nodes
    .filter((n) => !n.tracked && n.bridges.length >= 2 && visible.has(n.id))
    .map((n, i) => ({ p: pos.get(n.id)!, i }));
  const anchors = trackedNodes.map((n) => pos.get(n.id)!);
  relax(bridgePts, anchors, w, h);

  return { pos, visible, w, h, sectorLabels };
}

const MARGIN = 60;
const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v));

function relax(nodes: Array<{ p: Pt; i: number }>, anchors: Pt[], w: number, h: number): void {
  const MIN_NN = 92; // bridge-to-bridge
  const MIN_NA = 80; // bridge-to-company
  for (let iter = 0; iter < 60; iter++) {
    for (let a = 0; a < nodes.length; a++) {
      const pa = nodes[a].p;
      for (let b = a + 1; b < nodes.length; b++) {
        const pb = nodes[b].p;
        let dx = pb.x - pa.x;
        let dy = pb.y - pa.y;
        let d = Math.hypot(dx, dy);
        if (d < 0.01) {
          // Degenerate overlap: separate deterministically by index.
          dx = ((nodes[a].i + 1) % 2 === 0 ? 1 : -1) * (a + 1);
          dy = b - a;
          d = Math.hypot(dx, dy) || 1;
        }
        if (d < MIN_NN) {
          const push = (MIN_NN - d) / 2;
          const ux = dx / d;
          const uy = dy / d;
          pa.x -= ux * push;
          pa.y -= uy * push;
          pb.x += ux * push;
          pb.y += uy * push;
        }
      }
      for (const anch of anchors) {
        const dx = pa.x - anch.x;
        const dy = pa.y - anch.y;
        const d = Math.hypot(dx, dy) || 1;
        if (d < MIN_NA) {
          const push = MIN_NA - d;
          pa.x += (dx / d) * push;
          pa.y += (dy / d) * push;
        }
      }
      pa.x = clamp(pa.x, MARGIN, w - MARGIN);
      pa.y = clamp(pa.y, MARGIN, h - MARGIN);
    }
  }
}

const avg = (xs: number[]) => xs.reduce((s, x) => s + x, 0) / (xs.length || 1);

// ---- component -------------------------------------------------------------

interface RelationMapProps {
  graph: RelGraph;
  mode?: Mode;
  /** company key to centre, for `mode="ego"`. */
  focusKey?: string;
  legend?: boolean;
  /** override the default aspect height in px (the SVG still scales to width). */
  caption?: boolean;
  ariaLabel?: string;
}

export function RelationMap({
  graph,
  mode = "core",
  focusKey,
  legend = true,
  caption = true,
  ariaLabel,
}: RelationMapProps) {
  const navigate = useNavigate();
  const [hover, setHover] = useState<string | null>(null);
  const [picked, setPicked] = useState<string | null>(null);

  const { pos, visible, w, h } = useMemo(() => computeLayout(graph, mode, focusKey), [graph, mode, focusKey]);
  const nodeById = useMemo(() => new Map(graph.nodes.map((n) => [n.id, n])), [graph]);

  const edges = graph.edges.filter((e) => visible.has(e.source) && visible.has(e.target));
  const nodes = graph.nodes.filter((n) => visible.has(n.id));

  const focusId = hover ?? picked;
  const neighbours = useMemo(() => {
    if (!focusId) return null;
    const set = new Set<string>([focusId]);
    for (const e of edges) {
      if (e.source === focusId) set.add(e.target);
      if (e.target === focusId) set.add(e.source);
    }
    return set;
  }, [focusId, edges]);

  const pickedNode = picked ? nodeById.get(picked) ?? null : null;
  const pickedEdges = picked ? edges.filter((e) => e.source === picked || e.target === picked) : [];

  const activate = (n: GNode) => {
    if (n.tracked) navigate(`/companies/${n.key}`);
    else setPicked((p) => (p === n.id ? null : n.id));
  };
  const onKey = (e: KeyboardEvent, n: GNode) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      activate(n);
    }
  };

  if (nodes.length === 0) {
    return <div className="relmap-empty">No relationships to plot yet.</div>;
  }

  const summary =
    ariaLabel ??
    `Relationship map: ${nodes.filter((n) => n.tracked).length} companies, ${edges.length} connections.`;

  return (
    <div className="relmap-wrap">
      <div className="relmap-canvas">
        <svg viewBox={`0 0 ${w} ${h}`} className="relmap" role="img" aria-label={summary} preserveAspectRatio="xMidYMid meet">
          <g className="relmap-edges">
            {edges.map((e) => {
              const a = pos.get(e.source)!;
              const b = pos.get(e.target)!;
              const sN = nodeById.get(e.source)!;
              const tN = nodeById.get(e.target)!;
              const dim = neighbours && !(neighbours.has(e.source) && neighbours.has(e.target));
              const direct = sN.tracked && tN.tracked;
              const mx = (a.x + b.x) / 2;
              const my = (a.y + b.y) / 2;
              const d = direct
                ? `M${a.x},${a.y} Q${mx + (my - h / 2) * 0.18},${my - (mx - w / 2) * 0.18} ${b.x},${b.y}`
                : `M${a.x},${a.y} L${b.x},${b.y}`;
              return (
                <path
                  key={e.id}
                  d={d}
                  fill="none"
                  className={`redge tier-${e.tier}${dim ? " dim" : ""}${direct ? " arc" : ""}`}
                />
              );
            })}
          </g>
          <g className="relmap-nodes">
            {nodes.map((n) => {
              const p = pos.get(n.id)!;
              const dim = neighbours && !neighbours.has(n.id);
              const r = n.tracked ? 25 : 15;
              const tier = bridgeTier(n, edges);
              return (
                <g
                  key={n.id}
                  transform={`translate(${p.x},${p.y})`}
                  className={`rnode ${n.tracked ? "tracked" : "satellite"} tier-${tier}${dim ? " dim" : ""}${picked === n.id ? " picked" : ""}`}
                  tabIndex={0}
                  role="button"
                  aria-label={`${n.name}, ${n.kind}${n.bridges.length >= 2 ? `, connects ${n.bridges.length} companies` : ""}`}
                  onMouseEnter={() => setHover(n.id)}
                  onMouseLeave={() => setHover(null)}
                  onFocus={() => setHover(n.id)}
                  onBlur={() => setHover(null)}
                  onClick={() => activate(n)}
                  onKeyDown={(e) => onKey(e, n)}
                >
                  <circle r={r} className="rnode-disc" />
                  {n.tracked ? (
                    <text className="rnode-glyph" dy="0.34em">
                      {kindGlyph(n.kind)}
                    </text>
                  ) : (
                    <text className="rnode-glyph sm" dy="0.34em">
                      {kindGlyph(n.kind)}
                    </text>
                  )}
                  <NodeLabel name={n.name} y={r + (n.tracked ? 15 : 12)} big={n.tracked} />
                </g>
              );
            })}
          </g>
        </svg>
      </div>
      {legend ? <MapLegend /> : null}

      {caption ? (
        <div className="relmap-caption" aria-live="polite">
          {pickedNode ? (
            <>
              <span className="relmap-cap-kind" data-kind={pickedNode.kind}>
                {kindGlyph(pickedNode.kind)} {pickedNode.kind}
              </span>
              <strong>{pickedNode.name}</strong>
              {pickedEdges.map((e) => {
                const other = nodeById.get(e.source === picked ? e.target : e.source)!;
                return (
                  <span className={`relchip tier-${e.tier}`} key={e.id}>
                    {relationVerb(e.relation)} {other.name}
                  </span>
                );
              })}
              {pickedNode.tracked ? null : (
                <button className="relmap-clear" onClick={() => setPicked(null)}>
                  clear
                </button>
              )}
            </>
          ) : (
            <span className="faint">
              Hover to trace a connection. Click a company to open it; click a bridge to inspect what it links.
            </span>
          )}
        </div>
      ) : null}

      <ul className="sr-only">
        {nodes
          .filter((n) => n.tracked || n.bridges.length >= 2)
          .map((n) => (
            <li key={n.id}>
              {n.name} ({n.kind})
              {edges
                .filter((e) => e.source === n.id || e.target === n.id)
                .map((e) => {
                  const other = nodeById.get(e.source === n.id ? e.target : e.source)!;
                  return ` — ${tierLabel(e.tier)}: ${other.name}`;
                })
                .join("")}
            </li>
          ))}
      </ul>
    </div>
  );
}

/** Pick the visual tier for a satellite node from its strongest incident edge. */
export function bridgeTier(n: GNode, edges: GEdge[]): RelationTier {
  if (n.tracked) return "control";
  const order: RelationTier[] = ["control", "proxy", "supply", "alliance", "peer", "product", "mention"];
  let best: RelationTier = "product";
  for (const e of edges) {
    if (e.source !== n.id && e.target !== n.id) continue;
    if (order.indexOf(e.tier) < order.indexOf(best)) best = e.tier;
  }
  // A person/agency that bridges ≥2 companies reads as proxy-control.
  if (n.bridges.length >= 2 && (n.kind === "Person" || n.kind === "Agency")) return "proxy";
  return best;
}

function NodeLabel({ name, y, big }: { name: string; y: number; big: boolean }) {
  const max = big ? 18 : 13;
  const text = name.length > max ? `${name.slice(0, max - 1)}…` : name;
  const w = text.length * (big ? 7.1 : 6.2) + 12;
  // aria-hidden: the parent <g> already carries the full aria-label.
  return (
    <g transform={`translate(0,${y})`} aria-hidden="true">
      <rect x={-w / 2} y={0} width={w} height={big ? 19 : 16} rx={5} className="rnode-label-bg" />
      <text className={`rnode-label${big ? " big" : ""}`} y={big ? 13.5 : 11.5}>
        {text}
      </text>
    </g>
  );
}

function MapLegend() {
  return (
    <div className="relmap-legend" aria-hidden="true">
      {TIERS.map((t) => (
        <span className="relmap-legend-item" key={t.tier} title={t.hint}>
          <span className={`relmap-swatch tier-${t.tier}`} />
          {t.label}
        </span>
      ))}
    </div>
  );
}
