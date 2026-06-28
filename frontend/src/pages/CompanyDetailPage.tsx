import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import { docTypeLabel, Empty, ErrorView, Loading, sourceLabel } from "../components";
import { useAsync } from "../hooks";

export function CompanyDetailPage() {
  const { slug = "" } = useParams();
  const { data, error, loading } = useAsync(
    async () => {
      const [companies, documents, graph] = await Promise.all([
        api.companies(),
        api.documents({ company: slug }),
        api.companyGraph(slug),
      ]);
      return { company: companies.find((c) => c.slug === slug) ?? null, documents, graph };
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
              {data.company?.industry ? (
                <span className="pill accent">{data.company.industry}</span>
              ) : null}
              {data.company?.country ? <span className="pill">{data.company.country}</span> : null}
            </div>
            <div className="mono faint">{slug}</div>
          </div>
        ) : null}
      </div>

      {data ? (
        <div className="grid cols-2">
          <div className="stack gap">
            <div className="row-between">
              <h2>Documents</h2>
              <span className="badge">{data.documents.length}</span>
            </div>
            {data.documents.length === 0 ? (
              <Empty title="No documents" hint="Run ingestion to populate this company." />
            ) : (
              <div className="list">
                {data.documents.map((d) => (
                  <Link to={`/documents/${d.canonical_id}`} className="li" key={d.canonical_id}>
                    <div className="grow">
                      <div className="truncate" style={{ fontWeight: 560 }}>
                        {d.title ?? "Untitled"}
                      </div>
                      <div className="mono faint truncate">{d.source_uri}</div>
                    </div>
                    <span className="badge">{docTypeLabel(d.document_type)}</span>
                  </Link>
                ))}
              </div>
            )}
          </div>

          <div className="stack gap">
            <div className="row-between">
              <h2>Knowledge graph</h2>
              <span className="badge">{data.graph.neighbors.length} edges</span>
            </div>
            {!data.graph.found || data.graph.neighbors.length === 0 ? (
              <Empty
                icon="◬"
                title="No graph relations"
                hint="The company node has no projected edges yet."
              />
            ) : (
              <div className="card stack gap-sm">
                <div className="mono faint" style={{ fontSize: 12 }}>
                  Company:{slug}
                </div>
                {data.graph.neighbors.map((n, i) => (
                  <div className="wrap" key={i} style={{ gap: 10 }}>
                    <span className="pill accent">{n.relation}</span>
                    <span className="faint">→</span>
                    <span className="badge">{n.target_kind}</span>
                    <span className="truncate" style={{ minWidth: 0 }}>
                      {n.title ?? n.target_key}
                    </span>
                  </div>
                ))}
              </div>
            )}
            <div className="faint" style={{ fontSize: 12.5 }}>
              Relations are projected during ingestion. Filings use{" "}
              <span className="mono">filed</span>; other sources use{" "}
              <span className="mono">published</span>.
            </div>
            <Link to={`/documents`} className="btn ghost" style={{ alignSelf: "start" }}>
              Browse all {sourceLabel("sec_edgar")} & more →
            </Link>
          </div>
        </div>
      ) : null}
    </div>
  );
}
