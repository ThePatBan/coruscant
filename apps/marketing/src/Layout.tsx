import type { ReactNode } from "react";
import { Link, NavLink, Outlet } from "react-router-dom";
import { enterpriseContactUrl, exploreUrl, signInUrl } from "./links";

const NAV = [
  { to: "/ai", label: "AI" },
  { to: "/public", label: "Public" },
  { to: "/personal", label: "Personal" },
  { to: "/enterprise", label: "Enterprise" },
];

function Brand() {
  return (
    <Link to="/" className="brand" aria-label="Coruscant home">
      <span className="logo" />
      Coruscant
    </Link>
  );
}

function Nav() {
  return (
    <header className="nav">
      <div className="container nav-inner">
        <Brand />
        <nav className="nav-links" aria-label="Products">
          {NAV.map((n) => (
            <NavLink key={n.to} to={n.to} className={({ isActive }) => (isActive ? "active" : "")}>
              {n.label}
            </NavLink>
          ))}
        </nav>
        <div className="nav-cta">
          <a className="btn ghost sm" href={signInUrl()}>
            Sign in
          </a>
          <a className="btn primary sm" href={exploreUrl()}>
            Explore
          </a>
        </div>
      </div>
    </header>
  );
}

function Footer() {
  return (
    <footer className="footer">
      <div className="container">
        <div className="footer-grid">
          <div className="footer-col">
            <Brand />
            <span style={{ maxWidth: "32ch", marginTop: 4 }}>
              Evidence-based intelligence. Every insight traces back to its source.
            </span>
          </div>
          <div className="footer-links">
            <div className="footer-col">
              <span className="h">Products</span>
              <Link to="/public">Public Knowledge</Link>
              <Link to="/personal">Personal Console</Link>
              <Link to="/enterprise">Enterprise</Link>
              <Link to="/ai">AI analyst</Link>
            </div>
            <div className="footer-col">
              <span className="h">Get started</span>
              <a href={exploreUrl()}>Explore public knowledge</a>
              <a href={signInUrl()}>Sign in</a>
              <a href={enterpriseContactUrl()}>Contact enterprise</a>
            </div>
          </div>
        </div>
        <p className="footer-note">
          Coruscant links every statement to a filing or public classification, and never presents an
          inference as a fact. Coverage today is a curated sample and expands over time.
        </p>
      </div>
    </footer>
  );
}

export function Layout() {
  return (
    <>
      <Nav />
      <Outlet />
      <Footer />
    </>
  );
}

/** Primary + secondary calls to action, reused across pages. */
export function HeroCta({ children }: { children?: ReactNode }) {
  return (
    <div className="hero-cta">
      <a className="btn primary" href={exploreUrl()}>
        Explore public knowledge →
      </a>
      <a className="btn ghost" href={signInUrl()}>
        Sign in
      </a>
      {children}
    </div>
  );
}
