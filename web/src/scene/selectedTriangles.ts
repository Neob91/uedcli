// The single-SURFACE (texture) selection highlight's pure geometry. A WHOLE-brush selection is shown
// by recoloring its outline ring (BrushOutlines, brightened x1.2) + vertex/pivot markers, never a
// face overlay (owner ruling). A single clicked surface still lights up: a pure BRIGHTNESS boost
// (additive white overlay) over the actor's existing material, not a new tint hue.
//
// Mesh-actor selection bug fix (2026-09-15, same investigation as the "sunglasses" fix in
// `preview_native.py`/`meshrender.py` -- see that file's history for the unrelated bug): the flat
// white overlay above ignored each triangle's own MASKED cutout (`resolveMaterialState`'s
// `alphaTest`), so a masked mesh triangle -- an NPC's alpha-cutout hair/collar card, a fence, a
// ceiling-fan blade -- lit up as its full untested quad instead of just its real (alpha-tested)
// visible shape. On an NPC head, whose hair card is a noticeably larger quad than the head it
// wraps, this reads as "the head renders oversized" the instant it's selected. Root cause confirmed
// by probing real `DeusExCharacters` NPC meshes (`_scratch/probe_npc_mesh.py`): every stock
// ScriptedPawn body mesh carries a masked, two-sided head/hair material slot (`PolyFlags` `0x102` =
// `PF_TwoSided|PF_Masked`) sized a large fraction of the whole body's bounding box. The fix groups
// the selected-triangle set by the geometry's own draw group (`selectedSurfaceTriangleGroups` below)
// so `SelectionHighlight.tsx` can give a MASKED group's overlay the same `map`/`alphaTest`/`side` as
// its real base material -- clipped to the real cutout shape, never revealing what the base render
// hides.
//
// The pure piece: which triangles (as flat vertex-index triples into the shared merged geometry)
// belong to each draw GROUP, given the per-triangle ownership map `selection.ts`'s `resolveHitActor`
// already uses (`sceneResources.ts`'s `triangleOwners`, one entry per triangle in `geometry.ts`'s
// `buildGeometryData` order) and the base mesh's own `THREE.BufferGeometry.groups` (contiguous
// [start, count) vertex ranges in the SAME triangle order, tagged with the group's `materialIndex`).
import { surfaceKey } from './selectionSet'

/** One draw group's own selected-triangle subset: `materialIndex` names which of the base mesh's
 * per-group materials this subset's real cutout/cull state should be read from; `indices` is the
 * flat vertex-index triple list (three per triangle) into the shared position/uv attributes. */
export interface SelectedTriangleGroup {
  materialIndex: number
  indices: number[]
}

/** The subset of a `THREE.BufferGeometry.groups` entry this module needs -- `start`/`count` in
 * VERTICES (three.js's own convention for a non-indexed geometry), `materialIndex` defaulting to 0
 * to match three.js's own default when a group is added with none. */
export interface TriangleGroupRange {
  start: number
  count: number
  materialIndex?: number
}

/** The surface (single-polygon) selection triangle groups (GUI.md "Selection & the Inspector": a
 * texture selection highlights only the ONE clicked polygon's triangles, not the whole brush's).
 * `selectedSurfaces` holds `selectionSet.ts`'s `surfaceKey(owner, polyIndex)` strings; a triangle
 * qualifies when its OWN owner+poly-index pair encodes to a member of that set. (A whole-brush
 * selection is shown by recoloring its outline ring, `BrushOutlines`, not a per-triangle overlay.) */
export function selectedSurfaceTriangleGroups(
  triangleOwners: (string | null)[],
  trianglePolyIndex: (number | null)[],
  selectedSurfaces: ReadonlySet<string>,
  groups: readonly TriangleGroupRange[],
): SelectedTriangleGroup[] {
  if (selectedSurfaces.size === 0) return []
  const out: SelectedTriangleGroup[] = []
  for (const group of groups) {
    const indices: number[] = []
    for (let tri = group.start / 3; tri < (group.start + group.count) / 3; tri++) {
      const owner = triangleOwners[tri]
      const polyIndex = trianglePolyIndex[tri]
      if (owner != null && polyIndex != null && selectedSurfaces.has(surfaceKey(owner, polyIndex))) {
        const base = tri * 3
        indices.push(base, base + 1, base + 2)
      }
    }
    if (indices.length > 0) out.push({ materialIndex: group.materialIndex ?? 0, indices })
  }
  return out
}
