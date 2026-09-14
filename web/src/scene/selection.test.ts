import { describe, expect, it } from 'vitest'

import type { SceneActor } from '../api'
import { isTap, pickActor, rayAabbIntersect } from './selection'

function actor(name: string, lo: [number, number, number], hi: [number, number, number]): SceneActor {
  return {
    name,
    cls: 'Engine.Brush',
    bbox_lo: lo,
    bbox_hi: hi,
    location: [0, 0, 0],
    rotation: [0, 0, 0],
    folder: null,
    labels: [],
    order_value: 'm',
    props: [],
  }
}

describe('rayAabbIntersect', () => {
  it('hits a box the ray passes through', () => {
    const t = rayAabbIntersect({ origin: [-10, 0, 0], direction: [1, 0, 0] }, [-1, -1, -1], [1, 1, 1])
    expect(t).toBeCloseTo(9)
  })

  it('misses a box the ray does not pass through', () => {
    const t = rayAabbIntersect({ origin: [-10, 5, 5], direction: [1, 0, 0] }, [-1, -1, -1], [1, 1, 1])
    expect(t).toBeNull()
  })

  it('misses a box entirely behind the ray origin', () => {
    const t = rayAabbIntersect({ origin: [10, 0, 0], direction: [1, 0, 0] }, [-1, -1, -1], [1, 1, 1])
    expect(t).toBeNull()
  })
})

describe('pickActor', () => {
  it('picks the nearest actor along the ray', () => {
    const near = actor('Near', [-1, -1, -1], [1, 1, 1])
    const far = actor('Far', [9, -1, -1], [11, 1, 1])
    const ray = { origin: [-10, 0, 0] as [number, number, number], direction: [1, 0, 0] as [number, number, number] }
    expect(pickActor(ray, [far, near])?.name).toBe('Near') // order-independent: nearest wins
  })

  it('returns null when the ray misses every actor', () => {
    const only = actor('Only', [-1, -1, -1], [1, 1, 1])
    const ray = { origin: [-10, 50, 50] as [number, number, number], direction: [1, 0, 0] as [number, number, number] }
    expect(pickActor(ray, [only])).toBeNull()
  })
})

describe('isTap', () => {
  it('is a tap when total travel stays within the threshold', () => {
    expect(isTap(100, 100, 102, 101)).toBe(true) // ~2.24px, under the 4px default
  })

  it('is a drag once travel exceeds the threshold', () => {
    expect(isTap(100, 100, 110, 100)).toBe(false) // 10px, over the 4px default
  })

  it('is exactly at the threshold boundary (inclusive)', () => {
    expect(isTap(0, 0, 4, 0, 4)).toBe(true)
    expect(isTap(0, 0, 4.01, 0, 4)).toBe(false)
  })
})
