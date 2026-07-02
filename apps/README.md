# `apps/` — Frontend surfaces

Coruscant's frontend is **three independently deployable surfaces**. Each is a distinct
audience, domain, and deploy target. They share a backend (the FastAPI service in
`src/coruscant/`) but are separate builds — no shared build tooling or npm workspace is
wired up yet (deliberately deferred; see below).

| App              | Domain(s)                          | Audience              | Status |
| ---------------- | ---------------------------------- | --------------------- | ------ |
| `apps/marketing` | `coruscant.com`, `coruscant.com/ai`| Prospects, public web | **Live** — public marketing SPA (Phase 10) |
| `apps/console`   | `console.coruscant.com`            | Customers (all tiers) | **Live** — the Vite SPA |
| `apps/admin`     | `admin.coruscant.com`              | Internal operators    | **Live** — internal ops SPA (Phase 9) |

## What each surface owns

- **`apps/marketing`** — the unauthenticated marketing/brand site (`/`, `/ai`, and the
  three product pages `/public`, `/personal`, `/enterprise`). A static SPA with **no
  backend of its own**; every CTA links out to the console or an email. It reuses the
  brand **tokens** but not the console's app-shell stylesheet, so it stays decoupled.

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
- CI builds all three apps (the `console`, `admin`, and `marketing` jobs in
  [../.github/workflows/ci.yml](../.github/workflows/ci.yml)); the `docker` job builds all
  three images.

## Deliberately deferred

The following are **not** done yet:

- npm workspaces / a monorepo package manager root;
- `packages/*` shared libraries. Phase 11 audited the duplication across the three apps and
  chose **no-op by design** — real console↔admin duplication exists (`index.css`,
  `useAsync`, the api transport), but a clean extraction requires workspaces + a Docker
  build-context restructure that outweighs the current benefit. See
  [../docs/frontend/shared-packages-audit.md](../docs/frontend/shared-packages-audit.md) for
  the measurements, the blocking constraint, and the trigger to revisit.
