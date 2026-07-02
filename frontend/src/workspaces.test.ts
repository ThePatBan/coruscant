import { describe, expect, it } from "vitest";
import {
  canEnterWorkspace,
  isPublicReadablePath,
  isWorkspaceKind,
  postLoginPath,
  resolveHomeWorkspace,
  routeAccess,
  WORKSPACES,
  workspaceForPath,
} from "./workspaces";

describe("isWorkspaceKind", () => {
  it("accepts the three product kinds", () => {
    expect(isWorkspaceKind("public")).toBe(true);
    expect(isWorkspaceKind("personal")).toBe(true);
    expect(isWorkspaceKind("enterprise")).toBe(true);
  });
  it("rejects anything else", () => {
    expect(isWorkspaceKind("team")).toBe(false);
    expect(isWorkspaceKind("")).toBe(false);
    expect(isWorkspaceKind(null)).toBe(false);
    expect(isWorkspaceKind(undefined)).toBe(false);
  });
});

describe("workspaceForPath", () => {
  it("routes /public* to the public workspace", () => {
    expect(workspaceForPath("/public")).toBe("public");
    expect(workspaceForPath("/public/anything")).toBe("public");
  });
  it("routes /enterprise* to the enterprise workspace", () => {
    expect(workspaceForPath("/enterprise")).toBe("enterprise");
    expect(workspaceForPath("/enterprise/policy")).toBe("enterprise");
  });
  it("treats every other signed-in path as personal", () => {
    expect(workspaceForPath("/world")).toBe("personal");
    expect(workspaceForPath("/companies/apple")).toBe("personal");
    expect(workspaceForPath("/settings")).toBe("personal");
  });
  it("does not confuse look-alike prefixes", () => {
    // A hypothetical "/publications" must not be read as the public workspace.
    expect(workspaceForPath("/publications")).toBe("personal");
    expect(workspaceForPath("/enterprises")).toBe("personal");
  });
});

describe("resolveHomeWorkspace (the routing gate)", () => {
  it("sends anonymous visitors to the free public product", () => {
    expect(resolveHomeWorkspace({ authed: false })).toBe("public");
    expect(resolveHomeWorkspace({ authed: false, remembered: "enterprise" })).toBe("public");
  });
  it("returns signed-in visitors to their remembered workspace", () => {
    expect(resolveHomeWorkspace({ authed: true, remembered: "enterprise" })).toBe("enterprise");
    expect(resolveHomeWorkspace({ authed: true, remembered: "public" })).toBe("public");
  });
  it("defaults signed-in visitors with no history to personal", () => {
    expect(resolveHomeWorkspace({ authed: true })).toBe("personal");
    expect(resolveHomeWorkspace({ authed: true, remembered: null })).toBe("personal");
  });
});

describe("postLoginPath", () => {
  it("honours an explicit deep link the guard bounced from", () => {
    expect(postLoginPath({ from: "/risk" })).toBe("/risk");
    expect(postLoginPath({ from: "/enterprise/api", requested: "personal" })).toBe("/enterprise/api");
  });
  it("ignores trivial from-paths and uses the requested workspace", () => {
    expect(postLoginPath({ from: "/", requested: "enterprise" })).toBe(WORKSPACES.enterprise.home);
    expect(postLoginPath({ from: "/login", requested: "personal" })).toBe(WORKSPACES.personal.home);
  });
  it("falls back to the remembered workspace, then to personal", () => {
    expect(postLoginPath({ remembered: "enterprise" })).toBe(WORKSPACES.enterprise.home);
    expect(postLoginPath({})).toBe(WORKSPACES.personal.home);
  });
  it("never lands a login on the no-auth public workspace", () => {
    // Signing in for the public product still makes no sense; send to personal.
    expect(postLoginPath({ requested: "public" })).toBe(WORKSPACES.personal.home);
  });
});

describe("isPublicReadablePath (Phase 6 public surface)", () => {
  it("admits the curated discovery destinations", () => {
    for (const p of ["/companies", "/companies/apple", "/atlas", "/changes", "/search", "/graph", "/documents", "/documents/x", "/compare"]) {
      expect(isPublicReadablePath(p)).toBe(true);
    }
  });
  it("excludes monitoring, portfolio, admin and enterprise surfaces", () => {
    for (const p of ["/portfolio", "/watchlists", "/alerts", "/settings", "/admin", "/monitoring", "/enterprise", "/enterprise/api", "/world", "/dashboard"]) {
      expect(isPublicReadablePath(p)).toBe(false);
    }
  });
  it("does not confuse look-alike prefixes", () => {
    expect(isPublicReadablePath("/companies-house")).toBe(false);
    expect(isPublicReadablePath("/graphql")).toBe(false);
  });
});

describe("routeAccess (the deterministic guard)", () => {
  it("lets a signed-in visitor go anywhere", () => {
    expect(routeAccess("/portfolio", { authed: true })).toBe("allow");
    expect(routeAccess("/enterprise/api", { authed: true })).toBe("allow");
  });
  it("lets an anonymous visitor read the public surface", () => {
    expect(routeAccess("/companies/apple", { authed: false })).toBe("allow");
    expect(routeAccess("/search", { authed: false })).toBe("allow");
  });
  it("sends an anonymous visitor to login for private surfaces", () => {
    expect(routeAccess("/portfolio", { authed: false })).toBe("requireLogin");
    expect(routeAccess("/enterprise", { authed: false })).toBe("requireLogin");
    expect(routeAccess("/admin", { authed: false })).toBe("requireLogin");
  });
});

describe("canEnterWorkspace (entitlement gate)", () => {
  it("keeps Public open to everyone", () => {
    expect(canEnterWorkspace("public", { authed: false })).toBe(true);
    expect(canEnterWorkspace("public", { authed: true })).toBe(true);
  });
  it("requires a session for Personal and Enterprise", () => {
    expect(canEnterWorkspace("personal", { authed: false })).toBe(false);
    expect(canEnterWorkspace("enterprise", { authed: false })).toBe(false);
    expect(canEnterWorkspace("personal", { authed: true })).toBe(true);
    expect(canEnterWorkspace("enterprise", { authed: true })).toBe(true);
  });
});

describe("Public nav advertises only anon-reachable destinations", () => {
  it("every Public workspace nav target clears the anonymous read gate", () => {
    // The Public nav is what an unauthenticated visitor sees. /public (and any
    // /public/* sub-page) is served by the unguarded PublicShell; every other target
    // must satisfy isPublicReadablePath, or an anon click bounces to /login — silently
    // breaking the "free & open" promise. Keeps PUBLIC_NAV and the read gate in lockstep.
    for (const item of WORKSPACES.public.nav) {
      const reachable =
        item.to === "/public" || item.to.startsWith("/public/") || isPublicReadablePath(item.to);
      expect(reachable, `Public nav advertises ${item.to} but it is not anon-readable`).toBe(true);
    }
  });
});
