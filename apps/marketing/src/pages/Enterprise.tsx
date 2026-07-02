import { ProductPage } from "./ProductPage";
import { PLANNED } from "../content";

export function Enterprise() {
  return (
    <>
      <ProductPage productKey="enterprise">
        <div className="card">
          <span className="eyebrow">Available now</span>
          <p className="blurb">
            Shared research workspaces for your team — notes, theses, and collections. Scoped API keys for
            programmatic access to the evidence graph. Organization settings and member management for
            entitled accounts.
          </p>
          <span className="pill">Enterprise plan</span>
        </div>
      </ProductPage>

      <section className="section" style={{ paddingTop: 0 }}>
        <div className="container">
          <div className="section-head">
            <span className="eyebrow">On the roadmap</span>
            <h2>Planned for enterprise.</h2>
            <p>These are in development — listed here so expectations stay honest. They are not live yet.</p>
          </div>
          <div className="grid cols-2">
            {PLANNED.map((c) => (
              <div className="card" key={c.title}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <h3>{c.title}</h3>
                  <span className="pill planned">Planned</span>
                </div>
                <p className="blurb">{c.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>
    </>
  );
}
