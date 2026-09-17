+++
priority = "p1"
kind = "debug"
summary = "a selected surface's highlight renders above a point-actor sprite it's actually behind, but not above a mesh actor"
+++

# selected surface highlight renders above point-actor sprites it's actually behind

When a surface (poly) is selected, and that surface is geometrically BEHIND a point actor's sprite
(farther from the camera), the surface's selection highlight still renders on top of the sprite —
visually as if the highlight ignored depth/occlusion for sprites specifically. The same relative
positioning with a mesh actor (instead of a point-actor sprite) occludes correctly — this is
sprite-specific, not a general highlight depth-test bug.

Screenshot: a selected wall surface's highlight washes out/renders over nearby point-actor sprites
(a torch, fruit pickups, a hat) that should be in front of it.

## Repro

1. Any level with point actors near a wall/surface (any level — not level-specific).
2. Position the camera so a point actor's sprite is in front of (closer to camera than) a surface.
3. Select that surface.
4. Expected: the sprite still renders in front of the highlight (correct occlusion). Actual: the
   highlight renders in front of the sprite.
5. The same test with a mesh actor instead of a point actor does NOT show this bug — mesh
   occlusion vs. the highlight is already correct.

## Where to look

`web/src/scene/` — whatever renders point-actor sprites (billboards, likely always-facing-camera)
vs. the surface highlight overlay (`SelectionHighlight.tsx`/`BrushOutlines.tsx` per `GUI-PARITY.md`'s
inventory). Likely cause: the highlight is drawn with depth-testing disabled (or in a render pass/
`renderOrder` that runs after sprites regardless of depth), and sprites use a rendering technique
(e.g. `depthWrite: false`, or a separate always-on-top pass) that a normal mesh actor doesn't — worth
comparing the sprite material/render setup against the mesh actor's. This is a rendering/compositing
bug in this codebase, not a UED22-fidelity question — no RE needed, straight to build.
