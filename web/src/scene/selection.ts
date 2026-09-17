// Click-to-select picking. The PRIMARY path (`resolveHitActor`) raycasts the actual rendered
// geometry (the merged bufferGeometry Viewport3D.tsx builds from `scene.polys`) and maps the hit
// triangle back to its owning actor via `ScenePoly.owner` -- real per-poly ownership, so a small
// brush fully enclosed in a bigger brush's bounding box is still selectable by its OWN geometry.
// `pickActor` (ray-vs-actor-AABB) is the FALLBACK for a tap that doesn't land on any drawn
// triangle -- the only way to select a non-brush point actor (no geometry of its own, out of scope
// here) today, so it must keep working exactly as before. Pure and framework-free (the
// screen-to-ray conversion, which needs the real camera projection, lives in Viewport3D.tsx via
// three.js's Raycaster; only the picking algorithm itself is here, so it's testable without a
// WebGL context).
import type { SceneActor } from '../api'
import type { Vec3 } from './camera'
import type { ShadingMode } from './shadingMode'

/** Resolves a raycast hit on the merged scene geometry to its owning actor: `faceIndex` is
 * `THREE.Intersection.faceIndex` (a triangle index into the non-indexed geometry, so it indexes
 * `triangleOwners` directly -- `geometry.ts`'s `buildGeometryData` emits one owner entry per
 * triangle in the SAME order). Returns null when there was no hit, the hit triangle has no
 * resolved owner (an out-of-range CSG join), or the name doesn't match any actor in the current
 * payload (a live-reload race). */
export function resolveHitActor(
  faceIndex: number | null | undefined,
  triangleOwners: (string | null)[],
  actors: SceneActor[],
): SceneActor | null {
  if (faceIndex == null) return null
  const name = triangleOwners[faceIndex]
  if (name == null) return null
  return actors.find((a) => a.name === name) ?? null
}

/** A raycast hit resolved to its owning actor and, when the hit poly has one, its `i_brush_poly`
 * (`ScenePoly.i_brush_poly`, `geometry.ts`'s `trianglePolyIndex`) -- the surface (texture) selection
 * identity (GUI.md "Selection & the Inspector": a plain click in non-wireframe mode selects the one
 * clicked surface's texture, distinct from selecting the whole brush actor). `polyIndex` is null for
 * an actor with no single source poly for the hit triangle (a mesh actor, which has no
 * `.brush.polys`) -- the actor still resolves; there's just no ONE polygon to surface-select. */
export interface SurfaceHit {
  actor: SceneActor
  polyIndex: number | null
}

/** Resolves a raycast hit on the merged scene geometry to its owning actor AND poly, mirroring
 * `resolveHitActor` but also carrying `trianglePolyIndex[faceIndex]` -- `geometry.ts`'s
 * `buildGeometryData` emits one entry per triangle in the same order for both arrays. Returns null
 * only when `resolveHitActor` itself does (no hit, no resolved owner, or a stale name from a
 * live-reload race) -- an unresolved POLY (a mesh-actor hit) still returns the resolved actor, with
 * `polyIndex: null`, so a click on a mesh actor's own triangles keeps identifying it instead of
 * falling through to the AABB fallback (or missing/deselecting) the way a lost actor would. */
export function resolveHitSurface(
  faceIndex: number | null | undefined,
  triangleOwners: (string | null)[],
  trianglePolyIndex: (number | null)[],
  actors: SceneActor[],
): SurfaceHit | null {
  const actor = resolveHitActor(faceIndex, triangleOwners, actors)
  if (!actor || faceIndex == null) return null
  return { actor, polyIndex: trianglePolyIndex[faceIndex] ?? null }
}

/** Resolves a raycast hit on `BrushOutlines`' merged thin-wireframe `LineSegments` (bug report item
 * 4/6) to its owning actor: `index` is `THREE.Intersection.index` -- for a `LineSegments` hit,
 * three.js's own `Line.raycast` sets it to the segment's FIRST vertex index, so `index / 2` is the
 * segment number, indexing `segmentOwners` directly (`brushRings.ts`'s `mergeThinRings`, one owner
 * per 2-vertex segment, same per-index-array shape as `resolveHitActor`'s `triangleOwners`). */
