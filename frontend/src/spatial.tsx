// The spatial spine — a camera-driven canvas over the knowledge graph.
//
// This does NOT fork the graph: it reuses the deterministic, auditable layout
// (`computeLayout` in graph.tsx) and the relation visual-language CSS. What it
// adds is the *navigation* the vision asks for — a continuous space you pan,
// zoom and focus through, instead of a page you scroll. Selecting an entity is
// a camera move (fly-to), not a route change; the parent owns selection and
// opens an evidence rail beside the canvas.
//
// Scale note: the universe is a handful of companies and their satellites — a
// single SVG transform is more than enough for 60fps. A WebGL/React-Flow layer
// would be solving a scale problem the data does not have. Deliberately omitted.

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import {
  bridgeTier,
  computeLayout,
  type GEdge,
  type GNode,
  type RelGraph,
} from "./graph";
import { kindGlyph, relationVerb, tierLabel } from "./relations";

interface Cam {
  x: number;
  y: number;
  k: number;
}

const K_MIN = 0.45;
const K_MAX = 4;
const FOCUS_K = 1.7; // zoom the camera settles at when flying to an entity
const FOCUS_MS = 320;
const PAN_STEP = 70; // viewBox units per arrow press
const DRAG_PX = 5; // movement over this many screen px is a pan, not a click
const FRAME_PAD = 60; // world-units of breathing room around the graph when framing
// Fractions of the viewBox left as margin when framing to content. The top is
// larger so the graph clears the header overlay rather than hiding under it.
const FRAME_MARGIN = { x: 0.05, top: 0.16, bottom: 0.06 };

const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v));

function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const sync = () => setReduced(mq.matches);
    sync();
    mq.addEventListener("change", sync);
    return () => mq.removeEventListener("change", sync);
  }, []);
  return reduced;
}

/** Per-company material-change aggregate, keyed by slug (a tracked node's key). */
export interface ChangeCount {
  added: number;
  removed: number;
  material: boolean;
}

interface SpatialCanvasProps {
  graph: RelGraph;
  /** Nodes revealed by expanding an entity, laid out as a burst around their parent. */
  extraNodes?: GNode[];
  /** Edges revealed by expansion (parent → revealed neighbour, or cross-links). */
  extraEdges?: GEdge[];
  /** extra-node id → the id of the node it was expanded from (its layout anchor). */
  anchorOf?: Map<string, string>;
  /** Material-change counts per tracked company (slug). Drives the change notch. */
  changes?: Map<string, ChangeCount>;
  /** Ordered node ids of a traced shortest path; lights the path, dims the rest. */
  pathNodeIds?: string[];
  /** Edge keys (`a|b|relation`, a/b sorted) of the traced path — exact edges to light. */
  pathEdgeKeys?: Set<string>;
  /** The entity currently focused, or null for the open overview. */
  selected: GNode | null;
  /** Open an entity — the parent flies the camera here and shows its evidence. */
  onActivate: (node: GNode) => void;
  /** A click on empty space — dismiss the evidence rail. */
  onBackground: () => void;
}

/** Merge by id, keeping the first occurrence (base wins over expansion duplicates). */
function mergeById<T extends { id: string }>(base: T[], extra?: T[]): T[] {
  if (!extra || extra.length === 0) return base;
  const seen = new Set(base.map((x) => x.id));
  const out = base.slice();
  for (const x of extra) {
    if (!seen.has(x.id)) {
      seen.add(x.id);
      out.push(x);
    }
  }
  return out;
}

/** Place expansion nodes on a radial burst around their anchor, fanning outward
 *  from the graph centre. Deterministic (angle by index); iterates so a node
 *  expanded from another expansion still anchors correctly. */
function placeExtras(
  extras: GNode[],
  anchorOf: Map<string, string> | undefined,
  pos: Map<string, { x: number; y: number }>,
  visible: Set<string>,
  w: number,
  h: number,
): void {
  if (!extras.length || !anchorOf) return;
  const cx = w / 2;
  const cy = h / 2;
  const R = 125;
  let pending = extras.filter((n) => !pos.has(n.id));
  for (let guard = 0; pending.length && guard < 12; guard++) {
    const ready = pending.filter((n) => {
      const a = anchorOf.get(n.id);
      return a !== undefined && pos.has(a);
    });
    if (!ready.length) break;
    const byAnchor = new Map<string, GNode[]>();
    for (const n of ready) {
      const a = anchorOf.get(n.id)!;
      (byAnchor.get(a) ?? byAnchor.set(a, []).get(a)!).push(n);
    }
    for (const [anchorId, members] of byAnchor) {
      const ap = pos.get(anchorId)!;
      const baseAng = Math.atan2(ap.y - cy, ap.x - cx);
      const spread = Math.min(0.6 + members.length * 0.2, Math.PI * 1.5);
      members.forEach((m, i) => {
        const ang = members.length === 1 ? baseAng : baseAng + (i / (members.length - 1) - 0.5) * spread;
        pos.set(m.id, { x: ap.x + R * Math.cos(ang), y: ap.y + R * Math.sin(ang) });
        visible.add(m.id);
      });
    }
    pending = pending.filter((n) => !pos.has(n.id));
  }
}

