import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import { SIDEBAR_COLLAPSE_BREAKPOINT_PX } from './useCollapsiblePanel'
import { useSidebar } from './useSidebar'

function setViewportWidth(width: number) {
  Object.defineProperty(window, 'innerWidth', { configurable: true, value: width })
}

beforeEach(() => {
  localStorage.clear()
  setViewportWidth(1920)
})

afterEach(() => {
  localStorage.clear()
})

describe('useSidebar', () => {
  it('defaults to the "selection" tab and expanded above the breakpoint, with no stored choice', () => {
    const { result } = renderHook(() => useSidebar())
    expect(result.current.activeTabId).toBe('selection')
    expect(result.current.collapsed).toBe(false)
  })

  it('defaults to collapsed below the breakpoint, with no stored choice', () => {
    setViewportWidth(SIDEBAR_COLLAPSE_BREAKPOINT_PX - 1)
    const { result } = renderHook(() => useSidebar())
    expect(result.current.collapsed).toBe(true)
  })

  it('setActiveTab on the already-active tab collapses the sidebar, and persists that across a fresh hook instance', () => {
    const { result, unmount } = renderHook(() => useSidebar())
    expect(result.current.collapsed).toBe(false)
    expect(result.current.activeTabId).toBe('selection')

    act(() => result.current.setActiveTab('selection')) // same as the current tab -> collapse
    expect(result.current.collapsed).toBe(true)
    expect(result.current.activeTabId).toBe('selection') // unchanged

    unmount()
    const { result: fresh } = renderHook(() => useSidebar())
    expect(fresh.current.collapsed).toBe(true)
  })

  it('an explicit collapse choice wins over the breakpoint, same as useCollapsiblePanel', () => {
    const { result } = renderHook(() => useSidebar())
    act(() => result.current.setActiveTab('selection')) // collapses (already active)
    setViewportWidth(1920)
    const { result: fresh } = renderHook(() => useSidebar())
    expect(fresh.current.collapsed).toBe(true)
  })

  it('setActiveTab changes the active tab and persists it across a fresh hook instance', () => {
    const { result, unmount } = renderHook(() => useSidebar())
    act(() => result.current.setActiveTab('org'))
    expect(result.current.activeTabId).toBe('org')
    expect(result.current.collapsed).toBe(false) // switching tabs never collapses

    unmount()
    const { result: fresh } = renderHook(() => useSidebar())
    expect(fresh.current.activeTabId).toBe('org')
  })

  it('setActiveTab on the active tab while COLLAPSED expands instead of collapsing further', () => {
    const { result } = renderHook(() => useSidebar())
    act(() => result.current.setActiveTab('selection')) // collapse
    expect(result.current.collapsed).toBe(true)

    act(() => result.current.setActiveTab('selection')) // same tab again, but now collapsed
    expect(result.current.collapsed).toBe(false)
    expect(result.current.activeTabId).toBe('selection')
  })
})
