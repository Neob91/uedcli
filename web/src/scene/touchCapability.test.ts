import { describe, expect, it } from 'vitest'

import { resolveTouchCapable } from './touchCapability'

describe('resolveTouchCapable', () => {
  it('is false with neither signal present', () => {
    expect(resolveTouchCapable(false, 0)).toBe(false)
  })

  it('is true when the browser exposes ontouchstart, regardless of maxTouchPoints', () => {
    expect(resolveTouchCapable(true, 0)).toBe(true)
  })

  it('is true when maxTouchPoints is positive, regardless of ontouchstart', () => {
    expect(resolveTouchCapable(false, 1)).toBe(true)
    expect(resolveTouchCapable(false, 5)).toBe(true)
  })

  it('is true when both signals are present', () => {
    expect(resolveTouchCapable(true, 5)).toBe(true)
  })
})
