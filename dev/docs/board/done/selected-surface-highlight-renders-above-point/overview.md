+++
priority = "p1"
kind = "debug"
summary = "a selected surface's highlight renders above a point-actor sprite it's actually behind, but not above a mesh actor"
+++

# selected surface highlight renders above point-actor sprites it's actually behind

Root-caused and fixed on `staging`: `SurfaceSelectionHighlight`'s overlay mesh and a point-actor
sprite are both `transparent` with the default `renderOrder` (0); three.js's transparent-pass sort
falls back to distance-from-camera on a tie, and that distance is each object's own `matrixWorld`
origin — meaningless for the highlight mesh (it never sets a `.position`). Fixed by giving marker
sprites an explicit `MARKER_RENDER_ORDER` (`web/src/scene/markers.ts`) higher than the highlight's
default, so a sprite always composites after a coincident-depth highlight. `depthTest` untouched
(sprite-vs-wall occlusion unaffected). Live-verified: reverting just the `renderOrder` live
reproduces the bug exactly, isolated to the sprite's own screen footprint.
