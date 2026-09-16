// The world-anchored, escalating ortho grid -- a faithful port of UnrealEd's real
// `UEditorEngine::DrawGridSection` (RE'd in `dev/docs/spikes/2026-08-30-unrealed-ortho-grid-density/`),
// via `uedcli/preview.py`'s own port of the same algorithm (`_grid_escalation`/`_grid_line_color`/
// `_grid_indices`, `preview.py:2000-2042`). Decided (dev/docs/GUI.md "The world-anchored grid"):
// real UED22 parity, not the earlier 1-2-5-10-per-decade sequence this file used to compute.
//
// The user picks a fixed BASE step (`GRID_SIZE_OPTIONS`, UnrealEd's own persistent "Grid Size"
// preference -- `GridOverlay`'s `baseGridSize` prop, set by `QuadLayout`'s grid-size dropdown); the
// escalation below doubles that step as the view zooms out, exactly like the real editor, rather
// than re-deriving a step from the current zoom the way `_auto_grid_step` does for `preview.py`'s
// own no-`--grid-size` default path (out of scope here -- the GUI always has an explicit base step).

/** Powers of two from 1 to 512 -- the same "must be a power of two" domain `preview.py --grid-size`
 * validates (`uedcli/tests/test_preview_grid.py::test_grid_size_must_be_a_power_of_two`), offered as
 * the GUI's base-grid-size choices. */
export const GRID_SIZE_OPTIONS = [1, 2, 4, 8, 16, 32, 64, 128, 256, 512] as const

// No fixed default in `preview.py` (it auto-picks from zoom when `--grid-size` is omitted) -- 16 is
// a sensible engine-standard "Grid Size" default that keeps on-screen density close to what this
// GUI's prior 1-2-5-10 default looked like at typical zoom.
export const DEFAULT_GRID_SIZE = 16

// `preview.py`'s `_GRID_BASE`/`_GRID_TARGET` (`preview.py:1982-1983`): the lerp endpoints a line's
// colour interpolates between -- BASE is also this GUI's own ortho background (`#404040`), so a
// fully-faded odd line fades to invisible, matching the real editor's own base-colour lerp origin.
export const GRID_BASE: readonly [number, number, number] = [64, 64, 64]
export const GRID_TARGET: readonly [number, number, number] = [96, 96, 96]

// UE1's own world extent (`preview.py:1984` `_GRID_WORLD_CLAMP`) -- line indices never range past
// +/- this, regardless of how far a pane is zoomed/panned.
const GRID_WORLD_CLAMP = 32768

export interface GridEscalation {
  shift: number
  drawn: number
  fade: number
}

/** Port of `preview.py`'s `_grid_escalation` (`preview.py:2000-2018`), itself UnrealEd's real
 * `DrawGridSection` density rule (spike "The rule"): `step` doubles (`shift` counts the doublings)
 * until lines are drawn >= 4px apart in a `widthPx`-wide pane; `fade` (else 1.0) anti-pops the lines
 * the next doubling would drop. `widthPx < 4` returns unescalated -- narrower than the 4px threshold
 * itself, so there's nothing to escalate to (guards `limit === 0`, which the loop's own exit
 * condition could never satisfy). The real editor reads only the viewport's pixel WIDTH
 * (`Frame->X`), never its height, for this calculation -- ported verbatim by `GridOverlay`, which
 * always passes the pane's screen width regardless of axis. */
export function gridEscalation(widthPx: number, worldUnitsPerPixel: number, step: number): GridEscalation {
  if (widthPx < 4) return { shift: 0, drawn: step, fade: 1.0 }
  // Python's `int(x)` truncates toward zero; every input here is positive, so `Math.floor` agrees.
  const count = Math.floor((widthPx * worldUnitsPerPixel) / step)
  const limit = Math.floor(widthPx / 4)
  let shift = 0
  let fade = 1.0
  if (2 * count >= limit) {
    while (count >> shift >= limit) shift++
    fade = 2.0 - (2.0 * count) / ((1 << shift) * limit)
  }
  return { shift, drawn: step << shift, fade }
}

/** Port of `preview.py`'s `_grid_line_color` (`preview.py:2021-2031`): `tier` lerps `GRID_BASE`
 * toward `GRID_TARGET` -- every 8th line (in DRAWN units, `(i << shift) & 7`) lands on `GRID_TARGET`
 * (major), the rest halfway (minor); an ODD line (`i & 1`) -- exactly the ones the next doubling
 * would drop -- additionally fades back toward `GRID_BASE` by `fade`, so it's already invisible when
 * it's dropped. Majors sit at multiples of 8 and so are always even and never fade. */
