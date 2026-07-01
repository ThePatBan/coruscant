# Deployment & Operations (M5)

## Run locally

```bash
make up        # docker compose up --build -d   → http://localhost:8080
make down
```

Demo login (local only): `demo@coruscant.local` / `coruscant-demo`.

## Production

```bash
export CORUSCANT_SECRET_KEY="$(python -c 'import secrets;print(secrets.token_urlsafe(32))')"
export CORUSCANT_CORS_ORIGINS='["https://app.example.com"]'
make prod      # docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

The production overrides ([docker-compose.prod.yml](../../docker-compose.prod.yml)):
- **require** a strong `CORUSCANT_SECRET_KEY` (the stack refuses to start without it),
- disable the demo account (`CORUSCANT_SEED_DEMO_USER=false`),
- stop publishing the API port directly (reach it only via the web proxy),
- set `restart: always` on `api` and `web`.

Scale-out path (documented seams, ADR-0005): point `CORUSCANT_DATABASE_URL` at
PostgreSQL, put the graph behind a real graph store (vendor TBD — the current
JSON-over-SQLite store won't scale to whole-exchange ingestion; ADR-0001), put
embeddings behind pgvector, and front the API with multiple workers.

## Backups

```bash
make backup                          # writes data/<dir>-backup.tar.gz
coruscant backup --out /backups/coruscant-$(date +%F).tar.gz
```

The archive contains the SQLite database (catalog, intelligence, users,
watchlists, portfolios, workspaces, orgs, usage, dead-letter), the graph
snapshot, and the raw/normalized document artifacts — the full platform state.
Restore by extracting the archive over the data directory and restarting.

## Scheduling

`coruscant schedule` shows which sources are due (per-source cadence vs last
successful run). Run `coruscant ingest` (or the `worker` service) on a cron/timer;
only due sources are re-pulled.

## Observability

- `GET /version` — API + schema version (public).
- `GET /health` — liveness + corpus counts.
- `GET /status` — last ingestion run summary.
- `GET /monitoring` — per-source reliability.
- `GET /admin/audit` — security-relevant actions (admin).
- `GET /admin/dead-letter` — failed ingestions for inspection/replay (admin).
- `GET /usage`, `GET /organizations/{id}/billing` — usage analytics & plan limits.
