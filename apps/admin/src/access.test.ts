import { describe, expect, it } from "vitest";
import { ADMIN_ROLE, canAccessAdmin } from "./access";

describe("canAccessAdmin (the internal-admin access mirror)", () => {
  it("admits only the admin role", () => {
    expect(canAccessAdmin(ADMIN_ROLE)).toBe(true);
    expect(canAccessAdmin("admin")).toBe(true);
  });

  it("rejects non-admin roles", () => {
    expect(canAccessAdmin("analyst")).toBe(false);
    expect(canAccessAdmin("enterprise")).toBe(false);
    expect(canAccessAdmin("")).toBe(false);
  });

  it("rejects an unresolved / absent session", () => {
    expect(canAccessAdmin(null)).toBe(false);
    expect(canAccessAdmin(undefined)).toBe(false);
  });
});
