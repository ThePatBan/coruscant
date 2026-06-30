import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, type ChangeSet, type Company, type EntityProfile, type Relationship } from "../api";
import { Cat, Loading, RelationGroups, Skeleton } from "../components";
import { graphStats, GraphIncompleteNote, type GEdge, type GNode, useRelGraph } from "../graph";
import { useAsync } from "../hooks";
import { coarseSector, isEntityRelation, kindGlyph, relationTier, relationVerb, TIERS } from "../relations";
import type { ChangeCount } from "../spatial";

// Lazy-loaded so ThreeJS / react-force-graph-3d (a large bundle) is fetched only
// when the Atlas opens, not on the app's initial load.
const Atlas3D = lazy(() => import("../Atlas3D").then((m) => ({ default: m.Atlas3D })));

// Atlas — the spatial spine. The relationship graph is the primary surface, not
// a tab: you navigate the universe by moving a camera, and selecting any entity
// flies to it and discloses its evidence beside the canvas. Expanding an entity
// pulls *its* neighbourhood onto the canvas, so you can walk the graph outward
// from any node — beyond the seeded companies. Nothing is shown until selected.
export function AtlasPage() {
  const { data, loading } = useRelGraph();
  const [searchParams, setSearchParams] = useSearchParams();
  const [selected, setSelected] = useState<GNode | null>(null);
  const [compareSlug, setCompareSlug] = useState<string | null>(null); // 2nd company for overlap compare
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());
  const [profiles, setProfiles] = useState<Map<string, EntityProfile>>(new Map());
  const [pending, setPending] = useState<Set<string>>(new Set());
  const [pathFrom, setPathFrom] = useState<GNode | null>(null);
  const [pathTo, setPathTo] = useState<GNode | null>(null);
  const [picking, setPicking] = useState(false);
  const [tableOpen, setTableOpen] = useState(false); // drill level 3: table/text view
  const stats = data ? graphStats(data.graph) : null;
  const ukCount = data?.companies.filter((c) => c.country === "United Kingdom").length ?? 0;
  const usCount = data?.companies.filter((c) => c.country === "United States").length ?? 0;

  const clearPath = useCallback(() => {
    setPathFrom(null);
    setPathTo(null);
    setPicking(false);
  }, []);

  // Material-change layer: fan out per-company change sets (like the Dashboard),
  // aggregate to a per-slug count for the canvas notch, and keep the full sets
  // for the rail's "What changed" detail. Local to Atlas — kept out of the shared
  // useRelGraph so the other pages don't pay this fetch.
  const changesAsync = useAsync(async () => {
    const companies = await api.companies();
    const lists = await Promise.all(
      companies.map((c) => api.companyChanges(c.slug).catch(() => [] as ChangeSet[])),
    );
    const counts = new Map<string, ChangeCount>();
    const setsBySlug = new Map<string, ChangeSet[]>();
    companies.forEach((c, i) => {
      const arr = lists[i];
      setsBySlug.set(c.slug, arr);
      counts.set(c.slug, {
        added: arr.reduce((s, cs) => s + cs.added_count, 0),
        removed: arr.reduce((s, cs) => s + cs.removed_count, 0),
        material: arr.some((cs) => cs.material),
      });
    });
    return { counts, setsBySlug };
  }, []);

  // Fetch an entity's profile once; shared by the evidence rail and expansion.
  const loadProfile = useCallback(
    (node: GNode) => {
      setProfiles((cache) => {
        if (cache.has(node.id)) return cache;
        setPending((p) => new Set(p).add(node.id));
        api
          .entity(node.kind, node.key)
          .then((prof) => setProfiles((m) => new Map(m).set(node.id, prof)))
          .catch(() => undefined)
          .finally(() =>
            setPending((p) => {
              const n = new Set(p);
              n.delete(node.id);
              return n;
            }),
          );
        return cache;
      });
    },
    [],
  );

  useEffect(() => {
    if (selected) loadProfile(selected);
  }, [selected, loadProfile]);

  // Escape unwinds one drill level: table → compare → isolated graph → overview.
  useEffect(() => {
    if (!selected && !picking && !pathFrom && !tableOpen && !compareSlug) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      if (tableOpen) setTableOpen(false);
      else if (compareSlug) setCompareSlug(null);
      else if (picking) clearPath();
      else if (pathFrom && pathTo) clearPath();
      else setSelected(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [selected, picking, pathFrom, pathTo, tableOpen, compareSlug, clearPath]);

  // Clearing the selection (back to overview) also closes the table.
  useEffect(() => {
    if (!selected && tableOpen) setTableOpen(false);
  }, [selected, tableOpen]);

  const toggleExpand = useCallback(
    (node: GNode) => {
      setExpandedIds((prev) => {
        const next = new Set(prev);
        if (next.has(node.id)) next.delete(node.id);
        else {
          next.add(node.id);
          loadProfile(node);
        }
        return next;
      });
    },
    [loadProfile],
  );

  // Derive the expansion subgraph: for every expanded node, add its entity
  // neighbours that aren't already on the canvas, anchored to it for layout.
  const baseIds = useMemo(() => new Set(data?.graph.nodes.map((n) => n.id) ?? []), [data]);
  const baseEdgeIds = useMemo(() => new Set(data?.graph.edges.map((e) => e.id) ?? []), [data]);
  const expansion = useMemo(() => {
    const nodes: GNode[] = [];
    const edges: GEdge[] = [];
    const anchorOf = new Map<string, string>();
    const revealedBy = new Map<string, number>();
    const addedNodes = new Set<string>();
    const addedEdges = new Set<string>(baseEdgeIds);
    for (const pid of expandedIds) {
      const prof = profiles.get(pid);
      if (!prof) continue;
      for (const rel of prof.relationships) {
        if (!isEntityRelation(rel.relation)) continue;
        const y = rel.other;
        // Mirror buildGraph (graph.tsx): Country is a low-signal hub everything
        // links to via operates_in — excluded from the map and the BFS alike.
        if (y.kind === "Country") continue;
        const yId = `${y.kind}:${y.key}`;
        if (yId === pid) continue;
        const tier = relationTier(rel.relation);
        if (!baseIds.has(yId) && !addedNodes.has(yId)) {
          addedNodes.add(yId);
          nodes.push({ id: yId, kind: y.kind, key: y.key, name: y.name, tracked: false, bridges: [] });
          anchorOf.set(yId, pid);
          revealedBy.set(pid, (revealedBy.get(pid) ?? 0) + 1);
        }
        const [a, b] = [pid, yId].sort();
        const ek = `${a}|${b}|${rel.relation}`;
        if (!addedEdges.has(ek)) {
          addedEdges.add(ek);
          edges.push({ id: ek, source: pid, target: yId, relation: rel.relation, tier });
        }
      }
    }
    return { nodes, edges, anchorOf, revealedBy };
  }, [expandedIds, profiles, baseIds, baseEdgeIds]);

  // ---- pathfinding: shortest chain of relationships between two entities ------
  const nodeById = useMemo(() => {
    const m = new Map<string, GNode>();
    for (const n of data?.graph.nodes ?? []) m.set(n.id, n);
    for (const n of expansion.nodes) m.set(n.id, n);
    return m;
  }, [data, expansion.nodes]);

  const adjacency = useMemo(() => {
    const adj = new Map<string, Array<{ to: string; relation: string }>>();
    const link = (a: string, b: string, relation: string) =>
      (adj.get(a) ?? adj.set(a, []).get(a)!).push({ to: b, relation });
    for (const e of [...(data?.graph.edges ?? []), ...expansion.edges]) {
      link(e.source, e.target, e.relation);
      link(e.target, e.source, e.relation);
    }
    return adj;
  }, [data, expansion.edges]);

  // Breadth-first shortest path (undirected, fewest hops). `ids` empty ⇒ no path.
  const path = useMemo(() => {
    if (!pathFrom || !pathTo || pathFrom.id === pathTo.id) return null;
    const start = pathFrom.id;
    const goal = pathTo.id;
    const prev = new Map<string, { from: string; relation: string }>();
    const seen = new Set<string>([start]);
    const queue: string[] = [start];
    for (let head = 0; head < queue.length; head++) {
      const cur = queue[head];
      if (cur === goal) break;
      for (const nb of adjacency.get(cur) ?? []) {
        if (seen.has(nb.to)) continue;
        seen.add(nb.to);
        prev.set(nb.to, { from: cur, relation: nb.relation });
        queue.push(nb.to);
      }
    }
    if (!seen.has(goal)) return { ids: [] as string[], steps: [] as Array<{ toId: string; relation: string }> };
    const ids: string[] = [];
    const steps: Array<{ toId: string; relation: string }> = [];
    for (let n = goal; n !== start; ) {
      const p = prev.get(n)!;
      ids.unshift(n);
      steps.unshift({ toId: n, relation: p.relation });
      n = p.from;
    }
    ids.unshift(start);
    return { ids, steps };
  }, [pathFrom, pathTo, adjacency]);

  const startPath = useCallback((from: GNode) => {
    setPathFrom(from);
    setPathTo(null);
    setPicking(true);
  }, []);
  const onBackground = useCallback(() => {
    setSelected(null);
    setCompareSlug(null);
    clearPath();
  }, [clearPath]);

  // The second company to compare against `selected` (the overlap view).
  const compareNode = useMemo(
    () => (compareSlug ? (data?.graph.nodes.find((n) => n.tracked && n.key === compareSlug) ?? null) : null),
    [compareSlug, data],
  );
  const onToggleCompare = useCallback(
    (slug: string) => {
      setCompareSlug((cur) => (cur === slug ? null : slug)); // shift-click again clears it
    },
    [],
  );
  // Load the compared company's profile (selection loads its own elsewhere).
  useEffect(() => {
    if (compareNode) loadProfile(compareNode);
  }, [compareNode, loadProfile]);

  // ---- shareable view state: round-trip selection / path / expansions to the URL
  const desired = useRef<{ sel?: string; cmp?: string; from?: string; to?: string; exp: string[] } | null>(null);
  if (desired.current === null) {
    desired.current = {
      sel: searchParams.get("sel") ?? undefined,
      cmp: searchParams.get("cmp") ?? undefined,
      from: searchParams.get("from") ?? undefined,
      to: searchParams.get("to") ?? undefined,
      exp: (searchParams.get("exp") ?? "").split(",").filter(Boolean),
    };
  }
  const hydrated = useRef(false);
  const expApplied = useRef(false);
  const hydrateAttempts = useRef(0);
  useEffect(() => {
    if (hydrated.current || !data) return;
    hydrateAttempts.current += 1;
    const d = desired.current!;
    if (d.exp.length) {
      if (!expApplied.current) {
        expApplied.current = true;
        setExpandedIds(new Set(d.exp));
      }
      // setExpandedIds alone doesn't fetch profiles (toggleExpand normally does),
      // so the restored expansions would never produce their burst nodes. Load
      // each available expanded node's profile here (loadProfile is idempotent).
      for (const id of d.exp) {
        const n = nodeById.get(id);
        if (n) loadProfile(n);
      }
    }
    if (d.sel && !selected) {
      const n = nodeById.get(d.sel);
      if (n) setSelected(n);
    }
    if (d.cmp && !compareSlug) setCompareSlug(d.cmp);
    if (d.from && d.to && !pathFrom) {
      const a = nodeById.get(d.from);
      const b = nodeById.get(d.to);
      if (a && b) {
        setPathFrom(a);
        setPathTo(b);
      }
    }
    const selDone = !d.sel || nodeById.has(d.sel);
    const pathDone = !(d.from && d.to) || (nodeById.has(d.from) && nodeById.has(d.to));
    if (selDone && pathDone) {
      hydrated.current = true; // everything restored
    } else if (d.exp.length === 0) {
      // No expansions to wait on → the base graph is already final, so an
      // unresolved id never will resolve. Finalize now and drop it; a stale or
      // hand-edited URL must never permanently freeze URL writes for the session.
      hydrated.current = true;
    } else if (expApplied.current && hydrateAttempts.current >= 2 && pending.size === 0) {
      // Restored expansions have settled (kickoff fetches registered then drained);
      // give up on any id still unresolved rather than freeze forever.
      hydrated.current = true;
    }
  }, [data, nodeById, selected, pathFrom, pending, loadProfile]);

  // Collapsing a node whose descendants were themselves expanded leaves orphan
  // ids in expandedIds (no longer base nodes, no longer revealed by any parent).
  // Prune them — but only post-hydration and only once their profile has loaded,
  // so a still-loading restored expansion is never mistaken for an orphan.
  useEffect(() => {
    if (!hydrated.current || !data) return;
    const available = new Set<string>(baseIds);
    for (const n of expansion.nodes) available.add(n.id);
    let changed = false;
    const next = new Set(expandedIds);
    for (const id of expandedIds) {
      if (!available.has(id) && profiles.has(id)) {
        next.delete(id);
        changed = true;
      }
    }
    if (changed) setExpandedIds(next);
  }, [data, baseIds, expansion.nodes, expandedIds, profiles]);

  // Write current state to the URL (replace, so the back button isn't flooded).
  // Gated on `hydrated` so the restore pass is never clobbered by an empty write.
  useEffect(() => {
    if (!hydrated.current) return;
    const next = new URLSearchParams();
    if (pathFrom && pathTo) {
      next.set("from", pathFrom.id);
      next.set("to", pathTo.id);
    } else if (selected) {
      next.set("sel", selected.id);
      if (compareSlug) next.set("cmp", compareSlug);
    }
    if (expandedIds.size) next.set("exp", [...expandedIds].join(","));
    setSearchParams(next, { replace: true });
  }, [selected, compareSlug, pathFrom, pathTo, expandedIds, setSearchParams]);

  return (
    <div className="atlas">
      <div className="atlas-stage">
        <header className="atlas-header">
          <div className="atlas-title">
            <div className="kicker"><span className="idx">◆</span> Atlas</div>
            <h1>The connected universe</h1>
          </div>
          {stats ? (
            <div className="atlas-meta">
              <span className="pill">{stats.companies} companies</span>
              <span className="pill">{stats.links} edges</span>
              <span className="pill">{stats.bridges} bridges</span>
              {ukCount > 0 ? (
                <span className="pill" title="Companies by country">
                  🇺🇸 {usCount} · 🇬🇧 {ukCount}
                </span>
              ) : null}
              {expansion.nodes.length > 0 ? (
                <span className="pill accent">+{expansion.nodes.length} expanded</span>
              ) : null}
              {selected || pathFrom || expandedIds.size > 0 ? <CopyLink /> : null}
            </div>
          ) : null}
          <div className="relmap-legend atlas-legend">
            {TIERS.map((t) => (
              <span className="relmap-legend-item" key={t.tier} title={t.hint}>
                <span className={`relmap-swatch tier-${t.tier}`} />
                {t.label}
              </span>
            ))}
          </div>
          {data && data.failed > 0 ? (
            <div className="atlas-note">
              <GraphIncompleteNote failed={data.failed} />
            </div>
          ) : null}
        </header>

        {picking && pathFrom ? (
          <div className="atlas-pickbanner" role="status">
            Tracing from <strong>{pathFrom.name}</strong> — click a target entity · <kbd>Esc</kbd> to cancel
          </div>
        ) : null}

        {loading || !data ? (
          <div className="atlas-loading">
            <Loading label="Mapping the universe" />
          </div>
        ) : (
          <Suspense fallback={<div className="atlas-loading"><Loading label="Loading the 3D view" /></div>}>
            <Atlas3D
              companies={data.companies}
              profiles={data.profiles}
              selectedSlug={selected?.key}
              compareSlug={compareSlug ?? undefined}
              onSelectCompany={(slug) => {
                clearPath();
                setCompareSlug(null);
                setSelected(data.graph.nodes.find((n) => n.tracked && n.key === slug) ?? null);
              }}
              onToggleCompare={onToggleCompare}
              onBackground={onBackground}
            />
          </Suspense>
        )}
        {selected && !compareNode && !tableOpen ? (
          <div className="atlas-hint" role="note">
            ⇧-click another company to compare
          </div>
        ) : null}
        {selected && !tableOpen ? (
          <button className="atlas-back" onClick={onBackground}>
            ← Overview
          </button>
        ) : null}
      </div>

      {tableOpen && selected && !compareNode ? (
        <TableView
          node={selected}
          profile={profiles.get(selected.id)}
          changeSets={selected.tracked ? changesAsync.data?.setsBySlug.get(selected.key) : undefined}
          trackedKeys={data?.trackedKeys}
          onClose={() => setTableOpen(false)}
        />
      ) : null}

      {selected && compareNode ? (
        <ComparePanel
          a={selected}
          b={compareNode}
          profileA={profiles.get(selected.id)}
          profileB={profiles.get(compareNode.id)}
          loading={(pending.has(compareNode.id) && !profiles.has(compareNode.id)) || (pending.has(selected.id) && !profiles.has(selected.id))}
          companies={data?.companies ?? []}
          onClear={() => setCompareSlug(null)}
          onClose={onBackground}
        />
      ) : pathFrom && pathTo ? (
        <PathPanel
          from={pathFrom}
          to={pathTo}
          steps={path?.steps ?? []}
          found={(path?.ids.length ?? 0) > 0}
          nodeById={nodeById}
          onClear={clearPath}
        />
      ) : selected ? (
        <EvidenceRail
          node={selected}
          profile={profiles.get(selected.id)}
          loading={pending.has(selected.id) && !profiles.has(selected.id)}
          trackedKeys={data?.trackedKeys}
          changeSets={selected.tracked ? changesAsync.data?.setsBySlug.get(selected.key) : undefined}
          expanded={expandedIds.has(selected.id)}
          revealed={expansion.revealedBy.get(selected.id) ?? 0}
          picking={picking}
          graphInteractive={false}
          onTracePath={() => startPath(selected)}
          onToggleExpand={() => toggleExpand(selected)}
          onViewTable={() => setTableOpen(true)}
          onClose={() => setSelected(null)}
        />
      ) : null}
    </div>
  );
}

// A shareable link to the current Atlas view (selection / path / expansions are
// already serialized into the URL). Pointer-events are re-enabled by .atlas-meta.
function CopyLink() {
  const [state, setState] = useState<"idle" | "copied" | "failed">("idle");
  const copy = async () => {
    const url = window.location.href;
    let ok = false;
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(url);
        ok = true;
      }
    } catch {
      ok = false;
    }
    if (!ok) {
      // Fallback for insecure contexts (plain HTTP off localhost) where
      // navigator.clipboard is undefined or the write is denied.
      try {
        const ta = document.createElement("textarea");
        ta.value = url;
        ta.style.position = "fixed";
        ta.style.opacity = "0";
        document.body.appendChild(ta);
        ta.select();
        ok = document.execCommand("copy");
        document.body.removeChild(ta);
      } catch {
        ok = false;
      }
    }
    setState(ok ? "copied" : "failed");
    setTimeout(() => setState("idle"), 1800);
  };
  return (
    <button
      type="button"
      className={`pill${state === "copied" ? " accent" : ""}`}
      style={{ cursor: "pointer" }}
      title="Copy a shareable link to this exact view"
      aria-live="polite"
      onClick={copy}
    >
      {state === "copied" ? "✓ Copied" : state === "failed" ? "⌘C to copy" : "⎘ Copy link"}
    </button>
  );
}

