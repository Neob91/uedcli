// Pure glue for Ctrl/Cmd-drag actor movement (Task 8, spec "Interaction design") -- which perspective
// onDrag frames are actor-move gestures rather than camera gestures, and how a gesture's per-frame
// deltas accumulate into a running per-actor staged-location record. No three.js/React/DOM
// dependency, testable against known inputs (mirrors actorMove.ts's/camera.ts's own style). Kept out
// of Viewport3D.tsx itself: that file mixes a component export with value exports would break Vite's
// react-refresh (see viewportRender.ts's own doc comment for the same reasoning), and out of
// actorMove.ts (Task 6, already reviewed/complete) so this task's own new logic stays in its own file.
import type { SceneActor } from '../api'
import type { Vec3 } from './camera'
import type { MoveAxis } from './actorMove'
import { PERSPECTIVE_AXIS_BY_BUTTONS } from './actorMove'

/** The branch-selection Viewport3D.tsx's onDrag needs BEFORE its existing camera-dispatch chain
 * (spec: an actor-move drag must never also move the camera): null means "not an actor-move frame,
 * fall through to the camera dispatch"; a `MoveAxis` means "this frame moves the selection along
 * that axis instead, and the camera must NOT also move." Gated on a non-empty selection -- Ctrl held
 * with nothing selected is not an actor-move gesture, since there's nothing to move. */
export function resolveActorMoveAxis(
  additive: boolean,
  buttons: number,
  selectedNames: ReadonlySet<string>,
): MoveAxis | null {
  if (!additive || selectedNames.size === 0) return null
  return PERSPECTIVE_AXIS_BY_BUTTONS[buttons] ?? null
}

/** Whether the CURRENT drag gesture should move in grid-size increments (owner ruling): brush
 * movement snaps to grid; non-brush actors move continuously; a MIXED selection with ANY brush
 * present snaps the WHOLE selection together (so the group doesn't visibly drift apart relative to
 * each other mid-drag -- every selected actor gets the SAME delta either way, per `applyDelta`
 * below, so snapping is an all-or-nothing choice for the gesture, not a per-actor one). `Mover`s
 * count as brushes here (`SceneActor.brush != null`, the same test `SceneResourcesContext.tsx`'s
 * `meshActorNames` already uses to mean "not a mesh actor") -- a Mover IS a moving brush. */
export function anySelectedIsBrush(selectedNames: ReadonlySet<string>, actors: readonly SceneActor[]): boolean {
  return actors.some((a) => a.brush != null && selectedNames.has(a.name))
}

/** Component-wise vector addition -- accumulates one frame's raw move delta onto the running
 * per-gesture total (Viewport3D.tsx's/OrthoViewport.tsx's `moveDeltaAccRef`), which `snapVecToGrid`
 * below quantizes BEFORE it's applied to the gesture-START base position via `applyDelta`. Snapping
 * the ACCUMULATED total (not each small per-frame delta) is what lets sub-grid mouse motion build up
 * instead of rounding to zero every single frame. */
export function addVec3(a: Vec3, b: Vec3): Vec3 {
  return [a[0] + b[0], a[1] + b[1], a[2] + b[2]]
}

/** Rounds each component of `delta` to the nearest multiple of `gridSize` -- "brush movement should
 * move in grid-size increments, not continuously" (owner ruling). Snaps the drag's own MOVEMENT
 * amount, not the actor's final world coordinate: an actor that didn't start grid-aligned doesn't
 * jump onto one, but every increment it moves by is still an exact multiple of the grid. `gridSize`
 * of 0 or less returns `delta` unchanged (defensive only -- the GUI's own grid-size dropdown,
 * `grid.ts`'s `GRID_SIZE_OPTIONS`, never offers a non-positive value). */
export function snapVecToGrid(delta: Vec3, gridSize: number): Vec3 {
  if (gridSize <= 0) return delta
  return [
    Math.round(delta[0] / gridSize) * gridSize,
    Math.round(delta[1] / gridSize) * gridSize,
    Math.round(delta[2] / gridSize) * gridSize,
  ]
}

/** Accumulates `delta` onto every selected actor's running staged position: starting from its
 * PREVIOUS staged position if this selection already has one (a second drag gesture on the same
 * actor continues from where the first left off, rather than re-basing off the original trunk
 * location), else its original `actors` location (the first move of this actor this session).
 * Returns a NEW object -- `prev`'s untouched entries are reused, not copied -- matching
 * `setStagedOffsets`'s functional-update convention (React state must never be mutated in place). */
export function applyDelta(
  prev: Readonly<Record<string, Vec3>>,
  selectedNames: ReadonlySet<string>,
  delta: Vec3,
  actors: readonly SceneActor[],
): Record<string, Vec3> {
  const next = { ...prev }
  for (const name of selectedNames) {
    const base = prev[name] ?? actors.find((a) => a.name === name)?.location
    if (!base) continue // a selected name absent from this scene (shouldn't happen) -- skip, don't crash
    next[name] = [base[0] + delta[0], base[1] + delta[1], base[2] + delta[2]]
  }
  return next
}

/** The staged locations for exactly the CURRENT selection, read out of the running `offsets`
 * record -- `postStage`'s payload at drag-end. Omits a selected name that has no staged offset (it
 * was never actually moved this session, so it has nothing to stage). */
export function stagedLocationsFor(
  offsets: Readonly<Record<string, Vec3>>,
  selectedNames: ReadonlySet<string>,
): Record<string, Vec3> {
  const result: Record<string, Vec3> = {}
  for (const name of selectedNames) {
    const loc = offsets[name]
    if (loc) result[name] = loc
  }
  return result
}

