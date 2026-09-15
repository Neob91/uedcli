// Issue 1 (owner finding, 2026-09-15): a selected brush's drawn SURFACE showed no visual change --
// only its wireframe outline (BrushOutlines' bold ring) and vertex/pivot markers (SelectionMarkers)
// did. `dev/docs/unrealed/quirks.md`/`rendering.md` carry no citable engine fact for exactly how a
// selected BSP surface renders in a solid/shaded UnrealEd viewport (checked; `PF_Selected` is
// documented only as a non-round-tripping flag, never as a render rule). The closest citable
// convention IN THIS CODEBASE is `BrushOutlines.tsx`'s own selected-ring rule: a selected brush keeps
// its OWN hue, just bolder -- never an alien highlight color painted over it -- matching `preview.py`'s
// module docstring ("a highlighted poly ... stays vivid+bold on top, at FULL fill strength"). So the
// surface highlight here is a pure BRIGHTNESS boost (additive white overlay) over the actor's existing
// material, not a new tint hue.
//
// The pure piece: which triangles (as flat vertex-index triples into the shared merged geometry) to
// draw the highlight overlay for, given the same per-triangle ownership map `selection.ts`'s
// `resolveHitActor` already uses (`sceneResources.ts`'s `triangleOwners`, one entry per triangle in
// `geometry.ts`'s `buildGeometryData` order).
export function selectedTriangleIndices(
  triangleOwners: (string | null)[],
  selectedNames: ReadonlySet<string>,
): number[] {
  if (selectedNames.size === 0) return []
  const indices: number[] = []
  for (let tri = 0; tri < triangleOwners.length; tri++) {
    const owner = triangleOwners[tri]
    if (owner != null && selectedNames.has(owner)) {
      const base = tri * 3
      indices.push(base, base + 1, base + 2)
    }
  }
  return indices
}
