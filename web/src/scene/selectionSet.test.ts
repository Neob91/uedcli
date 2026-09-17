import { describe, expect, it } from 'vitest'

import { clearSelection, primarySelection, toggleSelection } from './selectionSet'

describe('toggleSelection', () => {
  it('additive=false always replaces with exactly {name}, regardless of the starting set', () => {
    expect([...toggleSelection(new Set(), 'A', false)]).toEqual(['A'])
    expect([...toggleSelection(new Set(['X', 'Y']), 'A', false)]).toEqual(['A'])
  })

  it('additive=false on the sole already-selected actor is a no-op reselect, not a toggle-off', () => {
    expect([...toggleSelection(new Set(['A']), 'A', false)]).toEqual(['A'])
  })

  it('additive=true adds the name when absent', () => {
    const result = toggleSelection(new Set(['A']), 'B', true)
    expect([...result].sort()).toEqual(['A', 'B'])
  })

  it('additive=true removes the name when present, including the last member (empty, not null)', () => {
    expect(toggleSelection(new Set(['A']), 'A', true).size).toBe(0)
    const result = toggleSelection(new Set(['A', 'B']), 'A', true)
    expect([...result]).toEqual(['B'])
  })

  it('deselectSole=true clears a non-additive re-tap of the sole selected member (poly deselect)', () => {
    expect(toggleSelection(new Set(['A']), 'A', false, true).size).toBe(0)
  })

  it('deselectSole=true still replaces when the sole member differs, or when several are selected', () => {
    expect([...toggleSelection(new Set(['A']), 'B', false, true)]).toEqual(['B'])
    expect([...toggleSelection(new Set(['A', 'B']), 'A', false, true)]).toEqual(['A'])
  })
})

describe('clearSelection', () => {
  it('is always an empty set', () => {
    expect(clearSelection().size).toBe(0)
  })
})

describe('primarySelection', () => {
  it('is undefined for an empty selection', () => {
    expect(primarySelection(new Set())).toBeUndefined()
  })

  it('is the sole member of a single-actor selection', () => {
    expect(primarySelection(new Set(['A']))).toBe('A')
  })

  it('is the most-recently-added member of a multi-actor selection', () => {
    const afterA = toggleSelection(new Set(), 'A', false)
    const afterB = toggleSelection(afterA, 'B', true)
    expect(primarySelection(afterB)).toBe('B')
  })
})
