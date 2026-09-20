// The world-space grid backdrop for an ortho pane (quad-layout Part 8, Task 28) -- drawn
// first/always-behind-everything (depthTest false, matching preview.py's own grid: "a BACKDROP,
// drawn first, before any geometry, never depth-tested"). The escalation/tiering math itself
// (major/minor lerp, odd-line fade, world clamp) is `grid.ts`'s `worldGridLines`, a faithful port of
// UnrealEd's real `DrawGridSection` via `preview.py` (dev/docs/GUI.md "The world-anchored grid" --
// decided: real UED22 parity). This file is a pure rendering wrapper around that math -- not
// meaningfully unit-testable itself (`grid.test.ts` covers the math it draws from).
import { useEffect, useMemo } from 'react'
import { useThree } from '@react-three/fiber'
import * as THREE from 'three'

import type { Vec3 } from './camera'
import { orthoGridWindow, worldGridLines } from './grid'
import type { OrthoAxis, OrthoPose } from './orthoCamera'
import { orthoBasis } from './orthoCamera'

function worldPointAt(center: Vec3, right: Vec3, up: Vec3, u: number, v: number): Vec3 {
  return [center[0] + right[0] * u + up[0] * v, center[1] + right[1] * u + up[1] * v, center[2] + right[2] * u + up[2] * v]
}

// A grid line's world coordinate maps to a CONTINUOUS device-pixel position; whenever that position
// lands off a whole pixel, `LineBasicMaterial`'s antialiased 1px GL_LINE splits coverage across two
// pixels -- a real, well-known WebGL rasterization artifact (not a bug in the escalation/color math
// below, which a prior investigation already verified matches UED22 -- see
// `dev/docs/board/done/ortho-grid-density-no-reproducible-bug-found/`). Two adjacent grid lines
// almost never share the same sub-pixel phase (their spacing in device pixels is essentially never a
// whole number for a continuous zoom level), so one frame shows some lines crisp and others blurred
// ("some render wider"); panning continuously shifts every line's phase together, so WHICH lines are
// crisp keeps changing ("when I move, they alternate"). Confirmed live (headless-Chromium pixel
// measurement of the actual rendered canvas, not reasoning about the math alone): at a fixed pose,
// several lines were exactly 1 device pixel wide at full color strength while their neighbors split
// evenly across 2 pixels at half strength; panning by a few CSS pixels changed WHICH lines were
// which, with the boundary between the two groups sliding along the row -- the reported symptom,
// reproduced exactly.
//
// Fixed the standard way (Illustrator, browser devtools' own grid overlay): snap each line's
// coordinate to the nearest device-pixel CENTER before building its geometry (empirically the
// correct target here -- the alternative, snapping to a pixel BOUNDARY, was tried and measured
// uniformly WORSE, every line landing exactly on the half-blurred worst case instead of crisp).
// UED22's own software rasterizer has no sub-pixel concept at all (`Draw2DPoint`/`DrawLine` write
// whole pixels) -- landing our lines on whole device pixels is closer to that than reproducing a
// WebGL-only antialiasing artifact UED22 could never exhibit.
//
// `originWorld` is the world coordinate that maps to device pixel 0 (the pane's own left/top edge --
// `bounds.uMin`/`bounds.vMax`), a stable reference independent of pan; `axisSign` is +1 for 'u'
// (screen X grows with `u`) and -1 for 'v' (screen Y grows as `v` -- world "up" -- SHRINKS).
function snapToDevicePixel(worldCoord: number, originWorld: number, pxPerUnit: number, axisSign: 1 | -1): number {
  const rawDevicePx = axisSign * (worldCoord - originWorld) * pxPerUnit
  const snappedDevicePx = Math.floor(rawDevicePx) + 0.5
  return worldCoord + (axisSign * (snappedDevicePx - rawDevicePx)) / pxPerUnit
}