export function resolveSegmentHitActor(
  index: number | null | undefined,
  segmentOwners: (string | null)[],
  actors: SceneActor[],
): SceneActor | null {
  if (index == null) return null
  const name = segmentOwners[Math.floor(index / 2)]
  if (name == null) return null
  return actors.find((a) => a.name === name) ?? null
}

export type TapAction =
  | { kind: 'select-actor'; name: string; additive: boolean }
  | { kind: 'select-surface'; actor: string; polyIndex: number; additive: boolean }
  | { kind: 'deselect' }
  | { kind: 'none' }

/** What the raycast+AABB hit-test pipeline (`tapSelect.ts`'s `resolveTapSelect`) found, before the
 * click-target (surface vs. whole actor) and modifier-key rules below are applied. `polyIndex` is
 * non-null ONLY for a genuine hit on the drawn solid mesh (`selection.ts`'s `resolveHitSurface`) --
 * a marker/wireframe-line hit or an AABB-fallback hit (missed all real geometry) carries `null`,
 * since neither identifies one specific polygon. `isLineHit` distinguishes those two `polyIndex:
 * null` cases: true for a genuine hit on drawn LINE geometry (a brush/Mover outline,
 * `resolveSegmentHitActor`/the bold-ring branch in `tapSelect.ts`), false for the ray-vs-AABB
 * fallback (`pickActor`, engaged only once the raycast found nothing at all to hit). */
export interface RawTapHit {
  actor: SceneActor
  polyIndex: number | null
  isLineHit: boolean
}

/** The tap-resolution decision Viewport3D/OrthoViewport's `performTapSelect` both make once they've
 * run the hit-test pipeline (GUI.md "Selection & the Inspector"). `rawHit` is null for a genuine
 * miss (clicked empty space) -- ALWAYS `'deselect'`, in any pane/mode (owner ruling 2026-09-15,
 * reversing spec §9's earlier "Esc is the only deselect path"). Otherwise:
 * - A POINT actor (`!actor.brush`) is always plain-tap-selectable, everywhere, unaffected by Shift
 *   or shading mode -- `'select-actor'` with the passed-through (Ctrl/Cmd-driven) `additive`.
 * - A genuine SURFACE hit (`polyIndex` set) in a NON-wireframe mode is the one case Shift forks the
 *   SAME click target between texture-select (unmodified) and actor-select (shifted): unmodified ->
 *   `'select-surface'` (additive = Ctrl, "multi-selects textures"); Shift held -> `'select-actor'`,
 *   ALWAYS additive (repeated Shift+LMB accumulates multiple brush selections, no Ctrl needed).
 * - A genuine LINE hit (`isLineHit`, e.g. a Mover's always-visible outline) never needs a modifier,
 *   in ANY shading mode -- same rule as wireframe mode's own outline click, since a line click has no
 *   competing poly/texture-select interpretation to disambiguate from a camera-fly drag (owner
 *   ruling 2026-09-17, `shift-modifier-convention-broken-for-poly-and`).
 * - Anything else -- a wireframe-mode click with no poly hit, or a non-wireframe hit that missed all
 *   real geometry (AABB fallback, no specific surface to fall back to a texture-select on) -- is a
 *   whole-brush pick, gated the same way brush selection has always been (`canSelectBrushTap`):
 *   wireframe needs no modifier (Ctrl still multi-selects); a non-wireframe fallback hit still needs
 *   Shift, and a hit that Shift didn't clear is ABSORBED (`'none'`), not treated as a miss -- the tap
 *   landed on something, so it must not wipe an existing selection.
 * Pulled out as a pure, tiny function so this exact decision is testable without a WebGL raycast. */
