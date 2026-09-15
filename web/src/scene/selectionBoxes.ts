// Shared by Viewport3D.tsx and OrthoViewport.tsx (item 16 dedup): every SELECTED non-brush actor's
// own AABB -- the fallback highlight for a selected actor with no CSG ring of its own to draw (a
// point actor, a mesh actor, etc.), one entry per selected actor. Pure data, no THREE dependency
// (mirrors frame.ts's style) -- each caller wraps `lo`/`hi` into its own `THREE.Box3` for its own
// `<box3Helper>`.
import type { SceneActor } from '../api'
import type { Vec3 } from './camera'

export interface SelectedBox {
  name: string
  lo: Vec3
  hi: Vec3
}

export function selectedNonBrushBoxes(actors: SceneActor[], selectedNames: ReadonlySet<string>): SelectedBox[] {
  return actors.filter((a) => selectedNames.has(a.name) && !a.brush).map((a) => ({ name: a.name, lo: a.bbox_lo, hi: a.bbox_hi }))
}
