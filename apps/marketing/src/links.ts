// Outbound targets for the marketing site. Marketing is a standalone public site with
// NO backend of its own — every call to action points at the console (a different origin)
// or an email. The console origin is env-configurable so previews can point at staging;
// it defaults to production. Pure and total, so the CTA builders are unit-testable.

const DEFAULT_CONSOLE_URL = "https://console.coruscant.com";

/** The console origin, without a trailing slash. */
export function consoleOrigin(): string {
  const raw = import.meta.env.VITE_CONSOLE_URL ?? DEFAULT_CONSOLE_URL;
  return raw.replace(/\/+$/, "");
}

/** A URL into the console app for the given absolute path (must start with "/"). */
export function consoleUrl(path: string): string {
  const p = path.startsWith("/") ? path : `/${path}`;
  return `${consoleOrigin()}${p}`;
}

/** Where "Explore public knowledge" lands — the console's free public discovery surface. */
export const exploreUrl = () => consoleUrl("/public");

/** Where "Sign in" lands — the console login. */
export const signInUrl = () => consoleUrl("/login");

/** Enterprise contact. No sales backend exists yet, so this is a mailto placeholder. */
export const ENTERPRISE_EMAIL = "enterprise@coruscant.com";
export const enterpriseContactUrl = () =>
  `mailto:${ENTERPRISE_EMAIL}?subject=${encodeURIComponent("Enterprise access — Coruscant")}`;
