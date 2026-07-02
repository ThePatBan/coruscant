# `apps/` — Frontend surfaces

Coruscant's frontend is **three independently deployable surfaces**. Each is a distinct
audience, domain, and deploy target. They share a backend (the FastAPI service in
`src/coruscant/`) but are separate builds — no shared build tooling or npm workspace is
wired up yet (deliberately deferred; see below).

| App              | Domain(s)                          | Audience              | Status |
| ---------------- | ---------------------------------- | --------------------- | ------ |
| `apps/marketing` | `coruscant.com`, `coruscant.com/ai`| Prospects, public web | Planned — README only |
| `apps/console`   | `console.coruscant.com`            | Customers (all tiers) | **Live** — the Vite SPA |
| `apps/admin`     | `admin.coruscant.com`              | Internal operators    | **Live** — internal ops SPA (Phase 9) |

## What each surface owns

- **`apps/marketing`** — the unauthenticated marketing/brand site and the `/ai` story.
  Static/SSG content, no customer data. Does **not** exist as code yet.

- **`apps/console`** — the customer-facing product. It contains:
  - **public discovery** — search, company profiles, the relationship graph (`/atlas`),
    evidence, and what-changed; usable without an account;
  - **personal workspace** — live signals (`/world`), risk/country reads, portfolio
    exposure, watchlists, alerts;
  - **enterprise workspace** — the org-level preview/gate (shared workspaces, API access,
    organization settings), entitlement-gated.
  - It carries **no internal operations UI**. Admins get a clearly-external link (opens a
    new tab) to `apps/admin` from the user menu; nothing internal renders in the console.

- **`apps/admin`** — the internal operations console (`admin.coruscant.com`): LLM model
  routing + provider keys, and the customers list. Staff-only — it signs in against
  `/auth/login` and admits `role === "admin"` (the API is the real gate: every `/admin/*`
  route is `require_admin`). Extracted from the console in Phase 9.

## Conventions

- Each app is self-contained: its own `package.json`, `Dockerfile`, and build. No app
  imports another app's source.
- Shared code (a future `packages/ui`, `packages/api-client`, `packages/auth-client`) is
  **not** extracted yet — each app currently carries what it needs. `apps/admin` copies the
  console's design-system stylesheet (`src/index.css`) verbatim; extracting it is the
  Phase 11 duplication-audit decision.
- CI builds `apps/console` and `apps/admin` (the `console` and `admin` jobs in
  [../.github/workflows/ci.yml](../.github/workflows/ci.yml)); the `docker` job builds both
  images. Add a job per app as each becomes real.

## Deliberately deferred

The following are **not** done yet and belong to later phases:

- npm workspaces / a monorepo package manager root;
- `packages/*` shared libraries (Phase 11 — extract only where real duplication exists);
- any real code in `apps/marketing` (Phase 10).