export function resolveTapAction(
  rawHit: RawTapHit | null,
  mode: ShadingMode,
  shiftKey: boolean,
  additive: boolean,
): TapAction {
  if (!rawHit) return { kind: 'deselect' }
  const { actor, polyIndex, isLineHit } = rawHit

  if (!actor.brush) return { kind: 'select-actor', name: actor.name, additive }

  if (polyIndex != null && mode !== 'wireframe') {
    if (shiftKey) return { kind: 'select-actor', name: actor.name, additive: true }
    return { kind: 'select-surface', actor: actor.name, polyIndex, additive }
  }

  if (isLineHit) return { kind: 'select-actor', name: actor.name, additive }

  if (!canSelectBrushTap(mode, shiftKey)) return { kind: 'none' }
  return { kind: 'select-actor', name: actor.name, additive: mode === 'wireframe' ? additive : true }
}

export interface Ray {
  origin: Vec3
  direction: Vec3
}

/** One raycast candidate, reduced to its screen-pixel position (`tapSelect.ts` projects each
 * `THREE.Intersection.point` through the camera before calling this). */
export interface ScreenHit<T> {
  value: T
  screenX: number
  screenY: number
}

/** Picks the candidate whose PROJECTED SCREEN POSITION is closest to the actual click point --
 * fixes a real bug in naively taking `Raycaster.intersectObjects(...)[0]`: three.js sorts line/mesh
 * intersections by `distance` (depth from the ray origin to the intersection point), NOT by how
 * close the hit is to the click on screen (`node_modules/three/src/objects/Line.js`'s
 * `checkIntersection`: `distance = raycaster.ray.origin.distanceTo(_intersectPointOnRay)`). For a
 * THRESHOLD-based line hit-test (wireframe brush/mover outlines, `WIREFRAME_LINE_HIT_WORLD_UNITS`/
 * `orthoLineHitThresholdUU`) that threshold can, in a busy or tightly-framed scene, admit several
 * candidates at once -- and depth-nearest is frequently NOT the one visually under the cursor (an
 * unrelated line or marker sprite merely closer to the camera along that ray). Confirmed live
 * (`wireframe-brush-selection-should-hit-test-lines`/`mover-near-brush803-unclickable-in-wireframe-
 * 2d`): clicking squarely on a Mover's own rendered outline line consistently resolved to a
 * different, farther-on-screen actor whose line happened to sit nearer the camera. Real UED22's own
 * click hit-test (disassembled `UEditorEngine::Click`, `Editor.dll`) is fundamentally screen-space
 * too -- it scans a fixed ~5x5 PIXEL box around the cursor, never a world-space radius -- so
 * screen-nearest is the faithful tie-break, not merely a plausible one. A genuine miss (empty hits
 * array) is unaffected -- this only re-ranks candidates the threshold already accepted. */
export function nearestScreenHit<T>(hits: ScreenHit<T>[], clickX: number, clickY: number): T | null {
  if (hits.length === 0) return null
  let best = hits[0]
  let bestDistSq = (best.screenX - clickX) ** 2 + (best.screenY - clickY) ** 2
  for (let i = 1; i < hits.length; i++) {
    const distSq = (hits[i].screenX - clickX) ** 2 + (hits[i].screenY - clickY) ** 2
    if (distSq < bestDistSq) {
      bestDistSq = distSq
      best = hits[i]
    }
  }
  return best.value
}

/** One raycast hit, tagged with what `pickHit` needs to rank it. `isLine` distinguishes a
 * `THREE.Line`/`LineSegments`/`LineLoop` hit (only THRESHOLD-accepted -- see `nearestScreenHit`'s
 * doc comment) from a PRECISE mesh/sprite hit (a real ray-triangle/quad intersection). `alwaysOnTop`
 * is only meaningful when `isLine` is true: whether that line renders `depthTest: false`, so it
 * composites over other geometry regardless of real depth (a Mover's outline, a selected brush's
 * bold ring -- `BrushOutlines.tsx`). `hits` must arrive with PRECISE hits already in real ray-depth
 * order (`intersectObjects`' own ascending-distance sort) -- `pickHit` never reorders them. */
