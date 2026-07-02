import { defineConfig } from "vitest/config";

// The link builders are pure, so tests run in a plain Node environment — no jsdom
// needed. Kept separate from vite.config.ts so the build pipeline (tsc + vite) stays
// untouched.
export default defineConfig({
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
  },
});
