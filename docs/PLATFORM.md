# Coruscant Intelligence Platform — Platform Brief

**Canonical brief. 2026-07-02.** This file defines what "the platform" *is* and how
it relates to the product you can see today. When another doc talks about "the
platform" loosely, this file is what the term means. It is a **plan-of-record for the
platform/workspace split**, not a claim about what is fully built — [`BUILD-STATE.md`](BUILD-STATE.md)
remains the honest snapshot of what ships today, and this brief marks clearly where a
boundary is *drawn in docs and organization* versus *fully enforced in code*.

---

## 1. Why this document exists

Coruscant began — and still reads, in most of its docs — as a single application:
*"portfolio-exposure intelligence,"* the two-tab investment-research surface at
`/world` and `/atlas`. That framing is true but incomplete. The thing that took the
most effort to build is not the two tabs; it is the **substrate underneath them**: a
provenance-first knowledge graph, entity resolution, ingestion, retrieval, cited
intelligence, LLM routing, auth, tenancy/billing, and collaboration. That substrate is
domain-agnostic. The two tabs are one way to consume it.

This brief makes that distinction first-class:

> **Coruscant is a platform. The investment-research app is one workspace built on it.**

Naming this now — before the next phases (live ownership UI, broader markets, and
eventually Public / Professional / Enterprise editions) — keeps new work from silently
inheriting investment-research coupling as if it were platform behavior.

## 2. The split, in one sentence each

- **The Coruscant Intelligence Platform** is the shared, domain-neutral substrate:
  *turn sourced material into an evidence-bearing, queryable graph, and let identified
  users ask grounded questions of it, under tenancy and access-tier controls.*
- **A workspace** is a composed product surface built on the platform for a specific
  audience and job. Today there is exactly one: the **Portfolio-Exposure Workspace**
  (the investment-research app). It is *a* workspace, not *the* platform.

Everything below is the detail behind those two sentences.

## 3. Platform primitives (the shared substrate)

These are domain-neutral. Nothing here should know the words "portfolio," "holding,"
"GICS," "13F," "Yahoo," "GLEIF," or "yente." Each maps to a package under
`src/coruscant/` (see the boundary map in §7 for the mixed cases).

| Primitive | What it provides | Home |
|---|---|---|
| **Knowledge graph store** | The `KnowledgeGraphStore` port + backends (in-memory / Kùzu), deterministic IDs, provenance on every edge, multi-hop `reachable()` traversal, bitemporal + `access_tier` substrate | `knowledge_graph` (store/substrate/kuzu/memory/persistence), `common/types.py` |
| **Entity resolution & identity** | Reversible resolver (`same`/`different`/`undecided`), merge-resistant clustering, canonical IDs; corporate anchoring seam (LEI/GLEIF) | `knowledge_graph/resolution.py`, `anchoring` |
| **Ingestion** | Source registry, generic pipeline, orchestrator, scheduler, dead-letter — sources register a definition, they do not fork core | `ingestion`, `connectors` (interfaces) |
| **Document corpus & retrieval** | Raw/normalized document repositories, catalog, hybrid (lexical+vector) search, template reasoning | `infrastructure` (repositories/catalog), `search` |
| **Cited intelligence** | Summaries, diffs, event/change extraction — every output a sourced `Claim`, LLM adapters behind Protocol ports | `intelligence` (mechanism half — see §7) |
| **LLM gateway** | Provider-agnostic, tiered model routing (`LLMGateway`, tiers, routes) | `llm` |
| **Identity & access** | Users, PBKDF2/JWT auth, RBAC (admin/analyst/viewer) | `auth` |
| **Tenancy, plans & billing** | Organizations, plans (free/pro/enterprise), usage metering, quota, billing summaries | `commercial` |
| **Ecosystem seams** | Programmatic API keys, append-only audit log; SSO / private-deploy / customer-LLM as documented seams | `enterprise` |
| **Collaboration** | Team-shared notes/theses/bookmarks/collections/comments with membership ACL (the `workspaces` package — a *collaboration space*, see §5) | `workspaces` |
| **Delivery** | Notification matching + delivery mechanism (the taxonomy it matches on is workspace-specific) | shared mechanism in `watchlists`/API |

The runtime plumbing that assembles these — `apps/api.py` (HTTP), `apps/runtime.py`
(store/pipeline wiring), `apps/cli.py`, `apps/worker.py` — is platform, but today it
also wires product pipelines into the same objects (see §9, seam 2).

## 4. Workspace applications (the product layer)

A **workspace** composes platform primitives into a coherent product for an audience.
It owns: a domain vocabulary, a set of pipelines/connectors, a set of API resources, a
navigation surface, and (eventually) a tenancy/tier posture.

