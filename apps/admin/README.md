# `apps/admin` — Internal admin console

**Deploy target:** `admin.coruscant.com`
**Audience:** Coruscant operations staff (admin accounts only)
**Status:** live app — extracted from `apps/console` in Phase 9.

The standalone internal-operations console. It is a separate deployable so that
`console.coruscant.com` stays purely customer-facing and internal operations live on
their own origin.

## What's here

A Vite + React SPA (no router — a single authenticated surface):

- **Model routing** — route each task tier to a provider/model, manage provider keys,
  live-test a tier. (`GET/PUT /admin/llm`, `POST /admin/llm/test/{tier}`)
- **Customers** — every account, its role, join date, and API usage.
  (`GET /admin/customers`)

## Access

Staff-only. The app signs in against `/auth/login`, reads the role from `/auth/me`, and
admits only `role === "admin"` (see [`src/access.ts`](src/access.ts)). This is only a
shell gate — the backend is the real authority: every `/admin/*` route is guarded by
`require_admin` (see `src/coruscant/apps/api.py`).

## API access

Same-origin only. The app calls `/api/*`, which nginx proxies to the API
([`nginx.conf`](nginx.conf)) — the exact-origin model for `admin.coruscant.com`. No CORS
is involved; auth is Bearer-token (no cookies).

## Develop

```bash
npm install
npm run dev      # http://localhost:5174 (proxies /api -> http://localhost:8000)
npm test         # vitest — pure access logic
npm run build    # tsc -b && vite build
```

## Design system

The visual language is the shared Coruscant design system. [`src/index.css`](src/index.css)
is copied verbatim from the console; admin-only chrome is in
[`src/admin-shell.css`](src/admin-shell.css). Extracting the shared stylesheet into a
package is deferred to Phase 11 (see [../README.md](../README.md)).

See [../README.md](../README.md) for the full frontend-surface map.