export function SpatialCanvas({ graph, extraNodes, extraEdges, anchorOf, changes, pathNodeIds, pathEdgeKeys, selected, onActivate, onBackground }: SpatialCanvasProps) {
  const reduced = usePrefersReducedMotion();
  const svgRef = useRef<SVGSVGElement | null>(null);

  const allNodes = useMemo(() => mergeById(graph.nodes, extraNodes), [graph.nodes, extraNodes]);
  const allEdges = useMemo(() => mergeById(graph.edges, extraEdges), [graph.edges, extraEdges]);

  // The "full" layout spreads the seeded universe; expansion bursts are placed
  // around their anchor afterwards so the deterministic base layout is preserved.
  const { pos, visible, w, h, sectorLabels } = useMemo(() => {
    const base = computeLayout(graph, "full");
    const p = new Map(base.pos);
    const vis = new Set(base.visible);
    placeExtras(extraNodes ?? [], anchorOf, p, vis, base.w, base.h);
    return { pos: p, visible: vis, w: base.w, h: base.h, sectorLabels: base.sectorLabels };
  }, [graph, extraNodes, anchorOf]);
  const nodeById = useMemo(() => new Map(allNodes.map((n) => [n.id, n])), [allNodes]);
  const edges = useMemo(
    () => allEdges.filter((e) => visible.has(e.source) && visible.has(e.target)),
    [allEdges, visible],
  );
  const nodes = useMemo(() => allNodes.filter((n) => visible.has(n.id)), [allNodes, visible]);

  // Bounding box of everything drawn (world units), padded for discs + labels.
  const contentBox = useMemo(() => {
    let minX = Infinity;
    let minY = Infinity;
    let maxX = -Infinity;
    let maxY = -Infinity;
    for (const n of nodes) {
      const p = pos.get(n.id);
      if (!p) continue;
      minX = Math.min(minX, p.x);
      minY = Math.min(minY, p.y);
      maxX = Math.max(maxX, p.x);
      maxY = Math.max(maxY, p.y);
    }
    if (!Number.isFinite(minX)) return null;
    return { minX: minX - FRAME_PAD, minY: minY - FRAME_PAD, maxX: maxX + FRAME_PAD, maxY: maxY + FRAME_PAD };
  }, [nodes, pos]);

  // camRef is the source of truth (read by event listeners that close over a
  // single render); `cam` mirrors it for rendering.
  const camRef = useRef<Cam>({ x: 0, y: 0, k: 1 });
  const [cam, setCamState] = useState<Cam>(camRef.current);
  const setCam = useCallback((c: Cam) => {
    camRef.current = c;
    setCamState(c);
  }, []);

  const rafRef = useRef<number | null>(null);
  const cancelTween = useCallback(() => {
    if (rafRef.current != null) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
  }, []);

  const tweenTo = useCallback(
    (target: Cam) => {
      cancelTween();
      if (reduced) {
        setCam(target);
        return;
      }
      const start = { ...camRef.current };
      const t0 = performance.now();
      const tick = (now: number) => {
        const t = Math.min(1, (now - t0) / FOCUS_MS);
        const e = 1 - Math.pow(1 - t, 3); // easeOutCubic
        setCam({
          x: start.x + (target.x - start.x) * e,
          y: start.y + (target.y - start.y) * e,
          k: start.k + (target.k - start.k) * e,
        });
        if (t < 1) rafRef.current = requestAnimationFrame(tick);
        else rafRef.current = null;
      };
      rafRef.current = requestAnimationFrame(tick);
    },
    [cancelTween, reduced, setCam],
  );

  useEffect(() => cancelTween, [cancelTween]);

  // Fly to the selected entity whenever the selection changes.
  const lastFocus = useRef<string | null>(null);
  useEffect(() => {
    if (!selected) {
      lastFocus.current = null;
      return;
    }
    if (selected.id === lastFocus.current) return;
    lastFocus.current = selected.id;
    const p = pos.get(selected.id);
    if (!p) return;
    const k = Math.max(camRef.current.k, FOCUS_K);
    tweenTo({ x: w / 2 - p.x * k, y: h / 2 - p.y * k, k });
  }, [selected, pos, w, h, tweenTo]);

  // ---- camera operations (anchored zoom keeps a point fixed under the cursor) -
  const zoomAround = useCallback(
    (anchor: { x: number; y: number }, mult: number) => {
      cancelTween();
      const c = camRef.current;
      const k = clamp(c.k * mult, K_MIN, K_MAX);
      setCam({
        x: anchor.x - (anchor.x - c.x) * (k / c.k),
        y: anchor.y - (anchor.y - c.y) * (k / c.k),
        k,
      });
    },
    [cancelTween, setCam],
  );
  const zoomCenter = useCallback((mult: number) => zoomAround({ x: w / 2, y: h / 2 }, mult), [zoomAround, w, h]);

  // Frame an arbitrary world-box into the viewBox, leaving room up top for the header.
  const frameToBox = useCallback(
    (box: { minX: number; minY: number; maxX: number; maxY: number }, animate: boolean) => {
      const bw = box.maxX - box.minX;
      const bh = box.maxY - box.minY;
      const availW = w * (1 - 2 * FRAME_MARGIN.x);
      const availH = h * (1 - FRAME_MARGIN.top - FRAME_MARGIN.bottom);
      const k = clamp(Math.min(availW / bw, availH / bh), K_MIN, K_MAX);
      const cwx = (box.minX + box.maxX) / 2;
      const cwy = (box.minY + box.maxY) / 2;
      const target = { x: w / 2 - cwx * k, y: h * FRAME_MARGIN.top + availH / 2 - cwy * k, k };
      if (animate) tweenTo(target);
      else setCam(target);
    },
    [w, h, tweenTo, setCam],
  );
  const frameView = useCallback((animate: boolean) => { if (contentBox) frameToBox(contentBox, animate); }, [contentBox, frameToBox]);
  const fit = useCallback(() => frameView(true), [frameView]);

  // Bounding box of a set of nodes (world units), padded — used to frame a path.
  const boxOf = useCallback(
    (ids: string[]) => {
      let a = Infinity, b = Infinity, c = -Infinity, d = -Infinity;
      for (const id of ids) {
        const p = pos.get(id);
        if (!p) continue;
        a = Math.min(a, p.x); b = Math.min(b, p.y); c = Math.max(c, p.x); d = Math.max(d, p.y);
      }
      if (!Number.isFinite(a)) return null;
      return { minX: a - 90, minY: b - 90, maxX: c + 90, maxY: d + 90 };
    },
    [pos],
  );

  // Path highlight: lit node ids + the node-pair keys of consecutive path edges.
  const pathNodeSet = useMemo(
    () => (pathNodeIds && pathNodeIds.length ? new Set(pathNodeIds) : null),
    [pathNodeIds],
  );

  // Fly the camera to frame a newly-traced path.
  const lastPath = useRef<string>("");
  useEffect(() => {
    const key = (pathNodeIds ?? []).join(">");
    if (key === lastPath.current) return;
    lastPath.current = key;
    if (!pathNodeIds || pathNodeIds.length < 2) return;
    const box = boxOf(pathNodeIds);
    if (box) frameToBox(box, true);
  }, [pathNodeIds, boxOf, frameToBox]);

  // Frame to content on first layout, before paint (no identity-zoom flash).
  const framed = useRef(false);
  useLayoutEffect(() => {
    if (framed.current || !contentBox) return;
    framed.current = true;
    frameView(false);
  }, [contentBox, frameView]);

  // Wheel zoom must preventDefault, so it is a non-passive native listener.
  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const ctm = svg.getScreenCTM();
      if (!ctm) return;
      const vb = new DOMPoint(e.clientX, e.clientY).matrixTransform(ctm.inverse());
      zoomAround({ x: vb.x, y: vb.y }, Math.exp(-e.deltaY * 0.0012));
    };
    svg.addEventListener("wheel", onWheel, { passive: false });
    return () => svg.removeEventListener("wheel", onWheel);
  }, [zoomAround]);

  // ---- drag-to-pan (only from empty canvas; nodes stop propagation) ----------
  const drag = useRef<{ id: number; sx: number; sy: number; cx: number; cy: number; moved: boolean } | null>(null);
  const [panning, setPanning] = useState(false);

  const onBgPointerDown = (e: React.PointerEvent<SVGSVGElement>) => {
    cancelTween();
    drag.current = { id: e.pointerId, sx: e.clientX, sy: e.clientY, cx: camRef.current.x, cy: camRef.current.y, moved: false };
    setPanning(true);
    e.currentTarget.setPointerCapture(e.pointerId);
  };
  const onPointerMove = (e: React.PointerEvent<SVGSVGElement>) => {
    const d = drag.current;
    if (!d) return;
    const dx = e.clientX - d.sx;
    const dy = e.clientY - d.sy;
    if (!d.moved && Math.hypot(dx, dy) > DRAG_PX) d.moved = true;
    const s = svgRef.current?.getScreenCTM()?.a || 1;
    setCam({ x: d.cx + dx / s, y: d.cy + dy / s, k: camRef.current.k });
  };
  const onPointerUp = (e: React.PointerEvent<SVGSVGElement>) => {
    const d = drag.current;
    if (!d) return;
    drag.current = null;
    setPanning(false);
    try {
      svgRef.current?.releasePointerCapture(e.pointerId);
    } catch {
      /* capture already released */
    }
    if (!d.moved) onBackground(); // a clean click on empty space dismisses the rail
  };

  // ---- keyboard navigation ---------------------------------------------------
  const onKeyDown = (e: React.KeyboardEvent) => {
    const c = camRef.current;
    switch (e.key) {
      case "ArrowRight": setCam({ ...c, x: c.x - PAN_STEP }); break;
      case "ArrowLeft": setCam({ ...c, x: c.x + PAN_STEP }); break;
      case "ArrowDown": setCam({ ...c, y: c.y - PAN_STEP }); break;
      case "ArrowUp": setCam({ ...c, y: c.y + PAN_STEP }); break;
      case "+": case "=": zoomCenter(1.2); break;
      case "-": case "_": zoomCenter(1 / 1.2); break;
      case "0": case "f": case "F": fit(); break;
      case "Escape": if (selected) onBackground(); break;
      default: return;
    }
    e.preventDefault();
  };

  // ---- highlight: the focused entity's neighbourhood stays lit ---------------
  const focusId = selected?.id ?? null;
  const neighbours = useMemo(() => {
    if (!focusId) return null;
    const set = new Set<string>([focusId]);
    for (const e of edges) {
      if (e.source === focusId) set.add(e.target);
      if (e.target === focusId) set.add(e.source);
    }
    return set;
  }, [focusId, edges]);

  const activate = (n: GNode) => onActivate(n);
  const onNodeKey = (e: React.KeyboardEvent, n: GNode) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      e.stopPropagation();
      activate(n);
    }
  };

  if (nodes.length === 0) {
    return <div className="relmap-empty">No relationships to plot yet.</div>;
  }

  return (
    <div
      className={`spatial${panning ? " panning" : ""}`}
      role="application"
      aria-label="Spatial intelligence canvas. Pan with arrow keys, zoom with plus and minus, press F to fit, Escape to close a panel."
      tabIndex={0}
      onKeyDown={onKeyDown}
    >
      <svg
        ref={svgRef}
        className="spatial-svg"
        viewBox={`0 0 ${w} ${h}`}
        preserveAspectRatio="xMidYMid meet"
        onPointerDown={onBgPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
        role="presentation"
      >
        <g transform={`translate(${cam.x},${cam.y}) scale(${cam.k})`}>
          {/* Sector cluster labels — drawn behind the graph as quiet context. */}
          <g className="spatial-sectors" aria-hidden="true">
            {sectorLabels.map((s) => (
              <text key={s.label} x={s.x} y={s.y} className="spatial-sector-label" textAnchor="middle">
                {s.label}
              </text>
            ))}
          </g>
          <g className="relmap-edges">
            {edges.map((e) => {
              const a = pos.get(e.source)!;
              const b = pos.get(e.target)!;
              const sN = nodeById.get(e.source)!;
              const tN = nodeById.get(e.target)!;
              const onPath = pathEdgeKeys ? pathEdgeKeys.has(`${[e.source, e.target].sort().join("|")}|${e.relation}`) : false;
              const dim = pathNodeSet
                ? !onPath
                : neighbours && !(neighbours.has(e.source) && neighbours.has(e.target));
              const direct = sN.tracked && tN.tracked;
              const mx = (a.x + b.x) / 2;
              const my = (a.y + b.y) / 2;
              const d = direct
                ? `M${a.x},${a.y} Q${mx + (my - h / 2) * 0.18},${my - (mx - w / 2) * 0.18} ${b.x},${b.y}`
                : `M${a.x},${a.y} L${b.x},${b.y}`;
              return (
                <path key={e.id} d={d} fill="none" className={`redge tier-${e.tier}${dim ? " dim" : ""}${direct ? " arc" : ""}${onPath ? " path" : ""}`} />
              );
            })}
          </g>
          <g className="relmap-nodes">
            {nodes.map((n) => {
              const p = pos.get(n.id)!;
              const onPath = pathNodeSet ? pathNodeSet.has(n.id) : false;
              const dim = pathNodeSet ? !onPath : neighbours && !neighbours.has(n.id);
              const r = n.tracked ? 25 : 15;
              const tier = bridgeTier(n, edges);
              const picked = n.id === focusId;
              const ch = n.tracked ? changes?.get(n.key) : undefined;
              const changed = ch?.material ? ch.added + ch.removed : 0;
              return (
                <g
                  key={n.id}
                  transform={`translate(${p.x},${p.y})`}
                  className={`rnode ${n.tracked ? "tracked" : "satellite"} tier-${tier}${dim ? " dim" : ""}${picked ? " picked" : ""}${onPath ? " path" : ""}`}
                  tabIndex={0}
                  role="button"
                  aria-label={`${n.name}, ${n.kind}${n.bridges.length >= 2 ? `, connects ${n.bridges.length} companies` : ""}${changed > 0 ? `, ${changed} material change line${changed === 1 ? "" : "s"}` : ""}`}
                  onPointerDown={(ev) => ev.stopPropagation()}
                  onClick={(ev) => {
                    ev.stopPropagation();
                    activate(n);
                  }}
                  onKeyDown={(ev) => onNodeKey(ev, n)}
                >
                  <circle r={r} className="rnode-disc" />
                  {/* Quiet ledger notch: a static indigo count of material change-lines.
                      No animation by design — reduced-motion-correct by construction. */}
                  {changed > 0 ? (
                    <g className="rnode-change" transform={`translate(${r * 0.7},${-r * 0.7})`} aria-hidden="true">
                      <circle r={9} className="rnode-change-dot" />
                      <text className="rnode-change-n" dy="0.32em">{changed > 9 ? "9+" : changed}</text>
                    </g>
                  ) : null}
                  <text className={`rnode-glyph${n.tracked ? "" : " sm"}`} dy="0.34em">
                    {kindGlyph(n.kind)}
                  </text>
                  <NodeLabel name={n.name} y={r + (n.tracked ? 15 : 12)} big={n.tracked} />
                </g>
              );
            })}
          </g>
        </g>
      </svg>

      <div className="spatial-controls" role="group" aria-label="Camera controls">
        <button className="spatial-btn" onClick={() => zoomCenter(1.2)} aria-label="Zoom in" title="Zoom in">+</button>
        <button className="spatial-btn" onClick={() => zoomCenter(1 / 1.2)} aria-label="Zoom out" title="Zoom out">−</button>
        <button className="spatial-btn" onClick={fit} aria-label="Fit to view" title="Fit to view">⤢</button>
      </div>

      <div className="spatial-hint" aria-hidden="true">
        Drag to pan · scroll to zoom · click an entity to open it
      </div>

      {/* Screen-reader path into the graph (the SVG itself is decorative here). */}
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
                  return ` — ${relationVerb(e.relation)} ${other.name} (${tierLabel(e.tier)})`;
                })
                .join("")}
            </li>
          ))}
      </ul>
    </div>
  );
}

function NodeLabel({ name, y, big }: { name: string; y: number; big: boolean }) {
  const max = big ? 18 : 13;
  const text = name.length > max ? `${name.slice(0, max - 1)}…` : name;
  const width = text.length * (big ? 7.1 : 6.2) + 12;
  return (
    <g transform={`translate(0,${y})`} aria-hidden="true">
      <rect x={-width / 2} y={0} width={width} height={big ? 19 : 16} rx={5} className="rnode-label-bg" />
      <text className={`rnode-label${big ? " big" : ""}`} y={big ? 13.5 : 11.5}>
        {text}
      </text>
    </g>
  );
}
