# Coruscant Project Context

Repo location:
- `/Users/pathikritbanerjea/src/coruscant`

Current state:
- Full-stack repo: React/Vite frontend + FastAPI/Python backend.
- Architecture framing: the codebase is the **Coruscant Intelligence Platform** (shared, domain-neutral substrate) with the investment-research app as **one workspace** on it — the Portfolio-Exposure Workspace. See `docs/PLATFORM.md` (the platform/workspace split) and `docs/adr/ADR-0013-platform-and-workspace-clarification.md`.
- Core product surfaces exist: `/world`, `/atlas`, dashboard, graph, portfolio, alerts, search, country, documents, settings, admin.
- Evidence-first principle is active: never fabricate coverage, exposure, ownership, or match results.
- Current storage/runtime state is documented in `docs/BUILD-STATE.md`.

Completed roadmap tranches:
1. US coverage hardening
2. User portfolio upload
3. Ownership substrate foundation
4. India coverage
5. UK coverage

Key implemented substrates:
- Whole-exchange coverage pipeline with market-plural provider seam.
- Portfolio resolution/upload flow.
- Ownership edge model and provenance/access-tier handling.
- 13F ingestion, LEI anchoring, screening, and exposure engine.

Current next tranche:
1. Live ownership sources
2. UBO chain-following
3. Contagion and group exposure
4. Live LEI / consolidation expansion
5. UI surfacing for the new substrate
6. Broader market expansion

Important guardrails:
- Keep declared ownership, beneficial ownership, and accounting consolidation distinct.
- Keep unresolved/restricted states explicit.
- Prefer additive changes with tests.
- Do not redo already completed coverage/portfolio/ownership foundation work.

Useful source-of-truth files:
- `README.md`
- `docs/PLATFORM.md` (platform vs workspace split)
- `docs/BUILD-STATE.md`
- `docs/global-exposure-architecture.md`
- `docs/roadmap/Milestones.md`

