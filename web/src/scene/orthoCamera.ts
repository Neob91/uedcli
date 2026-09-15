// Pure orthographic-camera math for the three ortho panes (Top/Front/Side, quad-layout Part 1, Task
// 5) -- pan/zoom/screen-projection, no three.js dependency, testable against known inputs (mirrors
// camera.ts's own style). World convention: Z-up, matching camera.ts and the backend's actor
// location tuples (x, y, z).
//
// Axis conventions are NOT re-derived here -- they are the disassembly-sourced, already-shipped
// `actor diagram` conventions this slice's own new requirement asks ortho views to MATCH
// (dev/docs/unrealed/rendering.md "uedcli's offline `actor diagram`", `uedcli/preview.py`'s
// `_DEPTH`/`_framing`): TOP looks down -Z (+X screen-right, +Y screen-down); FRONT looks along +Y
// ("looking south", +X screen-LEFT, +Z screen-up); SIDE looks along +X ("looking east", +Y
// screen-right, +Z screen-up). Deviates from the plan's own loose paraphrase ("Front: looking down
// -Y") in favor of the actual calibrated-against-UnrealEd convention this file must match.
import type { Vec3 } from './camera'
import type { BBox } from './frame'
import { bboxCenter } from './frame'

export type OrthoAxis = 'top' | 'front' | 'side'

export interface OrthoPose {
  center: Vec3
  worldUnitsPerPixel: number
}

interface OrthoBasis {
  forward: Vec3 // into-screen world direction (what the camera looks along)
  right: Vec3 // world direction mapping to increasing screen-x
  up: Vec3 // world direction mapping to decreasing screen-y (i.e. "up" on screen)
}

const ORTHO_BASIS: Record<OrthoAxis, OrthoBasis> = {
  top: { forward: [0, 0, -1], right: [1, 0, 0], up: [0, -1, 0] },
  front: { forward: [0, 1, 0], right: [-1, 0, 0], up: [0, 0, 1] },
  side: { forward: [1, 0, 0], right: [0, 1, 0], up: [0, 0, 1] },
}

export function orthoBasis(axis: OrthoAxis): OrthoBasis {
  return ORTHO_BASIS[axis]
}

function addScaled(v: Vec3, dir: Vec3, s: number): Vec3 {
  return [v[0] + dir[0] * s, v[1] + dir[1] * s, v[2] + dir[2] * s]
}

/** Drag-pan: content follows the cursor (the standard direct-manipulation "grab and drag"
 * convention) -- dragging screen-right moves the visible window LEFT in world space (so content
 * that was already visible appears to slide right with the cursor), and symmetrically for
 * screen-down/`up`. Scaled by `worldUnitsPerPixel` so pan speed is zoom-independent in screen
 * terms. */
export function orthoPan(pose: OrthoPose, axis: OrthoAxis, dxPx: number, dyPx: number): OrthoPose {
  const { right, up } = orthoBasis(axis)
  let center = addScaled(pose.center, right, -dxPx * pose.worldUnitsPerPixel)
  center = addScaled(center, up, dyPx * pose.worldUnitsPerPixel)
  return { center, worldUnitsPerPixel: pose.worldUnitsPerPixel }
}

// A wheel delta of one notch (the browser's standard 120-unit tick) doubles/halves the visible
// world-per-pixel scale -- an exponential zoom curve, matching the perspective camera's own
// dolly-along-forward zoom feel (camera.ts's `zoom`) rather than a linear one that would let a
// large zoomed-out scale overshoot to a negative/zero span.
const ZOOM_NOTCH_PX = 120

