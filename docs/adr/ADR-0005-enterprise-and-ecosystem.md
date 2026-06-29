# ADR-0005: Enterprise and Ecosystem Seams

## Status

Accepted

## Context

To serve teams and third parties, Coruscant needs collaboration, role-based
access, auditability, programmatic access, and clear extension points — without
coupling the core to a single identity provider, deployment model, or LLM vendor.

## Decision

Implement the concrete primitives now, and expose the larger enterprise concerns
as configuration seams:

**Implemented**
- **Workspaces** — team-shared notes, bookmarks, collections, theses, and
  comments, with membership-based access control (owner + members).
- **RBAC** — users carry a role (`admin` / `analyst` / `viewer`); admin-only
  endpoints are gated by a `require_admin` dependency.
- **Audit log** — an append-only record of security-relevant actions (login,
  watchlist/portfolio/workspace/api-key changes), readable by admins.
- **API keys** — hashed-at-rest keys enable programmatic / third-party access to
  the same public API via `X-API-Key`; the raw key is shown once.
- **Public API / OpenAPI** — FastAPI serves a complete machine-readable spec at
  `/openapi.json` and interactive docs at `/docs`; API keys make it a usable
  ecosystem surface for plugins, integrations, dashboards, and agents.

**Seams (configuration / adapter, documented; not vendor-locked)**
- **SSO** — `require_user` resolves an authenticated principal; an OIDC/SAML
  adapter can populate it from an external IdP instead of password login.
- **Private deployment** — every store is addressed by `database_url`; the stack
  is a self-contained `docker compose` with no external dependencies.
- **Customer-managed LLMs** — the intelligence layer is deterministic behind
  `Protocol` ports (ADR-0004); a customer LLM (or Claude) is an adapter swap
  selected by configuration.
- **Webhooks** — notifications are persisted with stable ids; a webhook delivery
  worker can POST new notifications to a configured endpoint.
- **Compliance** — provenance on every claim, the audit log, and RBAC provide
  the traceability and access controls compliance requires.

## Consequences

- Teams collaborate; admins audit; third parties integrate via keys and OpenAPI.
- No lock-in to an IdP, deployment, or LLM vendor — each is an adapter/config.
- The seams are documented and have clear insertion points, but the heavier
  enterprise integrations (live SSO, webhook delivery worker, signed audit
  export) remain to be built per deployment.

## Date

2026-06-29
