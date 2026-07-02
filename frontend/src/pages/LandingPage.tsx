import { Link } from "react-router-dom";
import { useAuth } from "../auth";
import {
  resolveHomeWorkspace,
  WORKSPACE_KINDS,
  WORKSPACES,
  workspaceStore,
  type WorkspaceKind,
} from "../workspaces";

// The home page is the product chooser AND the routing gate: it presents the three
// Coruscant products and routes each visitor by auth state. Anonymous visitors are
// pointed at the free public product and a sign-in path for the paid workspaces;
// signed-in visitors get a one-click return to where they left off.

function ctaFor(
  kind: WorkspaceKind,
  ctx: { authed: boolean; enterprise: boolean },
): { to: string; label: string } {
  const ws = WORKSPACES[kind];
  if (!ws.requiresAuth) return { to: ws.home, label: "Explore free →" };
  if (!ctx.authed) return { to: `/login?ws=${kind}`, label: "Sign in →" };
  // Enterprise is entitlement-gated: an un-entitled account is offered the overview
  // (an honest "what you'd get" upsell), not a dead-ending "open" into locked surfaces.
  if (kind === "enterprise" && !ctx.enterprise) return { to: "/enterprise", label: "Learn more →" };
  return { to: ws.home, label: `Open ${ws.label.toLowerCase()} →` };
}

export function LandingPage() {
  const { email, enterprise } = useAuth();
  const authed = Boolean(email);
  const remembered = workspaceStore.get();
  const resume = authed ? WORKSPACES[resolveHomeWorkspace({ authed, remembered })] : null;

  return (
    <div className="landing">
      <div className="nav-top">
        <div className="brand">
          <div className="logo" />
          <div className="name">Coruscant</div>
        </div>
        {authed ? (
          <Link className="btn ghost" to={resume!.home}>
            Open workspace →
          </Link>
        ) : (
          <Link className="btn ghost" to="/login">
            Sign in
          </Link>
        )}
      </div>

      <section className="hero">
        <span className="pill accent" style={{ marginBottom: 18 }}>
          Evidence-based financial intelligence
        </span>
        <h1>
          Choose how you use <span className="accent-text">Coruscant</span>.
        </h1>
        <p>
          One evidence graph, three products. Explore public company intelligence for free, monitor
          what matters to you, or run it across your whole organization — every insight traces back
          to its source.
        </p>
      </section>

      {resume ? (
        <div className="ws-continue card" role="note">
          <span className="muted">
            Signed in as <strong style={{ color: "var(--text)" }}>{email}</strong> — continue in your{" "}
            <strong style={{ color: "var(--text)" }}>{resume.label}</strong> workspace.
          </span>
          <Link className="btn" to={resume.home}>
            Continue →
          </Link>
        </div>
      ) : null}

      <section className="feature-grid ws-grid">
        {WORKSPACE_KINDS.map((kind) => {
          const ws = WORKSPACES[kind];
          const cta = ctaFor(kind, { authed, enterprise });
          const current = resume?.kind === kind;
          return (
            <Link className="card hover ws-card" key={kind} to={cta.to}>
              <div className="kicker">
                {ws.eyebrow}
                {current ? <span className="badge">current</span> : null}
              </div>
              <h2>{ws.label}</h2>
              <p className="blurb">{ws.blurb}</p>
              <ul className="ws-bullets">
                {ws.bullets.map((b) => (
                  <li key={b}>{b}</li>
                ))}
              </ul>
              <div className={current ? "ws-cta ws-current" : "ws-cta"}>{cta.label}</div>
            </Link>
          );
        })}
      </section>
    </div>
  );
}