export interface HitCandidate<T> {
  value: T
  isLine: boolean
  alwaysOnTop: boolean
  screenX: number
  screenY: number
}

/** Decides which of several accepted raycast hits wins a click -- pulled out of `tapSelect.ts` so
 * the decision is directly unit-testable without a real `THREE.Raycaster`/camera.
 *
 * Among LINE hits, screen-nearest wins (`nearestScreenHit`'s own rationale: a line's reported point
 * may be genuinely off to the side of the click). Among PRECISE hits, the one already nearest in
 * real depth wins outright (`hits`' own order) -- screen-distance can't disambiguate two precise
 * hits, since any two points on the SAME ray reproject to the same screen pixel regardless of depth.
 *
 * Between the two kinds: the screen-nearest LINE only beats the depth-nearest PRECISE hit when THAT
 * WINNING line is `alwaysOnTop` AND is at least as close to the click as the precise hit --
 * `alwaysOnTop` alone is not enough (bug found 2026-09-17, `shift-modifier-convention-broken-for-
 * poly-and`): a Mover's outline is threshold-accepted out to `lineThreshold` world units, which can
 * be several screen pixels wide, so an always-on-top line can be a valid raycast candidate while
 * sitting well off to the side of a click that's actually centered on a closer, ordinary poly (e.g.
 * a brush's own wall right next to a Mover's frame) -- live-confirmed on `showcase_bar`: a precise
 * hit on `Brush803`'s own poly was silently discarded in favor of `DeusExMover4`'s outline merely
 * because the outline was ALSO within threshold, regardless of which was actually nearer the click.
 * The intended case (a Mover's outline drawn over the wall it doesn't occlude, board item
 * `mover-not-selectable-via-wireframe-click`) still wins: there the outline IS the nearest thing to
 * the click, so the distance check still passes. A merely-screen-nearest ORDINARY (non-always-on-top)
 * line never overrides a genuine precise hit either way -- only the WINNING line's own
 * always-on-top-ness (and now its distance) matters, never some other, losing line candidate's. */
export function pickHit<T>(hits: HitCandidate<T>[], clickX: number, clickY: number): T | null {
  if (hits.length === 0) return null
  const lineHits = hits.filter((h) => h.isLine)
  const preciseHits = hits.filter((h) => !h.isLine)
  let bestLine: HitCandidate<T> | null = null
  let bestLineDistSq = Infinity
  for (const h of lineHits) {
    const distSq = (h.screenX - clickX) ** 2 + (h.screenY - clickY) ** 2
    if (distSq < bestLineDistSq) {
      bestLineDistSq = distSq
      bestLine = h
    }
  }
  if (preciseHits.length > 0) {
    const precise = preciseHits[0]
    const preciseDistSq = (precise.screenX - clickX) ** 2 + (precise.screenY - clickY) ** 2
    const lineWins = (bestLine?.alwaysOnTop ?? false) && bestLineDistSq <= preciseDistSq
    if (!lineWins) return precise.value
  }
  if (bestLine) return bestLine.value
  return preciseHits[0]?.value ?? null
}

