import { Link } from "react-router-dom";
import { useAuth } from "../auth";
import {
  IconBell,
  IconCompany,
  IconGear,
  IconShield,
  IconSignals,
  type Icon,
} from "../icons";

// The enterprise workspace overview. Several org-level capabilities already exist
// in the platform (collaboration, API keys, admin/policy, data ops) and are wired
// live here; the rest is scaffolded so the shell and routing are in place before
// the backend internals land. See docs/PLATFORM.md.

interface Capability {
  to: string;
  Icon: Icon;
  title: string;
  body: string;
}

const LIVE: Capability[] = [
  {
    to: "/enterprise/collaboration",
    Icon: IconCompany,
    title: "Shared workspaces",
    body: "Team research spaces — notes, theses, bookmarks, and collections shared across members.",
  },
  {
    to: "/enterprise/api",
    Icon: IconGear,
    title: "API & access",
    body: "Programmatic access with scoped API keys and account controls for your integrations.",
  },
  {
    to: "/enterprise/policy",
    Icon: IconShield,
    title: "Policy & audit",
    body: "Admin console: model routing, customers, audit trail, and the dead-letter queue.",
  },
  {
    to: "/enterprise/sources",
    Icon: IconSignals,
    title: "Data sources",
    body: "The ingestion surface area — every source feeding the organization's evidence graph.",
  },
  {
    to: "/enterprise/monitoring",
    Icon: IconBell,
    title: "Monitoring",
    body: "Source freshness and pipeline health across the corpus your team depends on.",
  },
];

const PLANNED: { Icon: Icon; title: string; body: string }[] = [
  { Icon: IconGear, title: "Plans & billing", body: "Self-serve org plan management, seat-based billing, and invoices." },
  { Icon: IconShield, title: "SSO & SCIM", body: "Org-managed identity, directory sync, and role provisioning." },
  { Icon: IconGear, title: "Audit log export", body: "Streaming and scheduled export of the full activity trail." },
  { Icon: IconSignals, title: "Private connectors", body: "Bring your own filings, CRM, and internal documents into the graph." },
];

export function EnterprisePage() {
  const { email, role } = useAuth();
  // Policy & audit opens the admin console, which is admin-only (the backend 403s a
  // non-admin). The enterprise pilot admits any authenticated account, so only show it
  // as "available now" to admins — everyone else shouldn't be sold a card that dead-ends.
  const live = LIVE.filter((c) => c.to !== "/enterprise/policy" || role === "admin");

  return (
    <div className="stack gap-lg">
      <div className="page-head">
        <h1>Enterprise workspace</h1>
        <p className="sub">
          Org-level intelligence for your whole team — shared workspaces, private data, policy and
          audit controls, and programmatic access. Signed in as {email ?? "your account"}.
        </p>
      </div>

      <section className="stack gap">
        <div className="kicker">
          Available now
          <span className="pill accent">live</span>
        </div>
        <div className="grid cols-3">
          {live.map((c) => (
            <Link className="card hover ws-card" key={c.to} to={c.to}>
              <div className="ico-box">
                <c.Icon />
              </div>
              <h2>{c.title}</h2>
              <p className="blurb">{c.body}</p>
              <div className="ws-cta">Open →</div>
            </Link>
          ))}
        </div>
      </section>

      <section className="stack gap">
        <div className="kicker">On the roadmap</div>
        <div className="grid cols-3">
          {PLANNED.map((c) => (
            <div className="card ws-card ws-planned" key={c.title}>
              <div className="ico-box">
                <c.Icon />
              </div>
              <h2>{c.title}</h2>
              <p className="blurb">{c.body}</p>
              <div className="ws-cta">
                <span className="badge">Planned</span>
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
