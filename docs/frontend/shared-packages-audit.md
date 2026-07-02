# Frontend shared-packages audit (Phase 11)

**Date:** 2026-07-02
**Decision:** **No-op by design.** No `packages/*` are extracted in this phase. This
document is the audit result and the deferred extraction plan.

The three frontend apps (`apps/console`, `apps/admin`, `apps/marketing`) each remain
self-contained: their own `package.json`, lockfile, `Dockerfile`, and build.

## Why no-op — the short version

Real duplication exists, but only between **console and admin**, and it is bounded. A
*clean* extraction into shared packages requires introducing npm workspaces **and**
restructuring every app's Docker build context — a large, deployment-affecting change.
The current duplication does not yet churn enough to justify that cost. We keep the copies
and revisit when it does.

## What was measured

| Asset | console | admin | marketing | Verdict |
| --- | --- | --- | --- | --- |
| `src/index.css` (design system) | 111,733 B / 5,533 lines | **byte-identical copy** | — (own 8.7 KB `marketing.css`) | Real dup (console↔admin) |
| `src/hooks.ts` (`useAsync`) | 33 lines | **identical** | — | Real dup (console↔admin), small |
| API transport (`BASE`, `tokenStore`, `ApiError`, `request`, `get`, `post`) | in `api.ts` | near-identical (~50 lines) | — (no api client) | Real dup (console↔admin); 401 behavior **intentionally differs** (console → `/login`, admin → reload) |
| `tsconfig.json` / `tsconfig.node.json` | ✓ | identical | identical | Config dup (all three) |
| auth provider (`auth.tsx`) | full (enterprise entitlement, register) | focused subset (admin gate) | — | **Similar shape, not identical** — sharing would over-generalize |

**Marketing shares none of the above.** It has its own lean stylesheet, no `useAsync`, and
no API client (it is a static site whose CTAs link out). Forcing it to depend on a shared
auth/api/console-CSS package would violate the boundary rule ("don't force marketing to
depend on authenticated console internals"), so marketing is intentionally excluded from
every candidate below.

## Genuine candidates (all console↔admin)

- **`packages/ui`** — the design-system stylesheet (`index.css`) and `useAsync`. This is the
  largest, cleanest duplication (an exact 111 KB copy).
- **`packages/api-client`** — the transport wrapper (`BASE`, `tokenStore`, `ApiError`,
  `request`, `get`, `post`). Note the 401 handling diverges by design, so the shared piece
  is the request/error/token core, with each app keeping its own 401 policy.
- **`packages/config`** — a shared base `tsconfig`. Lowest value; mostly boilerplate.

**Not** candidates: `auth.tsx` (the two providers differ enough that a shared one would be a
fake abstraction), and anything page-level.

## The blocking constraint

Each app's Docker image builds from an **isolated per-app context**:

```
# docker-compose.yml            # .github/workflows/ci.yml
context: ./apps/console         docker build -f apps/console/Dockerfile   ... ./apps/console
context: ./apps/admin           docker build -f apps/admin/Dockerfile     ... ./apps/admin
context: ./apps/marketing       docker build -f apps/marketing/Dockerfile ... ./apps/marketing
```

and every `Dockerfile` does `COPY . .` — i.e. it can only see files **inside its own app
directory**. A `packages/*` directory living outside the app is not in the build context, so
`npm run build` inside the image cannot resolve it. Even a shared base `tsconfig` referenced
via `"extends": "../../packages/config/..."` fails the same way (the path is absent in the
image).

Therefore a clean extraction is not a localized change — it forces:

1. **npm/pnpm workspaces**: a root `package.json` with `workspaces`, a single root lockfile
   (replacing the three per-app lockfiles), and hoisted `node_modules`.
2. **Dockerfile restructure**: build from the repo root (or a `turbo prune`/`pnpm deploy`
   pruned context) so `packages/*` are present; re-do the `COPY` layering and dependency
   install for a workspace layout.
3. **CI changes**: the three `npm ci` steps (currently `cache-dependency-path:
   apps/<app>/package-lock.json`) move to a root install; the `docker` job's build contexts
   and `-f` paths change.
4. **Compose / `.dockerignore`**: build `context: .` for each service with per-app
   Dockerfiles, and re-scope `.dockerignore`.

This is exactly the "large rewrite" the Phase 11 stop condition names.

## Decision & trigger to revisit

**Keep the copies now.** Re-open extraction (starting with `packages/ui`) when **any** of:

- the design system (`index.css`) starts changing often enough that syncing two copies
  causes drift or bugs;
- a third consumer of the app-shell CSS / transport appears (e.g. admin grows, or a fourth
  app needs them);
- the team adopts a monorepo tool (pnpm/turbo/nx) for other reasons, making the workspace +
  Docker-context change cheap rather than a one-off cost.

Until then, the duplication is a deliberate, documented trade — not an oversight. The one
low-risk hygiene step available without the rewrite (a periodic `diff` check that
`apps/admin/src/index.css` still matches `apps/console/src/index.css`) can be added to CI if
drift becomes a concern; it is **not** added now to avoid coupling the two apps' pipelines.