function addDelta(v: Vec3, delta: Vec3): Vec3 {
  return [v[0] + delta[0], v[1] + delta[1], v[2] + delta[2]]
}

// Translates a flat [x,y,z, x,y,z, ...] array (a brush's own authored `polys`, or a directional
// arrow's `lines`) by `delta`, one (x,y,z) triple at a time.
function translateFlat(flat: readonly number[], delta: Vec3): number[] {
  const out = new Array<number>(flat.length)
  for (let i = 0; i + 2 < flat.length; i += 3) {
    out[i] = flat[i] + delta[0]
    out[i + 1] = flat[i + 1] + delta[1]
    out[i + 2] = flat[i + 2] + delta[2]
  }
  return out
}

/** Returns `actor` translated by its staged offset (if any) -- the delta between its current staged
 * position (`offsets[actor.name]`) and its original `actor.location`. Applied uniformly to every
 * WORLD-SPACE field this GUI reads for rendering an actor's own position-driven overlays:
 * `location`, `bbox_lo`/`bbox_hi` (a pure translation preserves box size), a brush's own AUTHORED
 * `brush.polys`/`brush.local_origin` (`BrushOutlines`' ring, `SelectionMarkers`' vertex/pivot dots),
 * and a `directional_arrow`'s `lines` (`DirectionalArrows`' gizmo) -- all already resolved to
 * world-space by the server from the actor's ORIGINAL (unstaged) location/rotation, so a uniform
 * translate keeps them internally consistent with the new position without re-deriving anything.
 *
 * Deliberately does NOT and cannot translate a BRUSH actor's baked CSG solid mesh
 * (`ScenePayload.polys` entries owned by a brush) -- a CSG result depends on every brush's position
 * relative to every other one, so translating one brush's own solved polys by a delta does not
 * reproduce what a real re-solve would produce; it can only be correct again after a server
 * Rebuild (`dev/docs/GUI.md`'s "Future direction" tracks closing this gap with a session-scoped
 * Rebuild against staged state). A MESH actor's own `ScenePayload.polys` entries have no such
 * constraint (they're independently addressable by owner, not CSG-composited) and DO move -- see
 * `computeOwnerDeltas` below, which `sceneResources.ts`'s `usePatchedMeshPositions` (called from
 * `SceneResourcesContext.tsx`) uses to live-patch exactly the mesh-actor-owned vertices of an
 * already-built geometry, in place, rather than rebuilding it. `radii`/`sprite` carry no vector
 * fields of their own to translate (their overlays derive position from `actor.location`, already
 * covered).
 *
 * Returns `actor` itself, unchanged, when it has no staged offset -- cheap for the (overwhelmingly
 * common) unmoved case, and lets a caller cheaply detect "did anything change" via reference
 * equality if it ever needs to. */
export function applyStagedOffset(actor: SceneActor, offsets: Readonly<Record<string, Vec3>>): SceneActor {
  const staged = offsets[actor.name]
  if (!staged) return actor
  const delta: Vec3 = [staged[0] - actor.location[0], staged[1] - actor.location[1], staged[2] - actor.location[2]]
  return {
    ...actor,
    location: staged,
    bbox_lo: addDelta(actor.bbox_lo, delta),
    bbox_hi: addDelta(actor.bbox_hi, delta),
    brush: actor.brush
      ? {
          ...actor.brush,
          polys: actor.brush.polys.map((p) => translateFlat(p, delta)),
          local_origin: addDelta(actor.brush.local_origin, delta),
        }
      : actor.brush,
    directional_arrow: actor.directional_arrow
      ? { ...actor.directional_arrow, lines: translateFlat(actor.directional_arrow.lines, delta) }
      : actor.directional_arrow,
  }
}

/** `applyStagedOffset` over a whole actor list -- the single derived array Viewport3D.tsx passes to
 * every position-driven overlay consumer (`BrushOutlines`, `SelectionMarkers`, `DirectionalArrows`,
 * `RadiiOverlays`) instead of `scene.actors` directly, so a staged Ctrl/Cmd-drag move is reflected
 * consistently across all of them (not just the point-actor marker sprite). */
export function applyStagedOffsets(actors: readonly SceneActor[], offsets: Readonly<Record<string, Vec3>>): SceneActor[] {
  return actors.map((a) => applyStagedOffset(a, offsets))
}

/** Every actor's own staged delta (`staged location - trunk location`), keyed by name -- omits an
 * unstaged actor entirely (an absent key means "no delta," never a `[0,0,0]` entry). The shared
 * "owner name -> delta" computation both `SceneResourcesContext.tsx`'s `usePatchedMeshPositions`
 * (live-patches a mesh actor's own vertices in place, `geometry.ts`'s `patchOwnerPositions`) and,
 * previously, a since-removed poly-array-rebuild approach needed -- kept here rather than inlined at
 * the one remaining call site so the delta math has one home. */
export function computeOwnerDeltas(
  actors: readonly SceneActor[],
  offsets: Readonly<Record<string, Vec3>>,
): Map<string, Vec3> {
  const deltas = new Map<string, Vec3>()
  for (const actor of actors) {
    const staged = offsets[actor.name]
    if (!staged) continue
    deltas.set(actor.name, [
      staged[0] - actor.location[0],
      staged[1] - actor.location[1],
      staged[2] - actor.location[2],
    ])
  }
  return deltas
}
