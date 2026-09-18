+++
priority = "p1"
kind = "debug"
summary = "selecting a mover's poly in Movers:on solid mode succeeds (inspector shows it) but no highlight renders"
+++

# Mover poly select in Movers:on mode has no visible highlight

Clicking a mover's own poly in "Movers:on" mode (mover geometry rendered solid, non-wireframe)
appears to select it correctly (state-wise -- the owner describes it as "it seems to select it"), but
no highlight renders on the poly, unlike an ordinary brush poly select.

This is the same SHAPE of bug as `poly-highlight-not-visible-for-brush116-0` (done earlier this
campaign, masked-texture surfaces) -- a real selection succeeding with no corresponding visual
highlight -- but for a DIFFERENT geometry class (Mover solid-mesh polys, wired into picking only
recently by `mover-polys-unselectable-in-movers-on-mode`, done). Likely cause: the highlight overlay
component (`SelectionHighlight.tsx`/`SurfaceSelectionHighlight`) may only know how to build its
overlay geometry from ordinary brush meshes, and was never extended to also target the Movers:on
solid mesh added by that recent fix (`Viewport3D.tsx`'s `moverMeshRef` / `moverTriangleOwners`).

## Where to look

`web/src/scene/SelectionHighlight.tsx` (how it resolves a selected surface's geometry to build the
overlay) and `web/src/scene/Viewport3D.tsx` (the Movers:on solid mesh added in
`mover-polys-unselectable-in-movers-on-mode` -- check whether the highlight component has access to
that same mesh/triangle-owner data, or only to the ordinary brush meshes).

## Repro

1. Enable "Movers:on" (mover geometry solid, non-wireframe).
2. Click a mover's own poly.
3. Inspector shows it selected (confirm this part still works -- don't assume, verify).
4. Expected: the poly highlights like any other selected poly. Actual: no highlight renders.
