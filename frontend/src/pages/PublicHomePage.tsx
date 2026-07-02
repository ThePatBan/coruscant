import { type FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../auth";
import { IconChanged, IconCompany, IconFind } from "../icons";

// The free product's home. Discovery-first — search, entity discovery, company
// profiles, relationships, timelines, evidence — with none of the portfolio /
// monitoring framing that defines the Personal workspace. Opening a result funnels
// anonymous visitors through sign-in (the demo account is one click); the surfaces
// themselves are the shared discovery pages, reused rather than duplicated.

const SAMPLES = [
  "Apple risk factors and guidance",
  "Tesla competition and margins",
  "Nvidia supply chain exposure",
  "Berkshire Hathaway holdings",
];

const SURFACES = [
  {
    to: "/companies",
    Icon: IconCompany,
    title: "Company profiles",
    body: "Browse the tracked universe — sector, jurisdiction, filings, and how each entity connects.",
  },
  {
    to: "/atlas",
    Icon: IconCompany,
    title: "Relationship graph",
    body: "Trace supply chains, ownership, board interlocks, and competitors across the evidence graph.",
  },
  {
    to: "/changes",
    Icon: IconChanged,
    title: "Evidence & timelines",
    body: "See what materially changed between disclosures — each claim linked to its source span.",
  },
];

export function PublicHomePage() {
  const { email } = useAuth();
  const navigate = useNavigate();
  const [query, setQuery] = useState("");

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    const q = query.trim();
    navigate(q ? `/search?q=${encodeURIComponent(q)}` : "/search");
  }

  return (
    <div className="stack gap-lg">
      <div className="page-head">
        <h1>Explore the evidence graph</h1>
        <p className="sub">
          Search companies, people, and filings across SEC EDGAR, investor updates, transcripts,
          press, and patents. Every result is grounded in a retrievable source span — free and open.
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
            placeholder="Search a company, person, or topic — e.g. Nvidia supply chain"
            aria-label="Search the evidence graph"
          />
          <button className="btn" type="submit">
            Search
          </button>
        </div>
        <div className="chips">
          {SAMPLES.map((s) => (
            <button
              type="button"
              key={s}
              className="chip"
              onClick={() => navigate(`/search?q=${encodeURIComponent(s)}`)}
            >
              {s}
            </button>
          ))}
        </div>
      </form>

      <div className="grid cols-3">
        {SURFACES.map((s) => (
          <Link className="card hover ws-card" key={s.to} to={s.to}>
            <div className="ico-box">
              <s.Icon />
            </div>
            <h2>{s.title}</h2>
            <p className="blurb">{s.body}</p>
            <div className="ws-cta">Open →</div>
          </Link>
        ))}
      </div>

      <div className="ws-continue card" role="note">
        <span className="muted">
          <IconFind style={{ verticalAlign: "-3px", marginRight: 6 }} />
          Want watchlists, alerts, and portfolio exposure?
        </span>
        {email ? (
          <Link className="btn ghost" to="/world">
            Open Personal →
          </Link>
        ) : (
          <Link className="btn ghost" to="/login?ws=personal">
            Get the Personal workspace →
          </Link>
        )}
      </div>
    </div>
  );
}
