# Coruscant API Contract (v1 — frozen at M1)

The MVP API surface is **frozen**: these paths and their response shapes are
stable. Breaking changes require bumping `api_version` (see `GET /version`); the
authoritative machine-readable schema is the live OpenAPI document at
`/openapi.json` (interactive docs at `/docs`).

`api_version`: **1.0** · `schema_version`: **1.0**

Auth: a bearer token (`Authorization: Bearer …`) from `/auth/login` or an
`X-API-Key` header. Public endpoints are noted; all others require authentication.

## Core platform (stable)

### Public
- `GET /version` — `{api_version, schema_version}`
- `GET /health` — `{status, documents, graph_nodes}`
- `POST /auth/register` · `POST /auth/login` → `{token, email}`
- `POST /auth/logout`
- `POST /auth/reset/request` · `POST /auth/reset/confirm`

### Authenticated — corpus & search
- `GET /auth/me` → `{email, created_at, role}`
- `GET /companies` · `GET /sources`
- `GET /documents` · `GET /documents/{canonical_id}`
- `POST /retrieve` · `GET /answer`
- `GET /graph/company/{slug}`

### Authenticated — observability
- `GET /status` — last ingestion run summary *(any authenticated user)*
- `GET /monitoring` — per-source reliability *(any authenticated user)*

### Admin only (RBAC — `admin` role)
- `GET /admin/audit` — audit log
- `GET /admin/dead-letter` — failed-ingestion dead-letter queue

## Future platform (evolves behind M2+ gates)

These exist but are **not** part of the frozen v1 contract and may change:
`/documents/{id}/summary`, `/companies/{slug}/timeline`,
`/companies/{slug}/changes`, `/compare`, `/entities`, `/entities/{kind}/{key}`,
`/graph/exposure`, `/graph/co-executives`, `POST /analyst/{slug}`,
`/signals/{slug}`, `/dashboard`, `/saved-searches*`, `/watchlists*`,
`/notifications*`, `/portfolios*`, `/workspaces*`, `/api-keys*`, `/usage`,
`/organizations*` (and `/organizations/{id}/plan`, `/organizations/{id}/billing`).

## Stable response invariants

- Every document `canonical_id` is `sha256(source_uri)`; every section carries a
  deterministic `id` (`section_id(canonical_id, order)`).
- Every evidence/claim object carries a `source_uri` (and `canonical_id` where a
  document backs it). No AI-derived field is returned without provenance.
