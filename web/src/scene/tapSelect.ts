// Shared click/tap-to-select raycast pipeline for Viewport3D.tsx and OrthoViewport.tsx (item 16
// dedup) -- both built a THREE.Raycaster from the same screen point, raycast the same candidate
// groups in the same priority order, fall back to ray-vs-AABB, and resolve to the same TapAction.
// The PICKING algorithm itself stays in `selection.ts` (framework-free, directly testable without a
// WebGL context); this file owns only the raycaster wiring the two viewports duplicated
// near-verbatim. Deliberate per-viewport deltas (the 2D line-hit threshold scaling with zoom, the
// perspective pane's fixed one) are threaded in as `lineThreshold`, not hidden here.
import * as THREE from 'three'

import type { SceneActor } from '../api'
import { isTransparentPixel, pickActor, pickHit, resolveHitSurface, resolveSegmentHitActor, resolveTapAction } from './selection'
import type { HitCandidate, Ray, RawTapHit, TapAction } from './selection'
import type { ShadingMode } from './shadingMode'

/** Whether a raycast hit on a point-actor marker sprite landed on a transparent icon pixel --
 * `isTransparentPixel`'s doc comment has the UED22 mechanism this reproduces. Samples the sprite's
 * own `CanvasTexture` source canvas (built by `sceneResources.ts`'s `useTextures`/`useMarkerTexture`,
 * always a real `HTMLCanvasElement`) at the intersection's `uv` -- `flipY` stays the THREE.Texture
 * default (true), so GL v=1 (top of texture) is canvas row 0, hence `1 - uv.y`. Non-sprite hits, or a
 * sprite whose map/uv/canvas isn't available (a test stub, a still-loading texture), are never
 * rejected -- this only narrows an already-accepted hit, never widens one. */
function isSpriteHitTransparent(hit: THREE.Intersection): boolean {
  if (!(hit.object instanceof THREE.Sprite) || !hit.uv) return false
  const map = hit.object.material.map
  const canvas = map?.image as HTMLCanvasElement | undefined
  if (!canvas || typeof canvas.getContext !== 'function') return false
  const ctx = canvas.getContext('2d')
  if (!ctx) return false
  const x = Math.min(canvas.width - 1, Math.max(0, Math.floor(hit.uv.x * canvas.width)))
  const y = Math.min(canvas.height - 1, Math.max(0, Math.floor((1 - hit.uv.y) * canvas.height)))
  const alpha = ctx.getImageData(x, y, 1, 1).data[3] / 255
  return isTransparentPixel(alpha)
}

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
  // Movers:on toggle (`Viewport3D.tsx`'s `showMoverSolid`): a Mover's own solid geometry, split out
  // of `meshObject` and drawn as a separate mesh only when that toggle is on (and never in wireframe
  // mode) -- null otherwise. Lets a Mover's own poly resolve to the Mover instead of falling through
  // to whatever's drawn behind it (board item `mover-polys-unselectable-in-movers-on-mode`).
  moverMeshObject: THREE.Object3D | null
  moverTriangleOwners: (string | null)[]
  moverTrianglePolyIndex: (number | null)[]
  // The invisible mesh-actor pick mesh + its per-triangle owner arrays (SceneResources). Lets a
  // DT_Mesh actor be selected in the ortho panes (and the perspective wireframe pane), where the
  // solid `meshObject` isn't drawn. A hit resolves to the whole owning actor (mesh actors have no
  // brush) via `resolveHitSurface`.
  meshPickObject: THREE.Object3D | null
  meshTriangleOwners: (string | null)[]
  meshTrianglePolyIndex: (number | null)[]
  markerObjects: THREE.Object3D[]
  // Every brush's own outline (`BrushOutlines.tsx`'s `groupRef`, `csg-all`/`selected-only` per mode)
  // -- only meaningful as a click target in wireframe mode (bug report item 6: never AABB/interior-
  // select a brush in wireframe/ortho views -- only its own outline lines may select it there); the
  // caller passes `[]` outside wireframe mode.
  brushObjects: THREE.Object3D[]
  // A Mover's own always-visible outline (`BrushOutlines.tsx`'s `moverGroupRef`) -- unlike
  // `brushObjects`, wired in EVERY mode: it's the Mover's only visible representation when its solid
  // geometry isn't drawn (board item `mover-not-selectable-via-wireframe-click`). Scoped to Movers
  // only, not every brush, so this never changes how an ordinary (non-Mover) brush is picked outside
  // wireframe mode.
  moverOutlineObjects: THREE.Object3D[]
  actors: SceneActor[]
  triangleOwners: (string | null)[]
  // Same per-triangle indexing as `triangleOwners` -- resolves a mesh hit to the specific polygon
  // clicked (surface/texture selection), not just its owning actor.
  trianglePolyIndex: (number | null)[]
}

