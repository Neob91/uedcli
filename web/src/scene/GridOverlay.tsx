// The adaptive world-space grid backdrop for an ortho pane (quad-layout Part 8, Task 28). A pure
// rendering wrapper around grid.ts's line math -- drawn first/always-on-top-of-nothing (depthTest
// false, matching preview.py's own grid: "a BACKDROP, drawn first, before any geometry, never
// depth-tested"). Rendering itself (line placement) is NOT meaningfully unit-testable -- the pure
// math it draws from is already covered by grid.test.ts; this file is a manual-verification item
// (Task 28's own note).
import { useEffect, useMemo } from 'react'
import { useThree } from '@react-three/fiber'
import * as THREE from 'three'

import type { Vec3 } from './camera'
import { gridLines, gridSpacingUU } from './grid'
import type { OrthoAxis, OrthoPose } from './orthoCamera'
import { orthoBasis } from './orthoCamera'

const GRID_COLOR = 0x3a3d4a

function worldPointAt(center: Vec3, right: Vec3, up: Vec3, u: number, v: number): Vec3 {
  return [center[0] + right[0] * u + up[0] * v, center[1] + right[1] * u + up[1] * v, center[2] + right[2] * u + up[2] * v]
}

export function GridOverlay({ pose, axis }: { pose: OrthoPose; axis: OrthoAxis }) {
  const { size } = useThree()
  const geometry = useMemo(() => {
    const { right, up } = orthoBasis(axis)
    const halfW = (size.width / 2) * pose.worldUnitsPerPixel
    const halfH = (size.height / 2) * pose.worldUnitsPerPixel
    const spacing = gridSpacingUU(pose.worldUnitsPerPixel)
    const bounds = { uMin: -halfW, uMax: halfW, vMin: -halfH, vMax: halfH }
    const lines = gridLines(spacing, bounds)

    const positions: number[] = []
    for (const line of lines) {
      const [p1, p2] =
        line.axis === 'u'
          ? [worldPointAt(pose.center, right, up, line.at, bounds.vMin), worldPointAt(pose.center, right, up, line.at, bounds.vMax)]
          : [worldPointAt(pose.center, right, up, bounds.uMin, line.at), worldPointAt(pose.center, right, up, bounds.uMax, line.at)]
      positions.push(...p1, ...p2)
    }
    const geo = new THREE.BufferGeometry()
    geo.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3))
    return geo
  }, [pose, axis, size.width, size.height])

  useEffect(() => () => geometry.dispose(), [geometry])

  return (
    <lineSegments geometry={geometry}>
      <lineBasicMaterial color={GRID_COLOR} depthTest={false} />
    </lineSegments>
  )
}
