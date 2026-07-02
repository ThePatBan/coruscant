import { Link } from "react-router-dom";
import { api } from "../api";
import { docTypeLabel, ErrorView, Loading } from "../components";
import { useAsync } from "../hooks";

const DESCRIPTIONS: Record<string, string> = {
  sec_edgar: "Regulatory filings (10-K, 10-Q, 8-K, DEF 14A) split into form-aware sections.",
  investor_relations: "Quarterly investor updates: highlights, financials, and guidance.",
  earnings_call: "Earnings call transcripts: prepared remarks, outlook, and Q&A.",
  press_release: "Company press releases announcing products and milestones.",
  job_postings: "Hiring signals that indicate investment in capacity and direction.",
  news: "News coverage and analysis in the broader sector context.",
  patents: "Patent metadata: abstracts and claims attributed to the company.",
};

export function SourcesPage() {
  const { data, error, loading } = useAsync(() => api.sources(), []);

  return (
    <div className="stack gap-lg">
      <div className="page-head">
        <h1>Sources</h1>
        <p className="sub">
          The seven in-scope source types. Each is registered with a connector and a normalizer;
          adding a new one is a registration, not a rewrite.
        </p>
      </div>

      {loading ? <Loading label="Loading sources" /> : null}
      {error ? <ErrorView error={error} /> : null}

      {data ? (
        <div className="grid cols-2">
          {data.map((s) => (
            <div className="card hover" key={s.source_type}>
              <div className="stack gap-sm">
                <div className="row-between">
                  <h2>{s.label}</h2>
                  <span className="badge">{docTypeLabel(s.document_type)}</span>
                </div>
                <p className="muted" style={{ fontSize: 14 }}>
                  {DESCRIPTIONS[s.source_type] ?? "Registered ingestion source."}
                </p>
                <div className="row-between">
                  <span className="mono faint">{s.source_type}</span>
                  <Link
                    to={`/documents?source_type=${encodeURIComponent(s.source_type)}`}
                    className="faint"
                    style={{ fontSize: 13 }}
                  >
                    View documents →
                  </Link>
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}