export function gridLineColor(i: number, shift: number, fade: number): [number, number, number] {
  const tier = ((i << shift) & 7) !== 0 ? 0.5 : 1.0
  let c: [number, number, number] = [
    GRID_BASE[0] + (GRID_TARGET[0] - GRID_BASE[0]) * tier,
    GRID_BASE[1] + (GRID_TARGET[1] - GRID_BASE[1]) * tier,
    GRID_BASE[2] + (GRID_TARGET[2] - GRID_BASE[2]) * tier,
  ]
  if (i & 1) {
    c = [
      GRID_BASE[0] + (c[0] - GRID_BASE[0]) * fade,
      GRID_BASE[1] + (c[1] - GRID_BASE[1]) * fade,
      GRID_BASE[2] + (c[2] - GRID_BASE[2]) * fade,
    ]
  }
  return [Math.round(c[0]), Math.round(c[1]), Math.round(c[2])]
}

export interface IndexRange {
  lo: number
  hi: number
}

/** Port of `preview.py`'s `_grid_indices` (`preview.py:2034-2042`): the DRAWN-unit index range
 * `[lo, hi)` for one axis -- the visible world range `[loWorld, hiWorld)` in units of `step`,
 * clamped to +/- `GRID_WORLD_CLAMP` world units, then scaled down by `shift` (`world = (i << shift)
 * * step` recovers the world coordinate). Returned as bounds, not a materialized array, mirroring
 * Python's lazy `range`. */
export function gridIndices(step: number, shift: number, loWorld: number, hiWorld: number): IndexRange {
  const firstVisible = Math.floor(loWorld / step)
  const lastVisible = Math.ceil(hiWorld / step)
  // `Math.floor(-CLAMP / step)`, NOT `-Math.floor(CLAMP / step)` -- Python's `//` floors toward
  // -infinity, and the two differ whenever `step` doesn't evenly divide `GRID_WORLD_CLAMP`.
  const lo = Math.max(Math.floor(-GRID_WORLD_CLAMP / step), firstVisible) >> shift
  const hi = Math.min(Math.floor(GRID_WORLD_CLAMP / step), lastVisible) >> shift
  return { lo, hi }
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
 * relative to the viewport, not geometry"). `bounds` must be in ABSOLUTE world u/v -- `worldGridLines`
 * places a line at every escalated multiple of the base step WITHIN `bounds`, so a window centered on
 * 0 makes lines always straddle the current pan position instead of landing on fixed world
 * coordinates. `planeOrigin` is `center` with its `right`/`up` components removed (keeping only its
 * component along the plane's own depth axis) -- the base point `u`/`v` offsets are added to when
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

export interface WorldGridLine {
  axis: 'u' | 'v'
  at: number
  /** 0-255 RGB, `gridLineColor`'s own scale -- callers building a `THREE.Color` divide by 255,
   * matching this codebase's existing 0-255-server-color convention (e.g. `BrushOutlines.tsx`). */
  color: [number, number, number]
}

/** Every escalated grid line (both axes) within `bounds`, for a pane `widthPx` wide showing
 * `worldUnitsPerPixel` UU/px, built from the user's chosen `baseStep`. The pure piece `GridOverlay`
 * draws -- ports `preview.py`'s `_draw_grid_backdrop` (`preview.py:2045-2067`) minus the actual pixel
 * blit. `drawnStep` is the step actually rendered after escalation (may differ from `baseStep`, same
 * as `preview.py`'s "set" vs "visible" report). */
export function worldGridLines(
  baseStep: number,
  widthPx: number,
  worldUnitsPerPixel: number,
  bounds: ViewBoundsWorld,
): { lines: WorldGridLine[]; drawnStep: number } {
  const { shift, drawn, fade } = gridEscalation(widthPx, worldUnitsPerPixel, baseStep)
  const lines: WorldGridLine[] = []
  const uRange = gridIndices(baseStep, shift, bounds.uMin, bounds.uMax)
  for (let i = uRange.lo; i < uRange.hi; i++) {
    const at = (i << shift) * baseStep
    lines.push({ axis: 'u', at: at === 0 ? 0 : at, color: gridLineColor(i, shift, fade) })
  }
  const vRange = gridIndices(baseStep, shift, bounds.vMin, bounds.vMax)
  for (let i = vRange.lo; i < vRange.hi; i++) {
    const at = (i << shift) * baseStep
    lines.push({ axis: 'v', at: at === 0 ? 0 : at, color: gridLineColor(i, shift, fade) })
  }
  return { lines, drawnStep: drawn }
}
