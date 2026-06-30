// The 3D Atlas — a deterministic, sector-clustered force-directed graph rendered
// on WebGL (react-force-graph-3d / three). Companies are hubs coloured by sector
// with their Exhibit-21 subsidiary halos; co-mention links weave between them.
// Hover lights the reachable subgraph to the end of the graph; click selects a
// company (opening the evidence rail) and flies the camera to it. The view
// auto-rotates ("the clustered ball") until you interact.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import ForceGraph3D from "react-force-graph-3d";
import { buildForceData, sectorColor, type FLink } from "./force3d";
import type { Company, EntityProfile } from "./api";

const DIM = "#2a2f3a";

// nodeLabel is rendered as raw HTML by react-force-graph-3d, and node names flow
// from external data (SEC filings, parsed Exhibit-21 subsidiary names). Escape
// every interpolated value to prevent HTML/script injection.
const esc = (s: string): string =>
  String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");

interface Atlas3DProps {
  companies: Company[];
  profiles: Map<string, EntityProfile>;
  selectedSlug?: string;
  onSelectCompany: (slug: string, name: string) => void;
  onBackground: () => void;
}

export function Atlas3D({ companies, profiles, selectedSlug, onSelectCompany, onBackground }: Atlas3DProps) {
  const data = useMemo(() => buildForceData(companies, profiles), [companies, profiles]);
  const fgRef = useRef<any>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ w: 900, h: 600 });
  const [hiNodes, setHiNodes] = useState<Set<string>>(new Set());
  const [hiLinks, setHiLinks] = useState<Set<FLink>>(new Set());

  // Fill the container.
  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const measure = () => setSize({ w: el.clientWidth, h: el.clientHeight });
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // Undirected adjacency for the hover reachable-subgraph highlight.
  const adjacency = useMemo(() => {
    const adj = new Map<string, Set<string>>();
    const link = (a: string, b: string) => (adj.get(a) ?? adj.set(a, new Set()).get(a)!).add(b);
    for (const l of data.links) {
      link(l.source, l.target);
      link(l.target, l.source);
    }
    return adj;
  }, [data]);

  // Click-to-isolate: the selected company's ego subgraph (it + its direct
  // neighbours — subsidiaries and co-mentioned peers). When set, everything else
  // is hidden and the camera frames just this.
  const focusSet = useMemo(() => {
    if (!selectedSlug) return null;
    const id = `Company:${selectedSlug}`;
    const set = new Set<string>([id]);
    for (const nb of adjacency.get(id) ?? []) set.add(nb);
    return set;
  }, [selectedSlug, adjacency]);

  // Sector-clustering force + a gentler charge, plus auto-rotate. Deferred to the
  // graph's first engine tick (onEngineTick) so the internal d3 layout exists
  // before we touch it — touching it from a mount effect races layout creation.
  const tunedRef = useRef(false);
  const tuneForces = useCallback(() => {
    if (tunedRef.current) return;
    const fg = fgRef.current;
    if (!fg) return;
    tunedRef.current = true;
    const anchor = data.sectorAnchor;
    let simNodes: any[] = [];
    const cluster: any = (alpha: number) => {
      const k = alpha * 0.16;
      for (const n of simNodes) {
        const a = anchor.get(n.sector);
        if (!a) continue;
        n.vx += (a.x - n.x) * k;
        n.vy += (a.y - n.y) * k;
        n.vz += (a.z - n.z) * k;
      }
    };
    cluster.initialize = (n: any[]) => {
      simNodes = n;
    };
    try {
      fg.d3Force("cluster", cluster);
      fg.d3Force("charge")?.strength(-55);
    } catch {
      /* force engine not ready */
    }
    const controls = fg.controls?.();
    if (controls) {
      controls.autoRotate = true;
      controls.autoRotateSpeed = 0.55;
    }
  }, [data]);

  // Reset the "tuned once" guard if the data changes.
  useEffect(() => {
    tunedRef.current = false;
  }, [data]);

  // Isolate the focused subgraph (or restore the overview) with a camera move.
  useEffect(() => {
    const fg = fgRef.current;
    if (!fg) return;
    const controls = fg.controls?.();
    if (focusSet) {
      if (controls) controls.autoRotate = false;
      fg.zoomToFit?.(800, 90, (n: any) => focusSet.has(n.id));
    } else {
      if (controls) controls.autoRotate = true;
      fg.zoomToFit?.(800, 70);
    }
  }, [focusSet]);

  const onHover = useCallback(
    (node: any) => {
      // Pause the auto-rotation while the cursor is on a node so it can be read
      // and clicked precisely; resume when the cursor leaves.
      const controls = fgRef.current?.controls?.();
      if (controls) controls.autoRotate = !node;
      if (!node) {
        setHiNodes(new Set());
        setHiLinks(new Set());
        return;
      }
      const seen = new Set<string>([node.id]);
      const queue = [node.id];
      for (let i = 0; i < queue.length; i++) {
        for (const nb of adjacency.get(queue[i]) ?? []) {
          if (!seen.has(nb)) {
            seen.add(nb);
            queue.push(nb);
          }
        }
      }
      const lset = new Set<FLink>();
      for (const l of data.links) {
        const s = typeof l.source === "object" ? (l.source as any).id : l.source;
        const t = typeof l.target === "object" ? (l.target as any).id : l.target;
        if (seen.has(s) && seen.has(t)) lset.add(l);
      }
      setHiNodes(seen);
      setHiLinks(lset);
    },
    [adjacency, data],
  );

  // Clicking a company selects it (opens the rail) and isolates its subgraph via
  // the focusSet effect above; clicking a subsidiary jumps to its parent company.
  const onClick = useCallback(
    (node: any) => {
      if (!node) return;
      if (node.kind === "Company" && node.slug) {
        onSelectCompany(node.slug, node.name);
        return;
      }
      for (const nbId of adjacency.get(node.id) ?? []) {
        if (nbId.startsWith("Company:")) {
          const slug = nbId.slice("Company:".length);
          const parent = companies.find((c) => c.slug === slug);
          if (parent) {
            onSelectCompany(slug, parent.name);
            return;
          }
        }
      }
    },
    [onSelectCompany, adjacency, companies],
  );

  const dimming = hiNodes.size > 0;
  const nodeColor = useCallback(
    (n: any) => {
      const lit = !dimming || hiNodes.has(n.id) || n.slug === selectedSlug;
      return lit ? sectorColor(n.sector) : DIM;
    },
    [dimming, hiNodes, selectedSlug],
  );

  return (
    <div ref={wrapRef} className="atlas3d">
      <ForceGraph3D
        ref={fgRef}
        graphData={data as any}
        width={size.w}
        height={size.h}
        backgroundColor="#090b0f"
        showNavInfo={false}
        controlType="orbit"
        nodeId="id"
        nodeLabel={(n: any) =>
          `<div class="g3d-tip"><strong>${esc(n.name)}</strong><span>${esc(n.kind === "Company" ? n.sector : "Subsidiary")}</span></div>`
        }
        nodeVal={(n: any) => n.val}
        nodeColor={nodeColor as any}
        nodeOpacity={0.95}
        nodeResolution={14}
        nodeVisibility={(n: any) => !focusSet || focusSet.has(n.id)}
        linkColor={(l: any) => (hiLinks.has(l) ? "#e8ebef" : "#39414f")}
        linkWidth={(l: any) => (hiLinks.has(l) ? 1.4 : 0.4)}
        linkOpacity={0.55}
        linkVisibility={(l: any) => {
          if (!focusSet) return true;
          const s = typeof l.source === "object" ? l.source.id : l.source;
          const t = typeof l.target === "object" ? l.target.id : l.target;
          return focusSet.has(s) && focusSet.has(t);
        }}
        onNodeHover={onHover}
        onNodeClick={onClick}
        onBackgroundClick={onBackground}
        onEngineTick={tuneForces}
        onEngineStop={() => fgRef.current?.zoomToFit?.(700, 70)}
        enableNodeDrag={false}
        warmupTicks={80}
        cooldownTicks={140}
      />
    </div>
  );
}
