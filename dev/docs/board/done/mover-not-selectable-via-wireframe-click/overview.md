+++
priority = "p1"
kind = "debug"
summary = "FIXED -- a Mover's always-visible outline was never a raycast candidate outside wireframe mode"
+++

# Mover not selectable via its wireframe outline in non-wireframe mode

Fixed: `tapSelect.ts`'s `brushObjects` candidate array (fed from `BrushOutlines`' rendered ring
objects) was only passed non-empty in wireframe mode, so a Mover's always-visible outline -- the only
thing drawn there when "Movers:on" is off -- was never a raycast target outside wireframe mode.

`BrushOutlines.tsx` now renders a Fragment of two sibling groups instead of one: the original
`groupRef` group (ordinary brushes + any selected actor's bold ring, unchanged, still
wireframe-mode-gated) and a new `moverGroupRef` group holding just the unselected-Mover thin-ring
`MergedThinWireframe`, exposed to `tapSelect.ts` as `moverOutlineObjects` and wired in EVERY mode.
Scoped to Movers only (not every brush's outline) so this never changes how an ordinary brush is
picked in non-wireframe mode.

Needed a real hit-ranking fix too, not just wiring the candidate in: a Mover's outline renders
`depthTest: false` (always composites on top, per `mover-wireframe-occluded-by-geometry`), so
clicking it can coincide with a real precise hit on the wall/floor it doesn't occlude -- the OLD
"always take the nearest precise hit" rule picked the wrong (wall) actor every time. `selection.ts`'s
new `pickHit` (unit-tested, `selection.test.ts`) makes an always-on-top LINE win over a coincident
precise hit, but only when that line is the actual SCREEN-NEAREST winner among lines -- an ordinary,
merely-present line elsewhere never overrides a genuine precise hit under the cursor (a review
finding, fixed before merge).

Same root-cause FAMILY as `mover-polys-unselectable-in-movers-on-mode` (the raycast candidate set
didn't know about Mover-specific geometry) but a different concrete cause -- that item is the
Movers:on SOLID mesh, this one is the WIREFRAME outline. Landed together, same commit/review pass.

Live-verified (headless Chromium, `showcase_bar`, `DeusExMover4`, real synthetic clicks): Shift+click
on the Mover's outline in plain non-wireframe mode (Movers:on off) -- unfixed selects `Brush803`
(wrong); fixed selects `DeusExMover4`. Independently reproduced by a review subagent, at a different
pixel/actor line, same wrong-vs-right actor pattern. Regression-checked: a plain click elsewhere still
select-surfaces normally, and a wireframe-mode click on the Mover's outline (the pre-existing
`nearestScreenHit` fix) is unaffected.
