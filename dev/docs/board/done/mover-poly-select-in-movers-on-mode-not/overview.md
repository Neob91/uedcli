+++
priority = "p1"
kind = "debug"
summary = "FIXED -- SurfaceSelectionHighlight only read the world mesh's owner arrays, never the mover mesh's own"
+++

# Mover poly select in Movers:on mode has no visible highlight

Fixed: confirmed the board item's own hypothesis exactly. `Viewport3D.tsx` built the surface-pick
highlight (`SurfaceSelectionHighlight`) from `bufferGeometry`/`triangleOwners`/`trianglePolyIndex` --
the world/brush mesh's own arrays -- only. A Mover's Movers:on solid mesh is a SEPARATE
`THREE.BufferGeometry` with its own `moverGeometry`/`moverTriangleOwners`/`moverTrianglePolyIndex`
(wired into picking by `mover-polys-unselectable-in-movers-on-mode`), so a selected mover poly's
`(owner, polyIndex)` pair never appeared in the world mesh's owner array and
`selectedSurfaceTriangleGroups` (`selectedTriangles.ts`) never built a triangle group for it -- no
group, no overlay mesh, no visible highlight, even though selection itself (via
`moverTriangleOwners`/`moverTrianglePolyIndex` in `tapSelect.ts`) worked correctly.

Fix: added a second `SurfaceSelectionHighlight` instance in `Viewport3D.tsx`, pointed at
`moverGeometry`/`moverTriangleOwners`/`moverTrianglePolyIndex`/`activeMoverMaterials`, gated
identically to the mover solid mesh itself (`mode !== 'wireframe' && showMoverSolid`). No change to
`SelectionHighlight.tsx`/`selectedTriangles.ts` -- both were already geometry-agnostic; the gap was
purely that Viewport3D never called them with the mover's own data.

Live-verified (real synthetic clicks, headless Chromium, `showcase_bar`, `DeusExMover4`): with Movers:
on and Lit mode, a real click on the mover's door poly selects `DeusExMover4:4` (confirmed via the
Inspector's surface-detail view -- texture/pan/blend/masked/two-sided/lit fields, not a whole-actor
selection) both before and after the fix -- selection itself was never broken, matching the item's own
note to verify rather than assume. Sampled door-face pixels were IDENTICAL between the deselected
baseline and the post-select screenshot with the fix reverted (e.g. `(89,47,26)` unchanged), and
measurably brighter with the fix applied (e.g. `(89,47,26)` -> `(153,111,90)` at the same pixel, same
click, same camera pose) -- a clean causal A/B proving the highlight overlay renders only once the fix
is in place.

OrthoViewport.tsx does not wire Movers:on solid-mesh picking at all (`moverMeshObject: null`), so this
fix is scoped to the perspective pane only, matching `mover-polys-unselectable-in-movers-on-mode`'s
own scope.

Full offline `web/` vitest suite: 328/328 passed, no regressions.
