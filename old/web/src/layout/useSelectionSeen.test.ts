import { renderHook } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { useHasUnseenSelection } from './useSelectionSeen'

describe('useHasUnseenSelection', () => {
  it('is false while the Selection tab is active, even as the identity changes', () => {
    const { result, rerender } = renderHook(
      ({ identity, activeTabId }: { identity: string; activeTabId: string }) => useHasUnseenSelection(identity, activeTabId),
      { initialProps: { identity: '', activeTabId: 'selection' } },
    )
    expect(result.current).toBe(false)

    rerender({ identity: 'A', activeTabId: 'selection' })
    expect(result.current).toBe(false)
  })

  it('becomes true once the identity changes while a DIFFERENT tab is active', () => {
    const { result, rerender } = renderHook(
      ({ identity, activeTabId }: { identity: string; activeTabId: string }) => useHasUnseenSelection(identity, activeTabId),
      { initialProps: { identity: 'A', activeTabId: 'org' } },
    )
    expect(result.current).toBe(false) // no change yet

    rerender({ identity: 'A,B', activeTabId: 'org' })
    expect(result.current).toBe(true)
  })

  it('clears once the Selection tab becomes active again', () => {
    const { result, rerender } = renderHook(
      ({ identity, activeTabId }: { identity: string; activeTabId: string }) => useHasUnseenSelection(identity, activeTabId),
      { initialProps: { identity: 'A', activeTabId: 'org' } },
    )
    rerender({ identity: 'A,B', activeTabId: 'org' })
    expect(result.current).toBe(true)

    rerender({ identity: 'A,B', activeTabId: 'selection' })
    expect(result.current).toBe(false)
  })
})
