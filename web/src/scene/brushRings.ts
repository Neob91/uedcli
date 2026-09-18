// Which brush actors' authored (pre-CSG) poly rings to draw, in which colour/weight -- the pure
// logic behind `actor diagram`'s "every brush wireframed in its own CSG colour, selected one bolder"
// convention (quad-layout Part 2, Task 9). `'selected-only'` reproduces TODAY's Perspective-pane
// behavior (`SelectionHighlight`), EXCEPT a Mover's ring is always included regardless of selection
// (GUI.md "Movers" -- a Mover renders wireframe-outline-only by default in every shading mode, so its
// outline can't be gated on selection the way an ordinary brush's is); `'csg-all'` is the new
// requirement (spec §2): every brush actor's own rings, in its own colour, with the selected one(s)
// bold.
import type { SceneActor } from '../api'
import { resolveWireColor, scaleColor } from './selectionColor'

export interface BrushRing {
  actorName: string
  color: [number, number, number]
  // The server's own CSG classification (`preview.py`'s `_CSG_PALETTE` keys: add/subtract/
  // semisolid/nonsolid/mover) -- carried alongside `color` (the server's tuned palette value, kept
  // verbatim here so this stays a passthrough) so a consumer can resolve the FAITHFUL UED22
  // WireColor via `selectionColor.ts`'s `resolveWireColor` without a second actor lookup.
  csgClass: string
  verts: number[]
  bold: boolean
  // Carried through so a consumer (BrushOutlines.tsx) can render a Mover's ring depthTest-off/
  // high-renderOrder without a second actor lookup -- a Mover's wireframe must always composite on
  // top, in every shading mode, regardless of what's rendered in front of it (board item
  // `mover-wireframe-occluded-by-geometry`).
  isMover: boolean
}

export type BrushRingMode = 'csg-all' | 'selected-only'

/** One ring per poly of every brush actor `mode` selects: `'selected-only'` -> SELECTED actors' rings
 * (bold) plus every MOVER's ring even when unselected (thin) -- one ring per selected-or-mover brush
 * actor, matching today's single-selection `SelectionHighlight` output shape when `selectedNames.size
 * === 1` and no actor is a Mover; `'csg-all'` -> every brush actor's rings in its own `brush.color`,
 * bold only on selected ones (spec §9's multi-select cross-pane highlight). */
export function buildBrushRings(actors: SceneActor[], selectedNames: ReadonlySet<string>, mode: BrushRingMode): BrushRing[] {
  const rings: BrushRing[] = []
  // Brushes draw in CSG order (owner ruling) -- explicit rather than relying on `actors` already
  // arriving in that order. It does today (`scene.py`'s `_build_actors` enumerates `level.order`),
  // but this makes the invariant hold regardless of what the caller passes.
  const ordered = [...actors].sort((a, b) => a.csg_rank - b.csg_rank)
  for (const actor of ordered) {
    if (!actor.brush) continue
    const isSelected = selectedNames.has(actor.name)
    if (mode === 'selected-only' && !isSelected && !actor.is_mover) continue
    for (const verts of actor.brush.polys) {
      rings.push({
        actorName: actor.name,
        color: actor.brush.color,
        csgClass: actor.brush.csg_class,
        verts,
        bold: isSelected,
        isMover: actor.is_mover,
      })
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
    // Thin rings are always the UNSELECTED appearance -- even for a currently-selected actor's
    // ring, which is included here too (perf: BrushOutlines.tsx's `'csg-all'` merge intentionally
    // doesn't depend on `selectedNames`) but gets fully covered by its own undimmed `BoldRing` drawn
    // on top, so dimming it here is harmless. Real UED22: `DrawColor = WireColor * 0.5` when NOT
    // selected (`selectionColor.ts`'s doc comment; `UnEdRend.cpp`'s `DrawLevelBrush`).
    const faithful = resolveWireColor(ring.csgClass, ring.color)
    const dimmed = scaleColor(faithful, 0.5)
    const [r, g, b] = [dimmed[0] / 255, dimmed[1] / 255, dimmed[2] / 255]
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