/** Runs the raycast-then-AABB-fallback hit-test and resolves it to a `TapAction`: raycast the real
 * drawn geometry (main scene mesh, a Movers:on Mover's own solid mesh, point-actor marker sprites, a
 * Mover's own always-visible outline, and, in wireframe mode, every brush's outline) together --
 * dropping any marker-sprite hit that lands on the icon's transparent padding
 * (`isSpriteHitTransparent`) -- and picks the winner among every remaining hit via `selection.ts`'s
 * `pickHit` (see its doc comment for the precise-vs-line/always-on-top ranking rule). Falls back to
 * ray-vs-AABB on a genuine miss (never for a brush actor in wireframe mode; a point actor's own AABB
 * is a zero-size point at its Location, so this fallback can't re-select it through a transparent
 * sprite pixel the raycast just rejected).
 * The click-target (surface vs. whole actor) and modifier-key rules live in `selection.ts`'s
 * `resolveTapAction` -- this function only builds the raw hit-test result it needs. */
export function resolveTapSelect(params: TapSelectParams): TapAction {
  const {
    camera, rect, clientX, clientY, additive, shiftKey, mode, lineThreshold,
    meshObject, moverMeshObject, moverTriangleOwners, moverTrianglePolyIndex,
    meshPickObject, meshTriangleOwners, meshTrianglePolyIndex, markerObjects, brushObjects, moverOutlineObjects,
    actors, triangleOwners, trianglePolyIndex,
  } = params
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
  const candidates: THREE.Object3D[] = [
    ...(meshObject ? [meshObject] : []),
    ...(moverMeshObject ? [moverMeshObject] : []),
    ...(meshPickObject ? [meshPickObject] : []),
    ...markerObjects,
    ...brushObjects,
    ...moverOutlineObjects,
  ]
  if (candidates.length > 0) {
    // A marker sprite hit landing on its icon's transparent padding is dropped before ranking --
    // exactly like a genuine raycast miss on that candidate, so a click there falls through to
    // whatever else is actually drawn underneath (`isSpriteHitTransparent`'s doc comment).
    const hits = raycaster.intersectObjects(candidates, false).filter((h) => !isSpriteHitTransparent(h))
    if (hits.length > 0) {
      // `hits` is already PRECISE-hits-first-by-real-depth (intersectObjects' own ascending-distance
      // sort) -- `pickHit` (selection.ts) decides the winner: `Line`/`LineSegments`/`LineLoop` hits
      // (brushObjects/moverOutlineObjects) are THRESHOLD-accepted (see its doc comment for why an
      // `alwaysOnTop` -- `depthTest: false` -- line, e.g. a Mover's outline, can beat a precise hit
      // but an ordinary line cannot).
      const clickPx = clientX - rect.left
      const clickPy = clientY - rect.top
      const candidatesRanked: HitCandidate<THREE.Intersection>[] = hits.map((h) => {
        const isLine = h.object instanceof THREE.Line
        let alwaysOnTop = false
        if (isLine) {
          const obj = h.object as THREE.Line
          const material = Array.isArray(obj.material) ? obj.material[0] : obj.material
          alwaysOnTop = material?.depthTest === false
        }
        // `isMoverLine`/`isActor` -- `pickHit`'s Mover-wireframe-vs-polygon absolute-distance rule
        // (board item `mover-wireframe-should-outrank-polys-not-actors`). `moverOutlineObjects` is
        // its own candidate group (never `brushObjects`), so a Mover's outline is already
        // structurally distinguishable from an ordinary brush's here -- no new state needed.
        // `meshPickObject`/`markerObjects` are the only ACTOR candidates; `meshObject`/
        // `moverMeshObject` are polygon hits (a Mover's own solid poly picks like any other poly).
        const isMoverLine = isLine && moverOutlineObjects.includes(h.object)
        const isActor = !isLine && (h.object === meshPickObject || markerObjects.includes(h.object))
        const ndc = h.point.clone().project(camera)
        return {
          value: h,
          isLine,
          alwaysOnTop,
          isMoverLine,
          isActor,
          screenX: ((ndc.x + 1) / 2) * rect.width,
          screenY: ((1 - ndc.y) / 2) * rect.height,
        }
      })
      const raw = pickHit(candidatesRanked, clickPx, clickPy)
      // `pickHit` only returns null for an empty input, which can't happen here (guarded by
      // `hits.length > 0` above) -- the `if (raw)` just satisfies the type checker.
      if (raw) {
        if (raw.object === meshObject) {
          const surface = resolveHitSurface(raw.faceIndex, triangleOwners, trianglePolyIndex, actors)
          hit = surface ? { actor: surface.actor, polyIndex: surface.polyIndex, isLineHit: false } : null
        } else if (raw.object === moverMeshObject) {
          const surface = resolveHitSurface(raw.faceIndex, moverTriangleOwners, moverTrianglePolyIndex, actors)
          hit = surface ? { actor: surface.actor, polyIndex: surface.polyIndex, isLineHit: false } : null
        } else if (raw.object === meshPickObject) {
          // A mesh-actor triangle hit: resolve to the owning actor. `resolveTapAction` returns
          // select-actor for it regardless of polyIndex (a mesh actor has no brush), so the surface
          // index isn't load-bearing here -- it just identifies the actor.
          const surface = resolveHitSurface(raw.faceIndex, meshTriangleOwners, meshTrianglePolyIndex, actors)
          hit = surface ? { actor: surface.actor, polyIndex: surface.polyIndex, isLineHit: false } : null
        } else if (raw.object.userData.segmentOwners) {
          // A brush/Mover outline segment -- a genuine hit on drawn LINE geometry
          // (`RawTapHit.isLineHit`'s doc comment: never gated behind Shift, board item
          // `shift-modifier-convention-broken-for-poly-and`).
          const segmentOwners = raw.object.userData.segmentOwners as (string | null)[]
          const actor = resolveSegmentHitActor(raw.index, segmentOwners, actors)
          hit = actor ? { actor, polyIndex: null, isLineHit: true } : null
        } else {
          // The selected-actor bold ring (`BrushOutlines.tsx`'s `BoldRing`) -- also a genuine line hit.
          const name = raw.object.userData.actorName as string | undefined
          const actor = name ? (actors.find((a) => a.name === name) ?? null) : null
          hit = actor ? { actor, polyIndex: null, isLineHit: true } : null
        }
      }
    }
  }
  if (!hit) {
    // The camera is posed in REFLECTED space (viewportRender.ts reflects the pose by R = diag(1,-1,1),
    // the left-handed-world fix), so `raycaster.ray` is in reflected space. The raycast candidates
    // above resolve through their own `matrixWorld` (which carries the same reflection), so they need
    // no adjustment -- but `pickActor`'s AABBs come straight from `SceneActor.bbox_*` in GAME
    // coordinates, so map the ray back by R (its own inverse: negate Y of origin + direction).
    const ray: Ray = {
      origin: [raycaster.ray.origin.x, -raycaster.ray.origin.y, raycaster.ray.origin.z],
      direction: [raycaster.ray.direction.x, -raycaster.ray.direction.y, raycaster.ray.direction.z],
    }
    const aabbCandidates = mode === 'wireframe' ? actors.filter((a) => !a.brush) : actors
    const actor = pickActor(ray, aabbCandidates)
    hit = actor ? { actor, polyIndex: null, isLineHit: false } : null
  }
  return resolveTapAction(hit, mode, shiftKey, additive)
}
