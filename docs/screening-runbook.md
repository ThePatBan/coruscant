# PEP / sanctions screening — operator runbook

Two matchers sit behind one `ScreeningProvider` seam. The graph model, precision
gate, and reversible resolver are identical either way — only the candidate
*scorer* differs.

| Provider | When | Recall | Needs |
|---|---|---|---|
| `deterministic` (default) | quick, offline, CI | exact / near-exact names only | an OpenSanctions export file |
| `yente` | scale + fuzzy / cross-script | OpenSanctions' `logic-v2` scorer | the sidecar below |

## Deterministic (offline)

```bash
coruscant screen --dataset /path/to/opensanctions.json     # bulk targets.nested.json OR a JSON array
```

## yente (sidecar)

`yente` is OpenSanctions' matching service (nomenklatura's scorer + an OpenSearch
index). It runs as a container so its heavy dependencies (ICU, scikit-learn,
OpenSearch) never enter coruscant's Python process.

```bash
docker compose -f docker-compose.screening.yml up -d
# first boot indexes the dataset — watch `docker compose -f docker-compose.screening.yml logs -f yente`
CORUSCANT_SCREENING_PROVIDER=yente CORUSCANT_YENTE_URL=http://localhost:8001 \
  coruscant screen --provider yente
```

Config knobs (all `CORUSCANT_`-prefixed): `YENTE_URL`, `YENTE_DATASET`
(`default` | `sanctions` | `peps`), `YENTE_CUTOFF`, `YENTE_LIMIT`.

## ⚠️ Data & licence

`yente`'s default manifest fetches the **OpenSanctions** dataset, which is
**CC-BY-NC**. Internal development use is pending **written** licence clarification;
it is **not** cleared for external or commercial serving (see
`docs/global-exposure-architecture.md` §6). This gates *shipping a screen to
users*, not building the integration.

To run against your **own or synthetic** data instead (no OpenSanctions fetch),
mount a manifest and point `YENTE_MANIFEST` at it — uncomment the `YENTE_MANIFEST`
env + `volumes` in `docker-compose.screening.yml` and drop a manifest + a
FollowTheMoney dataset under `deploy/yente-manifests/`. See the
[yente manifest docs](https://www.opensanctions.org/docs/yente/).

## What lands in the graph (either provider)

- **Confirmed** (corroborated beyond the name) → `pep` / `sanctioned` edges,
  `access_tier="public"`, valid-time from the listing's `first_seen`.
- **Needs review** (name-only, unconfirmed) → `screening_candidate` edges — a
  candidate, never a determination.
- A reversible resolver judgement per decision (`data/graph/resolver.json`); a
  reviewer confirms/rejects and the graph re-projects from the log.

Surfaced at `GET /graph/screening` (honest `connected:false` until a run) and the
World-tab panel. A low/empty hit list is a real answer — most of our people are
US/UK/India public-company officers and Form-4 insiders (a low base rate).