### The Portfolio-Exposure Workspace (today's product)

The current investment-research app **is** this workspace. It answers *"an event
happens somewhere — does it touch my portfolio, and how?"* It contributes, on top of
the platform:

- **Domain vocabulary** — companies, holdings, funds, GICS sectors, MSCI market tiers,
  commodities, sovereign/corporate debt, ownership/UBO, PEP/sanctions.
- **Pipelines & connectors** — whole-exchange coverage (US/IN/GB), 13F portfolio front
  door, ownership sources (BODS/PSC/GLEIF-L2), and the finance connectors.
- **The exposure engine** — the geographic / sector / market-tier / commodity / debt /
  contagion pathways that trace an event to the holdings it touches.
- **Live feeds** — prices (Yahoo), macro (World Bank), news (GDELT), all gated.
- **Surfaces** — `/world` (Home/World), `/atlas` (company graph), and the supporting
  dashboard/risk/country/portfolio pages.

Packages that are wholly this workspace: `portfolio`, `pricing`, `macro`, `news`,
`coverage`; workspace-flavored: `ownership`, `screening`, `watchlists` (taxonomy),
and the exposure/taxonomy code inside `knowledge_graph` (see §7).

### Future workspaces (named, not built)

The commercial tiers already sketched in `commercial` (free/pro/enterprise) and the
enterprise seams (`enterprise`) point at three editions of the product, each a
workspace posture over the *same* platform and, largely, the same Portfolio-Exposure
domain:

- **Public** — open, low-friction, aggressively free-tier; heavily `access_tier: public`
  data only.
- **Professional** — the allocator/analyst instrument; the full exposure engine, gated
  live feeds, collaboration.
- **Enterprise** — SSO, private deployment, customer-managed LLMs, RBAC, audit, higher
  quotas, `restricted-authority` data access where licensed.

These are **not** implemented and this phase does not build them. They are recorded so
the boundary we draw now is drawn *toward* them.

## 5. Terminology (read this before using the word "workspace")

The word **workspace** is overloaded in this repo. Disambiguate deliberately:

- **Workspace (application)** — *this brief's primary sense.* A composed product surface
  on the platform (Portfolio-Exposure today; Public/Professional/Enterprise later).
- **Collaboration space** — the existing `workspaces` package and `/workspaces` API/UI:
  team-shared notes, theses, bookmarks, collections, comments (ADR-0005). This is a
  **platform primitive**, not a product edition. It keeps the code name `workspaces`
  for now to preserve behavior; a later phase may rename it to `collaboration` to
  remove the collision. **Do not conflate the two.**

Two more distinctions that already exist and must not be merged:

- **`access_tier`** (`public` / `legitimate-interest` / `restricted-authority` /
  `aggregator-licensed`) is a **data-access** classification on graph edges (ADR-0007,
  0011, 0012). It is enforced at query time and is *independent* of commercial plans.
- **Plan** (`free` / `pro` / `enterprise` in `commercial`) is a **commercial** tier:
  quotas and billing. A future *workspace edition* (Public/Professional/Enterprise) is
  a product composition that will *use* both `access_tier` and `plan`, but is not
  identical to either.

