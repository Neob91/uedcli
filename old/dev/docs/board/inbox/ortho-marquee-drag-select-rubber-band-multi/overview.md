+++
priority = "p?"
kind = "implement"
summary = "ortho marquee drag-select (rubber-band multi-select in ortho panes) — deferred out of gui-slice-2"
depends-on = ["gui-slice-2-quad-layout-ortho-views-matching"]
+++

# ortho marquee drag-select (rubber-band multi-select in ortho panes)

Scoped out of `gui-slice-2-quad-layout-ortho-views-matching` (2026-09-14 spec/plan correction pass)
so the rest of that slice's multi-select work (Ctrl+tap/Ctrl+click add-to-selection, `F` frame,
`Esc` deselect, multi-actor cross-pane highlight) could land without also inventing a new
interaction-model decision.

Two reasons, not one:

1. **A genuinely new mechanism.** Every other selection path in this codebase resolves a single
   screen point to an actor (`selection.ts`'s `resolveHitActor`/`pickActor`). Marquee needs the
   opposite: project every candidate actor's AABB into the CURRENT ortho pane's screen space (via
   `orthoCamera.ts`'s basis for that axis) and test which projected boxes intersect a dragged screen
   rectangle. No code in this repo does that projection today.
2. **An unresolved button conflict, not a planning-time detail.** The main GUI spec
   (`dev/docs/board/to-plan/uedcli-human-gui/spec.md`, "Camera") already binds plain drag in an
   ortho pane to PAN: "Ortho: drag-pan + both-button-drag zoom, plus modern scroll-zoom." Classic
   UnrealEd itself uses plain LMB-drag for marquee-select in ortho views and a DIFFERENT button/
   modifier for pan — this spec's settled camera bindings don't leave a free gesture for marquee
   without either overloading an existing one or introducing a new modifier. Picking one silently
   would be inventing a design decision the owner hasn't made, not filling in an implementation
   detail — needs an explicit ruling (`AskUserQuestion` or a spec amendment) before this item is
   planned.

## What's needed to build this later

- The button/modifier that triggers marquee vs. pan in an ortho pane (see above) — ask, don't guess.
- A screen-space AABB-projection helper (new, `orthoCamera.ts`-adjacent) + a rect-intersection test.
- Wiring into `OrthoViewport`'s drag handling (built in slice 2, `useDragGesture`/`orthoCamera.ts`)
  once the button question is settled.
- Reuses slice 2's `selectionSet.ts`/`selectedNames` model (already multi-actor by the time this
  lands) — no new selection-state design needed, only the geometric hit-test.
