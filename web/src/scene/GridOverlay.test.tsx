import { describe, expect, it } from 'vitest'
import ReactThreeTestRenderer from '@react-three/test-renderer'
import * as THREE from 'three'

import { GridOverlay } from './GridOverlay'
import { worldGridLines, orthoGridWindow } from './grid'
import { orthoBasis } from './orthoCamera'
import type { OrthoPose } from './orthoCamera'

// Regression for a reported bug ("even on 1uu, when I zoom out, I see way too many lines") this
// investigation could not reproduce live (real headless-Chromium zoom sweeps, `worldUnitsPerPixel`
// 4..512, matched the pure `worldGridLines` prediction exactly at every sample -- see the git history
// around this file for the investigation). This test locks in the property that investigation was
// checking for: `GridOverlay`'s rendered line count tracks `pose`/`baseGridSize` prop changes
// (no stale `useMemo`), and always matches what `worldGridLines` itself would compute for the same
// inputs -- so a future memo-dependency regression (the exact bug class this was suspected to be)
// fails a test instead of only showing up live.

const WIDTH = 420
const HEIGHT = 428

function expectedLineCount(pose: OrthoPose, baseGridSize: number): number {
  const { right, up } = orthoBasis('top')
  const halfW = (WIDTH / 2) * pose.worldUnitsPerPixel
  const halfH = (HEIGHT / 2) * pose.worldUnitsPerPixel
  const { bounds } = orthoGridWindow(pose.center, right, up, halfW, halfH)
  return worldGridLines(baseGridSize, WIDTH, pose.worldUnitsPerPixel, bounds).lines.length
}

function lineCountFrom(renderer: Awaited<ReturnType<typeof ReactThreeTestRenderer.create>>): number {
  let geometry: THREE.BufferGeometry | undefined
  renderer.scene.children[0].instance.traverse((o: THREE.Object3D) => {
    const line = o as THREE.LineSegments
    if (line.isLineSegments) geometry = line.geometry
  })
  if (!geometry) throw new Error('no lineSegments found')
  return geometry.attributes.position.count / 2
}

describe('GridOverlay', () => {
  it('matches worldGridLines exactly at the initial zoom', async () => {
    const pose: OrthoPose = { center: [0, 0, 0], worldUnitsPerPixel: 4 }
    const renderer = await ReactThreeTestRenderer.create(<GridOverlay pose={pose} axis="top" baseGridSize={1} />, {
      width: WIDTH,
      height: HEIGHT,
    })
    await renderer.advanceFrames(1, 0.016)
    expect(lineCountFrom(renderer)).toBe(expectedLineCount(pose, 1))
  })

  it('recomputes (not a stale memo) when the pose zooms out, matching the new prediction', async () => {
    const before: OrthoPose = { center: [0, 0, 0], worldUnitsPerPixel: 4 }
    const after: OrthoPose = { center: [0, 0, 0], worldUnitsPerPixel: 512 } // clamped max zoom-out
    const renderer = await ReactThreeTestRenderer.create(<GridOverlay pose={before} axis="top" baseGridSize={1} />, {
      width: WIDTH,
      height: HEIGHT,
    })
    await renderer.advanceFrames(1, 0.016)
    const beforeCount = lineCountFrom(renderer)

    await renderer.update(<GridOverlay pose={after} axis="top" baseGridSize={1} />)
    await renderer.advanceFrames(1, 0.016)
    const afterCount = lineCountFrom(renderer)

    // The escalation keeps the visible count roughly constant across zoom levels (that's the whole
    // point of escalating) -- so this asserts the STRONGER, exact property: the live geometry always
    // matches what the pure math says for the CURRENT pose, not the previous one.
    expect(afterCount).toBe(expectedLineCount(after, 1))
    expect(beforeCount).toBe(expectedLineCount(before, 1))
  })

  it('recomputes when baseGridSize changes at a fixed (already zoomed-out) pose', async () => {
    const pose: OrthoPose = { center: [0, 0, 0], worldUnitsPerPixel: 512 }
    const renderer = await ReactThreeTestRenderer.create(<GridOverlay pose={pose} axis="top" baseGridSize={16} />, {
      width: WIDTH,
      height: HEIGHT,
    })
    await renderer.advanceFrames(1, 0.016)
    expect(lineCountFrom(renderer)).toBe(expectedLineCount(pose, 16))

    await renderer.update(<GridOverlay pose={pose} axis="top" baseGridSize={1} />)
    await renderer.advanceFrames(1, 0.016)
    expect(lineCountFrom(renderer)).toBe(expectedLineCount(pose, 1))
  })

  it('never lets a fine (1uu) base step render denser than the ~4px design floor, at any zoom', async () => {
    // Sweeps a realistic zoom range (matches the live investigation's own sweep) and asserts the
    // on-screen spacing the escalation actually produces never drops below the design floor.
    for (const worldUnitsPerPixel of [4, 8, 16, 32, 64, 128, 256, 512]) {
      const pose: OrthoPose = { center: [0, 0, 0], worldUnitsPerPixel }
      const { right, up } = orthoBasis('top')
      const halfW = (WIDTH / 2) * worldUnitsPerPixel
      const halfH = (HEIGHT / 2) * worldUnitsPerPixel
      const { bounds } = orthoGridWindow(pose.center, right, up, halfW, halfH)
      const { drawnStep } = worldGridLines(1, WIDTH, worldUnitsPerPixel, bounds)
      const spacingPx = drawnStep / worldUnitsPerPixel
      expect(spacingPx).toBeGreaterThanOrEqual(4)
    }
  })
})