Finally: **"platform"** in older docs (M2 "Source Platform," ADR-0006's "core vs future
platform," `docs/api/Contract.md`) means *runtime/architecture layers*, not "a base
that hosts multiple products." This brief introduces the product-hosting sense; both
senses now coexist and the reader should note which is meant.

## 6. The three boundaries

The phase brief asks for three boundaries to be drawn. Here they are, mapped to code:

1. **Shared platform services** — §3. Domain-neutral, reusable by any workspace.
   Code: `common` (minus the domain config, §9), `knowledge_graph` (store/substrate),
   `anchoring`, `ingestion`, `connectors` (interfaces), `infrastructure`, `search`,
   `intelligence` (mechanism), `llm`, `auth`, `commercial`, `enterprise`, `workspaces`.

2. **Workspace applications** — §4. The Portfolio-Exposure Workspace: `portfolio`,
   `pricing`, `macro`, `news`, `coverage`, plus the workspace-flavored `ownership`,
   `screening`, `watchlists`, the exposure/taxonomy code in `knowledge_graph`, and the
   finance connectors/source-registry defaults.

3. **Legacy / product-specific routes & surfaces** — endpoints and pages that predate
   the split and encode the product directly: the `/graph/*` exposure family, the
   product-scoped intelligence endpoints (`/dashboard`, `/analyst`, `/signals`,
   company timeline/changes), the retired-but-routed frontend pages
   (`/companies /graph /portfolio /watchlists /workspaces /documents /compare /sources
   /monitoring`, per the `TODO(retire)` block in `frontend/src/App.tsx`), and the
   product nav spine. These stay working; they are *labelled* now and *relocated* in a
   later phase — not rewritten here.

## 7. Package boundary map

Classification of every package under `src/coruscant/`. **Platform** = domain-neutral
substrate. **Workspace** = Portfolio-Exposure product. **Mixed (seam)** = a package
that fuses both and is a named seam to split later (§9).

| Package | Class | Note |
|---|---|---|
| `common` | Mixed (seam) | Types/errors/logging are platform; `config.py` domain models (`CompanyConfig`, `CommodityConfig`, `DebtConfig`, `InstrumentsConfig`) and product `Settings` flags are workspace. |
| `knowledge_graph` | Mixed (seam) | `store`/`substrate`/`persistence`/`resolution`/`memory`/`kuzu_store`/`textmatch` are platform; `queries.py` (exposure engine), `taxonomy.py` (GICS/MSCI), `ownership_graph.py`, `entities.py` are workspace. |
| `anchoring` | Platform (corporate-scoped) | Identity/keys pillar; provider seam. Scoped to corporate legal-entity resolution (GLEIF LEI). |
| `ingestion` | Mixed (seam) | Orchestrator/registry/scheduler/pipeline are platform; `registry.py` default definitions are all finance sources. |
| `connectors` | Mixed (seam) | Interfaces are platform; every concrete connector is finance. |
| `infrastructure` | Platform | Repositories, catalog, dead-letter, saved-searches, status. (`intelligence_store` persists product intelligence keyed by `company_slug`.) |
| `search` | Platform | Hybrid retrieval over `NormalizedDocument`. |
| `intelligence` | Mixed (seam) | Summarize/diff/extract mechanism is platform; `_MATERIAL_CATEGORIES`/`EVENT_CATEGORIES` and `company_slug` keying are workspace. |
| `llm` | Platform | Provider-agnostic tiered routing. |
| `auth` | Platform | Users, auth, RBAC. |
| `commercial` | Platform | Orgs, plans, usage, billing. |
| `enterprise` | Platform | API keys, audit, ecosystem seams. |
| `workspaces` | Platform | Collaboration space (see §5) — *not* a product workspace. |
| `screening` | Workspace-flavored | Reusable ER pipeline; domain is compliance/finance (PEP/sanctions). |
| `ownership` | Workspace-flavored | Graph-substrate shape, corporate-ownership/UBO domain. |
| `watchlists` | Workspace | Notification mechanism is generic; watch taxonomy is investment-domain. |
| `coverage` | Workspace | Whole-exchange listed-issuer universe + holdings resolution. |
| `portfolio` | Workspace | Holdings, funds, 13F, briefings. |
| `pricing` | Workspace | Live equity quotes, sector-ETF benchmark. |
| `macro` | Workspace | Country macro for the World tab. |
| `news` | Workspace | Business-news feed for the World tab. |
| `apps` | Platform (assembly) | HTTP/CLI/worker/runtime. Assembly is platform; it currently wires product pipelines directly (§9, seam 2). |

The same platform/workspace tags are mirrored in code as package docstrings, in the
machine-readable manifest [`src/coruscant/packages.py`](../src/coruscant/packages.py)
(with a test that fails if a new package is left unclassified), and in the route-group
banners of `apps/api.py`.

## 8. What is intentionally product-specific (and stays that way)

Not everything should be generalized. The following are *correctly* investment-domain
and this phase deliberately leaves them coupled to the Portfolio-Exposure Workspace:

- The **exposure engine** and its pathways (`knowledge_graph/queries.py`) — this is the
  product's core value, not a platform primitive.
- **GICS / MSCI taxonomy**, commodities, debt instruments — a finance ontology.
- **Coverage / portfolio / pricing / macro / news** packages — they exist to serve the
  product surface.
- The **finance connectors** and the finance default **source registry**.
- The **watch taxonomy** (`company/industry/executive/topic/keyword/country/supply_chain`).
- The product **navigation spine** and the `/world`, `/atlas` surfaces.

Generalizing these prematurely would be over-abstraction with no second consumer to
justify it. They become a *workspace* concern, not a *platform* concern — the boundary
is about where they live and what depends on them, not about erasing them.

## 9. Known coupling seams to resolve in later phases

Drawing the boundary in docs and organization was Phase 1. Enforcing it in code is
later, deliberate work — **Phase 2 (ADR-0013) enforced seams 1 and 2 and wrapped seam 3
at the API layer**; the rest remain. The concrete seams, in rough priority order:

1. **Domain config in the shared layer.** `common/config.py` defines investment models
   (`CompanyConfig`, `CommodityConfig`, `DebtConfig`, `InstrumentsConfig`) and product
   flags on `Settings` (`enable_live_prices/macro/news`, screening/anchoring/
   companies-house). A platform `Settings` should not import a domain schema. → move
   domain config into a workspace config module. **✅ Phase 2: isolated** — the domain
   models moved to `common/domain_config.py` (re-exported from `common/config.py` for
   compatibility); the product *flags* on `Settings` remain (follow-up).
2. **Monolithic API app.** `apps/api.py` declared all ~95 routes on one `FastAPI` with
   no routers, and `_AppState` bundles platform stores with product services. → split
   into a platform router set + a Portfolio-Exposure workspace router, composed at
   assembly time. **✅ Phase 2: done (composition level)** — routes are split across a
   `plat` (platform) router and a `pe` (Portfolio-Exposure) router, mounted via the
   `apps/composition` registry (`enabled_workspaces()`). Behavior-preserving (no prefix;
   route table unchanged). The `_AppState` store bundling remains (follow-up).
3. **Exposure engine inside `knowledge_graph`.** The generic store and the product
   query engine share a package. → extract `queries.py`/`taxonomy.py`/`entities.py`
   into a workspace `exposure` package that depends on the store port. **◐ Phase 2:
   wrapped at the API layer** — the exposure endpoints are isolated on the `pe` workspace
   router; the physical package extraction is still pending.
4. **Finance defaults wired into generic ingestion.** `ingestion/registry.py` default
   definitions are finance-only. → move defaults into the workspace; keep the registry
   empty/pluggable at the platform layer.
5. **Investment taxonomy in the intelligence layer.** `_MATERIAL_CATEGORIES` /
   `EVENT_CATEGORIES` and `company_slug` keying. → parameterize the category set per
   workspace.
6. **No tenant/workspace data-partition abstraction.** Every user resource is scoped by
   `email`; the graph/corpus is one global store; the org is a billing label only. A
   real multi-workspace platform needs a workspace/tenant boundary object. → design
   alongside the first *second* workspace, not before.
7. **`workspaces` naming collision.** Resolve by renaming the collaboration package to
   `collaboration` once a code-touching phase is warranted (§5).

Each of these was behavior-preserving to *mark* (Phase 1) and a real refactor to
*move* (later). Phase 2 moved seams 1 and 2 and wrapped seam 3; seams 4–7 remain, each
to be done when it is the highest-value next step — not speculatively.

## 10. How future workspaces compose (the evolution path)

The target shape, stated so the boundary is drawn toward it:

```
                 Workspace applications (product surfaces)
   ┌────────────────┬──────────────────┬────────────────────┐
   │ Portfolio-     │ Public / Prof. / │  (future domains)   │
   │ Exposure       │ Enterprise edn.  │                     │
   └────────────────┴──────────────────┴────────────────────┘
        composes ▲ owns domain vocab, pipelines, resources, nav, tier posture
   ─────────────────────────────────────────────────────────────
        Coruscant Intelligence Platform (shared substrate)
   graph store · entity resolution · ingestion · corpus/search ·
   cited intelligence · LLM gateway · auth/RBAC · tenancy/plans/billing ·
   ecosystem seams · collaboration · delivery
```

A new workspace should be able to: register its connectors/sources, contribute its
domain nodes/edges to the shared graph, mount its API router, add its nav surface, and
declare its tier/`access_tier` posture — **without editing platform packages.** How far
today's code is from that is exactly the seam list in §9.

## 11. Relationship to existing decisions

- **ADR-0005** (Enterprise & Ecosystem Seams) defined the collaboration `workspaces`,
  RBAC, audit, API keys, SSO/private-deploy seams. This brief classifies all of those
  as **platform**, and renames the *concept* (collaboration space) to free the word
  "workspace" for the product sense (§5).
- **ADR-0006** (Foundation Hardening) drew a **core platform vs future platform** line —
  a *layering/maturity* split. This brief adds an orthogonal **platform vs workspace**
  line — a *domain-ownership* split. Both are valid and coexist.
- **ADR-0007 / 0011 / 0012** established `access_tier` and the ownership substrate;
  §5 keeps `access_tier` distinct from commercial plans and product tiers.
- **`docs/global-exposure-architecture.md`** §0 already separates *substrate* from
  *product* ("the pillars are not the product"). This brief names that substrate the
  **platform** and names the product a **workspace**, and makes the split first-class.
- **ADR-0013** records the decision behind this brief; this file is the fuller,
  living reference.

---

*Companion decision record: [ADR-0013](adr/ADR-0013-platform-and-workspace-clarification.md).
Honest current state: [BUILD-STATE.md](BUILD-STATE.md). Plan of record for the exposure
substrate: [global-exposure-architecture.md](global-exposure-architecture.md).*
