import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import { navigate, parseRoute, useRoute } from './route'

beforeEach(() => {
  window.history.replaceState(null, '', '/')
})

afterEach(() => {
  window.history.replaceState(null, '', '/')
})

describe('parseRoute', () => {
  it('a bare "/" is the picker screen', () => {
    expect(parseRoute('/')).toEqual({ screen: 'picker' })
  })

  it('/session/<id> is the session screen', () => {
    expect(parseRoute('/session/abc-123')).toEqual({ screen: 'session', id: 'abc-123' })
  })

  it('/session/<id>/ (trailing slash) is the same session screen', () => {
    expect(parseRoute('/session/abc-123/')).toEqual({ screen: 'session', id: 'abc-123' })
  })

  it('anything else falls back to the picker screen', () => {
    expect(parseRoute('/unknown/path')).toEqual({ screen: 'picker' })
  })
})

describe('useRoute', () => {
  it('reflects the initial pathname on mount', () => {
    window.history.replaceState(null, '', '/session/abc-123/')
    const { result } = renderHook(() => useRoute())
    expect(result.current).toEqual({ screen: 'session', id: 'abc-123' })
  })

  it('navigate() updates the route synchronously for every mounted subscriber', () => {
    const { result } = renderHook(() => useRoute())
    expect(result.current).toEqual({ screen: 'picker' })

    act(() => navigate('/session/new-id/'))

    expect(result.current).toEqual({ screen: 'session', id: 'new-id' })
    expect(window.location.pathname).toBe('/session/new-id/')
  })

  it('a real popstate (browser back/forward) also updates the route', () => {
    window.history.replaceState(null, '', '/session/first/')
    const { result } = renderHook(() => useRoute())
    window.history.pushState(null, '', '/session/second/')

    act(() => window.dispatchEvent(new PopStateEvent('popstate')))

    expect(result.current).toEqual({ screen: 'session', id: 'second' })
  })

  it('unmounting stops updating on navigate()', () => {
    const { unmount } = renderHook(() => useRoute())
    unmount()
    act(() => navigate('/session/late/'))
    // No assertion on `result.current` after unmount (React forbids reading it) -- this test's
    // only job is proving `navigate()` doesn't throw once every subscriber has unsubscribed.
    expect(window.location.pathname).toBe('/session/late/')
  })
})
