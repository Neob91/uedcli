import { describe, expect, it } from 'vitest'

import type { OrthoPose } from './orthoCamera'
import { orthoBasis, orthoPan, orthoZoom, screenToWorld } from './orthoCamera'

describe('orthoBasis', () => {
  it('TOP looks down -Z, +X screen-right, +Y screen-down (-Y up)', () => {
    const { forward, right, up } = orthoBasis('top')
    expect(forward).toEqual([0, 0, -1])
    expect(right).toEqual([1, 0, 0])
    expect(up).toEqual([0, -1, 0])
  })

  it('FRONT looks along +Y (south), +X screen-LEFT, +Z screen-up', () => {
    const { forward, right, up } = orthoBasis('front')
    expect(forward).toEqual([0, 1, 0])
    expect(right).toEqual([-1, 0, 0])
    expect(up).toEqual([0, 0, 1])
  })

  it('SIDE looks along +X (east), +Y screen-right, +Z screen-up', () => {
    const { forward, right, up } = orthoBasis('side')
    expect(forward).toEqual([1, 0, 0])
    expect(right).toEqual([0, 1, 0])
    expect(up).toEqual([0, 0, 1])
  })
})

describe('orthoPan', () => {
  it('a Top-axis pan moves center X/Y by the screen-to-world-scaled delta, never Z', () => {
    const pose: OrthoPose = { center: [0, 0, 100], worldUnitsPerPixel: 2 }
    const panned = orthoPan(pose, 'top', 10, 5)
    // right=[1,0,0] scaled by -dxPx*wupp=-20; up=[0,-1,0] scaled by dyPx*wupp=10 -> y -= 10
    expect(panned.center[0]).toBeCloseTo(-20)
    expect(panned.center[1]).toBeCloseTo(-10)
    expect(panned.center[2]).toBe(100)
    expect(panned.worldUnitsPerPixel).toBe(2)
  })

  it('a zero-movement pan is a no-op on center', () => {
    const pose: OrthoPose = { center: [5, 5, 5], worldUnitsPerPixel: 1 }
    expect(orthoPan(pose, 'front', 0, 0).center).toEqual([5, 5, 5])
  })
})

describe('orthoZoom', () => {
  it('a +120 wheel delta (one notch) doubles worldUnitsPerPixel', () => {
    const pose: OrthoPose = { center: [0, 0, 0], worldUnitsPerPixel: 4 }
    expect(orthoZoom(pose, 120).worldUnitsPerPixel).toBeCloseTo(8)
  })

  it('a -120 wheel delta halves worldUnitsPerPixel', () => {
    const pose: OrthoPose = { center: [0, 0, 0], worldUnitsPerPixel: 4 }
    expect(orthoZoom(pose, -120).worldUnitsPerPixel).toBeCloseTo(2)
  })

  it('leaves center unchanged', () => {
    const pose: OrthoPose = { center: [1, 2, 3], worldUnitsPerPixel: 4 }
    expect(orthoZoom(pose, 60).center).toEqual([1, 2, 3])
  })

  // Regression (GUI bug report item 3): unclamped, a long scroll zoomed out/in without limit --
  // and past a certain scale, the grid's own line geometry silently stopped rendering (bug 2,
  // measured live to be a WebGL/float32 precision issue at extreme worldUnitsPerPixel).
  it('clamps zoom-out at the max (UE1 world-extent-derived) ceiling', () => {
    const pose: OrthoPose = { center: [0, 0, 0], worldUnitsPerPixel: 400 }
    expect(orthoZoom(pose, 1_000_000).worldUnitsPerPixel).toBe(512)
  })

  it('clamps zoom-in at the min floor', () => {
    const pose: OrthoPose = { center: [0, 0, 0], worldUnitsPerPixel: 0.02 }
    expect(orthoZoom(pose, -1_000_000).worldUnitsPerPixel).toBe(0.01)
  })

  it('does not clamp a zoom that stays within range', () => {
    const pose: OrthoPose = { center: [0, 0, 0], worldUnitsPerPixel: 4 }
    expect(orthoZoom(pose, 120).worldUnitsPerPixel).toBeCloseTo(8)
  })
})

describe('screenToWorld', () => {
  it('at the exact viewport center, returns pose.center', () => {
    const pose: OrthoPose = { center: [10, 20, 30], worldUnitsPerPixel: 3 }
    expect(screenToWorld(pose, 'side', { w: 800, h: 600 }, 400, 300)).toEqual([10, 20, 30])
  })

  it('offsets along right/up scaled by worldUnitsPerPixel for a Top-axis point', () => {
    const pose: OrthoPose = { center: [0, 0, 0], worldUnitsPerPixel: 2 }
    // 10px right, 10px down from center
    const p = screenToWorld(pose, 'top', { w: 200, h: 200 }, 110, 110)
    expect(p[0]).toBeCloseTo(20) // +right (world +X) * 10px * 2
    expect(p[1]).toBeCloseTo(20) // TOP's own "+Y -> screen-down": screen-down increases world Y
    expect(p[2]).toBe(0)
  })
})
