// Which brush actors' authored (pre-CSG) poly rings to draw, in which colour/weight -- the pure
// logic behind `actor diagram`'s "every brush wireframed in its own CSG colour, selected one bolder"
// convention (quad-layout Part 2, Task 9). `'selected-only'` reproduces TODAY's Perspective-pane
// behavior (`SelectionHighlight`) unchanged -- a regression pin; `'csg-all'` is the new requirement
// (spec §2): every brush actor's own rings, in its own colour, with the selected one(s) bold.
import type { SceneActor } from '../api'

export interface BrushRing {
  actorName: string
  color: [number, number, number]
  verts: number[]
  bold: boolean
}

export type BrushRingMode = 'csg-all' | 'selected-only'

/** One ring per poly of every brush actor `mode` selects: `'selected-only'` -> only SELECTED
 * actors' rings (all bold -- one ring per selected brush actor, matching today's single-selection
 * `SelectionHighlight` output shape exactly when `selectedNames.size === 1`, a regression pin, not a
 * new shape); `'csg-all'` -> every brush actor's rings in its own `brush.color`, bold only on
 * selected ones (spec §9's multi-select cross-pane highlight). */
export function buildBrushRings(actors: SceneActor[], selectedNames: ReadonlySet<string>, mode: BrushRingMode): BrushRing[] {
  const rings: BrushRing[] = []
  for (const actor of actors) {
    if (!actor.brush) continue
    const isSelected = selectedNames.has(actor.name)
    if (mode === 'selected-only' && !isSelected) continue
    for (const verts of actor.brush.polys) {
      rings.push({ actorName: actor.name, color: actor.brush.color, verts, bold: isSelected })
    }
  }
  return rings
}

export interface MergedWireframe {
  positions: Float32Array
  colors: Float32Array
  // Parallel to segments: segmentOwners[i] is the actor name owning the i'th 2-vertex segment
  // (positions[6i..6i+5]) -- a raycast hit's `intersection.index` (the segment's first vertex
  // index, three.js `Line.raycast`) maps back via `Math.floor(index / 2)`.
  segmentOwners: (string | null)[]
}

/** Merges every ring's closed vertex loop into ONE `THREE.LineSegments`-shaped buffer (bug report
 * item 4): `BrushOutlines` used to render one `LineLoop`/draw call per POLY, which measured at
 * roughly 11,000+ WebGL draw calls per wireframe pane for a WanChai-sized level (~2287 actors) --
 * ~350ms/frame even sitting idle, since each of the 4 quad panes re-issues that same draw-call
 * count every animation frame regardless of whether anything changed. One merged buffer is one
 * draw call for the same picture; per-vertex color reproduces each ring's own CSG hue. */
export function mergeThinRings(rings: BrushRing[]): MergedWireframe {
  let segmentCount = 0
  for (const ring of rings) segmentCount += ring.verts.length / 3
  const positions = new Float32Array(segmentCount * 6)
  const colors = new Float32Array(segmentCount * 6)
  const segmentOwners: (string | null)[] = new Array(segmentCount)
  let offset = 0
  let seg = 0
  for (const ring of rings) {
    const n = ring.verts.length / 3
    const [r, g, b] = [ring.color[0] / 255, ring.color[1] / 255, ring.color[2] / 255]
    for (let i = 0; i < n; i++) {
      const j = (i + 1) % n
      positions[offset] = ring.verts[i * 3]
      positions[offset + 1] = ring.verts[i * 3 + 1]
      positions[offset + 2] = ring.verts[i * 3 + 2]
      positions[offset + 3] = ring.verts[j * 3]
      positions[offset + 4] = ring.verts[j * 3 + 1]
      positions[offset + 5] = ring.verts[j * 3 + 2]
      colors[offset] = r
      colors[offset + 1] = g
      colors[offset + 2] = b
      colors[offset + 3] = r
      colors[offset + 4] = g
      colors[offset + 5] = b
      segmentOwners[seg] = ring.actorName
      seg += 1
      offset += 6
    }
  }
  return { positions, colors, segmentOwners }
}
