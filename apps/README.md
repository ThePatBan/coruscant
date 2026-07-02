# `apps/` — Frontend surfaces

Coruscant's frontend is planned as **three independently deployable surfaces**. Each is
a distinct audience, domain, and deploy target. They share a backend (the FastAPI service
in `src/coruscant/`) but are separate builds — no shared build tooling or npm workspace is
wired up yet (deliberately deferred; see below).

| App              | Domain(s)                          | Audience              | Status |
| ---------------- | ---------------------------------- | --------------------- | ------ |
| `apps/marketing` | `coruscant.com`, `coruscant.com/ai`| Prospects, public web | Planned — README only |
| `apps/console`   | `console.coruscant.com`            | Customers (all tiers) | **Live** — the Vite SPA |
| `apps/admin`     | `admin.coruscant.com`              | Internal operators    | Planned — currently embedded in `apps/console` |

## What each surface owns

- **`apps/marketing`** — the unauthenticated marketing/brand site and the `/ai` story.
  Static/SSG content, no customer data. Does **not** exist as code yet.

- **`apps/console`** — the customer-facing product. This is the entire current SPA and the
  only real frontend app today. It contains:
  - **public discovery** — search, company profiles, the relationship graph (`/atlas`),
    evidence, and what-changed; usable without an account;
  - **personal workspace** — live signals (`/world`), risk/country reads, portfolio
    exposure, watchlists, alerts;
  - **enterprise workspace** — the org-level preview/gate (shared workspaces, API access,
    policy/audit), entitlement-gated;
  - the **existing embedded admin route** (`/admin`, `src/pages/AdminPage.tsx`) — kept
    inside the console **for now**; extracting it into `apps/admin` is a later phase.

- **`apps/admin`** — the internal operations console (LLM gateway/admin, tenant and
  entitlement management, ingestion controls). Today this lives as a route inside
  `apps/console`; `apps/admin` is a placeholder for the eventual standalone app.

## Conventions

- Each app is self-contained: its own `package.json`, `Dockerfile`, and build. No app
  imports another app's source.
- Shared code (a future `packages/ui`, `packages/api-client`, `packages/auth-client`) is
  **not** extracted yet — each app currently carries what it needs.
- CI builds `apps/console` (the `console` job in [../.github/workflows/ci.yml](../.github/workflows/ci.yml)).
  Add a job per app as each becomes real.

## Deliberately deferred

To keep this move behavior-preserving, the following are **not** done yet and belong to
later phases:

- npm workspaces / a monorepo package manager root;
- `packages/*` shared libraries;
- splitting `AdminPage` out of `apps/console` into `apps/admin`;
- any real code in `apps/marketing` or `apps/admin`.
