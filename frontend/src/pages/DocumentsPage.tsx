import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { docTypeLabel, Empty, ErrorView, Loading, sourceLabel } from "../components";
import { useAsync } from "../hooks";

export function DocumentsPage() {
  // Seed the source filter from the URL so per-source "View documents →" links
  // (SourcesPage) land pre-scoped; defaults to unfiltered when no param is present.
  const [params] = useSearchParams();
  const [company, setCompany] = useState("");
  const [sourceType, setSourceType] = useState(() => params.get("source_type") ?? "");

  const filters = useAsync(
    async () => {
      const [companies, sources] = await Promise.all([api.companies(), api.sources()]);
      return { companies, sources };
    },
    [],
  );

  const docs = useAsync(
    () => api.documents({ company: company || undefined, source_type: sourceType || undefined }),
    [company, sourceType],
  );

  return (
    <div className="stack gap-lg">
      <div className="page-head">
        <h1>Documents</h1>
        <p className="sub">
          Normalized, evidence-bearing documents across every source. Filter by company or source
          type, then open one to read its sections and provenance.
        </p>
      </div>

      <div className="wrap">
        <select
          className="input"
          value={company}
          onChange={(e) => setCompany(e.target.value)}
          aria-label="Filter by company"
        >
          <option value="">All companies</option>
          {filters.data?.companies.map((c) => (
            <option key={c.slug} value={c.slug}>
              {c.name}
            </option>
          ))}
        </select>
        <select
          className="input"
          value={sourceType}
          onChange={(e) => setSourceType(e.target.value)}
          aria-label="Filter by source type"
        >
          <option value="">All sources</option>
          {filters.data?.sources.map((s) => (
            <option key={s.source_type} value={s.source_type}>
              {s.label}
            </option>
          ))}
        </select>
        {docs.data ? <span className="pill">{docs.data.length} results</span> : null}
      </div>

      {docs.loading ? <Loading label="Loading documents" /> : null}
      {docs.error ? <ErrorView error={docs.error} /> : null}
      {docs.data && docs.data.length === 0 ? (
        <Empty title="No documents match these filters" />
      ) : null}

      {docs.data && docs.data.length > 0 ? (
        <div className="list">
          {docs.data.map((d) => (
            <Link to={`/documents/${d.canonical_id}`} className="li" key={d.canonical_id}>
              <div className="grow">
                <div className="truncate" style={{ fontWeight: 560 }}>
                  {d.title ?? "Untitled"}
                </div>
                <div className="mono faint truncate">{d.source_uri}</div>
              </div>
              {d.published_at ? <span className="faint">{d.published_at}</span> : null}
              <span className="badge">{docTypeLabel(d.document_type)}</span>
            </Link>
          ))}
        </div>
      ) : null}

      <div className="faint" style={{ fontSize: 12.5 }}>
        Tip: {sourceLabel("sec_edgar")} filings are split into form-aware sections; other sources
        use markdown-style section parsing.
      </div>
    </div>
  );
}
