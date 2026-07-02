# ADR-0013: Platform / workspace clarification — Coruscant is a platform; the investment app is one workspace

## Status

Accepted (2026-07-02). Extends — does not supersede — [ADR-0006](ADR-0006-foundation-hardening.md)
(the "core vs future platform" *layering* split) with an orthogonal *domain-ownership*
split, and reclassifies the collaboration `workspaces` concept from
[ADR-0005](ADR-0005-enterprise-and-ecosystem.md). The full, living reference is
[`docs/PLATFORM.md`](../PLATFORM.md); this ADR records the decision.

## Context

The repository consistently describes itself as one product — *"portfolio-exposure
intelligence,"* the two tabs at `/world` and `/atlas`. That framing is accurate but
hides the real shape of the code: the majority of the effort — a provenance-first
knowledge graph, entity resolution, ingestion, retrieval, cited intelligence, an LLM
gateway, auth/RBAC, tenancy/billing, ecosystem seams, and collaboration — is
**domain-neutral substrate**. The investment-research features (exposure engine,
coverage, portfolios, pricing, macro, news, the GICS/MSCI ontology) are one **domain**
consuming that substrate.

The distinction is not merely cosmetic. Without it:

- new work (live-ownership UI, more markets, and eventually Public/Professional/
  Enterprise editions) silently inherits investment-research assumptions as if they
  were platform behavior;
- the substrate/product separation that `docs/global-exposure-architecture.md` §0
  already gestures at ("the pillars are not the product") is never made load-bearing;
- the word **"workspace"** is ambiguous — it already names a *collaboration* feature
  (ADR-0005), so it cannot be casually reused for the product-composition concept
  without confusion.

There is also real risk in *over*-correcting: prematurely extracting a general "product
platform SDK," renaming packages en masse, or building a tenant abstraction before a
second workspace exists would be speculative and destabilizing.

## Decision

Adopt one framing, first-class, in docs and in code organization — **without changing
runtime behavior in this phase**:

1. **Name the platform.** The domain-neutral substrate is the **Coruscant Intelligence
   Platform**. Its primitives are enumerated in `docs/PLATFORM.md` §3.

2. **Name the workspace.** The current investment-research application is **one
   workspace** — the **Portfolio-Exposure Workspace** — built on the platform, not the
   platform itself. Future Public / Professional / Enterprise editions are additional
   workspace postures over the same platform (named, not built).

3. **Fix the vocabulary** (`docs/PLATFORM.md` §5):
   - **Workspace (application)** = a composed product surface (primary sense going
     forward).
   - **Collaboration space** = the existing `workspaces` package/feature (a platform
     primitive). It keeps its code name for now to preserve behavior; renaming to
     `collaboration` is deferred to a later, code-touching phase.
   - `access_tier` (data-access classification) and `plan` (commercial tier) stay
     distinct from each other and from a *workspace edition*.

4. **Draw three boundaries** (`docs/PLATFORM.md` §6): shared platform services,
   workspace applications, and legacy product-specific routes/surfaces.

5. **Mark the boundary in code, behavior-preserving:**
   - a platform/workspace classification in each package docstring under
     `src/coruscant/`;
   - a machine-readable manifest in `src/coruscant/packages.py` (previously an empty
     marker), with a test that fails if a new package is left unclassified;
   - `[PLATFORM]` / `[WORKSPACE]` / `[SHARED]` tags on the route-group banners in
     `apps/api.py` and a boundary map in `create_app`'s docstring;
   - shell-vs-product comments in the frontend `App.tsx` navigation model.

6. **Record the coupling seams, do not cut them yet** (`docs/PLATFORM.md` §9): domain
   config in `common`, the monolithic API app, the exposure engine inside
   `knowledge_graph`, finance defaults in generic ingestion, investment taxonomy in the
   intelligence layer, the missing tenant/partition abstraction, and the `workspaces`
   naming collision. Each is marked in Phase 1 and moved in a later phase.

## Consequences

- "The platform" now has one canonical meaning (product-hosting substrate) alongside
  the pre-existing layering sense from ADR-0006; readers are told which is meant.
- The boundary is documented **and** encoded (docstrings + manifest + a guard test + API
  banners), so it is greppable and drift is caught, not just asserted in prose.
- No routes, schemas, stores, or endpoints change; the whole suite stays green. The
  cost is that the boundary is *marked* but not yet *enforced* by module structure — the
  seams in §9 remain real until a later phase moves them. This is deliberate: mark
  before move.
- The next phases can target a named seam instead of re-deriving the boundary.
- New packages must declare a classification (the manifest test enforces it), which
  keeps the split from silently eroding.

## Alternatives Considered

- **Do the refactor now** (split `common`/`knowledge_graph`, add routers, extract an
  `exposure` package, build a tenant abstraction) — rejected for this phase: high blast
  radius, and building a tenant/partition abstraction before a second workspace exists
  is speculative. Phase 1 marks; later phases move.
- **Reuse "workspace" for the product concept without disambiguation** — rejected: it
  collides with the existing collaboration feature (ADR-0005) and would make both
  meanings ambiguous in code and docs.
- **Rename the collaboration `workspaces` package now** — rejected for this phase: it is
  a behavior/imports change (API path, frontend, stores) with no functional benefit
  yet; deferred to a code-touching phase and recorded as a seam.
- **Put the brief in `docs/vision/` or `docs/manifesto/`** — rejected: the load-bearing
  strategy docs live as top-level `docs/*.md` (BUILD-STATE, global-exposure-architecture)
  and are cross-referenced as canonical; `docs/PLATFORM.md` matches that convention.
- **Treat the split as ADR-0006's core/future platform line** — rejected: that is a
  layering/maturity split; platform-vs-workspace is an orthogonal domain-ownership
  split. Both are kept.

## Date

2026-07-02
