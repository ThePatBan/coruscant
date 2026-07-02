# Console (`apps/console`)

The Coruscant customer-facing SPA — **React + Vite + TypeScript**. Deploys to
`console.coruscant.com` (see [../README.md](../README.md) for the app-boundary map).
Three workspaces sharing one shell (see [../../PRODUCT.md](../../PRODUCT.md) and
`src/workspaces.ts`):

- **Public** — free, discovery-first: search, company profiles, the relationship graph
  (`/atlas`, the labelled stakeholder map), evidence, and what-changed. No account needed.
- **Personal** — the monitoring product: live signals (`/world`), country & risk-
  concentration reads, portfolio exposure, watchlists, and alerts.
- **Enterprise** — org-level: shared workspaces, API access, and policy/audit.

Key files: `src/App.tsx` (shell + routing), `src/workspaces.ts` (the three-workspace
model + anonymous access gate), `src/api.ts` (typed API client), `src/index.css` (the
design system — see [../../DESIGN.md](../../DESIGN.md)).

## Run

```bash
npm install
npm run dev     # SPA on :5173, proxies /api -> :8000
npm run build   # type-check + production build
```

The API must be running (`make api` from the repo root, on :8000). A `Dockerfile`
+ `nginx.conf` serve the built SPA and reverse-proxy `/api` in the docker stack.
