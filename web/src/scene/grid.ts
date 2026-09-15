// Adaptive Unreal-Units grid for ortho panes (quad-layout Part 8, Task 27, spec §7): spacing gets
// coarser as you zoom out, finer as you zoom in, snapping to a 1-2-5-10 log-scale sequence at each
// order of magnitude (the common CAD/level-editor convention) -- picked as the DEFAULT since the
// spec explicitly leaves log-2-vs-log-10 open as "cosmetic, planning-time" (flagged for owner
// confirmation, not treated as final). Pure, framework-free.

// The target on-screen spacing (px) grid lines aim for -- fine enough to be useful, coarse enough
// not to look like noise; the spacing snaps UP from this ideal to the nearest 1-2-5-10 value.
const TARGET_LINE_SPACING_PX = 50

/** The minor grid-line spacing, in world (UU) units, for a pane currently showing
 * `worldUnitsPerPixel` UU per screen pixel -- snapped to the nearest 1-2-5-10-times-a-power-of-10
 * value at or above `TARGET_LINE_SPACING_PX` worth of world units, so on-screen line density stays
 * roughly constant as the pane zooms. */
export function gridSpacingUU(worldUnitsPerPixel: number): number {
  const idealUU = TARGET_LINE_SPACING_PX * worldUnitsPerPixel
  const magnitude = Math.pow(10, Math.floor(Math.log10(idealUU)))
  const normalized = idealUU / magnitude // in [1, 10)
  const step = normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 5 ? 5 : 10
  return step * magnitude
}

export interface ViewBoundsWorld {
  uMin: number
  uMax: number
  vMin: number
  vMax: number
}

type Vec3 = [number, number, number]

function dot(a: Vec3, b: Vec3): number {
  return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
}

/** The world-anchored view window for an ortho pane centered on `center` (bug report: "grid is
 * relative to the viewport, not geometry"). `bounds` must be in ABSOLUTE world u/v -- `gridLines`
 * places a line at every multiple of `spacingUU` WITHIN `bounds`, so a window centered on 0 makes
 * lines always straddle the current pan position instead of landing on fixed world coordinates.
 * `planeOrigin` is `center` with its `right`/`up` components removed (keeping only its component
 * along the plane's own depth axis) -- the base point `u`/`v` offsets are added to when
 * reconstructing a line's endpoints, so `center`'s in-plane position isn't double-counted. */
export function orthoGridWindow(
  center: Vec3,
  right: Vec3,
  up: Vec3,
  halfWidthUU: number,
  halfHeightUU: number,
): { bounds: ViewBoundsWorld; planeOrigin: Vec3 } {
  const centerU = dot(center, right)
  const centerV = dot(center, up)
  const bounds = { uMin: centerU - halfWidthUU, uMax: centerU + halfWidthUU, vMin: centerV - halfHeightUU, vMax: centerV + halfHeightUU }
  const planeOrigin: Vec3 = [
    center[0] - right[0] * centerU - up[0] * centerV,
    center[1] - right[1] * centerU - up[1] * centerV,
    center[2] - right[2] * centerU - up[2] * centerV,
  ]
  return { bounds, planeOrigin }
}

export interface GridLine {
  axis: 'u' | 'v'
  at: number
}

/** Every grid line (on each axis) that falls within `bounds`, evenly spaced by `spacingUU` -- the
 * pure piece `GridOverlay` (Task 28) draws. */
export function gridLines(spacingUU: number, bounds: ViewBoundsWorld): GridLine[] {
  const lines: GridLine[] = []
  // `=== 0 ? 0 : x` normalizes a `-0` from `Math.ceil` of a small negative bound back to `+0` --
  // otherwise identical to `0` in every arithmetic sense, but `-0` fails a strict deep-equality
  // check (`toEqual`/`Object.is`) against `0`, which would surprise a caller diffing line positions.
  for (let u = Math.ceil(bounds.uMin / spacingUU) * spacingUU; u <= bounds.uMax; u += spacingUU) {
    lines.push({ axis: 'u', at: u === 0 ? 0 : u })
  }
  for (let v = Math.ceil(bounds.vMin / spacingUU) * spacingUU; v <= bounds.vMax; v += spacingUU) {
    lines.push({ axis: 'v', at: v === 0 ? 0 : v })
  }
  return lines
}
