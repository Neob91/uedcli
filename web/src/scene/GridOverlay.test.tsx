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

  // Regression for a SEPARATE reported bug ("some lines render wider than others... when I move,
  // they alternate") -- confirmed live (headless-Chromium pixel measurement of the real rendered
  // canvas) to be sub-pixel antialiasing on `LineBasicMaterial`'s 1px GL_LINEs: a line's continuous
  // world->device-pixel position rarely lands on a whole pixel, so it blurs across two at half
  // strength; which lines are blurred shifts as you pan. Fixed by snapping each line's coordinate to
  // the nearest device-pixel center before building geometry (`snapToDevicePixel`). These tests read
  // the actual `BufferGeometry` position buffer back (not a screenshot) and assert every vertex's
  // computed device-pixel coordinate lands within float32 rounding of a half-integer -- the exact
  // property a live pixel probe confirmed eliminates the blur.
  describe('pixel-snapped grid lines (sub-pixel antialiasing fix)', () => {
    function devicePx(worldCoord: number, originWorld: number, pxPerUnit: number, axisSign: 1 | -1): number {
      return axisSign * (worldCoord - originWorld) * pxPerUnit
    }

    function assertHalfIntegerAligned(value: number, label: string) {
      const frac = value - Math.floor(value)
      // float32 storage of a value on the order of a few hundred UU has ~1e-3 absolute precision at
      // worst (Float32BufferAttribute) -- well inside this tolerance, so a genuine snap failure
      // (e.g. reverting to the raw continuous coordinate) fails this by a wide margin, not a rounding
      // hair.
      expect(Math.abs(frac - 0.5), `${label}: expected device-px fractional part 0.5, got ${frac}`).toBeLessThan(1e-2)
    }

    it('snaps every u-axis (vertical) line to a device-pixel center, at an INTEGER pane width', async () => {
      const pose: OrthoPose = { center: [0, 0, 0], worldUnitsPerPixel: 0.0625 } // ~16px/UU, matches the live probe
      const width = 360
      const height = 428
      const renderer = await ReactThreeTestRenderer.create(<GridOverlay pose={pose} axis="top" baseGridSize={1} />, {
        width,
        height,
      })
      await renderer.advanceFrames(1, 0.016)

      let geometry: THREE.BufferGeometry | undefined
      renderer.scene.children[0].instance.traverse((o: THREE.Object3D) => {
        const line = o as THREE.LineSegments
        if (line.isLineSegments) geometry = line.geometry
      })
      if (!geometry) throw new Error('no lineSegments found')

      const { right, up } = orthoBasis('top')
      const halfW = (width / 2) * pose.worldUnitsPerPixel
      const halfH = (height / 2) * pose.worldUnitsPerPixel
      const { bounds } = orthoGridWindow(pose.center, right, up, halfW, halfH)
      const pxPerUnitU = width / (2 * halfW)
      const { lines } = worldGridLines(1, width, pose.worldUnitsPerPixel, bounds)

      // `worldGridLines` interleaves 'u' (vertical) and 'v' (horizontal) lines in one array, and
      // `GridOverlay` appends 2 vertices per line in that same order -- only check the 'u' ones here
      // (their constant coordinate is `pos.getX`, since `pose.center` is the origin so `planeOrigin`
      // is exactly zero and 'top' maps world X straight onto the geometry's own X).
      const pos = geometry.attributes.position
      let checked = 0
      for (let li = 0; li < lines.length; li++) {
        if (lines[li].axis !== 'u') continue
        const worldU = pos.getX(li * 2)
        assertHalfIntegerAligned(devicePx(worldU, bounds.uMin, pxPerUnitU, 1), `line ${li}`)
        checked++
      }
      expect(checked).toBeGreaterThan(10) // sanity: the sweep actually exercised real lines
    })

    it('snaps correctly at a FRACTIONAL pane width too (the exact drift this fix closes)', async () => {
      // Reproduces the real quad-pane shape live-measured (360.5 CSS px) that exposed the
      // gl.domElement.width-floors-but-viewport-rounds mismatch: using the floored value here left
      // every line off by a small scale error, compounding to over half a device pixel of drift by
      // the pane's far edge (crisp only near the snap origin, blurred toward the edges).
      const pose: OrthoPose = { center: [0, 0, 0], worldUnitsPerPixel: 0.0625 }
      const width = 360.5
      const height = 428.7
      const renderer = await ReactThreeTestRenderer.create(<GridOverlay pose={pose} axis="top" baseGridSize={1} />, {
        width,
        height,
      })
      await renderer.advanceFrames(1, 0.016)

      let geometry: THREE.BufferGeometry | undefined
      renderer.scene.children[0].instance.traverse((o: THREE.Object3D) => {
        const line = o as THREE.LineSegments
        if (line.isLineSegments) geometry = line.geometry
      })
      if (!geometry) throw new Error('no lineSegments found')

      const { right, up } = orthoBasis('top')
      const halfW = (width / 2) * pose.worldUnitsPerPixel
      const halfH = (height / 2) * pose.worldUnitsPerPixel
      const { bounds } = orthoGridWindow(pose.center, right, up, halfW, halfH)
      // The CORRECT denominator: three.js's real viewport rect (`Math.round(width*dpr)`), not the
      // floored canvas backing-buffer size -- exactly what `GridOverlay` itself now computes.
      const pxPerUnitU = Math.round(width) / (2 * halfW)
      const { lines } = worldGridLines(1, width, pose.worldUnitsPerPixel, bounds)

      const pos = geometry.attributes.position
      let worstDrift = 0
      let checked = 0
      for (let li = 0; li < lines.length; li++) {
        if (lines[li].axis !== 'u') continue
        const worldU = pos.getX(li * 2)
        const raw = devicePx(worldU, bounds.uMin, pxPerUnitU, 1)
        const frac = raw - Math.floor(raw)
        worstDrift = Math.max(worstDrift, Math.abs(frac - 0.5))
        checked++
      }
      expect(checked).toBeGreaterThan(10)
      // Every line, even the farthest from the pane's own snap origin, lands within float32
      // precision of a half-integer device pixel -- no accumulated scale drift toward the edges.
      expect(worstDrift).toBeLessThan(1e-2)
    })

    it('snaps v-axis (horizontal) lines too, in a DIFFERENT ortho pane (front) -- no u/v asymmetry', async () => {
      const pose: OrthoPose = { center: [0, 0, 0], worldUnitsPerPixel: 0.0625 }
      const width = 360
      const height = 428
      const renderer = await ReactThreeTestRenderer.create(<GridOverlay pose={pose} axis="front" baseGridSize={1} />, {
        width,
        height,
      })
      await renderer.advanceFrames(1, 0.016)

      let geometry: THREE.BufferGeometry | undefined
      renderer.scene.children[0].instance.traverse((o: THREE.Object3D) => {
        const line = o as THREE.LineSegments
        if (line.isLineSegments) geometry = line.geometry
      })
      if (!geometry) throw new Error('no lineSegments found')

      const { right, up } = orthoBasis('front')
      const halfW = (width / 2) * pose.worldUnitsPerPixel
      const halfH = (height / 2) * pose.worldUnitsPerPixel
      const { bounds, planeOrigin } = orthoGridWindow(pose.center, right, up, halfW, halfH)
      const pxPerUnitU = width / (2 * halfW)
      const pxPerUnitV = height / (2 * halfH)
      const { lines } = worldGridLines(1, width, pose.worldUnitsPerPixel, bounds)

      const pos = geometry.attributes.position
      let checkedU = 0
      let checkedV = 0
      for (let li = 0; li < lines.length; li++) {
        const i = li * 2
        const line = lines[li]
        // Every vertex is `planeOrigin + right*u + up*v`; project out `planeOrigin` before reading
        // back whichever coordinate (`u` via `right`, `v` via `up`) this line held constant --
        // `right`/`up` are orthonormal, so a dot product recovers the exact scalar.
        const rel: [number, number, number] = [pos.getX(i) - planeOrigin[0], pos.getY(i) - planeOrigin[1], pos.getZ(i) - planeOrigin[2]]
        if (line.axis === 'u') {
          const worldU = rel[0] * right[0] + rel[1] * right[1] + rel[2] * right[2]
          assertHalfIntegerAligned(devicePx(worldU, bounds.uMin, pxPerUnitU, 1), `u-line ${li}`)
          checkedU++
        } else {
          const worldV = rel[0] * up[0] + rel[1] * up[1] + rel[2] * up[2]
          assertHalfIntegerAligned(devicePx(worldV, bounds.vMax, pxPerUnitV, -1), `v-line ${li}`)
          checkedV++
        }
      }
      expect(checkedU).toBeGreaterThan(5)
      expect(checkedV).toBeGreaterThan(5)
    })

    it('snaps correctly with a PANNED pose.center (the exact scenario the bug report described)', async () => {
      // Every other test here uses `center: [0,0,0]`, where `planeOrigin` happens to be zero -- this
      // pans the camera so `originWorld` (`bounds.uMin`/`vMax`) is a nontrivial value too, directly
      // covering "when I move, they alternate" rather than only a fixed pose.
      const pose: OrthoPose = { center: [123.7, 0, -45.3], worldUnitsPerPixel: 0.0625 }
      const width = 360
      const height = 428
      const renderer = await ReactThreeTestRenderer.create(<GridOverlay pose={pose} axis="top" baseGridSize={1} />, {
        width,
        height,
      })
      await renderer.advanceFrames(1, 0.016)

      let geometry: THREE.BufferGeometry | undefined
      renderer.scene.children[0].instance.traverse((o: THREE.Object3D) => {
        const line = o as THREE.LineSegments
        if (line.isLineSegments) geometry = line.geometry
      })
      if (!geometry) throw new Error('no lineSegments found')

      const { right, up } = orthoBasis('top')
      const halfW = (width / 2) * pose.worldUnitsPerPixel
      const halfH = (height / 2) * pose.worldUnitsPerPixel
      const { bounds, planeOrigin } = orthoGridWindow(pose.center, right, up, halfW, halfH)
      const pxPerUnitU = width / (2 * halfW)
      const { lines } = worldGridLines(1, width, pose.worldUnitsPerPixel, bounds)

      const pos = geometry.attributes.position
      let checked = 0
      for (let li = 0; li < lines.length; li++) {
        if (lines[li].axis !== 'u') continue
        const i = li * 2
        const rel: [number, number, number] = [pos.getX(i) - planeOrigin[0], pos.getY(i) - planeOrigin[1], pos.getZ(i) - planeOrigin[2]]
        const worldU = rel[0] * right[0] + rel[1] * right[1] + rel[2] * right[2]
        assertHalfIntegerAligned(devicePx(worldU, bounds.uMin, pxPerUnitU, 1), `panned line ${li}`)
        checked++
      }
      expect(checked).toBeGreaterThan(10)
    })

    it('snaps correctly at dpr=2 with a fractional CSS width (the fix\'s real motivating case)', async () => {
      // The whole fix is `Math.round(size.width * dpr)` vs. three.js's floored `gl.domElement.width`
      // -- a plain `dpr=1` test can't tell those apart when `width` is already an integer. At `dpr=2`
      // the two formulas diverge even further, so this is the sharpest test of the real mechanism.
      const pose: OrthoPose = { center: [0, 0, 0], worldUnitsPerPixel: 0.0625 }
      const width = 360.5
      const height = 428.7
      const dpr = 2
      const renderer = await ReactThreeTestRenderer.create(<GridOverlay pose={pose} axis="top" baseGridSize={1} />, {
        width,
        height,
        dpr,
      })
      await renderer.advanceFrames(1, 0.016)

      let geometry: THREE.BufferGeometry | undefined
      renderer.scene.children[0].instance.traverse((o: THREE.Object3D) => {
        const line = o as THREE.LineSegments
        if (line.isLineSegments) geometry = line.geometry
      })
      if (!geometry) throw new Error('no lineSegments found')

      const { right, up } = orthoBasis('top')
      const halfW = (width / 2) * pose.worldUnitsPerPixel
      const halfH = (height / 2) * pose.worldUnitsPerPixel
      const { bounds } = orthoGridWindow(pose.center, right, up, halfW, halfH)
      // The correct denominator at dpr=2: three.js's real viewport rect is `Math.round(width * dpr)`,
      // NOT `Math.round(width) * dpr` -- rounding happens after scaling by dpr, same as `GridOverlay`.
      const pxPerUnitU = Math.round(width * dpr) / (2 * halfW)
      const { lines } = worldGridLines(1, width, pose.worldUnitsPerPixel, bounds)

      const pos = geometry.attributes.position
      let worstDrift = 0
      let checked = 0
      for (let li = 0; li < lines.length; li++) {
        if (lines[li].axis !== 'u') continue
        const worldU = pos.getX(li * 2)
        const raw = devicePx(worldU, bounds.uMin, pxPerUnitU, 1)
        const frac = raw - Math.floor(raw)
        worstDrift = Math.max(worstDrift, Math.abs(frac - 0.5))
        checked++
      }
      expect(checked).toBeGreaterThan(10)
      expect(worstDrift).toBeLessThan(1e-2)
    })

    it('snaps v-axis lines in the front pane across MULTIPLE zoom levels, not just one', async () => {
      const width = 360
      const height = 428
      for (const worldUnitsPerPixel of [0.25, 0.0625, 0.015625]) {
        const pose: OrthoPose = { center: [0, 0, 0], worldUnitsPerPixel }
        const renderer = await ReactThreeTestRenderer.create(<GridOverlay pose={pose} axis="front" baseGridSize={1} />, {
          width,
          height,
        })
        await renderer.advanceFrames(1, 0.016)

        let geometry: THREE.BufferGeometry | undefined
        renderer.scene.children[0].instance.traverse((o: THREE.Object3D) => {
          const line = o as THREE.LineSegments
          if (line.isLineSegments) geometry = line.geometry
        })
        if (!geometry) throw new Error('no lineSegments found')

        const { right, up } = orthoBasis('front')
        const halfW = (width / 2) * worldUnitsPerPixel
        const halfH = (height / 2) * worldUnitsPerPixel
        const { bounds, planeOrigin } = orthoGridWindow(pose.center, right, up, halfW, halfH)
        const pxPerUnitV = height / (2 * halfH)
        const { lines } = worldGridLines(1, width, worldUnitsPerPixel, bounds)

        const pos = geometry.attributes.position
        let checkedV = 0
        for (let li = 0; li < lines.length; li++) {
          if (lines[li].axis !== 'v') continue
          const i = li * 2
          const rel: [number, number, number] = [pos.getX(i) - planeOrigin[0], pos.getY(i) - planeOrigin[1], pos.getZ(i) - planeOrigin[2]]
          const worldV = rel[0] * up[0] + rel[1] * up[1] + rel[2] * up[2]
          assertHalfIntegerAligned(devicePx(worldV, bounds.vMax, pxPerUnitV, -1), `zoom=${worldUnitsPerPixel} v-line ${li}`)
          checkedV++
        }
        expect(checkedV, `zoom=${worldUnitsPerPixel}`).toBeGreaterThan(5)
      }
    })
  })
})
