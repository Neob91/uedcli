import { describe, expect, it } from 'vitest'

import { resolveCollapsed } from './useCollapsiblePanel'

describe('resolveCollapsed', () => {
  it('collapses below the breakpoint with no manual choice', () => {
    expect(resolveCollapsed(null, 500, 768)).toBe(true)
  })

  it('stays open at/above the breakpoint with no manual choice', () => {
    expect(resolveCollapsed(null, 768, 768)).toBe(false)
    expect(resolveCollapsed(null, 1920, 768)).toBe(false)
  })

  it('an explicit choice wins over the breakpoint in either direction', () => {
    expect(resolveCollapsed('collapsed', 1920, 768)).toBe(true)
    expect(resolveCollapsed('expanded', 500, 768)).toBe(false)
  })
})