/** A point-actor sprite's icon has transparent padding around its drawn shape (`tapSelect.ts`'s
 * `resolveTapSelect` raycasts the sprite's full billboard quad, then samples this alpha at the hit
 * point). Whether a sampled alpha counts as "nothing drawn there" -- board item
 * `point-actor-sprite-picking-ignores-sprite-alpha`. UED22's own click hit-test needs no special
 * sprite-alpha rule at all: it reads a rendered hit-proxy buffer back for the cursor's ~5x5 pixel box
 * (`nearestScreenHit`'s doc comment), and its masked-sprite BLIT (`SoftDrv/Src/DrawTile.cpp`'s
 * `FlashSprite32Masked`: `if (Texel) Screen[x] = Palette[Texel]` -- source confirmed against the
 * `SoftDrv.SoftwareRenderDevice` this project's own headless editor uses, `dev/docs/unrealed/
 * rendering.md`) never writes the destination pixel at all when the source texel is the reserved
 * transparent palette index -- so a transparent pixel is invisible to the SAME hit-proxy readback
 * that makes the sprite's opaque pixels selectable, as a pure side effect of the shared raster path,
 * not a separately-coded rule (📖 source: `Source/SoftDrv/Src/{Hit,DrawTile}.cpp`, `fgsfdsfgs/UE1`;
 * cross-checked against this repo's `Editor.dll`/`render.dll` exports -- `HActor`'s `PUSH_HIT` call
 * site in `UnSprite.cpp`'s `DrawActorSprite` matches the real DLL's hit-proxy class exports). UE1's
 * masking is a hard binary test (palette index 0 or not); this codebase's atlas textures are
 * anti-aliased PNGs with soft edges, so `threshold` reuses the existing masked-material alphaTest
 * cutoff (`sceneResources.ts`'s `resolveMaterialState`, 0.5) rather than testing for exact zero. */
export function isTransparentPixel(alpha: number, threshold = 0.5): boolean {
  return alpha < threshold
}

/** Ray-vs-AABB slab test. Returns the entry distance (clamped to >= 0 for a ray starting inside
 * the box), or null if the ray misses. */
export function rayAabbIntersect(ray: Ray, lo: Vec3, hi: Vec3): number | null {
  let tmin = -Infinity
  let tmax = Infinity
  for (let i = 0; i < 3; i++) {
    const o = ray.origin[i]
    const d = ray.direction[i]
    if (Math.abs(d) < 1e-12) {
      if (o < lo[i] || o > hi[i]) return null
      continue
    }
    let t1 = (lo[i] - o) / d
    let t2 = (hi[i] - o) / d
    if (t1 > t2) [t1, t2] = [t2, t1]
    tmin = Math.max(tmin, t1)
    tmax = Math.min(tmax, t2)
    if (tmin > tmax) return null
  }
  if (tmax < 0) return null
  return Math.max(tmin, 0)
}

/** The actor whose bbox the ray hits first (closest positive-t AABB hit), or null if the ray
 * misses every actor. */
export function pickActor(ray: Ray, actors: SceneActor[]): SceneActor | null {
  let best: SceneActor | null = null
  let bestT = Infinity
  for (const actor of actors) {
    const t = rayAabbIntersect(ray, actor.bbox_lo, actor.bbox_hi)
    if (t !== null && t < bestT) {
      bestT = t
      best = actor
    }
  }
  return best
}

/** This is SHADING-MODE-gated (wireframe vs. non-wireframe), not viewport-gated -- corrected owner
 * ruling 2026-09-15 (an earlier pass had this backwards as 3D-vs-2D). In wireframe mode -- the 2D
 * ortho panes are always wireframe, and the 3D perspective pane can be too -- a plain LMB tap
 * selects a brush directly, matching how a point actor is always plain-tap-selectable. In a
 * NON-wireframe shading mode (only possible in the 3D perspective pane: `unlit`/`flat`/`lit`), a
 * plain LMB-drag is camera-fly (dolly+turn), so a tap landing on a brush is ambiguous with an
 * incidental camera nudge -- Shift+LMB is the disambiguator there. */
export function canSelectBrushTap(mode: ShadingMode, shiftKey: boolean): boolean {
  return mode === 'wireframe' || shiftKey
}

export const TAP_DRAG_THRESHOLD_PX = 4

/** Was a pointer-down/up pair a TAP (click-to-select) or a DRAG (camera fly)? A tap is one whose
 * total on-screen travel stayed within `thresholdPx` -- the gate between LMB's two dual-purpose
 * behaviors (spec, "Selection & inspector": "LMB tap ... below the camera-fly drag threshold"). */
export function isTap(
  startX: number,
  startY: number,
  endX: number,
  endY: number,
  thresholdPx: number = TAP_DRAG_THRESHOLD_PX,
): boolean {
  return Math.hypot(endX - startX, endY - startY) <= thresholdPx
}
