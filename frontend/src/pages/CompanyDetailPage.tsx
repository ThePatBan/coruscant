import { Link, useParams } from "react-router-dom";
import { api, type ChangeSet } from "../api";
import { Cat, docTypeLabel, Empty, ErrorView, Loading, sourceLabel } from "../components";
import { useAsync } from "../hooks";
import { AnalystPanel, SignalsPanel } from "./CompanyIntel";

function ChangePanel({ changeSet }: { changeSet: ChangeSet }) {
  if (!changeSet.material) return null;
  return (
    <div className="card stack gap-sm">
      <div className="row-between">
        <div className="wrap" style={{ gap: 8 }}>
          <span className="badge">{sourceLabel(changeSet.source_type)}</span>
          <span className="pill" style={{ color: "var(--good)" }}>
            +{changeSet.added_count} added
          </span>
          <span className="pill" style={{ color: "var(--danger)" }}>
            −{changeSet.removed_count} removed
          </span>
        </div>
        {changeSet.current_title ? (
          <Link to={`/documents/${changeSet.current_canonical_id}`} className="faint" style={{ fontSize: 12.5 }}>
            current →
          </Link>
        ) : null}
      </div>
      <div>
        {changeSet.changes.map((c, i) => (
          <div className={`change-row ${c.kind}`} key={`${c.kind}-${c.statement}-${i}`}>
            <span className="change-mark">{c.kind === "added" ? "+" : "−"}</span>
            <div className="grow">
              <div className="wrap" style={{ gap: 8, marginBottom: 3 }}>
                <Cat category={c.category} />
                <span className="faint" style={{ fontSize: 11.5 }}>{c.kind}</span>
              </div>
              <div className="stmt">{c.statement}</div>
              <Link
                to={`/documents/${c.evidence.canonical_id}`}
                className="mono faint truncate"
                style={{ display: "block", marginTop: 4, fontSize: 11.5 }}
                title={c.evidence.source_uri}
              >
                ↳ {c.evidence.section_title ?? c.evidence.source_uri}
              </Link>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export function CompanyDetailPage() {
  const { slug = "" } = useParams();
  const { data, error, loading } = useAsync(
    async () => {
      const [companies, documents, timeline, changes, profile] = await Promise.all([
        api.companies(),
        api.documents({ company: slug }),
        api.companyTimeline(slug),
        api.companyChanges(slug),
        api.entity("Company", slug).catch(() => null),
      ]);
      return {
        company: companies.find((c) => c.slug === slug) ?? null,
        documents,
        timeline,
        changes: changes.filter((c) => c.material),
        relationships: profile?.relationships.filter((r) => r.relation !== "mentions") ?? [],
      };
    },
    [slug],
  );

  return (
    <div className="stack gap-lg">
      <div>
        <Link to="/companies" className="back-link">
          ← Companies
        </Link>
        {loading ? <Loading label="Loading company" /> : null}
        {error ? <ErrorView error={error} /> : null}
        {data ? (
          <div className="page-head">
            <div className="wrap" style={{ marginBottom: 8 }}>
              <h1>{data.company?.name ?? slug}</h1>
              {data.company?.industry ? <span className="pill accent">{data.company.industry}</span> : null}
              {data.company?.country ? <span className="pill">{data.company.country}</span> : null}
            </div>
            <div className="mono faint">{slug}</div>
          </div>
        ) : null}
      </div>

      {data ? (
        <>
          <AnalystPanel slug={slug} name={data.company?.name ?? slug} />
          <SignalsPanel slug={slug} />

          <div className="stack gap">
            <div className="row-between">
              <h2>What changed</h2>
              <span className="badge">{data.changes.length} disclosures with changes</span>
            </div>
            {data.changes.length === 0 ? (
              <Empty icon="⇄" title="No material changes detected" hint="Change detection runs across periodic disclosures." />
            ) : (
              data.changes.map((cs) => <ChangePanel changeSet={cs} key={cs.current_canonical_id} />)
            )}
          </div>

          {data.relationships.length > 0 ? (
            <div className="stack gap">
              <div className="row-between">
                <h2>Relationships</h2>
                <Link to="/graph" className="faint" style={{ fontSize: 13 }}>
                  Explore the graph →
                </Link>
              </div>
              <div className="card stack gap-sm">
                {data.relationships.map((r, i) => (
                  <div className="wrap" key={i} style={{ gap: 8 }}>
                    <span className="cat" data-c={r.relation}>{r.relation.replace(/_/g, " ")}</span>
                    <span className="faint">{r.direction === "out" ? "→" : "←"}</span>
                    <span className="badge">{r.other.kind}</span>
                    <span>{r.other.name}</span>
                  </div>
                ))}
              </div>
            </div>
          ) : null}

          <div className="grid cols-2">
            <div className="stack gap">
              <div className="row-between">
                <h2>Documents</h2>
                <span className="badge">{data.documents.length}</span>
              </div>
              {data.documents.length === 0 ? (
                <Empty title="No documents" />
              ) : (
                <div className="list">
                  {data.documents.map((d) => (
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
            </div>

            <div className="stack gap">
              <div className="row-between">
                <h2>Timeline</h2>
                <span className="badge">{data.timeline.length} events</span>
              </div>
              {data.timeline.length === 0 ? (
                <Empty title="No events" />
              ) : (
                <div className="card">
                  <div className="timeline">
                    {data.timeline.slice(0, 12).map((e, i) => (
                      <Link
                        to={`/documents/${e.canonical_id}`}
                        className="tl-item"
                        style={{ display: "block" }}
                        key={`${e.canonical_id}-${i}`}
                      >
                        <div className="wrap" style={{ gap: 8, marginBottom: 2 }}>
                          <Cat category={e.category} />
                          <span className="when">{e.occurred_at ?? "—"}</span>
                        </div>
                        <div style={{ fontSize: 13.5 }}>{e.title}</div>
                      </Link>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        </>
      ) : null}
    </div>
  );
}