// Path panel — the traced shortest chain of relationships between two entities,
// read top-to-bottom with the relation verb on each hop.
function PathPanel({
  from,
  to,
  steps,
  found,
  nodeById,
  onClear,
}: {
  from: GNode;
  to: GNode;
  steps: Array<{ toId: string; relation: string }>;
  found: boolean;
  nodeById: Map<string, GNode>;
  onClear: () => void;
}) {
  return (
    <aside className="evidence-rail" aria-label={`Path from ${from.name} to ${to.name}`}>
      <div className="rail-head">
        <div className="rail-id">
          <span className="rail-kind">◆ Path</span>
          <h2 className="rail-name">
            {from.name} → {to.name}
          </h2>
        </div>
        <button className="rail-close" onClick={onClear} aria-label="Clear path" title="Clear (Esc)">
          ✕
        </button>
      </div>
      {!found ? (
        <p className="rail-expand-note" role="status" aria-live="polite">
          No connection found between these two entities in the current graph.
        </p>
      ) : (
        <div className="rail-body">
          <p className="faint" role="status" aria-live="polite" style={{ fontSize: 12.5, margin: "2px 0 12px" }}>
            {steps.length} {steps.length === 1 ? "hop" : "hops"} — the shortest chain of relationships.
          </p>
          <ol className="path-chain">
            <li className="path-node">
              <span className="path-glyph">{kindGlyph(from.kind)}</span>
              <span className="path-nm">{from.name}</span>
              <span className="path-knd">{from.kind}</span>
            </li>
            {steps.map((s, i) => {
              const n = nodeById.get(s.toId);
              return (
                <li key={i} className="path-step">
                  <span className={`relchip tier-${relationTier(s.relation)} path-rel`}>{relationVerb(s.relation)}</span>
                  <div className="path-node">
                    <span className="path-glyph">{kindGlyph(n?.kind ?? "")}</span>
                    <span className="path-nm">{n?.name ?? s.toId}</span>
                    <span className="path-knd">{n?.kind}</span>
                  </div>
                </li>
              );
            })}
          </ol>
        </div>
      )}
    </aside>
  );
}

