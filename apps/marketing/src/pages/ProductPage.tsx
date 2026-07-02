import type { ReactNode } from "react";
import { productByKey, type Product } from "../content";
import { enterpriseContactUrl, exploreUrl, signInUrl } from "../links";

// One layout for the three product pages. The primary CTA differs per product: Public
// sends you straight into the free surface; Personal to sign-in; Enterprise to contact.
function primaryCta(p: Product): { href: string; label: string } {
  if (p.key === "public") return { href: exploreUrl(), label: "Explore public knowledge →" };
  if (p.key === "enterprise") return { href: enterpriseContactUrl(), label: "Contact enterprise →" };
  return { href: signInUrl(), label: "Sign in →" };
}

export function ProductPage({ productKey, children }: { productKey: Product["key"]; children?: ReactNode }) {
  const p = productByKey(productKey);
  const cta = primaryCta(p);
  return (
    <main>
      <section className="page-intro">
        <div className="container">
          <span className="eyebrow">{p.eyebrow}</span>
          <h1>{p.name}</h1>
          <p className="lede">{p.blurb}</p>
        </div>
      </section>

      <section className="section">
        <div className="container">
          <div className="grid cols-2">
            <div className="card">
              <h2>{p.tagline}</h2>
              <ul className="checks">
                {p.bullets.map((b) => (
                  <li key={b}>{b}</li>
                ))}
              </ul>
              <div className="hero-cta" style={{ marginTop: 8 }}>
                <a className="btn primary" href={cta.href}>
                  {cta.label}
                </a>
                {p.key !== "public" ? (
                  <a className="btn ghost" href={exploreUrl()}>
                    Try the public graph
                  </a>
                ) : null}
              </div>
            </div>
            {children}
          </div>
        </div>
      </section>
    </main>
  );
}
