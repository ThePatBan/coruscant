import { Link, useParams } from "react-router-dom";
import { type AISummary, api, type Claim } from "../api";
import { Cat, docTypeLabel, ErrorView, Loading } from "../components";
import { useAsync } from "../hooks";

function str(value: unknown): string {
  return value == null ? "" : String(value);
}

const HIDDEN_META = new Set(["company_slug", "source_name", "title", "headline"]);

function ClaimList({ title, claims }: { title: string; claims: Claim[] }) {
  if (claims.length === 0) return null;
  return (
    <div className="stack gap-sm">
      <h3>{title}</h3>
      {claims.map((c, i) => (
        <div className="evidence" key={i}>
          <div className="excerpt">{c.text}</div>
          <div className="src">
            {c.category ? <Cat category={c.category} /> : null}
            {c.section_title ? <span className="pill">§ {c.section_title}</span> : null}
          </div>
        </div>
      ))}
    </div>
  );
}

function SummaryPanel({ summary }: { summary: AISummary }) {
  return (
    <div className="card stack gap">
      <div className="row-between">
        <h2>AI summary</h2>
        <span className="pill accent">cited · extractive</span>
      </div>
      <div className="answer">
        <div className="answer-label">Overview</div>
        <div>{summary.overview}</div>
      </div>
      <ClaimList title="Key points" claims={summary.key_points} />
      <div className="grid cols-2">
        <ClaimList title="Risks" claims={summary.risks} />
        <ClaimList title="Opportunities" claims={summary.opportunities} />
        <ClaimList title="Financial highlights" claims={summary.financial_highlights} />
        <ClaimList title="Management commentary" claims={summary.management_commentary} />
      </div>
      <ClaimList title="Events" claims={summary.events} />
      <div className="faint" style={{ fontSize: 12 }}>
        Every line is lifted verbatim from this document — no paraphrasing, fully auditable.
      </div>
    </div>
  );
}

export function DocumentDetailPage() {
  const { id = "" } = useParams();
  const { data, error, loading } = useAsync(() => api.document(id), [id]);
  const summary = useAsync(() => api.documentSummary(id).catch(() => null), [id]);

  const metaEntries = data
    ? Object.entries(data.metadata).filter(([k, v]) => !HIDDEN_META.has(k) && v != null && v !== "")
    : [];

  return (
    <div className="stack gap-lg">
      <div>
        <Link to="/documents" className="back-link">
          ← Documents
        </Link>
        {loading ? <Loading label="Loading document" /> : null}
        {error ? <ErrorView error={error} /> : null}
      </div>

      {data ? (
        <>
          <div className="page-head">
            <div className="wrap" style={{ marginBottom: 10 }}>
              <h1>{data.title ?? "Untitled document"}</h1>
              <span className="badge">{docTypeLabel(data.document_type)}</span>
              {data.published_at ? <span className="pill">{data.published_at}</span> : null}
            </div>
            <a href={data.source_uri} className="mono faint" target="_blank" rel="noreferrer" title={data.source_uri}>
              {data.source_uri}
            </a>
          </div>

          {(metaEntries.length > 0 || data.entities.length > 0) && (
            <div className="card stack gap-sm">
              {data.entities.length > 0 ? (
                <div className="wrap">
                  {data.entities.map((e, i) => (
                    <span className="pill accent" key={i}>
                      {str(e["kind"])}: {str(e["name"] ?? e["key"])}
                    </span>
                  ))}
                </div>
              ) : null}
              {metaEntries.length > 0 ? (
                <div className="wrap">
                  {metaEntries.map(([k, v]) => (
                    <span className="pill" key={k}>
                      <span className="faint">{k.replace(/_/g, " ")}</span>&nbsp;{str(v)}
                    </span>
                  ))}
                </div>
              ) : null}
            </div>
          )}

          {summary.data ? <SummaryPanel summary={summary.data} /> : null}

          <div className="stack gap">
            <div className="row-between">
              <h2>Source document</h2>
              <span className="badge">{data.sections.length} sections</span>
            </div>
            {data.sections.map((s, i) => {
              const evidence = Array.isArray(s["evidence"])
                ? (s["evidence"] as Array<Record<string, unknown>>)
                : [];
              const sourceUri = str(evidence[0]?.["source_uri"] ?? data.source_uri);
              return (
                <div className="section-block" key={i}>
                  <div className="row-between">
                    <h3>{str(s["title"]) || `Section ${i + 1}`}</h3>
                    <span className="pill evidence">evidence ✓</span>
                  </div>
                  <div className="body">{str(s["content"])}</div>
                  <div className="src" style={{ marginTop: 10 }}>
                    <span className="mono faint truncate" title={sourceUri}>
                      ↳ {sourceUri}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </>
      ) : null}
    </div>
  );
}
