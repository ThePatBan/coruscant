import { type FormEvent, useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type RetrieveResponse, type SavedSearch } from "../api";
import { docTypeLabel, Empty } from "../components";

const SAMPLES = [
  "Apple risk factors and guidance",
  "Tesla competition and margins",
  "SpaceX patents and technology",
  "Microsoft investor update",
];

export function AskPage() {
  const [query, setQuery] = useState("");
  const [submitted, setSubmitted] = useState("");
  const [result, setResult] = useState<RetrieveResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<SavedSearch[]>([]);

  const reloadSaved = useCallback(async () => {
    try {
      setSaved(await api.savedSearches());
    } catch {
      /* saved searches are optional */
    }
  }, []);
  useEffect(() => {
    void reloadSaved();
  }, [reloadSaved]);

  async function save() {
    const text = query.trim();
    if (!text) return;
    await api.createSavedSearch(text.slice(0, 48), text);
    await reloadSaved();
  }

  async function run(raw: string) {
    const text = raw.trim();
    if (!text) return;
    setQuery(text);
    setSubmitted(text);
    setLoading(true);
    setError(null);
    try {
      setResult(await api.retrieve(text, 6));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setResult(null);
    } finally {
      setLoading(false);
    }
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    void run(query);
  }

  return (
    <div className="stack gap-lg">
      <div className="page-head">
        <h1>Ask the evidence</h1>
        <p className="sub">
          Query the corpus across SEC filings, investor updates, transcripts, press releases,
          job postings, news, and patents. Every answer cites the section and source it came from.
        </p>
      </div>

      <form onSubmit={onSubmit} className="stack gap">
        <div className="searchbar">
          <span className="faint" style={{ fontSize: 18 }}>
            ⌕
          </span>
          <input
            autoFocus
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="e.g. Apple risk factors and guidance"
            aria-label="Search query"
          />
          <button className="btn" type="submit" disabled={loading || !query.trim()}>
            {loading ? <span className="spinner" style={{ width: 14, height: 14 }} /> : "Ask"}
          </button>
          <button
            className="btn ghost"
            type="button"
            disabled={!query.trim()}
            onClick={() => void save()}
            title="Save this search"
          >
            ☆ Save
          </button>
        </div>
        <div className="chips">
          {SAMPLES.map((s) => (
            <button type="button" key={s} className="chip" onClick={() => void run(s)}>
              {s}
            </button>
          ))}
        </div>
        {saved.length > 0 ? (
          <div className="wrap" style={{ gap: 8 }}>
            <span className="faint" style={{ fontSize: 12.5 }}>Saved:</span>
            {saved.map((s) => (
              <span key={s.id} className="pill" style={{ gap: 6 }}>
                <button
                  type="button"
                  onClick={() => {
                    setQuery(s.query);
                    void run(s.query);
                  }}
                  style={{ background: "none", border: "none", color: "var(--accent)", cursor: "pointer", padding: 0 }}
                >
                  {s.name}
                </button>
                <button
                  type="button"
                  onClick={async () => {
                    await api.deleteSavedSearch(s.id);
                    await reloadSaved();
                  }}
                  style={{ background: "none", border: "none", color: "var(--text-faint)", cursor: "pointer", padding: 0 }}
                  title="Delete"
                >
                  ×
                </button>
              </span>
            ))}
          </div>
        ) : null}
      </form>

      {error ? <div className="errbox">Query failed: {error}</div> : null}

      {loading ? (
        <div className="loading">
          <span className="spinner" />
          Searching the corpus…
        </div>
      ) : null}

      {!loading && result ? (
        result.results.length === 0 ? (
          <Empty
            icon="⌕"
            title={`No evidence found for "${submitted}"`}
            hint="Try a company name or a topic like risk, guidance, or patents."
          />
        ) : (
          <div className="stack gap">
            <div className="row-between">
              <h2>Evidence</h2>
              <span className="badge">{result.results.length} sources</span>
            </div>
            <p className="faint" style={{ fontSize: 13, marginTop: -6 }}>
              Results are grounded in retrievable source spans — every excerpt links to its origin.
            </p>
            {result.results.map((r) => (
              <div className="card" key={r.canonical_id}>
                <div className="row-between" style={{ marginBottom: 4 }}>
                  <Link to={`/documents/${r.canonical_id}`} style={{ fontWeight: 620 }}>
                    {r.title ?? "Untitled document"}
                  </Link>
                  {r.document_type ? (
                    <span className="badge">{docTypeLabel(r.document_type)}</span>
                  ) : null}
                </div>
                {r.evidence.map((ev, i) => (
                  <div className="evidence" key={`${ev.source_uri}-${i}`}>
                      <div className="excerpt">“{ev.excerpt ?? "—"}”</div>
                      <div className="src">
                        {ev.section_title ? (
                          <span className="pill evidence">§ {ev.section_title}</span>
                        ) : null}
                        <span className="mono faint truncate" title={ev.source_uri}>
                          {ev.source_uri}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              ))}
          </div>
        )
      ) : null}

      {!loading && !result && !error ? (
        <Empty
          icon="◎"
          title="Ask a question to begin"
          hint="Pick a sample above or type your own. Results are grounded in retrievable evidence."
        />
      ) : null}
    </div>
  );
}
