+++
priority = "p1"
kind = "debug"
summary = "FIXED -- Movers:on solid mesh had no ref, so it was never a raycast pick target at all"
+++

# Mover polys can't be selected in Movers:on mode

Fixed: the "Movers:on" solid `<mesh>` (`Viewport3D.tsx`) rendered with no `ref`, so `tapSelect.ts`'s
`resolveTapSelect` never raycast it -- a click fell through to whatever brush sat behind it. Gave it
a `moverMeshRef`, threaded `SceneResourcesContext`'s already-computed `moverTriangleOwners`/
`moverTrianglePolyIndex` through to `resolveTapSelect`, and added a resolution branch for it
(`TapSelectParams.moverMeshObject`).

Same root-cause FAMILY as `mover-not-selectable-via-wireframe-click` (the raycast candidate set
simply didn't know about Mover-specific geometry) but a DIFFERENT concrete cause and fix -- that item
is about the Mover's WIREFRAME outline in non-solid mode, this one is about its SOLID mesh in
Movers:on mode. Landed together, same commit/review pass.

Live-verified (headless Chromium, `showcase_bar`, `DeusExMover4`, real synthetic clicks): Shift+click
on the Mover's Movers:on solid face -- unfixed selects `Brush803` (the brush behind); fixed selects
`DeusExMover4`. A plain (non-Shift) click on the same face now resolves `select-surface` for
`DeusExMover4`'s own poly, matching how any other brush's face click behaves. Independently
reproduced by a review subagent (its own backend/browser session, same before/after actor names).
