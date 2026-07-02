# `apps/marketing` — Marketing site

**Deploy target:** `coruscant.com` and `coruscant.com/ai`
**Audience:** prospects and the public web
**Status:** live app — built in Phase 10.

The unauthenticated brand/marketing surface: the product story and the three-product map.
Static SPA, **no backend of its own** and **no customer data** — every call to action links
out to the console (`console.coruscant.com`) or an email.

## Pages

- `/` — home: the value proposition, the three products, the evidence principle.
- `/ai` — the AI analyst story (grounded, source-cited answers).
- `/public` — Public Knowledge (free discovery).
- `/personal` — Personal Console (monitoring).
- `/enterprise` — Enterprise Intelligence (+ an explicit "Planned" roadmap section).

## Calls to action

- **Explore public knowledge** → `${console}/public` (the free discovery surface).
- **Sign in** → `${console}/login`.
- **Contact enterprise** → `mailto:` (no sales backend exists yet — placeholder).

The console origin is `VITE_CONSOLE_URL` (defaults to `https://console.coruscant.com`);
CTA builders live in [`src/links.ts`](src/links.ts) and are unit-tested.

## Positioning & honesty

Copy is grounded in current capabilities (see `PRODUCT.md` and the console's workspace
definitions). Anything not yet built — SSO/SCIM, billing, private connectors,
ownership/PEP pathways — appears **only** under an explicit "Planned" heading. Coverage is
described as a curated sample, never as exhaustive.

## Develop

```bash
npm install
npm run dev      # http://localhost:5175
npm test         # vitest — pure link builders
npm run build    # tsc -b && vite build
```

## Design system

Reuses the brand **tokens** (colors, radii, fonts, the logo treatment) in
[`src/marketing.css`](src/marketing.css) so it stays on-brand — but it deliberately does
**not** import the console's app-shell stylesheet or any console internals (a landing page
is a different surface). Whether the shared tokens become a package is the Phase 11
duplication-audit decision.

See [../README.md](../README.md) for the full frontend-surface map.
