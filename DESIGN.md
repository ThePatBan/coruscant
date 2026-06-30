# Coruscant — Design System

> Documents the existing system in `frontend/src/index.css`. Extend it; do not
> fork it. New surfaces must read as part of the same instrument.

## Aesthetic

A precise, evidence-forward **intelligence terminal**: near-black surfaces, a single
indigo accent, amber reserved exclusively for provenance / evidence. Calm, dense,
legible. The analyst works here for hours in a dim room on a wide monitor.

## Theme

Dark, and it is *earned*: sustained-focus tool, dim ambient light, long sessions,
data-dense panels where a bright field would fatigue. Not dark "because tools look
cool dark."

## Color (existing tokens — reuse these)

Neutrals (already tinted toward the indigo hue):
- `--bg #090b0f` · `--bg-elev #11141a` · `--bg-elev-2 #161a22` · `--bg-hover #1b2029`
- `--border #232a35` · `--border-strong #313a48`
- `--text #e8ebef` · `--text-muted #9aa4b2` · `--text-faint #6a7585`

Accent (indigo — structure, links, primary): `--accent #7c8cff` · `--accent-strong
#5b6cff` · `--accent-soft` · `--accent-border`.

Evidence (amber — provenance ONLY, never decoration): `--evidence #f3b94d` +
`--evidence-soft` / `--evidence-border`.

Semantic: `--good #4bd6a0` (added / opportunity) · `--danger #ff6b6b` (removed / risk).

**Relation visual language** (for graph + relationship UI): map relation *meaning* to
the existing palette so nothing new competes with provenance amber.
- Leadership / direct control (`employs`) → indigo accent, solid.
- Control-by-proxy (shared leader across companies) → indigo, emphasized / haloed.
- Supply-chain exposure (`relies_on_supplier`, `operates_in`) → evidence amber.
- Peer / rivalry (`competes_with`) → muted neutral, dashed.
- Alliance (`partners_with`, `supplies_to`) → good/teal.
- Product / technology → muted neutral.

## Type

System sans (`--font`); mono (`--mono`) for ids, timestamps, source paths, diff marks.
H1 28 / H2 19 / H3 15, weight 650, letter-spacing -0.02em. Body 15/1.55. Keep prose
≤72ch. Hierarchy comes from weight + scale + the mono/sans split, not color alone.

## Surfaces & spacing

`--radius 12` / `--radius-sm 8` / pill 999. Cards (`.card`) exist but are **not** the
default container — use them only when grouping truly needs an edge. Prefer rails,
dividers, and spatial grouping over nesting. Never nest cards. Stack rhythm via
`.stack.gap-sm|gap|gap-lg`.

## Motion

Subtle, ease-out, fast (0.13–0.16s). Hover affordances on interactive rows/nodes.
No bounce. Respect `prefers-reduced-motion`. Never animate layout properties.

## Evidence affordance

The `↳ source` mono link is a system signature — every derived statement carries one.
Amber is the provenance signal; keep it rare so it stays meaningful.

## Bans (in addition to the shared laws)

- No colored side-stripe borders > 1px. (The legacy `.answer` left-stripe is being
  retired; do not propagate it.)
- No gradient text outside the public landing hero.
- No relationship or number on screen that the API did not return.
