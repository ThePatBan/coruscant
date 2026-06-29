import { type FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type ChangeSet, type DocumentSummary } from "../api";
import { Cat, Empty, Loading } from "../components";
import { useAsync } from "../hooks";

export function ComparePage() {
  const companies = useAsync(() => api.companies(), []);
  const [slug, setSlug] = useState("");
  const [docs, setDocs] = useState<DocumentSummary[]>([]);
  const [a, setA] = useState("");
  const [b, setB] = useState("");
  const [result, setResult] = useState<ChangeSet | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!slug) {
      setDocs([]);
      return;
    }
    api.documents({ company: slug }).then((d) => {
      setDocs(d);
      setA(d[0]?.canonical_id ?? "");
      setB(d[1]?.canonical_id ?? "");
      setResult(null);
    });
  }, [slug]);

  async function run(e: FormEvent) {
    e.preventDefault();
    if (!a || !b || a === b) {
      setError("Pick two different documents.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      setResult(await api.compare(a, b));
    } catch {
      setError("Comparison failed.");
    } finally {
      setBusy(false);
    }
  }

  const label = (d: DocumentSummary) => `${d.title ?? d.canonical_id} (${d.published_at ?? "—"})`;

  return (
    <div className="stack gap-lg">
      <div className="page-head">
        <h1>Compare documents</h1>
        <p className="sub">
          Side-by-side diff of two filings — what was added or removed, categorized and cited.
        </p>
      </div>

      {companies.loading ? <Loading label="Loading" /> : null}

      <form className="card stack gap" onSubmit={run}>
        <div className="wrap" style={{ gap: 8 }}>
          <select className="input" value={slug} onChange={(e) => setSlug(e.target.value)} aria-label="Company">
            <option value="">Select a company…</option>
            {companies.data?.map((c) => (
              <option key={c.slug} value={c.slug}>{c.name}</option>
            ))}
          </select>
        </div>
        {docs.length >= 2 ? (
          <div className="wrap" style={{ gap: 8 }}>
            <select className="input" style={{ flex: 1 }} value={a} onChange={(e) => setA(e.target.value)}>
              {docs.map((d) => <option key={d.canonical_id} value={d.canonical_id}>{label(d)}</option>)}
            </select>
            <span className="faint">vs</span>
            <select className="input" style={{ flex: 1 }} value={b} onChange={(e) => setB(e.target.value)}>
              {docs.map((d) => <option key={d.canonical_id} value={d.canonical_id}>{label(d)}</option>)}
            </select>
            <button className="btn" type="submit" disabled={busy}>
              {busy ? <span className="spinner" style={{ width: 14, height: 14 }} /> : "Compare"}
            </button>
          </div>
        ) : slug ? (
          <span className="faint">This company has fewer than two documents to compare.</span>
        ) : null}
        {error ? <div className="errbox">{error}</div> : null}
      </form>

      {result ? (
        result.changes.length === 0 ? (
          <Empty icon="⇄" title="No differences between these documents" />
        ) : (
          <div className="card stack gap-sm">
            <div className="wrap" style={{ gap: 8 }}>
              <span className="pill" style={{ color: "var(--good)" }}>+{result.added_count} added</span>
              <span className="pill" style={{ color: "var(--danger)" }}>−{result.removed_count} removed</span>
            </div>
            {result.changes.map((c, i) => (
              <div className={`change-row ${c.kind}`} key={i}>
                <span className="change-mark">{c.kind === "added" ? "+" : "−"}</span>
                <div className="grow">
                  <div className="wrap" style={{ gap: 8, marginBottom: 3 }}>
                    <Cat category={c.category} />
                    <span className="faint" style={{ fontSize: 11.5 }}>
                      {(c.confidence * 100).toFixed(0)}% conf
                    </span>
                  </div>
                  <div className="stmt">{c.statement}</div>
                  <Link
                    to={`/documents/${c.evidence.canonical_id}`}
                    className="mono faint"
                    style={{ display: "block", marginTop: 4, fontSize: 11.5 }}
                  >
                    ↳ source
                  </Link>
                </div>
              </div>
            ))}
          </div>
        )
      ) : null}
    </div>
  );
}
