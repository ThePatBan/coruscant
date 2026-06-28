import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../auth";

const FEATURES = [
  {
    icon: "⇄",
    title: "What changed, not just what happened",
    body: "Coruscant diffs each new disclosure against the prior one and surfaces material changes — new risks, guidance moves, executive changes.",
  },
  {
    icon: "❝",
    title: "Every claim is traceable",
    body: "No unsupported assertions. Every summary line, event, and change links back to the exact source span that supports it.",
  },
  {
    icon: "⌕",
    title: "Search across everything",
    body: "Ask in natural language across filings, investor updates, transcripts, press, news, and patents — with evidence attached.",
  },
];

export function LandingPage() {
  const { email } = useAuth();
  const navigate = useNavigate();
  const primary = email ? "/dashboard" : "/login";

  return (
    <div className="landing">
      <div className="nav-top">
        <div className="brand">
          <div className="logo" />
          <div className="name">Coruscant</div>
        </div>
        <button className="btn ghost" onClick={() => navigate(primary)}>
          {email ? "Open workspace" : "Sign in"}
        </button>
      </div>

      <section className="hero">
        <span className="pill accent" style={{ marginBottom: 18 }}>
          Evidence-based financial intelligence
        </span>
        <h1>
          Understand what <span className="accent-text">materially changed</span> — and why it
          matters.
        </h1>
        <p>
          Coruscant continuously ingests public company information, understands what changed since
          the last disclosure, and shows you — with the source evidence behind every statement.
        </p>
        <div className="cta">
          <Link to={primary} className="btn lg">
            {email ? "Open workspace →" : "Get started →"}
          </Link>
          <a className="btn ghost lg" href="#features">
            How it works
          </a>
        </div>
      </section>

      <section className="feature-grid" id="features">
        {FEATURES.map((f) => (
          <div className="card feature" key={f.title}>
            <div className="ico-box">{f.icon}</div>
            <h3>{f.title}</h3>
            <p>{f.body}</p>
          </div>
        ))}
      </section>
    </div>
  );
}
