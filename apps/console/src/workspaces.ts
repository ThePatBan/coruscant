// The three-product model (see docs/PLATFORM.md and PRODUCT.md). Coruscant ships
// as three distinct workspaces that share ONE design system and shell:
//   • public     — free, discovery-first: search, company profiles, relationships,
//                  timelines, evidence. No monitoring framing.
//   • personal   — the monitoring product: watchlists, alerts, portfolio, exposure.
//   • enterprise — org-level: shared workspaces, policy/audit, and programmatic API access.
//
// This module is the single source of truth for what each workspace IS (identity,
// nav, entry path) and the pure logic that routes a visitor to the right one based
// on auth/role/remembered choice. Keep it framework-light (no JSX) so the routing
// logic stays unit-testable — see workspaces.test.ts.

import type { Icon } from "./icons";
import {
  IconBell,
  IconChanged,
  IconCompany,
  IconCountry,
  IconDashboard,
  IconFind,
  IconGear,
  IconRisk,
  IconShield,
  IconSignals,
} from "./icons";

export type WorkspaceKind = "public" | "personal" | "enterprise";

export const WORKSPACE_KINDS: readonly WorkspaceKind[] = ["public", "personal", "enterprise"];

export interface NavItem {
  to: string;
  label: string;
  Icon: Icon;
}

export interface WorkspaceMeta {
  kind: WorkspaceKind;
  /** Short identity shown in the shell brand tag and the chooser card. */
  label: string;
  /** Audience eyebrow on the chooser card. */
  eyebrow: string;
  /** One-line value proposition. */
  blurb: string;
  /** Three concrete capabilities. */
  bullets: [string, string, string];
  /** Where entering this workspace lands. */
  home: string;
  /** Requires a signed-in session to enter. */
  requiresAuth: boolean;
  /** The workspace's own primary nav spine. */
  nav: NavItem[];
}

// Personal keeps the existing Portfolio-Exposure spine verbatim (World → Country →
// Company + the analytical reads). This is the monitoring product, unchanged.
const PERSONAL_NAV: NavItem[] = [
  { to: "/dashboard", label: "Dashboard", Icon: IconDashboard },
  { to: "/changes", label: "What changed", Icon: IconChanged },
  { to: "/world", label: "Live signals", Icon: IconSignals },
  { to: "/risk", label: "Risk concentration", Icon: IconRisk },
  { to: "/country", label: "Country", Icon: IconCountry },
  { to: "/atlas", label: "Company graph", Icon: IconCompany },
  { to: "/search", label: "Find", Icon: IconFind },
];

// Public reuses the discovery surfaces but drops all monitoring framing. The links
// point at the shared discovery pages; anonymous visitors hit the sign-in funnel.
const PUBLIC_NAV: NavItem[] = [
  { to: "/public", label: "Discover", Icon: IconFind },
  { to: "/companies", label: "Companies", Icon: IconDashboard },
  { to: "/atlas", label: "Company graph", Icon: IconCompany },
  { to: "/changes", label: "What changed", Icon: IconChanged },
];

// Enterprise reframes the org/collaboration surfaces under its own spine. Deep features
// live under /enterprise/* so the enterprise shell stays sticky. Internal Coruscant
// operations are NOT here — they moved to the separate admin app (apps/admin) in Phase 9.
const ENTERPRISE_NAV: NavItem[] = [
  { to: "/enterprise", label: "Overview", Icon: IconDashboard },
  { to: "/enterprise/collaboration", label: "Collaboration", Icon: IconCompany },
  { to: "/enterprise/sources", label: "Data sources", Icon: IconSignals },
  { to: "/enterprise/monitoring", label: "Monitoring", Icon: IconBell },
  { to: "/enterprise/api", label: "API & access", Icon: IconGear },
  { to: "/enterprise/organization", label: "Organization", Icon: IconShield },
];

export const WORKSPACES: Record<WorkspaceKind, WorkspaceMeta> = {
  public: {
    kind: "public",
    label: "Public",
    eyebrow: "Free · no account needed",
    blurb:
      "Explore the evidence graph. Search companies, trace relationships, and read source-linked disclosures — open to everyone.",
    bullets: [
      "Company profiles & entity search",
      "Relationship & ownership graph",
      "Source-linked evidence & timelines",
    ],
    home: "/public",
    requiresAuth: false,
    nav: PUBLIC_NAV,
  },
  personal: {
    kind: "personal",
    label: "Personal",
    eyebrow: "For individual investors",
    blurb:
      "Turn discovery into monitoring. Watchlists, alerts, portfolio exposure, and what-changed briefings tuned to you.",
    bullets: [
      "Watchlists & saved searches",
      "Portfolio & exposure analysis",
      "Alerts on material change",
    ],
    home: "/world",
    requiresAuth: true,
    nav: PERSONAL_NAV,
  },
  enterprise: {
    kind: "enterprise",
    label: "Enterprise",
    eyebrow: "For teams & organizations",
    blurb:
      "Org-level intelligence. Shared workspaces, organization administration, and programmatic API access for your whole team.",
    bullets: [
      "Shared workspaces & collaboration",
      "Scoped API keys & programmatic access",
      "Organization settings & members",
    ],
    home: "/enterprise",
    requiresAuth: true,
    nav: ENTERPRISE_NAV,
  },
};

