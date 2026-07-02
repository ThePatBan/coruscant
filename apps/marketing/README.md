# `apps/marketing` — Marketing site (planned)

**Deploy target:** `coruscant.com` and `coruscant.com/ai`
**Audience:** prospects and the public web
**Status:** placeholder — no application code yet.

The unauthenticated brand/marketing surface and the `/ai` product story. Static/SSG
content only; it holds **no customer data** and does not talk to the authenticated API.

This directory intentionally contains only this README so the app boundary is visible
and reserved. It is **not** a build target yet — CI does not build it, and no fake
scaffold is committed until there is real content to serve.

See [../README.md](../README.md) for the full frontend-surface map. The live customer
app is [`apps/console`](../console/README.md).