// Max zoom-OUT: UE1's real world extent is +/-32768 UU (`preview.py`'s own `_GRID_WORLD_CLAMP` --
// line/geometry coordinates never range past this in any real level). Past the point where that
// whole 65536 UU span already fits on screen, zooming out further shows nothing but empty space --
// and, measured live, pushes `worldUnitsPerPixel` into a range where the grid's own line geometry
// silently stops rendering (WebGL/float32 precision loss at extreme scale, GUI bug report item 2).
// The ceiling is picked so the full extent still fits even in a small resized pane (128px) -- no
// pane can ever usefully need to show more world than that.
const MAX_WORLD_UNITS_PER_PIXEL = (2 * 32768) / 128 // 512 UU/px

// Max zoom-IN floor: sub-UU-per-pixel precision has no practical use (T3D coordinates and UnrealEd's
// own grid never resolve finer than whole UU), and the same extreme-scale precision loss noted above
// applies in this direction too -- measured live, the grid vanishes well before this floor is
// reached, so 0.01 (1 UU spans 100 screen pixels) leaves a wide, confirmed-safe margin.
const MIN_WORLD_UNITS_PER_PIXEL = 0.01

/** Clamps a `worldUnitsPerPixel` value to the confirmed-safe `[MIN_WORLD_UNITS_PER_PIXEL,
 * MAX_WORLD_UNITS_PER_PIXEL]` range -- ANY code path that sets `OrthoPose.worldUnitsPerPixel`
 * directly (not just `orthoZoom`'s scroll-wheel path) must run it through this, or risk the same
 * WebGL/float32 precision loss that makes the grid (and, at the extreme this was found from, the
 * whole scene) silently stop rendering. `OrthoViewport.tsx`'s `F`-frame handler (`orthoFrameFit`
 * below) needs this too: fitting a degenerate (zero-size, point-actor) bbox computes an unclamped
 * `worldUnitsPerPixel` far below this floor, and the ortho pane goes blank. */
export function clampWorldUnitsPerPixel(worldUnitsPerPixel: number): number {
  return Math.min(MAX_WORLD_UNITS_PER_PIXEL, Math.max(MIN_WORLD_UNITS_PER_PIXEL, worldUnitsPerPixel))
}

/** Scroll-wheel zoom: scales `worldUnitsPerPixel` exponentially by the wheel delta (positive
 * `wheelDeltaY`, i.e. scroll down/away, ZOOMS OUT -- matches `camera.ts`'s `zoom`'s sign
 * convention, where a positive delta dollies the camera backward). `center` is unchanged --
 * ortho zoom is a pure scale around the current view center, no dolly needed since there's no
 * camera position to move along an axis. Clamped via `clampWorldUnitsPerPixel` -- unclamped, a
 * long scroll can zoom out or in without limit (GUI bug report item 3). */
export function orthoZoom(pose: OrthoPose, wheelDeltaY: number): OrthoPose {
  const raw = pose.worldUnitsPerPixel * Math.pow(2, wheelDeltaY / ZOOM_NOTCH_PX)
  return { center: pose.center, worldUnitsPerPixel: clampWorldUnitsPerPixel(raw) }
}

// Leaves a visible margin around a framed bbox rather than filling the pane edge-to-edge.
const FRAME_FIT_MARGIN = 0.9

/** `F`-frame fit (quad-layout Part 3, Task 15): recenters on `bbox` and sizes `worldUnitsPerPixel`
 * so the bbox's extent along THIS axis's (right, up) screen plane fits `viewportPx`, clamped via
 * `clampWorldUnitsPerPixel` -- a degenerate (zero-size, point-actor) bbox floors its screen extent
 * at 1 UU, which without the clamp computes a `worldUnitsPerPixel` far below the safe floor and
 * blanks the whole pane (WebGL/float32 precision loss), not just the marker (GUI bug report,
 * confirmed live: framing on a point actor from the org panel zoomed ~1000x past the floor). Pure,
 * so the fit math is directly testable without mounting a `<Canvas>`. */