// Compare two companies → their specific overlap: shared leadership/board (the
// board interlocks), shared co-mentioned peers, a direct co-mention, same sector.
const GOV_RELS = new Set(["employs", "board_member"]);

function ComparePanel({
  a,
  b,
  profileA,
  profileB,
  loading,
  companies,
  onClear,
  onClose,
}: {
  a: GNode;
  b: GNode;
  profileA?: EntityProfile;
  profileB?: EntityProfile;
  loading: boolean;
  companies: Company[];
  onClear: () => void;
  onClose: () => void;
}) {
  // Shared leadership/board: a person both companies connect to (the interlock).
  const govA = new Map<string, Relationship>();
  for (const r of profileA?.relationships ?? []) {
    if (GOV_RELS.has(r.relation) && r.other.kind === "Person" && !govA.has(r.other.key)) govA.set(r.other.key, r);
  }
  const sharedPeople: { name: string; key: string; roleA?: string | null; roleB?: string | null }[] = [];
  const seenPerson = new Set<string>();
  for (const r of profileB?.relationships ?? []) {
    if (GOV_RELS.has(r.relation) && r.other.kind === "Person" && govA.has(r.other.key) && !seenPerson.has(r.other.key)) {
      seenPerson.add(r.other.key);
      sharedPeople.push({ name: r.other.name, key: r.other.key, roleA: govA.get(r.other.key)!.detail, roleB: r.detail });
    }
  }
  // Shared co-mentioned peers (companies both name in their filings).
  const refsA = new Set((profileA?.relationships ?? []).filter((r) => r.relation === "references").map((r) => r.other.key));
  const sharedPeers = (profileB?.relationships ?? []).filter((r) => r.relation === "references" && refsA.has(r.other.key));
  // A direct co-mention between the two.
  const direct =
    (profileA?.relationships ?? []).some((r) => r.relation === "references" && r.other.key === b.key) ||
    (profileB?.relationships ?? []).some((r) => r.relation === "references" && r.other.key === a.key);
  const sectorOf = (key: string) => {
    const c = companies.find((co) => co.slug === key);
    return c ? coarseSector(c.industry) : undefined;
  };
  const sectorA = sectorOf(a.key);
  const sameSector = sectorA && sectorA === sectorOf(b.key) ? sectorA : null;
  const nothing = !loading && sharedPeople.length === 0 && sharedPeers.length === 0 && !direct && !sameSector;

  return (
    <aside className="evidence-rail compare-rail" aria-label={`${a.name} compared with ${b.name}`}>
      <div className="rail-head">
        <span className="rail-kind">⇆ Compare</span>
        <button className="rail-close" onClick={onClose} aria-label="Close (Esc)" title="Overview (Esc)">
          ✕
        </button>
      </div>
      <h2 className="compare-title">
        <span>{a.name}</span>
        <span className="compare-amp">∩</span>
        <span>{b.name}</span>
      </h2>

      {loading ? (
        <Skeleton />
      ) : nothing ? (
        <p className="faint compare-empty">
          No shared leadership, peers, or sector — these two don't overlap directly. Their connection, if any, runs
          through longer chains.
        </p>
      ) : (
        <>
          {direct ? (
            <div className="compare-flag">
              <span className="relchip tier-reference">{a.name}</span> and{" "}
              <span className="relchip tier-reference">{b.name}</span> name each other in their filings.
            </div>
          ) : null}
          {sameSector ? <div className="compare-flag">Both operate in {sameSector}.</div> : null}

          {sharedPeople.length > 0 ? (
            <section className="rail-section">
              <div className="tbl-head">
                <h3>Shared leadership &amp; board</h3>
                <span className="pill">{sharedPeople.length}</span>
              </div>
              <div className="compare-people">
                {sharedPeople.map((p) => (
                  <div className="compare-person" key={p.key}>
                    <span className="tp-name">{p.name}</span>
                    <span className="compare-roles">
                      <span className="cr">
                        <em>{a.name}</em> {p.roleA ?? "—"}
                      </span>
                      <span className="cr">
                        <em>{b.name}</em> {p.roleB ?? "—"}
                      </span>
                    </span>
                  </div>
                ))}
              </div>
            </section>
          ) : null}

          {sharedPeers.length > 0 ? (
            <section className="rail-section">
              <div className="tbl-head">
                <h3>Both connected to</h3>
                <span className="pill">{sharedPeers.length}</span>
              </div>
              <div className="tbl-grid">
                {sharedPeers.map((r, i) => (
                  <span className="relchip tier-reference" key={i}>
                    {r.other.name}
                  </span>
                ))}
              </div>
            </section>
          ) : null}
        </>
      )}

      <div className="rail-actions">
        <button className="btn ghost" onClick={onClear}>
          ← Back to {a.name}
        </button>
      </div>
    </aside>
  );
}

