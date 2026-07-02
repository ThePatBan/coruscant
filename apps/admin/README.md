# `apps/admin` — Internal admin console (planned)

**Deploy target:** `admin.coruscant.com`
**Audience:** internal operators
**Status:** placeholder — admin currently lives **embedded in `apps/console`**.

The eventual standalone internal-operations console: the LLM gateway/admin, tenant and
entitlement management, and ingestion/observability controls.

### Where admin lives today

For now the admin surface is a **route inside the console**, not a separate app:

- Route: `/admin` in [`apps/console/src/App.tsx`](../console/src/App.tsx)
- Page: [`apps/console/src/pages/AdminPage.tsx`](../console/src/pages/AdminPage.tsx)

Extracting it into this app (its own build, its own `admin.coruscant.com` deploy, with a
shared auth/api client) is a **later phase**. Until then this directory intentionally
contains only this README so the boundary is visible and reserved — no code is duplicated
here, and CI does not build it.

See [../README.md](../README.md) for the full frontend-surface map.
