import { describe, expect, it } from "vitest";
import {
  isWorkspaceKind,
  postLoginPath,
  resolveHomeWorkspace,
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
