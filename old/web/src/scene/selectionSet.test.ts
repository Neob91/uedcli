import { describe, expect, it } from 'vitest'

import { clearSelection, pivotAnchor, primarySelection, toggleSelection } from './selectionSet'

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

// GUI-PARITY.md "Pivot-cross ... Part 4": UED22 recomputes its ONE global pivot only when exactly
// one actor is selected, so a click-built multi-selection keeps the cross on the first-clicked
// actor. Live-verified against real UED22 2026-09-18.
describe('pivotAnchor', () => {
  it('is undefined for an empty selection', () => {
    expect(pivotAnchor(new Set())).toBeUndefined()
  })

  it('is the sole member of a single-actor selection', () => {
    expect(pivotAnchor(new Set(['A']))).toBe('A')
  })

  it('stays on the first-clicked actor as Ctrl+clicks add more', () => {
    const afterA = toggleSelection(new Set(), 'A', false)
    const afterB = toggleSelection(afterA, 'B', true)
    const afterC = toggleSelection(afterB, 'C', true)
    expect(pivotAnchor(afterB)).toBe('A')
    expect(pivotAnchor(afterC)).toBe('A')
  })

  it('moves to the remaining actor when a two-actor selection drops back to one', () => {
    const afterA = toggleSelection(new Set(), 'A', false)
    const afterB = toggleSelection(afterA, 'B', true)
    expect(pivotAnchor(toggleSelection(afterB, 'A', true))).toBe('B')
  })

  it('differs from primarySelection, which tracks the last click instead', () => {
    const afterB = toggleSelection(toggleSelection(new Set(), 'A', false), 'B', true)
    expect(pivotAnchor(afterB)).toBe('A')
    expect(primarySelection(afterB)).toBe('B')
  })

  // The three DELIBERATE divergences from UED22, pinned so none is silently "fixed" later.
  // UED22's own behaviour in each case is in `pivotAnchor`'s doc comment and GUI-PARITY.md Part 4.
  it('deliberately diverges: deselecting the anchor out of a 3+ selection moves it on', () => {
    let s = toggleSelection(new Set(), 'A', false)
    s = toggleSelection(s, 'B', true)
    s = toggleSelection(s, 'C', true)
    // UED22 leaves its cross on the now-deselected A (the selection never returns to one actor).
    expect(pivotAnchor(toggleSelection(s, 'A', true))).toBe('B')
  })

  it('deliberately diverges: a batch select re-anchors on its first member', () => {
    // UED22's marquee/select-all never passes through one actor, so its cross stays put.
    expect(pivotAnchor(new Set(['X', 'Y', 'Z']))).toBe('X')
  })

  it('deliberately diverges: an empty selection has no anchor (UED22 keeps a stale cross)', () => {
    expect(pivotAnchor(clearSelection())).toBeUndefined()
  })
})
