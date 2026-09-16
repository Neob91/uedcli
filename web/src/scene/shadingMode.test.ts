import { describe, expect, it } from 'vitest'

import type { PaneId } from './paneLayout'
import { applyModeKey, canChangeMode, isModeAvailable, keyForMode, resolveEffectiveMode, usesUnlitMaterials } from './shadingMode'
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

describe('usesUnlitMaterials', () => {
  // Regression: 'flat' must pick the same material set as 'unlit' (its own doc comment says "'flat'
  // renders identically to 'unlit'") -- a bug shipped where only 'unlit' was checked, so 'flat'
  // silently fell through to the lit/lightmap material set instead.
  it("'unlit' and 'flat' both use the lightmap-free material set", () => {
    expect(usesUnlitMaterials('unlit')).toBe(true)
    expect(usesUnlitMaterials('flat')).toBe(true)
  })

  it("'lit' and 'wireframe' don't", () => {
    expect(usesUnlitMaterials('lit')).toBe(false)
    expect(usesUnlitMaterials('wireframe')).toBe(false)
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

describe('keyForMode', () => {
  it('is the exact inverse of KEY_TO_MODE, for every mode', () => {
    expect(keyForMode('wireframe')).toBe('1')
    expect(keyForMode('unlit')).toBe('2')
    expect(keyForMode('flat')).toBe('3')
    expect(keyForMode('lit')).toBe('4')
  })
})

describe('canChangeMode', () => {
  it('only perspective can change mode -- ortho panes are always wireframe', () => {
    expect(canChangeMode('perspective')).toBe(true)
    expect(canChangeMode('top')).toBe(false)
    expect(canChangeMode('front')).toBe(false)
    expect(canChangeMode('side')).toBe(false)
  })
})

describe('applyModeKey', () => {
  const ALL_WIRE: Record<PaneId, ShadingMode> = { perspective: 'wireframe', top: 'wireframe', front: 'wireframe', side: 'wireframe' }

  it("pressing '3' while focused==='perspective' changes only perspective's mode to 'flat'", () => {
    const next = applyModeKey(ALL_WIRE, 'perspective', '3', true)
    expect(next.perspective).toBe('flat')
    expect(next.top).toBe('wireframe')
    expect(next.front).toBe('wireframe')
    expect(next.side).toBe('wireframe')
  })

  it('is a no-op (same object reference) when the requested mode would fall back', () => {
    const next = applyModeKey(ALL_WIRE, 'perspective', '4', false) // 'lit' needs buildSolved
    expect(next).toBe(ALL_WIRE)
  })

  it("'1' (wireframe) is always available, even with buildSolved=false", () => {
    const solved: Record<PaneId, ShadingMode> = { ...ALL_WIRE, perspective: 'lit' }
    const next = applyModeKey(solved, 'perspective', '1', false)
    expect(next.perspective).toBe('wireframe')
  })

  // Regression: an ortho pane must NEVER change mode, even to a mode that's otherwise available.
  it('is a no-op for any ortho pane requesting a non-wireframe mode, even with a solved build', () => {
    for (const pane of ['top', 'front', 'side'] as const) {
      for (const key of ['2', '3', '4'] as const) {
        const next = applyModeKey(ALL_WIRE, pane, key, true)
        expect(next).toBe(ALL_WIRE)
      }
    }
  })

  it("an ortho pane CAN still process '1' (wireframe) -- it's a no-op change, not a rejected one", () => {
    const next = applyModeKey(ALL_WIRE, 'top', '1', true)
    expect(next.top).toBe('wireframe')
  })
})
