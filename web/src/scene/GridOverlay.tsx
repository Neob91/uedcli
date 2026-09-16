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

export function GridOverlay({ pose, axis, baseGridSize }: { pose: OrthoPose; axis: OrthoAxis; baseGridSize: number }) {
  const { size } = useThree()
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

    const positions: number[] = []
    const colors: number[] = []
    for (const line of lines) {
      const [p1, p2] =
        line.axis === 'u'
          ? [worldPointAt(planeOrigin, right, up, line.at, bounds.vMin), worldPointAt(planeOrigin, right, up, line.at, bounds.vMax)]
          : [worldPointAt(planeOrigin, right, up, bounds.uMin, line.at), worldPointAt(planeOrigin, right, up, bounds.uMax, line.at)]
      positions.push(...p1, ...p2)
      const [r, g, b] = line.color
      colors.push(r / 255, g / 255, b / 255, r / 255, g / 255, b / 255)
    }
    const geo = new THREE.BufferGeometry()
    geo.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3))
    geo.setAttribute('color', new THREE.Float32BufferAttribute(colors, 3))
    return geo
  }, [pose, axis, size.width, size.height, baseGridSize])

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
