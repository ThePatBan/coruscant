import { Link } from "react-router-dom";
import { HeroCta } from "../Layout";
import { PRODUCTS, COVERAGE_NOTE } from "../content";
import { enterpriseContactUrl } from "../links";

export function Home() {
  return (
    <main>
      <section className="hero">
        <div className="container">
          <span className="eyebrow"><span className="dot" /> Evidence-based intelligence</span>
          <h1>
            A random event happens. <span className="accent">Does it touch your portfolio?</span>
          </h1>
          <p className="lede">
            Coruscant trades pages of reading for orientation. Trace a public event to the holdings it
            actually touches — by geography, sector, and market tier — with the source behind every edge.
          </p>
          <HeroCta />
          <p className="hero-note">
            Start free in Public Knowledge — no account needed. {COVERAGE_NOTE}
          </p>
        </div>
      </section>

      <hr className="divider" />

      <section className="section">
        <div className="container">
          <div className="section-head">
            <span className="eyebrow">Three ways in</span>
            <h2>One evidence graph, three products.</h2>
            <p>
              The same source-linked graph, framed for how you work — open discovery, personal
              monitoring, or org-wide intelligence.
            </p>
          </div>
          <div className="grid cols-3">
            {PRODUCTS.map((p) => (
              <Link key={p.key} to={p.path} className="card link">
                <span className="eyebrow">{p.eyebrow}</span>
                <h3>{p.name}</h3>
                <p className="tagline">{p.tagline}</p>
                <p className="blurb">{p.blurb}</p>
                <span className="cta">Learn more →</span>
              </Link>
            ))}
          </div>
        </div>
      </section>

      <section className="section">
        <div className="container">
          <div className="band">
            <span className="eyebrow">The principle</span>
            <h2>Never fabricate. Never sacrifice traceability for intelligence.</h2>
            <p>
              Every relationship links back to the exact disclosure or public classification behind it.
              Derived or proxy links are labelled as such — an inference is never presented as a fact,
              and when a live feed is off, you see a labelled stub, never a placeholder.
            </p>
          </div>
        </div>
      </section>

      <section className="section">
        <div className="container">
          <div className="section-head">
            <span className="eyebrow">Ask the graph</span>
            <h2>An analyst that cites its sources.</h2>
            <p>
              The AI analyst answers from the same evidence graph you can browse — and every claim carries
              the source behind it. If the graph can't support a statement, it says so.
            </p>
          </div>
          <Link className="btn ghost" to="/ai">
            See how the AI works →
          </Link>
        </div>
      </section>

      <section className="cta-band">
        <div className="container">
          <h2>Orient before you read.</h2>
          <p>Explore the public evidence graph today, or talk to us about enterprise access.</p>
          <HeroCta>
            <a className="btn ghost" href={enterpriseContactUrl()}>
              Contact enterprise
            </a>
          </HeroCta>
        </div>
      </section>
    </main>
  );
}
