import { afterEach, describe, expect, it, vi } from "vitest";
import { consoleUrl, enterpriseContactUrl, exploreUrl, signInUrl } from "./links";

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("console link builders", () => {
  it("default to the production console origin", () => {
    expect(exploreUrl()).toBe("https://console.coruscant.com/public");
    expect(signInUrl()).toBe("https://console.coruscant.com/login");
  });

  it("honour a VITE_CONSOLE_URL override and strip a trailing slash", () => {
    vi.stubEnv("VITE_CONSOLE_URL", "https://staging.console.coruscant.com/");
    expect(exploreUrl()).toBe("https://staging.console.coruscant.com/public");
    expect(consoleUrl("plans")).toBe("https://staging.console.coruscant.com/plans");
  });

  it("builds a mailto for enterprise contact", () => {
    expect(enterpriseContactUrl()).toMatch(/^mailto:enterprise@coruscant\.com\?subject=/);
  });
});
