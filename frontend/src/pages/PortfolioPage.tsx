import { type FormEvent, useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type Company, type PortfolioBriefing, type Portfolio } from "../api";
import { Cat, Empty, Loading } from "../components";
import { useAsync } from "../hooks";

export function PortfolioPage() {
  const companiesState = useAsync(() => api.companies(), []);
  const [portfolios, setPortfolios] = useState<Portfolio[]>([]);
  const [name, setName] = useState("My portfolio");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [briefing, setBriefing] = useState<PortfolioBriefing | null>(null);
  const [busy, setBusy] = useState(false);

  const reload = useCallback(async () => setPortfolios(await api.portfolios()), []);
  useEffect(() => {
    void reload();
  }, [reload]);

  function toggle(slug: string) {
    const next = new Set(selected);
    next.has(slug) ? next.delete(slug) : next.add(slug);
    setSelected(next);
  }

  async function create(e: FormEvent) {
    e.preventDefault();
    if (!name.trim() || selected.size === 0) return;
    setBusy(true);
    try {
      await api.createPortfolio(name.trim(), [...selected].map((s) => ({ company_slug: s })));
      setSelected(new Set());
      await reload();
    } finally {
      setBusy(false);
    }
  }

  async function openBriefing(id: string) {
    setBriefing(await api.portfolioBriefing(id));
  }

  return (
    <div className="stack gap-lg">
      <div className="page-head">
        <h1>Portfolio</h1>
        <p className="sub">
          Connect your holdings and ask: what changed that affects my portfolio? Material changes
          aggregate across everything you hold.
        </p>
      </div>

      <div className="grid cols-2">
        <form className="card stack gap" onSubmit={create}>
          <h2>New portfolio</h2>
          <div className="field">
            <label>Name</label>
            <input className="input" value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="wrap">
            {companiesState.data?.map((c: Company) => (
              <button
                type="button"
                key={c.slug}
                className={`chip${selected.has(c.slug) ? " on" : ""}`}
                style={selected.has(c.slug) ? { borderColor: "var(--accent-border)", background: "var(--accent-soft)", color: "var(--text)" } : undefined}
                onClick={() => toggle(c.slug)}
              >
                {c.name}
              </button>
            ))}
          </div>
          <button className="btn" type="submit" disabled={busy || selected.size === 0}>
            {busy ? <span className="spinner" style={{ width: 14, height: 14 }} /> : "Create portfolio"}
          </button>
        </form>

        <div className="stack gap">
          <h2>Your portfolios</h2>
          {portfolios.length === 0 ? (
            <Empty title="No portfolios yet" />
          ) : (
            portfolios.map((p) => (
              <div className="card row-between" key={p.id}>
                <div>
                  <div style={{ fontWeight: 560 }}>{p.name}</div>
                  <div className="faint" style={{ fontSize: 12.5 }}>{p.holdings.length} holdings</div>
                </div>
                <div className="wrap" style={{ gap: 6 }}>
                  <button className="btn ghost" style={{ padding: "6px 12px" }} onClick={() => void openBriefing(p.id)}>
                    Briefing
                  </button>
                  <button
                    className="btn ghost"
                    style={{ padding: "6px 12px" }}
                    onClick={async () => {
                      await api.deletePortfolio(p.id);
                      if (briefing?.portfolio_id === p.id) setBriefing(null);
                      await reload();
                    }}
                  >
                    Delete
                  </button>
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      {briefing ? (
        <div className="stack gap">
          <div className="answer">
            <div className="answer-label">Portfolio briefing — {briefing.name}</div>
            <div style={{ fontWeight: 560 }}>{briefing.headline}</div>
          </div>
          <div className="grid cols-2">
            <div className="stack gap">
              <h2>What materially changed</h2>
              {briefing.material_changes.length === 0 ? (
                <Empty title="No material changes" />
              ) : (
                briefing.material_changes.map((cs) => (
                  <div className="card stack gap-sm" key={cs.current_canonical_id}>
                    <div className="wrap" style={{ gap: 8 }}>
                      <Link to={`/companies/${cs.company_slug}`} style={{ fontWeight: 560 }}>
                        {cs.company_slug}
                      </Link>
                      <span className="badge">{cs.source_type}</span>
                      <span className="pill">+{cs.added_count} −{cs.removed_count}</span>
                    </div>
                    {cs.changes[0] ? (
                      <Link to={`/documents/${cs.changes[0].evidence.canonical_id}`} style={{ fontSize: 13.5 }}>
                        {cs.changes[0].statement}
                      </Link>
                    ) : null}
                  </div>
                ))
              )}
            </div>
            <div className="stack gap">
              <h2>Recent events</h2>
              <div className="card">
                <div className="timeline">
                  {briefing.recent_events.map((e, i) => (
                    <Link to={`/documents/${e.canonical_id}`} className="tl-item" style={{ display: "block" }} key={`${e.canonical_id}-${i}`}>
                      <div className="wrap" style={{ gap: 8, marginBottom: 2 }}>
                        <Cat category={e.category} />
                        <span className="when">{e.occurred_at ?? "—"}</span>
                      </div>
                      <div style={{ fontSize: 13.5 }}>{e.title}</div>
                    </Link>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      ) : null}

      {companiesState.loading ? <Loading label="Loading" /> : null}
    </div>
  );
}
