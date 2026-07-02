// Atlas (design-pack Screen 5) — entity dossier + relationship intelligence as a
// labeled stakeholder map, not a force-directed hairball. Identity + why-you're-
// here first; insiders fan left, business relationships sit in typed lanes right;
// every edge carries its source. Grounded strictly in the graph's real edges
// (insider_holding, has_subsidiary, references/co-mention, in_sector,
// in_market_tier). Click a co-mentioned company to travel. The Ask bar answers
// only from the evidence via /analyst. Nothing here is fabricated.

import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, type AnalysisReport, type EntityProfile, type Relationship } from "../api";
import { useAuth } from "../auth";
import { ErrorView, Loading, Skeleton } from "../components";
import { useAsync } from "../hooks";
import { kindGlyph, relationVerb } from "../relations";

const START = "pg";

const TIER_COLOR: Record<string, string> = {
  people: "var(--accent)",
  references: "var(--rel-country)",
  has_subsidiary: "var(--evidence)",
  in_sector: "var(--rel-tech)",
  in_market_tier: "var(--text-faint)",
};

interface Lane {
  key: string;
  label: string;
  travel: boolean;
  items: { key: string; name: string; kind: string; rel: Relationship }[];
}

const LANE_DEFS: { key: string; label: string; travel: boolean }[] = [
  { key: "references", label: "Co-mentioned in filings", travel: true },
  { key: "has_subsidiary", label: "Owns (Exhibit-21)", travel: false },
  { key: "in_sector", label: "Sector", travel: false },
  { key: "in_market_tier", label: "Market tier", travel: false },
];

type Sel = { kind: "person"; rel: Relationship } | { kind: "rel"; rel: Relationship } | null;

