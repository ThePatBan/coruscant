import { type FormEvent, useState } from "react";
import { Link } from "react-router-dom";
import { type AnalysisReport, ApiError, api, type Signal } from "../api";
import { Cat, Loading } from "../components";
import { useAsync } from "../hooks";

function sevColor(severity: string): string {
  if (severity === "high") return "var(--danger)";
  if (severity === "medium") return "var(--evidence)";
  return "var(--text-faint)";
}

function sourceLink(uri: string, canonical: string | null) {
  if (canonical) {
    return (
      <Link to={`/documents/${canonical}`} className="mono faint" style={{ fontSize: 11.5 }}>
        ↳ source
      </Link>
    );
  }
  return <span className="mono faint" style={{ fontSize: 11.5 }}>↳ {uri}</span>;
}

export function AnalystPanel({ slug, name }: { slug: string; name: string }) {
  const [question, setQuestion] = useState(`Why should I worry about ${name} over the next six months?`);
  const [report, setReport] = useState<AnalysisReport | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      setReport(await api.analyst(slug, question));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Analysis failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card stack gap">
      <div>
        <h2>◎ AI Analyst</h2>
        <p className="faint" style={{ fontSize: 13 }}>
          Multi-step reasoning over what changed — not retrieval. Every conclusion is cited.
        </p>
      </div>
      <form onSubmit={run} className="searchbar" style={{ boxShadow: "none" }}>
        <input value={question} onChange={(e) => setQuestion(e.target.value)} aria-label="Question" />
        <button className="btn" type="submit" disabled={busy}>
          {busy ? <span className="spinner" style={{ width: 14, height: 14 }} /> : "Analyze"}
        </button>
      </form>
      {error ? <div className="errbox">{error}</div> : null}
      {report ? (
        <div className="stack gap">
          <div className="answer">
            <div className="answer-label">Assessment · {report.focus}</div>
            <div style={{ fontWeight: 560 }}>{report.headline}</div>
          </div>
          <div className="wrap" style={{ gap: 6 }}>
            {report.steps.map((s, i) => (
              <span className="pill" key={i} title={s.detail}>
                {i + 1}. {s.label}
              </span>
            ))}
          </div>
          {report.concerns.map((c, i) => (
            <div className="section-block" key={i}>
              <div className="row-between">
                <div className="wrap" style={{ gap: 8 }}>
                  <span style={{ fontWeight: 600 }}>{c.title}</span>
                  <Cat category={c.category} />
                </div>
                <span className="pill" style={{ color: sevColor(c.severity) }}>
                  {c.severity} · {(c.confidence * 100).toFixed(0)}% conf
                </span>
              </div>
              <div className="body" style={{ fontSize: 14 }}>{c.rationale}</div>
              {c.evidence[0] ? (
                <div style={{ marginTop: 8 }}>
                  {sourceLink(c.evidence[0].source_uri, c.evidence[0].canonical_id)}
                </div>
              ) : null}
            </div>
          ))}
          <div className="faint" style={{ fontSize: 12 }}>{report.disclaimer}</div>
        </div>
      ) : null}
    </div>
  );
}

export function SignalsPanel({ slug }: { slug: string }) {
  const { data } = useAsync(() => api.signals(slug), [slug]);
  if (!data) return <Loading label="Loading signals" />;
  if (data.length === 0) return null;
  return (
    <div className="stack gap">
      <div className="row-between">
        <h2>Predictive signals</h2>
        <span className="faint" style={{ fontSize: 12.5 }}>probabilistic · evidence-backed</span>
      </div>
      <div className="grid cols-2">
        {data.map((s: Signal, i) => (
          <div className="card stack gap-sm" key={i}>
            <div className="row-between">
              <span style={{ fontWeight: 560 }}>{s.label}</span>
              <span className="pill">{s.direction}</span>
            </div>
            <div style={{ height: 6, borderRadius: 999, background: "var(--bg-elev-2)", overflow: "hidden" }}>
              <div style={{ width: `${s.strength * 100}%`, height: "100%", background: "var(--accent)" }} />
            </div>
            <div className="faint" style={{ fontSize: 13 }}>{s.rationale}</div>
            {s.evidence[0] ? sourceLink(s.evidence[0].source_uri, s.evidence[0].canonical_id) : null}
          </div>
        ))}
      </div>
    </div>
  );
}
