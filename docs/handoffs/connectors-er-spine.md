# Handoff — Bulk connectors & the Entity-Resolution spine (backend)

Paste this into a new session. It continues the **plan of record**
([docs/global-exposure-architecture.md](../global-exposure-architecture.md)) now
that the **graph store is done** (this was the blocker; it no longer is).

> **North star:** portfolio-exposure intelligence — *"an event happens somewhere;
> does it touch my book, and how?"* Orientation over reading. **#1 rule: never
> fabricate** — every edge carries its source statement; a gap shows a labelled
> stub, never a placeholder.

---

## Read first (decisions live here)

- **Auto-memory `MEMORY.md`**, especially: `coruscant-global-vision` (the four
  pillars + the sequenced plan), `coruscant-graph-store` (what the store now is —
  read this, it changes your starting assumptions), `coruscant-product-spec`,
  `coruscant-north-star`.
- **[docs/BUILD-STATE.md](../BUILD-STATE.md)** — the single source of truth for
  what actually exists.
- **[docs/global-exposure-architecture.md](../global-exposure-architecture.md)** —
  §3 (pillars/sources), **§4 (entity resolution — the wall)**, **§5 Phase 0–1**
  (your scope), §6 (cost/access risk list). §2 = the invariants below.

## Where we are (all merged to main; store session, PRs #31–#33)

The graph store was the Phase-0 load-bearing prerequisite. **It's built:**
- **Kùzu** (embedded, disk-based, Cypher-native; free/MIT) behind the stable
  `KnowledgeGraphStore` port — the exposure engine + API query it, backend is
  swappable to Neo4j/Neptune later (a DSN change, not a rewrite; ADR-0001).
- **Ingest is O(E)** (the O(E²) dedup is gone), serving is indexed/columnar.
- **Multi-hop traversal exists:** `store.reachable(kind, key, relation, max_hops,
  direction)` — native variable-length `SHORTEST` Cypher on Kùzu, BFS default
  elsewhere. `company_network` / `GET /graph/company-network` proves it with
  per-hop evidence chains. **This is the primitive your `owns*` / `beneficial_owner_of*`
  / `supplies*` traversals will reuse — swap the relation, raise the depth.**
- Golden cross-backend parity test guards every exposure query.

**The graph today:** 53 Company · 661 Person · 152 Subsidiary · 58 Filing +
GICS/MarketTier/Commodity/Debt/Country; ~1,080 nodes. Provenance on every edge.
`has_subsidiary` is a subsidiary-NAME list (no %, no holder). There is **no
ownership / UBO / PEP / sanctions edge yet, and no portfolio/holding concept.**

## Your task: stand up the ER spine, then screen the people we already have

This is **Phase 0 (remaining) → Phase 1**. The store is ready to host it; what's
missing is identity + the connectors. Free-first at every step.

**Phase 0 — Substrate & keys (the load-bearing quarter):**
1. **Internal surrogate ID = the primary key.** LEI/CIK/DIN/registry-number are
   *anchors*, never the PK (LEI covers <1% of companies). Decide how a
   `canonical_id` rides on the graph (a property on the node + a **resolution
   table** mapping raw node → canonical cluster; keep it reversible/versioned).
   **Canonical IDs must be stable across re-resolution** — a customer's bookmark
   can't change because registries updated overnight.
