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
