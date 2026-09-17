+++
priority = "p1"
kind = "debug"
summary = "clicking a mover's wireframe outline in non-wireframe mode should select the mover actor, but doesn't"
+++

# Mover not selectable via its wireframe outline in non-wireframe mode

In ordinary non-wireframe (solid) mode -- NOT "Movers:on" solid-fill mode -- a Mover's always-visible
wireframe outline (its control cage) should be clickable to select the Mover as a whole actor/brush.
Currently clicking directly on that wireframe line does not select the Mover at all.

This is distinct from the two related mover items already filed:
- `mover-wireframe-occluded-by-geometry` -- the wireframe's VISIBILITY (gets hidden behind other
  geometry). This item assumes the wireframe is visible/clicked-on and is about pick resolution, not
  rendering.
- `mover-polys-unselectable-in-movers-on-mode` -- POLY-level selection failing inside "Movers:on"
  solid-fill mode. This item is about ACTOR-level selection via the wireframe line itself, in plain
  non-wireframe mode (Movers:on not required).

## Repro

1. Non-wireframe (solid) mode, Movers:on NOT required.
2. Click directly on a Mover's wireframe outline (its control-cage line).
3. Expected: the Mover gets selected (as an actor/brush).
4. Actual: nothing is selected (or something else is), even when clicking squarely on the line.

## Where to look

`web/src/scene/tapSelect.ts`/`selection.ts`'s raycast target set -- likely the Mover's wireframe line
geometry isn't included as a pick target for actor selection in non-wireframe mode at all (only brush
wireframe outlines are). May share a fix or at least investigation ground with
`mover-polys-unselectable-in-movers-on-mode` and the just-landed `nearestScreenHit` screen-space
hit-ranking fix (`wireframe-brush-selection-should-hit-test-lines`, done 2026-09-17) -- check that
work before starting from scratch.
