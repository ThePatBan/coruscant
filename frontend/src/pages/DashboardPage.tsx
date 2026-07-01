import { useMemo, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { api, type ChangeSet, type EntityProfile } from "../api";
import { ErrorView, PanelHead, Skeleton } from "../components";
import { buildGraph, graphStats, GraphIncompleteNote, RelationMap, type GNode, type RelGraph } from "../graph";
import { useAsync } from "../hooks";
import { kindGlyph } from "../relations";
import { buildCommits, ProgressLog, type Commit } from "../progress";

interface BridgeController {
  person: GNode;
  companies: Array<{ key: string; name: string }>;
}
interface SharedDependency {
  supplier: GNode;
  companies: Array<{ key: string; name: string }>;
}

interface DashData {
  ribbon: { companies: number; documents: number; events: number; material: number; links: number };
  graph: RelGraph;
  controllers: BridgeController[];
  dependencies: SharedDependency[];
  movements: Array<ChangeSet & { companyName: string }>;
  commits: Commit[];
  failed: number;
}

async function loadDashboard(): Promise<DashData> {
  const [dash, companies] = await Promise.all([api.dashboard(), api.companies()]);
  const trackedKeys = new Set(companies.map((c) => c.slug));
  const nameFor = (slug: string) => companies.find((c) => c.slug === slug)?.name ?? slug;

  const [profiles, changesPer, timelinePer] = await Promise.all([
    Promise.all(companies.map((c) => api.entity("Company", c.slug).catch(() => null))),
    Promise.all(companies.map((c) => api.companyChanges(c.slug).catch(() => [] as ChangeSet[]))),
    Promise.all(companies.map((c) => api.companyTimeline(c.slug).catch(() => []))),
  ]);

  const validProfiles = profiles.filter((p): p is EntityProfile => Boolean(p));
  const failed = profiles.length - validProfiles.length;
  const graph = buildGraph(validProfiles, trackedKeys);
  const byId = new Map(graph.nodes.map((n) => [n.id, n]));
  const named = (key: string) => ({ key, name: nameFor(key) });

  // Control proxies, derived only from *current* leadership (employs edges) of
  // tracked companies — never from prior tenure, which is not current control.
  const employsMap = new Map<string, Set<string>>();
  for (const e of graph.edges) {
    if (e.relation !== "employs") continue;
    const s = byId.get(e.source)!;
    const t = byId.get(e.target)!;
    const company = s.tracked ? s : t;
    const person = s.kind === "Person" ? s : t;
    if (!company.tracked || person.kind !== "Person") continue;
    (employsMap.get(person.id) ?? employsMap.set(person.id, new Set()).get(person.id)!).add(company.key);
  }
  const controllers: BridgeController[] = [...employsMap.entries()]
    .filter(([, set]) => set.size >= 2)
    .map(([id, set]) => ({ person: byId.get(id)!, companies: [...set].map(named) }))
    .sort((a, b) => b.companies.length - a.companies.length);

  // Shared critical suppliers: one supplier relied on by ≥2 tracked companies.
  const supMap = new Map<string, Set<string>>();
  for (const e of graph.edges) {
    if (e.relation !== "relies_on_supplier") continue;
    const s = byId.get(e.source)!;
    const t = byId.get(e.target)!;
    const company = s.tracked ? s : t;
    const supplier = s.tracked ? t : s;
    if (!company.tracked) continue;
    (supMap.get(supplier.id) ?? supMap.set(supplier.id, new Set()).get(supplier.id)!).add(company.key);
  }
  const dependencies: SharedDependency[] = [...supMap.entries()]
    .filter(([, set]) => set.size >= 2)
    .map(([id, set]) => ({ supplier: byId.get(id)!, companies: [...set].map(named) }));

  const allChanges = changesPer.flat();
  const allEvents = timelinePer.flat();

  const dateMap = new Map<string, string | null>();
  for (const d of dash.latest_documents) dateMap.set(d.canonical_id, d.published_at);
  for (const e of allEvents) if (e.occurred_at && !dateMap.has(e.canonical_id)) dateMap.set(e.canonical_id, e.occurred_at);
  const dateFor = (id: string | null) => (id ? dateMap.get(id) ?? null : null);

  const movements = allChanges
    .filter((c) => c.material)
    .map((c) => ({ ...c, companyName: nameFor(c.company_slug) }))
    .sort((a, b) => b.added_count + b.removed_count - (a.added_count + a.removed_count));

  return {
    ribbon: {
      companies: dash.companies,
      documents: dash.documents,
      events: dash.events,
      material: dash.material_changes,
      links: graph.edges.length,
    },
    graph,
    controllers,
    dependencies,
    movements,
    commits: buildCommits(allChanges, allEvents, nameFor, dateFor),
    failed,
  };
}

export function DashboardPage() {
  const { data, error, loading } = useAsync(loadDashboard, []);
  const stats = useMemo(() => (data ? graphStats(data.graph) : null), [data]);

  return (
    <div className="stack gap-lg">
      <div className="page-head">
        <h1>Intelligence overview</h1>
        <p className="sub">
          The monitored universe as a connected system: how its companies relate, who plausibly controls
          what, and how each has progressed disclosure by disclosure. Every line traces back to its source.
        </p>
      </div>

      {error ? <ErrorView error={error} /> : null}
      {loading ? <DashboardSkeleton /> : null}

      {data ? (
        <>
          <div className="ribbon">
            <Cell num={data.ribbon.companies} label="Companies" />
            <Cell num={data.ribbon.documents} label="Documents" />
            <Cell num={data.ribbon.events} label="Events extracted" />
            <Cell num={data.ribbon.material} label="Material changes" alert />
            <Cell num={data.ribbon.links} label="Graph connections" />
          </div>

          {/* Orientation — the three spatial reads, one click away. */}
          <nav className="orient-strip" aria-label="Orientation">
            <Link className="orient-card" to="/changes">
              <span className="oc-kicker"><span className="idx">01</span> What changed</span>
              <span className="oc-title">{data.ribbon.material} material changes</span>
              <span className="oc-sub">Overnight risks, opportunities and events — evidence first, with the line-level diff behind each.</span>
            </Link>
            <Link className="orient-card" to="/risk">
              <span className="oc-kicker"><span className="idx">02</span> Where risk concentrates</span>
              <span className="oc-title">Sector × region matrix</span>
              <span className="oc-sub">Where the book clusters by GICS sector and Exhibit-21 legal footprint. Drill to the named holdings.</span>
            </Link>
            <Link className="orient-card" to="/country">
              <span className="oc-kicker"><span className="idx">03</span> Country exposure</span>
              <span className="oc-title">The World → Country → Company rung</span>
              <span className="oc-sub">Per-country footprint, chokepoints and what changed among the holdings tied there.</span>
            </Link>
          </nav>

          {/* TIER 1 — relationship map (focal) */}
          <section className="stack gap">
            <PanelHead
              idx="01"
              kicker="Relationship map"
              title="How the universe connects"
              sub="Tracked companies and the bridges between them — a shared executive, a shared supplier, a shared technology. Color encodes the kind of tie."
              right={
                stats ? (
                  <div className="wrap" style={{ justifyContent: "flex-end" }}>
                    <span className="pill">{stats.companies} companies</span>
                    <span className="pill">{stats.bridges} bridges</span>
                    <Link to="/graph" className="pill accent">
                      Open full graph →
                    </Link>
                  </div>
                ) : null
              }
            />
            <RelationMap graph={data.graph} mode="core" />
            <GraphIncompleteNote failed={data.failed} />
          </section>

          {/* TIER 2 — control proxies + material movements */}
          <div className="dash-split">
            <ControlPanel controllers={data.controllers} dependencies={data.dependencies} />
            <MovementsPanel movements={data.movements} />
          </div>

          {/* TIER 3 — git-log progress history */}
          <section className="stack gap">
            <PanelHead
              idx="03"
              kicker="Progress history"
              title="What changed, in order"
              sub="Material disclosure diffs and extracted events as one commit log. Filter by lens; open any commit for its evidence."
            />
            <ProgressLog commits={data.commits} />
          </section>
        </>
      ) : null}
    </div>
  );
}

function Cell({ num, label, alert }: { num: number; label: string; alert?: boolean }) {
  return (
    <div className="cell">
      <div className={`num${alert ? " alert" : ""}`}>{num}</div>
      <div className="lbl">{label}</div>
    </div>
  );
}

function CompanyChip({ company }: { company: { key: string; name: string } }) {
  return (
    <Link to={`/companies/${company.key}`} className="pill accent">
      {company.name}
    </Link>
  );
}

function ControlPanel({
  controllers,
  dependencies,
}: {
  controllers: BridgeController[];
  dependencies: SharedDependency[];
}) {
  const hasAny = controllers.length > 0 || dependencies.length > 0;
  return (
    <section className="stack gap">
      <PanelHead
        idx="02"
        kicker="Ownership & control"
        title="Who plausibly controls what"
        sub="No disclosure in scope declares ultimate ownership. These are the strongest control proxies the graph supports, shown as inferences."
      />
      <div className="card stack gap">
        {!hasAny ? (
          <span className="faint">No cross-company control signals in the current graph.</span>
        ) : null}

        {controllers.length > 0 ? (
          <div>
            <SubHead>Bridge controllers</SubHead>
            {controllers.map((c) => (
              <div className="ctrl-row" key={c.person.id}>
                <span className="ctrl-actor tier-proxy">
                  <span className="glyph">{kindGlyph(c.person.kind)}</span>
                  <span className="nm">{c.person.name}</span>
                </span>
                <span className="ctrl-arrow">leads →</span>
                <div className="ctrl-targets">
                  {c.companies.map((co) => (
                    <CompanyChip company={co} key={co.key} />
                  ))}
                </div>
              </div>
            ))}
            <div className="ctrl-note">
              <span className="inf">inferred</span>
              Control implied by leading more than one company; projected from the curated entity graph, not a
              declared ownership relationship. Open a company for its source disclosures.
            </div>
          </div>
        ) : null}

        {dependencies.length > 0 ? (
          <div>
            <SubHead>Shared dependency</SubHead>
            {dependencies.map((d) => (
              <div className="ctrl-row" key={d.supplier.id}>
                <span className="ctrl-actor tier-supply">
                  <span className="glyph">{kindGlyph(d.supplier.kind)}</span>
                  <span className="nm">{d.supplier.name}</span>
                </span>
                <span className="ctrl-arrow">supplies →</span>
                <div className="ctrl-targets">
                  {d.companies.map((co) => (
                    <CompanyChip company={co} key={co.key} />
                  ))}
                </div>
              </div>
            ))}
            <div className="ctrl-note">
              <span className="inf">exposure</span>
              A single supplier that several companies depend on: a shared point of failure, not a controller.
            </div>
          </div>
        ) : null}
      </div>
    </section>
  );
}

function MovementsPanel({ movements }: { movements: Array<ChangeSet & { companyName: string }> }) {
  return (
    <section className="stack gap">
      <PanelHead
        idx="—"
        kicker="Material movements"
        title="Biggest disclosure shifts"
        sub="Ranked by how much each disclosure rewrote the prior one."
      />
      <div className="card stack gap-sm">
        {movements.length === 0 ? (
          <span className="faint">No material changes detected across the universe.</span>
        ) : (
          movements.slice(0, 5).map((m) => {
            const total = m.added_count + m.removed_count || 1;
            return (
              <Link
                to={`/companies/${m.company_slug}`}
                className="stack gap-sm"
                key={m.current_canonical_id}
                style={{ padding: "10px 0", borderTop: "1px solid var(--border)" }}
              >
                <div className="row-between">
                  <span className="commit-co">{m.companyName}</span>
                  <span className="wrap" style={{ gap: 6 }}>
                    <span className="pill" style={{ color: "var(--good)" }}>+{m.added_count}</span>
                    <span className="pill" style={{ color: "var(--danger)" }}>−{m.removed_count}</span>
                  </span>
                </div>
                <div
                  style={{ height: 6, borderRadius: 999, overflow: "hidden", display: "flex", background: "var(--bg-elev-2)" }}
                  aria-hidden="true"
                >
                  <span style={{ width: `${(m.added_count / total) * 100}%`, background: "var(--good)" }} />
                  <span style={{ width: `${(m.removed_count / total) * 100}%`, background: "var(--danger)" }} />
                </div>
                <div className="faint truncate" style={{ fontSize: 13 }}>
                  {m.current_title ?? `${m.added_count} added · ${m.removed_count} removed`}
                </div>
              </Link>
            );
          })
        )}
      </div>
    </section>
  );
}

function SubHead({ children }: { children: ReactNode }) {
  return (
    <div className="relgroup-head" style={{ marginBottom: 11 }}>
      <h4>{children}</h4>
    </div>
  );
}

function DashboardSkeleton() {
  return (
    <div className="stack gap-lg" aria-hidden="true">
      <Skeleton h={74} />
      <div className="stack gap">
        <Skeleton h={18} w={220} />
        <Skeleton h={420} />
      </div>
      <div className="dash-split">
        <Skeleton h={260} />
        <Skeleton h={260} />
      </div>
      <Skeleton h={320} />
    </div>
  );
}
