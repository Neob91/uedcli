+++
priority = "p1"
kind = "debug"
summary = "mover geometry doesn't participate in poly/surface picking in Movers:on mode -- clicks fall through to the brush behind"
+++

# Mover polys can't be selected in Movers:on mode

In "Movers:on" mode (mover geometry renders solid in non-wireframe view), a mover's own polys can't
be selected at all. Two symptoms, likely the same root cause:

1. Shift+LMB on a mover resolves to the brush sitting behind/underneath it, not the mover itself.
2. There is no way to select a mover's own poly directly in this mode -- every click on visible mover
   geometry falls through to whatever's behind it.

Both are consistent with mover geometry simply not being included as a raycast target for poly/
surface picking at all, even though it's now visibly rendered (Movers:on).

## Repro

1. Enable "Movers:on" mode (mover geometry rendered solid, non-wireframe).
2. Shift+LMB-click on a mover's own visible surface, where a brush sits directly behind it.
3. Observe: the brush behind gets selected, not the mover's poly.
4. There's no click that resolves to the mover's own poly in this mode.

## Where to look

`web/src/scene/tapSelect.ts`/`selection.ts`'s raycast target set for poly/surface picking -- likely
excludes Mover meshes even when Movers:on is enabled (only including brush/world-geometry meshes).
May be closely related to the just-landed `nearestScreenHit` fix in `selection.ts`
(`wireframe-brush-selection-should-hit-test-lines` / `mover-near-brush803-unclickable-in-
wireframe-2d`, done 2026-09-17) -- check whether that work already touched adjacent code.