export function GridOverlay({ pose, axis, baseGridSize }: { pose: OrthoPose; axis: OrthoAxis; baseGridSize: number }) {
  const { size } = useThree()
  const dpr = useThree((s) => s.viewport.dpr) || 1
  const geometry = useMemo(() => {
    const { right, up } = orthoBasis(axis)
    const halfW = (size.width / 2) * pose.worldUnitsPerPixel
    const halfH = (size.height / 2) * pose.worldUnitsPerPixel
    const { bounds, planeOrigin } = orthoGridWindow(pose.center, right, up, halfW, halfH)
    // UnrealEd's real DrawGridSection escalation reads ONLY the viewport's pixel WIDTH (`Frame->X`),
    // never its height, for both line directions (dev/docs/spikes/2026-08-30-unrealed-ortho-grid-
    // density/spike.md "int width = Frame->X") -- ported verbatim rather than inventing a
    // GUI-specific per-axis width for a pane that (unlike preview.py's always-square renders) isn't
    // necessarily square.
    const { lines } = worldGridLines(baseGridSize, size.width, pose.worldUnitsPerPixel, bounds)
    // NOT `gl.domElement.width/height` -- three.js floors THAT (`canvas.width = Math.floor(width *
    // pixelRatio)`) but ROUNDS the actual viewport rect it renders through (`setViewport`'s
    // `.round()`, see `snapToDevicePixel`'s doc comment), and a quad pane's CSS size is routinely
    // fractional (measured live: 360.5 CSS px -> canvas.width 360 but a real 361-wide viewport) --
    // using the floored value here left every line short by that 1-part-in-360 scale error,
    // compounding to over half a device pixel of drift by the pane's far edge (caught by live
    // screenshot pixel measurement: crisp lines only near the pane's own snap origin, blurred toward
    // its edges, not the uniform failure/success a scale bug this size should NOT look like at a
    // glance -- worth recording so a future reader doesn't mistake a partial-looking result for "the
    // fix didn't work" and revert it instead of re-deriving this same root cause).
    const pxPerUnitU = Math.round(size.width * dpr) / (2 * halfW)
    const pxPerUnitV = Math.round(size.height * dpr) / (2 * halfH)

    const positions: number[] = []
    const colors: number[] = []
    for (const line of lines) {
      const at =
        line.axis === 'u'
          ? snapToDevicePixel(line.at, bounds.uMin, pxPerUnitU, 1)
          : snapToDevicePixel(line.at, bounds.vMax, pxPerUnitV, -1)
      const [p1, p2] =
        line.axis === 'u'
          ? [worldPointAt(planeOrigin, right, up, at, bounds.vMin), worldPointAt(planeOrigin, right, up, at, bounds.vMax)]
          : [worldPointAt(planeOrigin, right, up, bounds.uMin, at), worldPointAt(planeOrigin, right, up, bounds.uMax, at)]
      positions.push(...p1, ...p2)
      const [r, g, b] = line.color
      colors.push(r / 255, g / 255, b / 255, r / 255, g / 255, b / 255)
    }
    const geo = new THREE.BufferGeometry()
    geo.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3))
    geo.setAttribute('color', new THREE.Float32BufferAttribute(colors, 3))
    return geo
  }, [pose, axis, size.width, size.height, baseGridSize, dpr])

  useEffect(() => () => geometry.dispose(), [geometry])

  return (
    // renderOrder pins the grid as the first thing drawn: with depthTest off, three.js's draw order
    // for depthTest-false siblings (brush outlines' bold ring, point-actor markers) is otherwise
    // scene-graph/insertion order, not guaranteed -- a low renderOrder makes "grid always at the
    // bottom" hold regardless of where in the tree it's mounted. depthWrite off too, so the grid's
    // own (somewhat arbitrary) plane depth can never fail a depth-tested sibling drawn after it.
    // vertexColors carries each line's own major/minor/fade colour from `worldGridLines`.
    <lineSegments geometry={geometry} renderOrder={-10}>
      <lineBasicMaterial vertexColors depthTest={false} depthWrite={false} />
    </lineSegments>
  )
}