export function AtlasStakeholderPage() {
  const { email } = useAuth();
  const [path, setPath] = useState<{ key: string; name: string }[]>([{ key: START, name: START.toUpperCase() }]);
  const [sel, setSel] = useState<Sel>(null);
  const focal = path[path.length - 1];

  const prof = useAsync(() => api.entity("Company", focal.key), [focal.key]);
  const d: EntityProfile | null = prof.data;

  const travel = (key: string, name: string) => {
    setSel(null);
    setPath((p) => (p[p.length - 1].key === key ? p : [...p, { key, name }]));
  };
  const goTo = (i: number) => {
    setSel(null);
    setPath((p) => p.slice(0, i + 1));
  };

  const model = useMemo(() => {
    if (!d) return null;
    const rels = d.relationships;
    const props = d.properties as Record<string, string>;
    const people: Relationship[] = [];
    const seenP = new Set<string>();
    for (const r of rels) {
      if (r.other.kind !== "Person") continue;
      if (seenP.has(r.other.key)) continue;
      seenP.add(r.other.key);
      people.push(r);
    }
    const lanes: Lane[] = [];
    for (const def of LANE_DEFS) {
      const seen = new Set<string>();
      const items: Lane["items"] = [];
      for (const r of rels) {
        if (r.relation !== def.key) continue;
        if (seen.has(r.other.key)) continue;
        seen.add(r.other.key);
        items.push({ key: r.other.key, name: r.other.name, kind: r.other.kind, rel: r });
      }
      if (items.length) lanes.push({ ...def, items });
    }
    const subs = rels.filter((r) => r.relation === "has_subsidiary").length;
    const refs = rels.filter((r) => r.relation === "references").length;
    const filings = rels.filter((r) => r.relation === "filed").length;
    return { rels, props, people, lanes, subs, refs, filings };
  }, [d]);

  return (
    <div className="atl spatial-page">
      {/* breadcrumb — /world is a signed-in (Personal) surface, so omit it for the
          anonymous public visitor funnelled here, who would otherwise hit the login
          wall. They start at the public "What changed" crumb. */}
      <div className="atl-crumb">
        {email ? (
          <>
            <Link to="/world" className="atl-crumb-link">World</Link>
            <span className="atl-crumb-sep">›</span>
          </>
        ) : null}
        <Link to="/changes" className="atl-crumb-link">What changed</Link>
        {path.map((p, i) => (
          <span key={p.key + i} style={{ display: "inline-flex", alignItems: "center" }}>
            <span className="atl-crumb-sep">›</span>
            <button
              className={`atl-crumb-node${i === path.length - 1 ? " cur" : ""}`}
              onClick={() => goTo(i)}
              disabled={i === path.length - 1}
            >
              {i === path.length - 1 && d ? d.entity.name : p.name}
            </button>
          </span>
        ))}
      </div>

      {prof.error ? (
        <ErrorView error={prof.error} />
      ) : prof.loading || !d || !model ? (
        <Skeleton h={520} />
      ) : (
        <>
          {/* why you're here */}
          <div className="dp-ribbon">
            <span className="why">Why you're here</span>
            <span className="dp-cat" data-c={catFromSector(model.props.gics_sector)}>{model.props.gics_sector || "—"}</span>
            <span className="reason">
              {d.entity.name} sits in {model.props.gics_sector || "an unclassified sector"}
              {model.props.market_tier ? ` (${model.props.market_tier})` : ""} — referenced in {model.refs} peer
              filing{model.refs === 1 ? "" : "s"} and holds {model.subs} disclosed subsidiar
              {model.subs === 1 ? "y" : "ies"}.
            </span>
          </div>

          <div className="atl-body">
            {/* DOSSIER */}
            <aside className="atl-dossier">
              <div className="atl-id">
                <div className="atl-id-glyph">◧</div>
                <div style={{ minWidth: 0 }}>
                  <h1 className="atl-id-name">{d.entity.name}</h1>
                  <div className="mono muted small" style={{ marginTop: 4 }}>
                    ENT·{model.props.cik || d.entity.key} · {model.props.gics_sub_industry || model.props.gics_sector || "—"}
                  </div>
                </div>
              </div>
              {model.props.industry ? <p className="atl-biz">{model.props.industry}</p> : null}

              <div className="atl-facts">
                <span className="atl-facts-l">Sector</span>
                <span className="atl-facts-v">
                  {model.props.gics_sector || "—"}{" "}
                  {model.props.gics_code ? <span className="mono muted small">GICS {model.props.gics_code}</span> : null}
                </span>
                <span className="atl-facts-l">Market tier</span>
                <span className="atl-facts-v">{model.props.market_tier || "—"}</span>
                <span className="atl-facts-l">Subsidiaries</span>
                <span className="atl-facts-v">{model.subs} <span className="mono muted small">EX-21</span></span>
                <span className="atl-facts-l">Filings</span>
                <span className="atl-facts-v">{model.filings}</span>
              </div>

              <div className="dp-section">
                <div className="dp-section-head">
                  <span className="kicker">Insiders &amp; board</span>
                  <span className="src-link"><span className="arrow">↳</span> Form 4 · DEF 14A</span>
                </div>
                {model.people.length === 0 ? (
                  <div className="muted small">No insider or board records in the graph.</div>
                ) : (
                  <div className="stack">
                    {model.people.slice(0, 8).map((p) => (
                      <button
                        key={p.other.key}
                        className={`atl-person${sel?.kind === "person" && sel.rel.other.key === p.other.key ? " active" : ""}`}
                        onClick={() => setSel({ kind: "person", rel: p })}
                      >
                        <span className="atl-person-av">{initials(p.other.name)}</span>
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div className="atl-person-nm">{p.other.name}</div>
                          <div className="mono muted small">{p.detail || relationVerb(p.relation)}</div>
                        </div>
                      </button>
                    ))}
                    {model.people.length > 8 ? <div className="mono muted small">+{model.people.length - 8} more</div> : null}
                  </div>
                )}
              </div>
            </aside>

            {/* MAIN */}
            <section className="atl-main">
              <AtlasAsk key={focal.key} slug={focal.key} name={d.entity.name} />

              <StakeholderMap
                focalName={d.entity.name}
                people={model.people}
                lanes={model.lanes}
                onTravel={travel}
                onSelectRel={(rel, kind) => setSel({ kind, rel })}
                selKey={sel?.rel.other.key ?? null}
              />

              <div className="atl-lower">
                <div className="atl-rels">
                  <div className="kicker" style={{ marginBottom: 10 }}>
                    Relationships · {model.people.length + model.lanes.reduce((a, l) => a + l.items.length, 0)}
                  </div>
                  <div className="stack gap">
                    <RelGroup
                      label="Insiders & board"
                      color={TIER_COLOR.people}
                      count={model.people.length}
                      items={model.people.map((r) => ({ rel: r, travel: false }))}
                      selKey={sel?.rel.other.key ?? null}
                      onSelect={(rel) => setSel({ kind: "person", rel })}
                    />
                    {model.lanes.map((lane) => (
                      <RelGroup
                        key={lane.key}
                        label={lane.label}
                        color={TIER_COLOR[lane.key] || "var(--text-faint)"}
                        count={lane.items.length}
                        items={lane.items.map((it) => ({ rel: it.rel, travel: lane.travel }))}
                        selKey={sel?.rel.other.key ?? null}
                        onSelect={(rel) => setSel({ kind: "rel", rel })}
                        onTravel={lane.travel ? (rel) => travel(rel.other.key, rel.other.name) : undefined}
                      />
                    ))}
                  </div>
                </div>

                <aside className="atl-evidence">
                  <EvidencePane sel={sel} focalName={d.entity.name} onTravel={travel} />
                </aside>
              </div>
            </section>
          </div>
        </>
      )}
    </div>
  );
}

