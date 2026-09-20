+++
priority = "p1"
kind = "implement"
summary = "clicking a fully-transparent texel of a masked poly's texture must not select that poly -- fall through to whatever's behind it"
+++

# masked-poly-transparent-area-click-should-fall

Owner report: some polys have a masked/alpha texture with fully see-through areas (e.g.
`Brush100:0`/`Brush106:0`/`Brush111:0` from the already-closed masked-surface-highlight work,
`GUI-PARITY.md`). Clicking one of those see-through areas currently still selects the poly. It
must not — a click landing on a fully transparent texel must act as though that poly wasn't there
at all, falling through to whatever real geometry is behind it (or a genuine miss).

## Existing precedent: the exact same mechanism already exists for point-actor sprites

`tapSelect.ts`'s `isSpriteHitTransparent` + `selection.ts`'s `isTransparentPixel` (cutoff 0.5,
matching the masked material's own `alphaTest`) already do this for marker sprites: sample the
sprite's own `CanvasTexture` source canvas at the raycast hit's UV, and drop the hit before ranking
if the sampled alpha is below the cutoff — `resolveTapSelect`'s
`raycaster.intersectObjects(candidates, false).filter((h) => !isSpriteHitTransparent(h))`. This
item extends the SAME idea to the main merged scene mesh (world/brush polys, `meshObject`) and the
Mover's own solid mesh (`moverMeshObject`) — not a new mechanism, a generalization of an existing
one.

## What's available (confirmed by investigation, no further research needed)

- The atlas is NOT one shared canvas — `sceneResources.ts`'s `useTextures` crops each `tex_index`'s
  rect onto its OWN `document.createElement('canvas')`, wrapped in `THREE.CanvasTexture`. So
  `material.map.image` is a real `HTMLCanvasElement`, exactly like the sprite case — `getContext('2d')`/
  `getImageData` works directly.
- **Difference from the sprite path #1 — no V-flip.** The sprite's texture uses the default
  `flipY = true`; the poly atlas texture sets `mapTex.flipY = false` (`sceneResources.ts`) because
  `geometry.ts`'s `polyUVs` already writes V in image-row (top-down) convention. Sampling must use
  `uv.y` directly, NOT `1 - uv.y` the way `isSpriteHitTransparent` does.
- **Difference from the sprite path #2 — UVs are not normalized to [0,1].** `polyUVs` computes UVs
  in texture-TILE space (`u = (rel·tu + pan.x) / rect.w`), and base materials use
  `RepeatWrapping`, so a poly spanning multiple tiles can have UVs like `2.35` or `-0.7`. The hit
  UV must be wrapped modulo 1 (handling negative values correctly) before mapping to canvas pixels.
- **Which material applied**: the merged geometry uses standard three.js multi-material `groups`
  (one per `(texIndex, masked, twoSided, blend, lit)` tuple). A `THREE.Intersection` on a
  non-indexed multi-group geometry carries `intersection.face.materialIndex`, and
  `intersection.object.material` is the material ARRAY (`activeMaterials`/`activeMoverMaterials`,
  `Viewport3D.tsx`/`OrthoViewport.tsx`) — so `hit.object.material[hit.face.materialIndex]` is the
  exact `THREE.MeshBasicMaterial` that rendered the hit triangle, with its own `.map` and
  `.alphaTest`. `SelectionHighlight.tsx` already uses this exact `materials[materialIndex]` lookup
  pattern for a different purpose (recovering "is this group masked" via `alphaTest > 0`) — reuse
  that convention, don't invent a new one.
- **Unmasked polys must never be affected**: only reject a hit when the resolved material has
  `alphaTest > 0` (masked) AND the sampled alpha is below `isTransparentPixel`'s existing 0.5
  cutoff. A material with `alphaTest === 0` (the overwhelming majority of polys) is never sampled
  at all — this must add zero risk/behavior change to ordinary opaque surfaces.

## Scope

`meshObject` (world/brush polys) and `moverMeshObject` (a Mover's own solid geometry, Movers:on
mode) — both go through the same merged-geometry/multi-material-group/atlas-canvas mechanism above.
Point-actor sprites are already handled (`isSpriteHitTransparent`, untouched, don't duplicate).
Mesh ACTORS (`meshPickObject`/`meshEdgePickObject`, static meshes with their own separate pick
geometry) are OUT OF SCOPE for this item unless investigation shows they share the exact same
atlas-canvas/masked-material mechanism — if they do turn out to need the same fix, flag it as a
follow-up rather than silently expanding scope.

## Implementation shape

Generalize the existing filter in `resolveTapSelect` (`tapSelect.ts`) — currently
`.filter((h) => !isSpriteHitTransparent(h))` — to also reject a transparent hit on `meshObject`/
`moverMeshObject`, e.g. a new `isMeshHitTransparent(hit)` in `selection.ts` (or `tapSelect.ts`,
matching where `isSpriteHitTransparent` already lives) that: checks the hit object is a `THREE.Mesh`
with an array material and a `faceIndex`/`face.materialIndex`; resolves the material; bails false
(never reject) if there's no `map` or `alphaTest <= 0`; otherwise wraps `hit.uv` mod 1 (both axes,
correct for negative values) and samples the canvas at `(u * width, v * height)` — no V-flip;
returns `isTransparentPixel(alpha)`. Combine both filters in the one `.filter(...)` call so a
rejected hit falls through to the next-best candidate exactly like the sprite case already does
(including all the way to the raycast-miss AABB fallback, if nothing solid is actually behind it).

No RE needed — matches an already-established, already-shipped mechanism and the material's own
existing `alphaTest` convention.
