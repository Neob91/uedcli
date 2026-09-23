import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { useSession } from './SessionContext'

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status })
}

function mockFetch(extra: (url: string, init?: RequestInit) => Response | undefined) {
  globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input)
    const overridden = extra(url)
    if (overridden) return overridden
    throw new Error(`unexpected fetch: ${url}`)
  }) as unknown as typeof fetch
}

afterEach(() => {
  vi.restoreAllMocks()
})

describe('useSession(sessionId)', () => {
  it('resolves the given id on mount and reaches view "editing"', async () => {
    mockFetch((url) => {
      if (url.endsWith('/api/session/sess-1')) {
        return jsonResponse({ id: 'sess-1', level: 'Beta', created_at: 'c', last_active_at: 'a', claim_token: 'tok-1', name: null })
      }
      return undefined
    })

    const { result } = renderHook(() => useSession('sess-1'))

    // `view` starts 'editing' by default (there's no separate "loading" state in the spec's view
    // enum), so waiting on it alone would pass before the async resolution even starts -- wait on
    // `sessionId` actually landing instead (it starts null).
    await waitFor(() => expect(result.current.sessionId).toBe('sess-1'))
    expect(result.current.view).toBe('editing')
    expect(result.current.level).toBe('Beta')
    expect(result.current.claimToken).toBe('tok-1')
  })

  it('a session id the server has never seen resolves to "notfound"', async () => {
    mockFetch((url) => {
      if (url.endsWith('/api/session/bad-id')) return jsonResponse({ error: 'session not found' }, 404)
      return undefined
    })

    const { result } = renderHook(() => useSession('bad-id'))

    await waitFor(() => expect(result.current.view).toBe('notfound'))
  })

  it('re-resolving an id this hook already knew was good, and now 404s, is "closed" not "notfound"', async () => {
    let shouldFail = false
    mockFetch((url) => {
      if (url.endsWith('/api/session/sess-1')) {
        return shouldFail
          ? jsonResponse({ error: 'gone' }, 404)
          : jsonResponse({ id: 'sess-1', level: 'Beta', created_at: 'c', last_active_at: 'a', claim_token: 'tok-1', name: null })
      }
      return undefined
    })

    const { result } = renderHook(() => useSession('sess-1'))
    await waitFor(() => expect(result.current.view).toBe('editing'))

    shouldFail = true
    act(() => result.current.reload())

    await waitFor(() => expect(result.current.view).toBe('closed'))
  })

  it('re-resolves automatically when the sessionId argument itself changes', async () => {
    mockFetch((url) => {
      if (url.endsWith('/api/session/sess-1')) return jsonResponse({ id: 'sess-1', level: 'A', created_at: 'c', last_active_at: 'a', claim_token: 't1', name: null })
      if (url.endsWith('/api/session/sess-2')) return jsonResponse({ id: 'sess-2', level: 'B', created_at: 'c', last_active_at: 'a', claim_token: 't2', name: null })
      return undefined
    })

    const { result, rerender } = renderHook(({ id }) => useSession(id), { initialProps: { id: 'sess-1' } })
    await waitFor(() => expect(result.current.sessionId).toBe('sess-1'))

    rerender({ id: 'sess-2' })

    await waitFor(() => expect(result.current.sessionId).toBe('sess-2'))
    expect(result.current.level).toBe('B')
  })

  it('markSuperseded flips view to "superseded" without touching sessionId/level/claimToken', async () => {
    mockFetch((url) => {
      if (url.endsWith('/api/session/sess-1')) return jsonResponse({ id: 'sess-1', level: 'Beta', created_at: 'c', last_active_at: 'a', claim_token: 'tok-1', name: null })
      return undefined
    })
    const { result } = renderHook(() => useSession('sess-1'))
    await waitFor(() => expect(result.current.view).toBe('editing'))

    act(() => result.current.markSuperseded())

    expect(result.current.view).toBe('superseded')
    expect(result.current.sessionId).toBe('sess-1')
  })

  it('markClosed flips view to "closed"', async () => {
    mockFetch((url) => {
      if (url.endsWith('/api/session/sess-1')) return jsonResponse({ id: 'sess-1', level: 'Beta', created_at: 'c', last_active_at: 'a', claim_token: 'tok-1', name: null })
      return undefined
    })
    const { result } = renderHook(() => useSession('sess-1'))
    await waitFor(() => expect(result.current.view).toBe('editing'))

    act(() => result.current.markClosed())

    expect(result.current.view).toBe('closed')
  })

  it('does not write anything into the URL -- that is route.ts/App.tsx\'s job now', async () => {
    window.history.replaceState(null, '', '/session/sess-1/')
    mockFetch((url) => {
      if (url.endsWith('/api/session/sess-1')) return jsonResponse({ id: 'sess-1', level: 'Beta', created_at: 'c', last_active_at: 'a', claim_token: 'tok-1', name: null })
      return undefined
    })

    renderHook(() => useSession('sess-1'))
    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled())

    expect(window.location.pathname).toBe('/session/sess-1/')
    window.history.replaceState(null, '', '/')
  })
})
