// Shared click/tap-to-select raycast pipeline for Viewport3D.tsx and OrthoViewport.tsx (item 16
// dedup) -- both built a THREE.Raycaster from the same screen point, raycast the same candidate
// groups in the same priority order, fall back to ray-vs-AABB, and resolve to the same TapAction.
// The PICKING algorithm itself stays in `selection.ts` (framework-free, directly testable without a
// WebGL context); this file owns only the raycaster wiring the two viewports duplicated
// near-verbatim. Deliberate per-viewport deltas (the 2D line-hit threshold scaling with zoom, the
// perspective pane's fixed one) are threaded in as `lineThreshold`, not hidden here.
import * as THREE from 'three'

import type { SceneActor } from '../api'
import { pickActor, resolveHitSurface, resolveSegmentHitActor, resolveTapAction } from './selection'
import type { Ray, RawTapHit, TapAction } from './selection'
import type { ShadingMode } from './shadingMode'

export interface TapSelectParams {
  camera: THREE.Camera
  rect: DOMRect
  clientX: number
  clientY: number
  additive: boolean
  shiftKey: boolean
  mode: ShadingMode
  // World-unit `Raycaster.params.Line.threshold` for a thin (non-`Line2`) brush outline hit -- a
  // fixed screen-equivalent px count for the perspective pane, `orthoLineHitThresholdUU`-scaled for
  // an ortho pane (bug report: 2D brush selection was near-pixel-exact once zoomed out).
  lineThreshold: number
  meshObject: THREE.Object3D | null
  markerObjects: THREE.Object3D[]
  // Only non-empty in wireframe mode (bug report item 6: never AABB/interior-select a brush in
  // wireframe/ortho views -- only its own outline lines may select it there).
  brushObjects: THREE.Object3D[]
  actors: SceneActor[]
  triangleOwners: (string | null)[]
  // Same per-triangle indexing as `triangleOwners` -- resolves a mesh hit to the specific polygon
  // clicked (surface/texture selection), not just its owning actor.
  trianglePolyIndex: (number | null)[]
}

/** Runs the raycast-then-AABB-fallback hit-test and resolves it to a `TapAction`: raycast the real
 * drawn geometry (main scene mesh + point-actor marker sprites +, in wireframe mode, the brush
 * outline lines) together so the nearest hit wins regardless of which one it lands on, else fall
 * back to ray-vs-AABB (never for a brush actor in wireframe mode). The click-target (surface vs.
 * whole actor) and modifier-key rules live in `selection.ts`'s `resolveTapAction` -- this function
 * only builds the raw hit-test result it needs. */
export function resolveTapSelect(params: TapSelectParams): TapAction {
  const { camera, rect, clientX, clientY, additive, shiftKey, mode, lineThreshold, meshObject, markerObjects, brushObjects, actors, triangleOwners, trianglePolyIndex } =
    params
  const ndcX = ((clientX - rect.left) / rect.width) * 2 - 1
  const ndcY = -((clientY - rect.top) / rect.height) * 2 + 1
  const raycaster = new THREE.Raycaster()
  raycaster.setFromCamera(new THREE.Vector2(ndcX, ndcY), camera)
  // `Line`/`LineLoop` (ThinRing) measure this threshold in WORLD units; `Line2` (BoldRing, the
  // selected ring) measures it in screen PIXELS -- both need setting, or an unset one falls back to
  // a threshold of 0 (line-exact clicks only).
  raycaster.params.Line = { threshold: lineThreshold }
  raycaster.params.Line2 = { threshold: 6 }

  let hit: RawTapHit | null = null
  const candidates: THREE.Object3D[] = [...(meshObject ? [meshObject] : []), ...markerObjects, ...brushObjects]
  if (candidates.length > 0) {
    const hits = raycaster.intersectObjects(candidates, false)
    if (hits.length > 0) {
      const raw = hits[0]
      if (raw.object === meshObject) {
        const surface = resolveHitSurface(raw.faceIndex, triangleOwners, trianglePolyIndex, actors)
        hit = surface ? { actor: surface.actor, polyIndex: surface.polyIndex } : null
      } else if (raw.object.userData.segmentOwners) {
        const segmentOwners = raw.object.userData.segmentOwners as (string | null)[]
        const actor = resolveSegmentHitActor(raw.index, segmentOwners, actors)
        hit = actor ? { actor, polyIndex: null } : null
      } else {
        const name = raw.object.userData.actorName as string | undefined
        const actor = name ? (actors.find((a) => a.name === name) ?? null) : null
        hit = actor ? { actor, polyIndex: null } : null
      }
    }
  }
  if (!hit) {
    const ray: Ray = {
      origin: [raycaster.ray.origin.x, raycaster.ray.origin.y, raycaster.ray.origin.z],
      direction: [raycaster.ray.direction.x, raycaster.ray.direction.y, raycaster.ray.direction.z],
    }
    const aabbCandidates = mode === 'wireframe' ? actors.filter((a) => !a.brush) : actors
    const actor = pickActor(ray, aabbCandidates)
    hit = actor ? { actor, polyIndex: null } : null
  }
  return resolveTapAction(hit, mode, shiftKey, additive)
}
