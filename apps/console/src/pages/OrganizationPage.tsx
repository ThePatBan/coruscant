import { Link } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { Loading } from "../components";
import { useAsync } from "../hooks";
import { IconCompany, IconGear, IconShield, IconSignals, type Icon } from "../icons";

// The customer-facing organization home for the Enterprise workspace. This replaced the
// internal "Policy & audit" surface (which opened the ops admin console) when that moved
// to apps/admin in Phase 9. Everything here is org self-service — plan & usage, and the
// org-level surfaces the team already has. No internal Coruscant operations.

interface Manage {
  to: string;
  Icon: Icon;
  title: string;
  body: string;
}

const MANAGE: Manage[] = [
  {
    to: "/enterprise/collaboration",
    Icon: IconCompany,
    title: "Members & collaboration",
    body: "Shared research workspaces — invite teammates and share notes, theses, and collections.",
  },
  {
    to: "/enterprise/api",
    Icon: IconGear,
    title: "API keys & access",
    body: "Create scoped API keys for your integrations and review programmatic access.",
  },
  {
    to: "/enterprise/sources",
    Icon: IconSignals,
    title: "Data sources",
    body: "The sources feeding your organization's evidence graph.",
  },
];

const PLANNED: { title: string; body: string }[] = [
  { title: "Seats & billing", body: "Self-serve seat management, plan changes, and invoices." },
  { title: "SSO & SCIM", body: "Org-managed identity, directory sync, and role provisioning." },
];

export function OrganizationPage() {
  const { email } = useAuth();
  const plan = useAsync(() => api.quota(), []);

  return (
    <div className="stack gap-lg">
      <div className="page-head">
        <h1>Organization</h1>
        <p className="sub">
          Manage your organization's plan, members, and access. Signed in as {email ?? "your account"}.
        </p>
      </div>

      <div className="card stack gap-sm">
        <div className="card-head">
          <h2>Plan &amp; usage</h2>
          <IconShield />
        </div>
        {plan.data ? (
          <>
            <div className="wrap">
              <span className="pill accent">{plan.data.plan_label} plan</span>
              <span className="pill">
                {plan.data.api_calls_today} / {plan.data.max_api_calls_per_day} API calls today
              </span>
              <span className="pill">
                {plan.data.watchlists_used} / {plan.data.max_watchlists} watchlists
              </span>
            </div>
            <p className="faint" style={{ fontSize: 12.5 }}>
              {plan.data.enforced
                ? `${plan.data.api_calls_remaining} calls remaining today on the ${plan.data.plan_label} plan.`
                : "Limits are shown for reference; quota enforcement is off on this deployment."}
            </p>
          </>
        ) : (
          <Loading label="Loading plan" />
        )}
      </div>

      <section className="stack gap">
        <div className="kicker">Manage</div>
        <div className="grid cols-3">
          {MANAGE.map((c) => (
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
                <IconGear />
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
