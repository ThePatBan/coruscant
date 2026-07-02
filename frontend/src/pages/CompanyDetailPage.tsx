import { useMemo } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { docTypeLabel, Empty, ErrorView, PanelHead, RelationGroups, Skeleton } from "../components";
import { GraphIncompleteNote, RelationMap, useRelGraph } from "../graph";
import { useAsync } from "../hooks";
import { isEntityRelation } from "../relations";
import { buildCommits, ProgressLog } from "../progress";
import { AnalystPanel, SignalsPanel } from "./CompanyIntel";

interface ControlSignal {
  name: string;
  kind: "leader" | "supplier";
  others: Array<{ key: string; name: string }>;
}

// Ownership vocabulary → evidence-first labels. Declared shareholding, beneficial
// ownership, and accounting consolidation are kept visibly distinct — never merged.
const RELATION_LABEL: Record<string, string> = {
  owns: "declared shareholding",
  beneficial_owner_of: "beneficial owner",
  consolidates: "consolidation",
};
// Chain terminal → (label, chip class). resolved terminals read as settled; the
// rest are honest incompletenesses the user should see, not hidden.
const TERMINAL_META: Record<string, { label: string; cls: string }> = {
  beneficial_owner: { label: "beneficial owner", cls: "active" },
  root: { label: "declared root", cls: "active" },
  unresolved: { label: "unresolved", cls: "" },
  cycle: { label: "circular holding", cls: "" },
  max_depth: { label: "depth-limited", cls: "" },
  restricted: { label: "restricted", cls: "" },
};

function magnitude(pct: number | null, band: string | null): string | null {
  if (pct != null) return `${pct}%`;
  if (band) return band; // a disclosed range, never coerced to a point
  return null;
}