export function isWorkspaceKind(value: string | null | undefined): value is WorkspaceKind {
  return value === "public" || value === "personal" || value === "enterprise";
}

/** Which workspace owns a given path — drives shell chrome and breadcrumbs. */
export function workspaceForPath(pathname: string): WorkspaceKind {
  if (pathname === "/public" || pathname.startsWith("/public/")) return "public";
  if (pathname === "/enterprise" || pathname.startsWith("/enterprise/")) return "enterprise";
  return "personal";
}

// The discovery destinations an anonymous visitor may read (Phase 6 public launch):
// search, company profiles, relationships, the entity graph, evidence — the routes
// the Public nav points at. Everything else under the signed-in shell (monitoring,
// portfolio, alerts, workspaces, admin, enterprise) requires auth. Kept in sync with
// the backend PUBLIC_READ allow-list (apps/api.py).
const PUBLIC_READABLE_PREFIXES: readonly string[] = [
  "/companies",
  "/atlas",
  "/changes",
  "/search",
  "/graph",
  "/documents",
  "/compare",
];

/** Whether an anonymous visitor may view this path (a curated read-only surface). */
export function isPublicReadablePath(pathname: string): boolean {
  return PUBLIC_READABLE_PREFIXES.some((p) => pathname === p || pathname.startsWith(`${p}/`));
}

export type RouteAccess = "allow" | "requireLogin";

/**
 * The single, deterministic access decision for a path. Signed-in visitors may go
 * anywhere; anonymous visitors may read the public surface and are otherwise sent to
 * sign in. Pure and total, so the shell guard is one testable call (workspaces.test.ts).
 */
export function routeAccess(pathname: string, ctx: { authed: boolean }): RouteAccess {
  if (ctx.authed) return "allow";
  if (isPublicReadablePath(pathname)) return "allow";
  return "requireLogin";
}

/** The entitlement inputs the enterprise gate needs: a session plus whether the
 * account actually holds the enterprise entitlement (backend-decided — see
 * `/entitlements` and `useAuth().enterprise`). `enterprise` is optional so anonymous
 * callers (no entitlement known) read as not-entitled. */
export interface EntitlementContext {
  authed: boolean;
  enterprise?: boolean;
}

/**
 * The SINGLE decision point for enterprise eligibility (Phase 7, Scope B). A caller is
 * eligible only with a session AND the enterprise entitlement — replacing the old "any
 * authenticated account may enter enterprise". The entitlement itself is decided by the
 * backend (admin role OR an enterprise-plan org); this stays a pure mirror so the shell
 * guard, the landing chooser, and the overview never re-derive eligibility themselves.
 */
export function canUseEnterprise(ctx: EntitlementContext): boolean {
  return ctx.authed && ctx.enterprise === true;
}

/**
 * Whether a visitor may ENTER a workspace — the deterministic entitlement gate.
 * Public is always open; Personal needs a session; Enterprise needs the enterprise
 * entitlement (via `canUseEnterprise`), so callers never branch on entitlement themselves.
 */
export function canEnterWorkspace(kind: WorkspaceKind, ctx: EntitlementContext): boolean {
  if (kind === "public") return true;
  if (kind === "enterprise") return canUseEnterprise(ctx);
  return ctx.authed;
}

export interface HomeContext {
  authed: boolean;
  remembered?: WorkspaceKind | null;
}

/**
 * The routing gate. An anonymous visitor belongs in the free public product; a
 * signed-in visitor returns to their remembered workspace, defaulting to personal
 * (the historical landing) when nothing is remembered.
 */
export function resolveHomeWorkspace(ctx: HomeContext): WorkspaceKind {
  if (!ctx.authed) return "public";
  if (isWorkspaceKind(ctx.remembered)) return ctx.remembered;
  return "personal";
}

export interface PostLoginContext {
  /** ?ws= on the login URL — an explicit product intent. */
  requested?: string | null;
  /** The path the guard bounced the user away from. */
  from?: string | null;
  remembered?: WorkspaceKind | null;
}

/** Where a successful sign-in should land, honouring an explicit deep link first. */
export function postLoginPath(ctx: PostLoginContext): string {
  const { from } = ctx;
  if (from && from !== "/" && from !== "/login") return from;
  const ws = isWorkspaceKind(ctx.requested)
    ? ctx.requested
    : isWorkspaceKind(ctx.remembered)
      ? ctx.remembered
      : "personal";
  // Public never needs a login round-trip; fall back to personal if it somehow asks.
  return WORKSPACES[ws].requiresAuth ? WORKSPACES[ws].home : WORKSPACES.personal.home;
}

const STORE_KEY = "coruscant.workspace";

/** Remembers the last workspace a signed-in user chose, so the gate can return them. */
export const workspaceStore = {
  get(): WorkspaceKind | null {
    try {
      const value = typeof localStorage !== "undefined" ? localStorage.getItem(STORE_KEY) : null;
      return isWorkspaceKind(value) ? value : null;
    } catch {
      return null;
    }
  },
  set(ws: WorkspaceKind): void {
    try {
      localStorage.setItem(STORE_KEY, ws);
    } catch {
      /* ignore — private mode / storage disabled */
    }
  },
};
