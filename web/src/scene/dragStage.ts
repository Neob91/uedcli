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
 * Deliberately does NOT and cannot translate the actor's baked CSG solid mesh
 * (`ScenePayload.polys`, built server-side from committed geometry) -- that has no per-actor
 * transform to apply (it's one shared merged buffer, not addressable per actor) and can only be
 * correct again after a server Rebuild; this stays the one documented carve-out (see
 * `Viewport3D.tsx`'s own `stagedOffsets` doc comment). `radii`/`sprite` carry no vector fields of
 * their own to translate (their overlays derive position from `actor.location`, already covered).
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