function OwnershipPanel({ slug }: { slug: string }) {
  const owners = useAsync(() => api.companyOwners(slug), [slug]);
  const chains = useAsync(() => api.ownershipChain(slug), [slug]);
  const group = useAsync(() => api.contagion(slug), [slug]);
  const loading = owners.loading || chains.loading || group.loading;

  const ownerRows = owners.data?.owners ?? [];
  const ownerRestricted = owners.data?.restricted ?? 0;
  const chainList = chains.data?.chains ?? [];
  const inherited = group.data?.inherited ?? [];
  const groupRestricted = group.data?.restricted ?? 0;

  const hasOwners = ownerRows.length > 0 || ownerRestricted > 0;
  const hasChains = chainList.length > 0;
  const hasGroup = inherited.length > 0 || groupRestricted > 0;
  // No ownership data for this company → render nothing (surface only where it helps).
  if (!loading && !hasOwners && !hasChains && !hasGroup) return null;

  return (
    <section className="stack gap">
      <PanelHead
        idx="◆"
        kicker="Ownership & control"
        title="Who owns and controls this company"
        sub="Declared shareholdings, beneficial owners, and accounting consolidation — three distinct claims, never merged. Unresolved and access-restricted items stay explicitly labelled."
      />
      {loading ? (
        <Skeleton h={160} />
      ) : (
        <div className="card stack gap-sm">
          <div className="small">
            <strong>{owners.data?.provider ?? "ownership"}</strong>
            {owners.data?.market ? <span className="muted"> · market {owners.data.market}</span> : null}
            {owners.data ? <span className="muted"> · {owners.data.connected ? "connected" : "not connected"}</span> : null}
          </div>
          {/* Declared owners / beneficial owners / consolidation */}
          {hasOwners ? (
            <div className="stack gap-sm">
              <div className="ci-section-label">
                Owners <span className="muted">· incoming ownership statements</span>
              </div>
              <ul className="ci-list">
                {ownerRows.map((o, i) => {
                  const mag = magnitude(o.percentage, o.percentage_band);
                  return (
                    <li key={`${o.holder_key}-${o.relation}-${i}`}>
                      <strong>{o.holder_name ?? o.holder_key}</strong>{" "}
                      <span className={`chip ${o.relation === "beneficial_owner_of" ? "active" : ""}`}>
                        {RELATION_LABEL[o.relation] ?? o.relation}
                      </span>{" "}
                      {mag ? <span className="pill">{mag}</span> : null}{" "}
                      {o.interest ? <span className="muted small">{o.interest}</span> : null}{" "}
                      <span className={`chip ${o.holder_resolved ? "active" : ""}`}>
                        {o.holder_resolved ? "resolved" : "unresolved"}
                      </span>
                      {o.source_url ? (
                        <>
                          {" · "}
                          <a href={o.source_url} target="_blank" rel="noreferrer">
                            {o.source ?? "source"}
                          </a>
                        </>
                      ) : o.source ? (
                        <span className="muted small"> · {o.source}</span>
                      ) : null}
                    </li>
                  );
                })}
              </ul>
              {ownerRestricted > 0 ? (
                <div className="muted small">
                  {ownerRestricted} owner{ownerRestricted === 1 ? "" : "s"} withheld at this access
                  tier — their existence is shown, their identity is not (e.g. an EU beneficial owner).
                </div>
              ) : null}
              {owners.data?.observed_at ? (
                <div className="muted small">Last ownership run: {owners.data.observed_at}</div>
              ) : null}
            </div>
          ) : null}

          {/* UBO chain-following */}
          {hasChains ? (
            <div className="stack gap-sm">
              <div className="ci-section-label">
                Ownership chains{" "}
                <span className="muted">
                  · {chains.data?.resolved_chains ?? 0} resolved · {chains.data?.partial_chains ?? 0} partial
                  {(chains.data?.cyclic_chains ?? 0) > 0 ? ` · ${chains.data?.cyclic_chains} circular` : ""}
                </span>
              </div>
              {chainList.slice(0, 8).map((c, i) => {
                const meta = TERMINAL_META[c.terminal] ?? { label: c.terminal, cls: "" };
                return (
                  <div className="ctrl-row" key={i} style={{ padding: "6px 0", flexWrap: "wrap" }}>
                    <span className="relchip tier-proxy">{chains.data?.company.name ?? slug}</span>
                    {c.links.map((l, j) => (
                      <span key={j}>
                        <span className="ctrl-arrow">
                          {" "}
                          {RELATION_LABEL[l.relation] ?? l.relation}
                          {magnitude(l.percentage, l.percentage_band) ? ` ${magnitude(l.percentage, l.percentage_band)}` : ""}
                          {" ← "}
                        </span>
                        <span className={`relchip ${l.holder_resolved === false ? "" : "tier-supply"}`}>
                          {l.holder.name}
                        </span>
                      </span>
                    ))}{" "}
                    <span className={`chip ${meta.cls}`}>{meta.label}</span>
                  </div>
                );
              })}
              <div className="ctrl-note">
                <span className="inf">evidence</span>
                {chains.data?.note}
              </div>
            </div>
          ) : null}

          {/* Group / UBO contagion — a distinct, inherited-exposure path */}
          {hasGroup ? (
            <div className="stack gap-sm">
              <div className="ci-section-label">
                Group exposure <span className="muted">· inherited through shared control, not a holding</span>
              </div>
              <ul className="ci-list">
                {inherited.slice(0, 12).map((m, i) => (
                  <li key={`${m.company.key}-${i}`}>
                    <Link to={`/companies/${m.company.key}`}>{m.company.name}</Link>{" "}
                    <span className="chip">{m.link}</span>{" "}
                    <span className="muted small">
                      {m.hops} hop{m.hops === 1 ? "" : "s"}
                      {m.shared_owner ? ` · via ${m.shared_owner.name}` : ""}
                    </span>
                  </li>
                ))}
              </ul>
              {groupRestricted > 0 ? (
                <div className="muted small">
                  {groupRestricted} group tie{groupRestricted === 1 ? "" : "s"} withheld at this access
                  tier — a beneficial-owner link exists but is not shown to unprivileged callers.
                </div>
              ) : null}
            </div>
          ) : null}
        </div>
      )}
    </section>
  );
}