/* ---- stakeholder map ------------------------------------------------------ */
function StakeholderMap({
  focalName,
  people,
  lanes,
  onTravel,
  onSelectRel,
  selKey,
}: {
  focalName: string;
  people: Relationship[];
  lanes: Lane[];
  onTravel: (key: string, name: string) => void;
  onSelectRel: (rel: Relationship, kind: "person" | "rel") => void;
  selKey: string | null;
}) {
  const VW = 940;
  const VH = 360;
  const FX = 250;
  const FY = 180;
  const pX = (x: number) => `${(x / VW) * 100}%`;
  const pY = (y: number) => `${(y / VH) * 100}%`;
  const halo = "0 0 3px var(--bg),0 0 4px var(--bg)";

  const edges: { d: string; color: string; dash?: string; op: number }[] = [];
  const nodes: React.ReactNode[] = [];

  // people left
  const pep = people.slice(0, 4);
  const pys = pep.length === 1 ? [FY] : pep.length === 2 ? [FY - 55, FY + 55] : pep.length === 3 ? [FY - 78, FY, FY + 78] : [90, 160, 240, 300];
  pep.forEach((p, i) => {
    const x = 92;
    const y = pys[i];
    edges.push({ d: `M ${FX} ${FY} C ${FX - 70} ${FY}, ${x + 70} ${y}, ${x} ${y}`, color: TIER_COLOR.people, op: 0.5 });
    const on = selKey === p.other.key;
    nodes.push(
      <button
        key={`p-${p.other.key}`}
        className="atl-node"
        style={{ left: pX(x), top: pY(y), opacity: 1 }}
        onClick={() => onSelectRel(p, "person")}
      >
        <span className="atl-node-c" style={{ borderColor: TIER_COLOR.people, color: TIER_COLOR.people, boxShadow: on ? `0 0 0 4px var(--accent-soft)` : "none" }}>
          {initials(p.other.name)}
        </span>
        <span className="atl-node-nm" style={{ textShadow: halo }}>{p.other.name}</span>
        <span className="atl-node-sub" style={{ textShadow: halo }}>{shortRole(p.detail)}</span>
      </button>,
    );
  });

  // lanes right
  const M = lanes.length;
  const laneXs = [470, 620, 758];
  lanes.forEach((lane, li) => {
    const ly = M <= 1 ? FY : 46 + li * ((316 - 46) / (M - 1));
    const color = TIER_COLOR[lane.key] || "var(--text-faint)";
    nodes.push(
      <div key={`lh-${lane.key}`} className="atl-lane-h" style={{ top: pY(ly), color }}>
        {lane.label}
      </div>,
    );
    lane.items.slice(0, 3).forEach((it, ci) => {
      const nx = laneXs[ci];
      const ny = ly;
      edges.push({
        d: `M ${FX} ${FY} C ${FX + 120} ${FY}, ${nx - 150} ${ny}, ${nx - 22} ${ny}`,
        color,
        dash: lane.key === "references" ? "5 5" : undefined,
        op: 0.55,
      });
      const on = selKey === it.key;
      nodes.push(
        <button
          key={`n-${lane.key}-${it.key}`}
          className="atl-node"
          style={{ left: pX(nx), top: pY(ny), cursor: lane.travel ? "pointer" : "default" }}
          onClick={() => (lane.travel ? onTravel(it.key, it.name) : onSelectRel(it.rel, "rel"))}
        >
          <span className="atl-node-c" style={{ borderColor: color, color, boxShadow: on ? `0 0 0 4px var(--accent-soft)` : "none" }}>
            {kindGlyph(it.kind)}
          </span>
          <span className="atl-node-nm" style={{ textShadow: halo }}>{trim(it.name)}</span>
          <span className="atl-node-sub" style={{ textShadow: halo }}>{it.kind}</span>
        </button>,
      );
    });
    if (lane.items.length > 3) {
      nodes.push(
        <div key={`more-${lane.key}`} className="atl-lane-more" style={{ left: pX(laneXs[2] + 40), top: pY(ly) }}>
          +{lane.items.length - 3}
        </div>,
      );
    }
  });

  return (
    <div className="atl-map">
      <div className="atl-map-head">
        <span className="kicker">Relationship map</span>
      </div>
      <div className="atl-map-legend mono">◧ company · ◍ person · ⌂ subsidiary · ❖ sector</div>
      <svg viewBox={`0 0 ${VW} ${VH}`} preserveAspectRatio="none" className="atl-map-svg">
        {edges.map((e, i) => (
          <path key={i} d={e.d} fill="none" stroke={e.color} strokeWidth={1.6} strokeDasharray={e.dash} opacity={e.op} />
        ))}
      </svg>
      <div className="atl-map-nodes">
        <button className="atl-node" style={{ left: `${(FX / VW) * 100}%`, top: `${(FY / VH) * 100}%`, cursor: "default" }}>
          <span className="atl-node-c focal">◧</span>
          <span className="atl-node-nm" style={{ textShadow: halo, fontSize: 13 }}>{trim(focalName)}</span>
          <span className="atl-node-sub" style={{ textShadow: halo }}>Focal</span>
        </button>
        {nodes}
      </div>
    </div>
  );
}

