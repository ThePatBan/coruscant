import { AI_POINTS } from "../content";
import { exploreUrl, signInUrl } from "../links";

export function AI() {
  return (
    <main>
      <section className="page-intro">
        <div className="container">
          <span className="eyebrow"><span className="dot" /> Coruscant AI</span>
          <h1>An analyst that cites its sources.</h1>
          <p className="lede">
            Ask a question and get an answer built from the same source-linked evidence graph you can
            browse. Every claim carries the disclosure or public classification behind it — grounded, not
            guessed.
          </p>
          <div className="hero-cta">
            <a className="btn primary" href={exploreUrl()}>
              Explore the graph →
            </a>
            <a className="btn ghost" href={signInUrl()}>
              Sign in
            </a>
          </div>
        </div>
      </section>

      <section className="section">
        <div className="container">
          <div className="grid cols-3">
            {AI_POINTS.map((pt) => (
              <div className="card" key={pt.title}>
                <h2>{pt.title}</h2>
                <p className="blurb">{pt.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="section" style={{ paddingTop: 0 }}>
        <div className="container">
          <div className="band">
            <span className="eyebrow">Why it matters</span>
            <h2>Intelligence you can defend.</h2>
            <p>
              For allocators and analysts who must defend every conclusion, an unsourced answer is worse
              than none. Coruscant's analyst is bound to the evidence graph: it surfaces what the data
              supports, labels what is inferred, and leaves a source link reachable from every claim.
            </p>
          </div>
        </div>
      </section>
    </main>
  );
}