// Drill level 3: the focused company as scannable tables — full material-change
// list (with source links), subsidiaries, co-mentions, and source documents.
function TableView({
  node,
  profile,
  changeSets,
  trackedKeys,
  onClose,
}: {
  node: GNode;
  profile?: EntityProfile;
  changeSets?: ChangeSet[];
  trackedKeys?: Set<string>;
  onClose: () => void;
}) {
  const subsidiaries = profile?.relationships.filter((r) => r.relation === "has_subsidiary") ?? [];
  const people = profile?.relationships.filter((r) => r.relation === "employs" && r.other.kind === "Person") ?? [];
  const board = profile?.relationships.filter((r) => r.relation === "board_member" && r.other.kind === "Person") ?? [];
  const sharesOf = (d?: string | null) => {
    const m = d?.match(/([\d,]+)\s+shares/);
    return m ? parseInt(m[1].replace(/,/g, ""), 10) : 0;
  };
  const holdings = (profile?.relationships.filter((r) => r.relation === "insider_holding" && r.other.kind === "Person") ?? [])
    .slice()
    .sort((a, b) => sharesOf(b.detail) - sharesOf(a.detail));
  const coMentions = profile?.relationships.filter((r) => r.relation === "references") ?? [];
  const material = (changeSets ?? []).filter((cs) => cs.material);
  const added = material.reduce((s, cs) => s + cs.added_count, 0);
  const removed = material.reduce((s, cs) => s + cs.removed_count, 0);
  const allChanges = material.flatMap((cs) => cs.changes);
  const changes = allChanges.slice(0, 24); // headline only; people/board sit below — full diff in the dossier
  const docs = profile?.mentioned_in ?? [];

  return (
    <div className="atlas-table" role="dialog" aria-label={`${node.name} detail`}>
      <div className="atlas-table-bar">
        <button className="btn ghost" onClick={onClose}>
          ← Back to graph
        </button>
        <div className="atlas-table-title">
          <span className="rail-kind">
            {kindGlyph(node.kind)} {node.kind}
          </span>
          <h2>{node.name}</h2>
        </div>
        <Link className="btn ghost" to={`/companies/${node.key}`}>
          Open full dossier →
        </Link>
      </div>
      <div className="atlas-table-body">
        <section className="tbl-section">
          <div className="tbl-head">
            <h3>What changed</h3>
            {material.length ? (
              <span className="wrap" style={{ gap: 6 }}>
                <span className="pill" style={{ color: "var(--good)" }}>+{added}</span>
                <span className="pill" style={{ color: "var(--danger)" }}>−{removed}</span>
              </span>
            ) : null}
          </div>
          {changes.length === 0 ? (
            <p className="faint">No material changes in the latest disclosure.</p>
          ) : (
            <table className="tbl">
              <thead>
                <tr>
                  <th aria-label="direction"></th>
                  <th>Category</th>
                  <th>Statement</th>
                  <th>Source</th>
                </tr>
              </thead>
              <tbody>
                {changes.map((c, i) => (
                  <tr key={i} className={c.kind}>
                    <td className="tbl-mark">{c.kind === "added" ? "+" : "−"}</td>
                    <td><Cat category={c.category} /></td>
                    <td className="tbl-stmt">{c.statement}</td>
                    <td>
                      {c.evidence?.canonical_id ? (
                        <Link className="pill evidence" to={`/documents/${c.evidence.canonical_id}`}>↳ source</Link>
                      ) : (
                        <span className="faint">—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {allChanges.length > changes.length ? (
            <p className="faint" style={{ marginTop: 10 }}>
              Showing {changes.length} of {allChanges.length} change lines —{" "}
              <Link to={`/companies/${node.key}`}>open the full dossier</Link>.
            </p>
          ) : null}
        </section>

        {people.length > 0 ? (
          <section className="tbl-section">
            <div className="tbl-head">
              <h3>Key people</h3>
              <span className="pill">{people.length}</span>
            </div>
            <div className="tbl-people">
              {people.map((r, i) => (
                <div className="tbl-person" key={i}>
                  <span className="tp-name">{r.other.name}</span>
                  {r.detail ? <span className="tp-role">{r.detail}</span> : null}
                </div>
              ))}
            </div>
          </section>
        ) : null}

        {board.length > 0 ? (
          <section className="tbl-section">
            <div className="tbl-head">
              <h3>Board of directors</h3>
              <span className="pill">{board.length}</span>
            </div>
            <div className="tbl-people">
              {board.map((r, i) => (
                <div className="tbl-person" key={i}>
                  <span className="tp-name">{r.other.name}</span>
                  {r.detail ? <span className="tp-role">{r.detail}</span> : null}
                </div>
              ))}
            </div>
          </section>
        ) : null}

        {holdings.length > 0 ? (
          <section className="tbl-section">
            <div className="tbl-head">
              <h3>Insider holdings</h3>
              <span className="pill">{holdings.length}</span>
            </div>
            <div className="tbl-people">
              {holdings.map((r, i) => (
                <div className="tbl-person" key={i}>
                  <span className="tp-name">{r.other.name}</span>
                  {r.detail ? <span className="tp-role">{r.detail}</span> : null}
                </div>
              ))}
            </div>
          </section>
        ) : null}

        {subsidiaries.length > 0 ? (
          <section className="tbl-section">
            <div className="tbl-head">
              <h3>Subsidiaries</h3>
              <span className="pill">{subsidiaries.length}</span>
            </div>
            <div className="tbl-grid">
              {subsidiaries.map((r, i) => (
                <span className="relchip tier-ownership" key={i} title={r.detail ?? undefined}>
                  {r.other.name}
                  {r.detail ? <span className="relchip-sub"> · {r.detail}</span> : null}
                </span>
              ))}
            </div>
          </section>
        ) : null}

        {coMentions.length > 0 ? (
          <section className="tbl-section">
            <div className="tbl-head">
              <h3>Co-mentions</h3>
              <span className="pill">{coMentions.length}</span>
            </div>
            <div className="tbl-grid">
              {coMentions.map((r, i) =>
                trackedKeys?.has(r.other.key) ? (
                  <Link className="relchip tier-reference" to={`/companies/${r.other.key}`} key={i}>
                    {r.other.name}
                  </Link>
                ) : (
                  <span className="relchip tier-reference" key={i}>
                    {r.other.name}
                  </span>
                ),
              )}
            </div>
          </section>
        ) : null}

        {docs.length > 0 ? (
          <section className="tbl-section">
            <div className="tbl-head">
              <h3>Mentioned in</h3>
              <span className="pill">{docs.length}</span>
            </div>
            <div className="wrap">
              {docs.slice(0, 40).map((id) => (
                <Link key={id} to={`/documents/${id}`} className="pill evidence" title={id}>
                  ↳ source
                </Link>
              ))}
            </div>
          </section>
        ) : null}
      </div>
    </div>
  );
}

function EvidenceRail({
  node,
  profile,
  loading,
  trackedKeys,
  changeSets,
  expanded,
  revealed,
  picking,
  graphInteractive = true,
  onTracePath,
  onToggleExpand,
  onViewTable,
  onClose,
}: {
  node: GNode;
  profile?: EntityProfile;
  loading: boolean;
  trackedKeys?: Set<string>;
  changeSets?: ChangeSet[];
  expanded: boolean;
  revealed: number;
  picking: boolean;
  graphInteractive?: boolean;
  onTracePath: () => void;
  onToggleExpand: () => void;
  onViewTable?: () => void;
  onClose: () => void;
}) {
  return (
    <aside className="evidence-rail" aria-label={`Evidence for ${node.name}`}>
      <div className="rail-head">
        <div className="rail-id">
          <span className="rail-kind">
            {kindGlyph(node.kind)} {node.kind}
          </span>
          <h2 className="rail-name">{node.name}</h2>
        </div>
        <button className="rail-close" onClick={onClose} aria-label="Close panel" title="Close (Esc)">
          ✕
        </button>
      </div>

      <div className="rail-actions">
        {node.tracked && onViewTable ? (
          <button className="btn" onClick={onViewTable}>
            View as table →
          </button>
        ) : null}
        {node.tracked ? (
          <Link className="btn ghost" to={`/companies/${node.key}`}>
            Open full dossier →
          </Link>
        ) : null}
        {!node.tracked && graphInteractive ? (
          <button className="btn ghost" onClick={onToggleExpand} aria-pressed={expanded}>
            {expanded ? "Collapse connections" : "Expand connections"}
          </button>
        ) : null}
        {graphInteractive ? (
          <button className="btn ghost" onClick={onTracePath} aria-pressed={picking}>
            Trace a path from here
          </button>
        ) : null}
      </div>
      {picking ? (
        <p className="rail-expand-note">Click another entity on the canvas to trace the shortest path · Esc to cancel.</p>
      ) : null}
      {expanded ? (
        <p className="rail-expand-note">
          {revealed > 0
            ? `${revealed} connection${revealed === 1 ? "" : "s"} added to the canvas, around this node.`
            : "All of this entity's connections were already on the canvas."}
        </p>
      ) : null}

      {node.tracked ? <WhatChanged slug={node.key} changeSets={changeSets} /> : null}

      {loading ? (
        <div className="stack gap-sm" style={{ marginTop: 14 }}>
          <Skeleton h={16} w={140} />
          <Skeleton h={64} />
          <Skeleton h={64} />
        </div>
      ) : profile ? (
        <RailBody profile={profile} trackedKeys={trackedKeys} />
      ) : (
        <span className="faint" style={{ marginTop: 14, display: "block" }}>
          No profile available for this entity.
        </span>
      )}
    </aside>
  );
}

// "What changed" — the headline question for a tracked company. Quiet on the
// canvas (a count notch); rich here: directional +adds/−removes split and the
// backend-ranked material change statements, each with its source link (amber).
function WhatChanged({ slug, changeSets }: { slug: string; changeSets?: ChangeSet[] }) {
  if (changeSets === undefined) {
    return (
      <div className="rail-section">
        <div className="rail-section-head">What changed</div>
        <Skeleton h={40} />
      </div>
    );
  }
  const material = changeSets.filter((cs) => cs.material);
  const added = material.reduce((s, cs) => s + cs.added_count, 0);
  const removed = material.reduce((s, cs) => s + cs.removed_count, 0);
  const total = added + removed || 1;
  const changes = material.flatMap((cs) => cs.changes).slice(0, 6);

  return (
    <div className="rail-section">
      <div className="rail-section-head">What changed</div>
      {material.length === 0 ? (
        <span className="faint">No material changes in the latest disclosure.</span>
      ) : (
        <div className="stack gap-sm">
          <div className="row-between">
            <span className="faint" style={{ fontSize: 12.5 }}>since last disclosure</span>
            <span className="wrap" style={{ gap: 6 }}>
              <span className="pill" style={{ color: "var(--good)" }}>+{added}</span>
              <span className="pill" style={{ color: "var(--danger)" }}>−{removed}</span>
            </span>
          </div>
          <div className="rail-splitbar" aria-hidden="true">
            <span style={{ width: `${(added / total) * 100}%`, background: "var(--good)" }} />
            <span style={{ width: `${(removed / total) * 100}%`, background: "var(--danger)" }} />
          </div>
          <div className="stack" style={{ marginTop: 2 }}>
            {changes.map((c, i) => (
              <div className={`change-row ${c.kind}`} key={i}>
                <span className="change-mark">{c.kind === "added" ? "+" : "−"}</span>
                <div className="grow stack gap-sm">
                  <div className="wrap" style={{ gap: 6 }}>
                    <Cat category={c.category} />
                  </div>
                  <div className="stmt rail-clamp">{c.statement}</div>
                  {c.evidence?.canonical_id ? (
                    <Link
                      to={`/documents/${c.evidence.canonical_id}`}
                      className="pill evidence"
                      style={{ alignSelf: "flex-start" }}
                    >
                      ↳ source
                    </Link>
                  ) : null}
                </div>
              </div>
            ))}
          </div>
          <Link to={`/companies/${slug}`} className="faint" style={{ fontSize: 12.5, marginTop: 2 }}>
            View all in dossier →
          </Link>
        </div>
      )}
    </div>
  );
}

function RailBody({ profile, trackedKeys }: { profile: EntityProfile; trackedKeys?: Set<string> }) {
  const hasRels = profile.relationships.some((r) => isEntityRelation(r.relation));
  const docs = profile.mentioned_in.slice(0, 8);

  return (
    <div className="rail-body">
      <div className="rail-section">
        <div className="rail-section-head">Relationships</div>
        {hasRels ? (
          <RelationGroups relationships={profile.relationships} trackedKeys={trackedKeys} />
        ) : (
          <span className="faint">No typed relationships recorded for this entity.</span>
        )}
      </div>

      {docs.length > 0 ? (
        <div className="rail-section">
          <div className="rail-section-head">Mentioned in</div>
          <div className="wrap">
            {docs.map((id) => (
              <Link key={id} to={`/documents/${id}`} className="pill evidence" title={id}>
                ↳ source
              </Link>
            ))}
          </div>
        </div>
      ) : null}

      <p className="rail-prov">
        Relationships are projected from the curated entity graph (current and prior roles, declared
        dependencies). Control is shown as an inference, never asserted — open a company for its source
        disclosures.
      </p>
    </div>
  );
}