export function orthoFrameFit(
  bbox: BBox,
  axis: OrthoAxis,
  viewportPx: { width: number; height: number },
  margin: number = FRAME_FIT_MARGIN,
): OrthoPose {
  const center = bboxCenter(bbox)
  const { right, up } = orthoBasis(axis)
  const size: Vec3 = [bbox.hi[0] - bbox.lo[0], bbox.hi[1] - bbox.lo[1], bbox.hi[2] - bbox.lo[2]]
  const extentAlong = (dir: Vec3) => Math.abs(dir[0] * size[0]) + Math.abs(dir[1] * size[1]) + Math.abs(dir[2] * size[2])
  const screenW = Math.max(extentAlong(right), 1)
  const screenH = Math.max(extentAlong(up), 1)
  const viewW = Math.max(viewportPx.width, 1)
  const viewH = Math.max(viewportPx.height, 1)
  const worldUnitsPerPixel = clampWorldUnitsPerPixel(Math.max(screenW / (viewW * margin), screenH / (viewH * margin)))
  return { center, worldUnitsPerPixel }
}

/** Both-mouse-button drag zoom (the ortho panes' "drag-pan + both-button-drag zoom" gesture,
 * `OrthoViewport.tsx`'s pointer-buttons branch): dragging the mouse DOWN (positive `dyPx`, screen-
 * space `movementY`) zooms IN, dragging UP zooms OUT -- the OPPOSITE sign from `orthoZoom`'s own
 * wheel-delta convention above (scroll down/away zooms OUT), since a mouse drag and a wheel notch
 * are different gestures with their own separately-established directions here; conflating the two
 * signs (passing `dyPx` straight through to `orthoZoom`) was the original bug (owner report:
 * both-button-drag zoom was inverted). NOT the projection-mirror bug family (`dev/docs/GUI.md`
 * "Camera & projection") -- that family is entirely about the screen-right/`dx` axis (yaw sign, A/D
 * strafe, fan winding); this is a `dy` gesture-to-gesture sign mismatch, unrelated to it. */
export function orthoDragZoom(pose: OrthoPose, dyPx: number): OrthoPose {
  return orthoZoom(pose, -dyPx)
}

// `THREE.Raycaster.params.Line.threshold` (an ordinary `Line`/`LineSegments`' hit-test tolerance,
// unlike `Line2`'s, which is already screen-space) is a WORLD-UNIT distance -- a fixed value means
// the click tolerance shrinks in screen terms as you zoom out (`worldUnitsPerPixel` grows), to the
// point of needing near-pixel-exact clicks on a brush outline at typical zoom (owner report: "Hard
// to select brushes in 2D view"). Scaling by `worldUnitsPerPixel` keeps the tolerance a constant
// number of ON-SCREEN pixels regardless of zoom.
const LINE_HIT_SCREEN_PX = 2

/** World-unit `Raycaster.params.Line.threshold` for a `screenPx`-wide click buffer around a thin
 * (non-`Line2`) brush outline at the pane's current zoom. */
export function orthoLineHitThresholdUU(worldUnitsPerPixel: number, screenPx: number = LINE_HIT_SCREEN_PX): number {
  return screenPx * worldUnitsPerPixel
}

/** Projects a screen point onto the axis's world plane through `pose.center` -- the click-to-select
 * ray origin/direction builder (an ortho ray direction is always `orthoBasis(axis).forward`,
 * screen-position-independent) AND the cursor-coordinate readout (Part 8). At the exact viewport
 * center this returns `pose.center` itself. */
export function screenToWorld(
  pose: OrthoPose,
  axis: OrthoAxis,
  viewportPx: { w: number; h: number },
  screenX: number,
  screenY: number,
): Vec3 {
  const { right, up } = orthoBasis(axis)
  const dxPx = screenX - viewportPx.w / 2
  const dyPx = screenY - viewportPx.h / 2
  let p = addScaled(pose.center, right, dxPx * pose.worldUnitsPerPixel)
  p = addScaled(p, up, -dyPx * pose.worldUnitsPerPixel) // screen-down (+dyPx) is -up in world terms
  return p
}