export function CompanyDetailPage() {
  const { slug = "" } = useParams();
  const { email } = useAuth();
  const g = useRelGraph();
  const detail = useAsync(async () => {
    const [documents, timeline, changes] = await Promise.all([
      api.documents({ company: slug }),
      api.companyTimeline(slug),
      api.companyChanges(slug),
    ]);
    return { documents, timeline, changes };
  }, [slug]);

  const company = g.data?.companies.find((c) => c.slug === slug) ?? null;
  const profile = g.data?.profiles.get(slug) ?? null;
  const nameFor = (s: string) => g.data?.companies.find((c) => c.slug === s)?.name ?? s;

  const controlSignals = useMemo<ControlSignal[]>(() => {
    if (!g.data) return [];
    const cid = `Company:${slug}`;
    const { nodes, edges } = g.data.graph;
    const byId = new Map(nodes.map((n) => [n.id, n]));

    // Other tracked companies that share a *specific* relation with `id`.
    const sharedVia = (id: string, relation: string): Array<{ key: string; name: string }> => {
      const others = new Set<string>();
      for (const e of edges) {
        if (e.relation !== relation || (e.source !== id && e.target !== id)) continue;
        const co = byId.get(e.source === id ? e.target : e.source);
        if (co?.tracked && co.key !== slug) others.add(co.key);
      }
      return [...others].map((key) => ({ key, name: nameFor(key) }));
    };

    const signals: ControlSignal[] = [];
    // Leaders: people who *currently* lead this company (employs edge) AND another.
    const leadersHere = edges
      .filter((e) => e.relation === "employs" && (e.source === cid || e.target === cid))
      .map((e) => (e.source === cid ? e.target : e.source));
    for (const pid of new Set(leadersHere)) {
      const person = byId.get(pid);
      if (person?.kind !== "Person") continue;
      const others = sharedVia(pid, "employs");
      if (others.length) signals.push({ name: person.name, kind: "leader", others });
    }
    // Shared suppliers: a supplier of this company also relied on by another.
    const suppliersHere = edges
      .filter((e) => e.relation === "relies_on_supplier" && (e.source === cid || e.target === cid))
      .map((e) => (e.source === cid ? e.target : e.source));
    for (const sid of new Set(suppliersHere)) {
      const supplier = byId.get(sid);
      if (!supplier) continue;
      const others = sharedVia(sid, "relies_on_supplier");
      if (others.length) signals.push({ name: supplier.name, kind: "supplier", others });
    }
    return signals;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [g.data, slug]);

  const commits = useMemo(() => {
    if (!detail.data) return [];
    const dateMap = new Map<string, string | null>();
    for (const d of detail.data.documents) dateMap.set(d.canonical_id, d.published_at);
    for (const e of detail.data.timeline) if (e.occurred_at && !dateMap.has(e.canonical_id)) dateMap.set(e.canonical_id, e.occurred_at);
    return buildCommits(
      detail.data.changes,
      detail.data.timeline,
      nameFor,
      (id) => (id ? dateMap.get(id) ?? null : null),
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [detail.data, g.data]);

  const error = g.error ?? detail.error;
  const loading = g.loading || detail.loading;
  const relationships = profile?.relationships.filter((r) => isEntityRelation(r.relation)) ?? [];
  const materialCount = detail.data?.changes.filter((c) => c.material).length ?? 0;

  return (
    <div className="stack gap-lg">
      <div>
        <Link to="/companies" className="back-link">
          ← Companies
        </Link>
        {error ? <ErrorView error={error} /> : null}
        {!error && loading ? <Skeleton h={48} w={320} /> : null}
        {!loading && !error ? (
          <div className="page-head" style={{ marginBottom: 0 }}>
            <div className="wrap" style={{ marginBottom: 8 }}>
              <h1>{company?.name ?? slug}</h1>
              {company?.industry ? <span className="pill accent">{company.industry}</span> : null}
              {company?.country ? <span className="pill">{company.country}</span> : null}
            </div>
            <div className="mono faint">{slug}</div>
          </div>
        ) : null}
      </div>

      {!error ? (
        <>
          {/* The analyst & signals panels call authenticated endpoints (POST /analyst,
              GET /signals). On the public profile an anonymous visitor would only see a
              stuck "Loading signals" spinner and an Analyze button that 401s, so gate
              them on a session — the rest of the profile is fully public. */}
          {email ? (
            <>
              <AnalystPanel key={slug} slug={slug} name={company?.name ?? slug} />
              <SignalsPanel slug={slug} />
            </>
          ) : null}

          {/* Relationship neighbourhood + control proxies */}
          <section className="stack gap">
            <PanelHead
              idx="01"
              kicker="Relationship neighbourhood"
              title="Who this company is connected to"
              sub="Its direct ties — leadership, suppliers, rivals, partners, products. Click another company to pivot."
              right={
                <Link to="/graph" className="pill accent">
                  Full graph →
                </Link>
              }
            />
            {g.loading ? (
              <Skeleton h={400} />
            ) : profile ? (
              <RelationMap graph={g.data!.graph} mode="ego" focusKey={slug} ariaLabel={`Relationship map centred on ${company?.name ?? slug}`} />
            ) : (
              <Empty icon="◬" title="No relationships recorded" />
            )}
            {g.data ? <GraphIncompleteNote failed={g.data.failed} /> : null}

            {controlSignals.length > 0 ? (
              <div className="card stack gap-sm">
                <div className="kicker" style={{ color: "var(--evidence)" }}>
                  <span className="idx">⚐</span> Control &amp; influence — inferred
                </div>
                {controlSignals.map((s, i) => (
                  <div className="ctrl-row" key={i} style={{ padding: "9px 0" }}>
                    <span className={`ctrl-actor ${s.kind === "leader" ? "tier-proxy" : "tier-supply"}`}>
                      <span className="glyph">{s.kind === "leader" ? "◍" : "◧"}</span>
                      <span className="nm">{s.name}</span>
                    </span>
                    <span className="ctrl-arrow">
                      {s.kind === "leader" ? "also leads →" : "also supplies →"}
                    </span>
                    <div className="ctrl-targets">
                      {s.others.map((o) => (
                        <Link className="relchip tier-proxy" to={`/companies/${o.key}`} key={o.key}>
                          {o.name}
                        </Link>
                      ))}
                    </div>
                  </div>
                ))}
                <div className="ctrl-note">
                  <span className="inf">inferred</span>
                  A control or exposure proxy from leadership and supplier overlap in the curated entity graph,
                  not a declared ownership relationship. Open a company to review its source disclosures.
                </div>
              </div>
            ) : null}

            {relationships.length > 0 ? (
              <div className="card">
                <RelationGroups relationships={relationships} trackedKeys={g.data?.trackedKeys} />
              </div>
            ) : null}
          </section>

          {/* Ownership & control — declared / beneficial / consolidation + UBO chains + contagion */}
          <OwnershipPanel slug={slug} />

          {/* Progression — git log */}
          <section className="stack gap">
            <PanelHead
              idx="02"
              kicker="Progression"
              title="How this company has changed"
              sub="Material disclosure diffs and extracted events in order. Each line keeps its evidence."
              right={<span className="pill">{materialCount} material changes</span>}
            />
            {detail.loading ? (
              <Skeleton h={260} />
            ) : commits.length === 0 ? (
              <Empty icon="⎇" title="No progression recorded yet" hint="Change detection runs across periodic disclosures." />
            ) : (
              <ProgressLog commits={commits} limit={40} />
            )}
          </section>

          {/* Source documents */}
          <section className="stack gap">
            <PanelHead idx="03" kicker="Evidence" title="Source documents" right={<span className="pill">{detail.data?.documents.length ?? 0}</span>} />
            {detail.loading ? (
              <Skeleton h={120} />
            ) : !detail.data || detail.data.documents.length === 0 ? (
              <Empty title="No documents" />
            ) : (
              <div className="list">
                {detail.data.documents.map((d) => (
                  <Link to={`/documents/${d.canonical_id}`} className="li" key={d.canonical_id}>
                    <div className="grow">
                      <div className="truncate" style={{ fontWeight: 560 }}>
                        {d.title ?? "Untitled"}
                      </div>
                      <div className="faint" style={{ fontSize: 12.5 }}>{d.published_at ?? "—"}</div>
                    </div>
                    <span className="badge">{docTypeLabel(d.document_type)}</span>
                  </Link>
                ))}
              </div>
            )}
          </section>
        </>
      ) : null}
    </div>
  );
}