function RelGroup({
  label,
  color,
  count,
  items,
  selKey,
  onSelect,
  onTravel,
}: {
  label: string;
  color: string;
  count: number;
  items: { rel: Relationship; travel: boolean }[];
  selKey: string | null;
  onSelect: (rel: Relationship) => void;
  onTravel?: (rel: Relationship) => void;
}) {
  if (count === 0) return null;
  return (
    <div>
      <div className="atl-relgroup-head">
        <span className="atl-reldot" style={{ background: color }} />
        <span className="atl-relgroup-l">{label}</span>
        <span className="mono muted small">{count}</span>
      </div>
      <div className="stack">
        {items.slice(0, 6).map(({ rel, travel }, i) => {
          const on = selKey === rel.other.key;
          return (
            <div
              key={`${rel.other.key}-${i}`}
              className={`atl-relrow${on ? " active" : ""}`}
              onClick={() => onSelect(rel)}
            >
              <span className="atl-relrow-nm">{rel.other.name}</span>
              <span className="mono muted small">{kindLabel(rel.other.kind)}</span>
              {travel ? (
                <button
                  className="atl-relrow-go mono"
                  onClick={(e) => {
                    e.stopPropagation();
                    onTravel?.(rel);
                  }}
                  title="Travel"
                >
                  ›
                </button>
              ) : (
                <span className="atl-relrow-go" />
              )}
            </div>
          );
        })}
        {count > 6 ? <div className="mono muted small" style={{ padding: "2px 10px" }}>+{count - 6} more</div> : null}
      </div>
    </div>
  );
}

