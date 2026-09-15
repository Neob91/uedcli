import { describe, expect, it } from 'vitest'

import type { PaneId } from './paneLayout'
import { applyModeKey, isModeAvailable, resolveEffectiveMode } from './shadingMode'
import type { ShadingMode } from './shadingMode'

describe('isModeAvailable', () => {
  it("'wireframe' is always available", () => {
    expect(isModeAvailable('wireframe', false)).toBe(true)
    expect(isModeAvailable('wireframe', true)).toBe(true)
  })

  it("'unlit'/'flat'/'lit' require a solved build", () => {
    for (const mode of ['unlit', 'flat', 'lit'] as const) {
      expect(isModeAvailable(mode, false)).toBe(false)
      expect(isModeAvailable(mode, true)).toBe(true)
    }
  })
})

describe('resolveEffectiveMode', () => {
  it('returns the requested mode when available', () => {
    expect(resolveEffectiveMode('lit', true)).toBe('lit')
    expect(resolveEffectiveMode('wireframe', false)).toBe('wireframe')
  })

  it('falls back to wireframe when the requested mode is unavailable', () => {
    expect(resolveEffectiveMode('lit', false)).toBe('wireframe')
    expect(resolveEffectiveMode('flat', false)).toBe('wireframe')
  })
})

describe('applyModeKey', () => {
  const ALL_WIRE: Record<PaneId, ShadingMode> = { perspective: 'wireframe', top: 'wireframe', front: 'wireframe', side: 'wireframe' }

  it("pressing '3' while focused==='top' changes only top's mode to 'flat'", () => {
    const next = applyModeKey(ALL_WIRE, 'top', '3', true)
    expect(next.top).toBe('flat')
    expect(next.perspective).toBe('wireframe')
    expect(next.front).toBe('wireframe')
    expect(next.side).toBe('wireframe')
  })

  it('is a no-op (same object reference) when the requested mode would fall back', () => {
    const next = applyModeKey(ALL_WIRE, 'top', '4', false) // 'lit' needs buildSolved
    expect(next).toBe(ALL_WIRE)
  })

  it("'1' (wireframe) is always available, even with buildSolved=false", () => {
    const solved: Record<PaneId, ShadingMode> = { ...ALL_WIRE, top: 'lit' }
    const next = applyModeKey(solved, 'top', '1', false)
    expect(next.top).toBe('wireframe')
  })
})