2. **ER service: `nomenklatura` / `yente`** (OpenSanctions' MIT stack) — native to
   FollowTheMoney (zero impedance with our statement model), deterministic +
   auditable scorer, and a **Resolver that is a reversible graph of
   `same`/`different`/`undecided` judgements**. Stand it up (Docker), self-hosted.
3. **Resolve the 152 subsidiary strings** (the hardest ER target — a name + a US
   state, no key; 14% of nodes). Link `Subsidiary` → `Company` where a real match
   exists; leave the rest explicitly unresolved. **Do not over-merge.**
4. **GLEIF Golden Copy** (free bulk) as the LEI anchor → enrich `Company` nodes.

**Phase 1 — PEP/sanctions on the 661 people (fastest wow):** screen the existing
`Person` nodes against **OpenSanctions** PEP (~949K) + sanctions on **on-prem
yente** (bulk, not the metered API) → `pep`/`sanctioned` edges, each with source +
`access_tier`. *Caveat:* ~half our Person nodes are **Form-4 insider-holders**,
not officers — a different PEP base rate; expect a low hit rate and design for it.
Internal-only until the OpenSanctions license is clarified in writing (gates
*external* demo, not building).

## The four corrections that actually bite (from §4 — do not skip)

1. **Clustering must be merge-resistant, NOT connected-components.** `A~B` and
   `B~C` at 0.9 does *not* imply `A~C`; connected-components silently fuses
   unrelated multinationals on one bad bridge. Use correlation/weighted clustering
   with persisted `different` judgements that break bridges. **#1 ER risk.**
2. **Benchmark F1 ≠ production accuracy.** The ~98% numbers are on attribute-rich
   sanctions/PEP pairs. Our hardest target is the 152 thin subsidiary strings —
   plan for far lower real precision there.
3. **Person ER is harder & higher-stakes than company ER.** Name-only against 949K
   PEPs floods false positives ("Wang Wei"), and **a false-positive PEP hit on a
   customer's counterparty is a defamation/discrimination exposure, not a data
   blip.** Requires a precision gate + a bounded human-review path — not
   hand-waving.
4. **A merge you can't undo is a bug.** Keep the resolver reversible + versioned.

## Invariants (non-negotiable; §2)

No edge without evidence · surrogate PK, external IDs are anchors · native-script
canonical (romanization is an alias/blocking key, never the sole merge basis) ·
`owns%` ≠ `beneficial_owner_of` ≠ `consolidates` (three edge types, never
equated) · absence is signal (`parent_unknown{reason}`, `ended{reason}` — not
delete; **GDPR-erasure for EU natural persons is the one exception → tombstone**)
· **bitemporal** (valid-time + system-time; "was X sanctioned *on the transaction
date*?") · **`access_tier` rides every UBO edge** + a query-time policy engine
enforces it.

**The store leaves room for these, unbuilt:** bitemporal + `access_tier` = extra
edge columns; the ER resolver = a table alongside the graph. Add them here.

## Watch-outs on access/licensing (§6 — clarify in writing, early)

OpenSanctions is **CC-BY-NC → paid Reseller/OEM for commercial**; dev-time use
needs written clarification. OpenCorporates is **D&B-owned now** (not an open
pillar). EU UBO public access collapsed (CJEU 2022); US CTA is non-public. These
gate *external launch*, not *building* — but start the license conversations now.

## Working discipline

- **Before merging, full CI locally, all green:**
  `ruff check src tests` · `mypy src` ·
  `env -u CORUSCANT_CONFIG_DIR -u CORUSCANT_DATA_DIR -u CORUSCANT_DATABASE_URL python3 -m pytest tests/ -q`
  · `(cd frontend && npm run build)`.
- **New graph edge types** (pep/sanctioned/owns%/beneficial_owner_of): add a
  **golden-parity case** (memory vs kuzu) and keep provenance on every edge.
- **Git/PR flow:** branch off main; commit trailer
  `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`;
  `gh auth switch --user ThePatBan` to push + open + merge the PR, then
  `gh auth switch --user sentinel-agentic` and fast-forward local main.
- **Run the API locally to verify:** kill any uvicorn, then
  `SSL_CERT_FILE=$(python3 -m certifi) CORUSCANT_DATA_DIR=$PWD/data
  CORUSCANT_DATABASE_URL=sqlite:///$PWD/data/coruscant.db
  CORUSCANT_CONFIG_DIR=$PWD/deploy/dow-config CORUSCANT_SECRET_KEY=dev-local-secret
  CORUSCANT_SEED_DEMO_USER=true CORUSCANT_DEMO_PASSWORD=coruscant-demo
  python3 -m uvicorn coruscant.apps.api:app --host ::1 --port 8000`
  (login: demo@coruscant.local / coruscant-demo; startup builds the Kùzu DB, give
  it ~8s). Auth field is `token`, not `access_token`.

## Suggested first slice (demoable, free, low-risk)

Stand up yente in Docker → ingest OpenSanctions bulk → screen the 661 `Person`
nodes → write `sanctioned` / `pep` edges with source + `access_tier="public"` →
surface as a labelled panel (honest empty/low-hit state). That is the fastest
"wow" and exercises the whole spine (connector → ER → provenance edge → query)
before tackling the harder 152-subsidiary company ER.

> **Critical path:** (store ✅) → surrogate keys + yente ER spine → screen 661
> people (PEP/sanctions) → resolve 152 subsidiaries + GLEIF anchor → portfolio
> edges (13F, Phase 2) → UK-PSC ownership (Phase 3) → GDELT event-proximity
> (Phase 4) → paid magnitude last. Free at every tier first.
