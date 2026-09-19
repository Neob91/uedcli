+++
priority = "p3"
kind = "debug"
summary = "DONE — investigated \"too many grid lines when zoomed out on 1uu\"; live + math verification found the escalation algorithm and its React/r3f wiring both correct, matching the disassembly-verified UED22 algorithm exactly. No code bug found; added regression tests locking in the checked properties."
+++

# Ortho grid density report — investigated, no reproducible bug found

Owner report: "I think we're still rendering ALL the grid lines, even on 1uu, when I zoom out, I see
way too many lines there." (`web/src/scene/GridOverlay.tsx`/`grid.ts`, the escalating ortho grid.)

## What was checked

1. **Pure math** (`grid.ts`'s `gridEscalation`/`gridIndices`/`worldGridLines`): re-derived the exact
   algorithm in a standalone Python port and swept `worldUnitsPerPixel` from 4 to 512 (the full clamp
   range) at `baseGridSize=1` (the finest option), for two pane widths (420px quad pane, 843px
   maximized pane). Every sample's predicted line count and drawn step matched hand calculation.
2. **Live wiring** (real headless Chromium, `showcase_bar`, the actual dev server + backend): drove
   the grid-size dropdown to `1`, zoomed an ortho pane out via real `page.mouse.wheel` events across
   the full range (`worldUnitsPerPixel` 4→512, 19 sample points, both quad and maximized pane sizes),
   and read back the LIVE React state (`pose`, `baseGridSize` props via fiber introspection) and the
   LIVE rendered `THREE.BufferGeometry` vertex count from the mounted `GridOverlay`. At every single
   sample point (38 total), the live line count and drawn step matched the pure-math prediction
   exactly — the on-screen spacing consistently landed between 5.66px and 8px, never denser, at every
   zoom level tested. `useMemo`'s dependency array correctly recomputes on every `pose`/`baseGridSize`
   change; `pose` is a freshly-constructed object on every zoom/pan (never mutated in place); the
   `baseGridSize` prop correctly threads from `QuadLayout`'s dropdown down to all three ortho panes.
3. **The design itself**: `dev/docs/spikes/2026-08-30-unrealed-ortho-grid-density/spike.md`
   disassembly-confirms the real UED22 algorithm keeps escalating until lines are >4px apart — this
   codebase's port matches it exactly (already independently confirmed by a prior investigation
   pass before this one started). A 1uu base grid, even correctly escalated, still shows a line
   every ~5.66-8 CSS pixels once fully zoomed out — on a wide/maximized pane that is still a lot of
   lines in absolute count (though not denser than UED22's own design), which may be what read as
   "too many" even though the density matches the real editor.

## Conclusion

No code defect found. The escalation algorithm and its rendering wiring are correct and already
faithfully match the real, disassembly-verified UnrealEd behavior — this was checked freshly rather
than assumed. Nothing was changed in `grid.ts`/`GridOverlay.tsx`.

Two possible explanations for the original report, neither actionable as a code fix here:
- It may have been observed during live development (Fast Refresh / hot-reload), a known class of
  "looks fixed in code but stays broken live" issue this project has hit before for other files
  (`9f469710`, unrelated files) — `GridOverlay.tsx` isn't itself vulnerable to that specific mixed-
  export Fast-Refresh bug (single component export), but a `useMemo` whose deps didn't change across
  a hot-reloaded module edit would still show stale output until the next real zoom/pan — a dev-only
  artifact, not a shippable bug.
- The density itself, while matching UED22 exactly, may just read as "too many lines" on a modern
  wide/high-res display in a way it never would have on a 1990s low-res CRT — a genuine UX question
  about whether to deviate from parity, not a bug. Not raised to the owner in this pass since it
  wasn't asked for and would need an explicit ruling to act on (`CLAUDE.md`'s "no change without
  a yes").

## What shipped

`web/src/scene/GridOverlay.test.tsx` — new regression tests (none existed for this component before):
asserts the live geometry always matches `worldGridLines`'s own prediction, both at a fixed pose and
across a `pose`/`baseGridSize` change (the "stale memo" bug class this report suspected), plus a
sweep asserting the escalation never produces less than the ~4px design floor at `baseGridSize=1`
across the full zoom range. Full frontend suite (442 tests, 50 files) green.
