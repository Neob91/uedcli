import { describe, expect, it } from 'vitest'

import { resolveEffectiveTheme } from './useTheme'

describe('resolveEffectiveTheme', () => {
  it("'system' follows the media query: dark when it prefers dark", () => {
    expect(resolveEffectiveTheme('system', true)).toBe('dark')
  })

  it("'system' follows the media query: light when it does not prefer dark", () => {
    expect(resolveEffectiveTheme('system', false)).toBe('light')
  })

  it('an explicit preference wins over the media query regardless of its value', () => {
    expect(resolveEffectiveTheme('light', true)).toBe('light')
    expect(resolveEffectiveTheme('dark', false)).toBe('dark')
  })
})