function EvidencePane({ sel, focalName, onTravel }: { sel: Sel; focalName: string; onTravel: (k: string, n: string) => void }) {
  if (!sel) {
    return (
      <>
        <div className="atl-ev-head"><span className="atl-ev-kick">Evidence</span> <span className="muted small">Select a relationship</span></div>
        <div className="muted small">Pick a relationship — on the map or in the list — to trace it to the disclosure it rests on.</div>
        <div className="atl-ev-foot mono">Every edge carries its source. Co-mention is orientation (network proximity), never a filed ownership relationship.</div>
      </>
    );
  }
  const r = sel.rel;
  const verb = relationVerb(r.relation);
  const travelable = r.other.kind === "Company";
  return (
    <>
      <div className="atl-ev-head"><span className="atl-ev-kick">Evidence</span> <span className="muted small">{r.other.name}</span></div>
      <div className="atl-ev-text">
        {focalName} <strong>{verb}</strong> {r.other.name}
        {r.detail ? ` — ${r.detail}` : "."}
      </div>
      {r.source ? <div className="src-link" style={{ marginTop: 12 }}><span className="arrow">↳</span> {r.source}</div> : null}
      {travelable ? (
        <button className="btn" style={{ marginTop: "auto" }} onClick={() => onTravel(r.other.key, r.other.name)}>
          Travel to {r.other.name} →
        </button>
      ) : null}
    </>
  );
}

/* ---- grounded ask bar ----------------------------------------------------- */
const ASK_EX = ["What are the key risks?", "What changed recently?", "What are the opportunities?"];
function AtlasAsk({ slug, name }: { slug: string; name: string }) {
  const { email } = useAuth();
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(false);
  const [report, setReport] = useState<AnalysisReport | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const run = async (question: string) => {
    const query = question.trim();
    if (!query || loading) return;
    setLoading(true);
    setErr(null);
    try {
      setReport(await api.analyst(slug, query));
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };
  // The grounded analyst is an authenticated capability (LLM-backed). Anonymous
  // public visitors browse the map + evidence; the Ask bar appears once signed in.
  if (!email) return null;
  return (
    <div className="atl-ask">
      <div className="atl-ask-bar">
        <span style={{ color: "var(--accent)", fontSize: 15 }}>✦</span>
        <input
          className="atl-ask-input"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") run(q); }}
          placeholder={`Ask what's next — e.g. key risks at ${name}`}
        />
        <button className="btn" onClick={() => run(q)} disabled={loading}>{loading ? "…" : "Ask"}</button>
      </div>
      {!report && !loading && !err ? (
        <div className="atl-ask-ex">
          <span className="mono muted small">try</span>
          {ASK_EX.map((ex) => (
            <button key={ex} className="chip" onClick={() => { setQ(ex); run(ex); }}>{ex}</button>
          ))}
        </div>
      ) : null}
      {loading ? <div style={{ marginTop: 9 }}><Loading label="Coruscant is reading the evidence" /></div> : null}
      {err ? <div className="rail-expand-note" style={{ color: "var(--danger)", marginTop: 9 }}>Could not reach the analyst: {err}</div> : null}
      {report ? (
        <div className="atl-ask-card">
          <div className="atl-ask-headline">{report.headline}</div>
          {report.concerns.slice(0, 3).map((c, i) => (
            <div className="atl-ask-concern" key={i}>
              <span className="atl-ask-sev" data-sev={c.severity}>{c.severity}</span>
              <span className="atl-ask-ct">{c.title}</span>
              {c.evidence[0]?.source_uri ? (
                <a className="src-link" href={c.evidence[0].source_uri} target="_blank" rel="noreferrer">
                  <span className="arrow">↳</span> src
                </a>
              ) : null}
            </div>
          ))}
          <div className="mono muted small">{report.generator}</div>
        </div>
      ) : null}
    </div>
  );
}

/* ---- helpers -------------------------------------------------------------- */
function initials(n: string): string {
  const p = n.replace(/^[A-Z]\.\s*/, "").split(/\s+/);
  return ((n[0] || "") + ((p[p.length - 1] || " ")[0] || "")).toUpperCase();
}
function shortRole(detail: string | null | undefined): string {
  if (!detail) return "Insider";
  return detail.split("·")[0].trim().slice(0, 18);
}
function trim(s: string): string {
  return s.length > 22 ? s.slice(0, 20) + "…" : s;
}
function kindLabel(k: string): string {
  return k === "Company" ? "Company" : k === "Subsidiary" ? "Subsidiary" : k === "Industry" ? "Sector" : k === "MarketTier" ? "Market tier" : k;
}
function catFromSector(sector: string | undefined): string {
  const s = (sector || "").toLowerCase();
  if (s.includes("financ")) return "gov";
  if (s.includes("stapl") || s.includes("discretion")) return "part";
  if (s.includes("industr") || s.includes("material") || s.includes("energy")) return "supply";
  return "gov";
}
