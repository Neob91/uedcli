import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useSession } from './SessionContext'

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status })
}

/** Routes the fixed set of GET/POST requests `useSession` makes -- follows App.test.tsx's own
 * `mockFetch` URL-router convention exactly. `extra` handles a test's own `/api/session/{id}` or
 * `/api/level/{level}/sessions` response, which differs per test. */
function mockFetch(extra: (url: string, init?: RequestInit) => Response | undefined) {
  globalThis.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    const overridden = extra(url, init)
    if (overridden) return overridden
    throw new Error(`unexpected fetch: ${url}`)
  }) as unknown as typeof fetch
}

beforeEach(() => {
  window.history.replaceState(null, '', '/')
})

afterEach(() => {
  window.history.replaceState(null, '', '/')
})

describe('useSession: no ?session= in the URL', () => {
  it('auto-creates a session on the default level and writes its id into the URL', async () => {
    mockFetch((url, init) => {
      if (url.endsWith('/api/levels')) {
        return jsonResponse({ levels: [{ name: 'Beta', active: true }], current: 'Beta' })
      }
      if (url.endsWith('/api/level/Beta/sessions') && init?.method === 'POST') {
        return jsonResponse({ id: 'sess-1', level: 'Beta', created_at: '2026-09-22T00:00:00Z', claim_token: 'tok-1' }, 201)
      }
      return undefined
    })

    const { result } = renderHook(() => useSession())

    // `view` starts 'editing' by default (there's no separate "loading" state in the spec's view
    // enum), so waiting on it alone would pass before the async bootstrap even starts -- wait on
    // `sessionId` actually landing instead.
    await waitFor(() => expect(result.current.sessionId).toBe('sess-1'))
    expect(result.current.view).toBe('editing')
    expect(result.current.level).toBe('Beta')
    expect(result.current.claimToken).toBe('tok-1')
    expect(new URLSearchParams(window.location.search).get('session')).toBe('sess-1')
  })

  it('falls back to the first level in the list when /api/levels has no current', async () => {
    mockFetch((url, init) => {
      if (url.endsWith('/api/levels')) {
        return jsonResponse({ levels: [{ name: 'Alpha', active: false }], current: '' })
      }
      if (url.endsWith('/api/level/Alpha/sessions') && init?.method === 'POST') {
        return jsonResponse({ id: 'sess-2', level: 'Alpha', created_at: '2026-09-22T00:00:00Z', claim_token: 'tok-2' }, 201)
      }
      return undefined
    })

    const { result } = renderHook(() => useSession())

    await waitFor(() => expect(result.current.level).toBe('Alpha'))
  })
})

describe('useSession: a bad ?session= id in the URL', () => {
  it('resolves to the notfound view, showing the id, with NO auto-create', async () => {
    window.history.replaceState(null, '', '/?session=bogus')
    const calledUrls: string[] = []
    mockFetch((url) => {
      calledUrls.push(url)
      if (url.endsWith('/api/session/bogus')) {
        return jsonResponse({ error: "session not found: 'bogus'" }, 404)
      }
      return undefined
    })

    const { result } = renderHook(() => useSession())

    await waitFor(() => expect(result.current.view).toBe('notfound'))
    expect(result.current.sessionId).toBe('bogus')
    expect(result.current.level).toBeNull()
    // No auto-create: never fell through to the bootstrap path (/api/levels or a sessions POST).
    expect(calledUrls.some((u) => u.endsWith('/api/levels'))).toBe(false)
    expect(calledUrls.some((u) => u.includes('/sessions'))).toBe(false)
  })
})

describe('useSession: this tab\'s own session gets closed', () => {
  it('a session that resolved fine once, then 404s on reload(), becomes "closed" (not "notfound")', async () => {
    window.history.replaceState(null, '', '/?session=good')
    let sessionStillExists = true
    mockFetch((url) => {
      if (url.endsWith('/api/session/good')) {
        return sessionStillExists
          ? jsonResponse({ id: 'good', level: 'Beta', created_at: '2026-09-22T00:00:00Z', last_active_at: '2026-09-22T00:00:01Z', claim_token: 'tok-1' })
          : jsonResponse({ error: "session not found: 'good'" }, 404)
      }
      return undefined
    })

    const { result } = renderHook(() => useSession())
    // Same "editing is also the default" caveat as the auto-create tests above -- wait on the real
    // resolved level landing, not the view alone.
    await waitFor(() => expect(result.current.level).toBe('Beta'))

    sessionStillExists = false
    act(() => result.current.reload())

    await waitFor(() => expect(result.current.view).toBe('closed'))
    expect(result.current.sessionId).toBe('good')
    // No auto-navigate: the URL still names the closed session, not a freshly created replacement.
    expect(new URLSearchParams(window.location.search).get('session')).toBe('good')
  })
})

describe('useSession: markSuperseded', () => {
  it('flips view to "superseded" without touching sessionId/level/claimToken', async () => {
    window.history.replaceState(null, '', '/?session=good')
    mockFetch((url) => {
      if (url.endsWith('/api/session/good')) {
        return jsonResponse({
          id: 'good', level: 'Beta', created_at: '2026-09-22T00:00:00Z',
          last_active_at: '2026-09-22T00:00:01Z', claim_token: 'tok-1',
        })
      }
      return undefined
    })

    const { result } = renderHook(() => useSession())
    await waitFor(() => expect(result.current.level).toBe('Beta'))

    act(() => result.current.markSuperseded())

    expect(result.current.view).toBe('superseded')
    expect(result.current.sessionId).toBe('good')
    expect(result.current.level).toBe('Beta')
    expect(result.current.claimToken).toBe('tok-1')
  })

  it('reload() (the takeover\'s own Reload button) re-claims the session and returns to "editing"', async () => {
    window.history.replaceState(null, '', '/?session=good')
    mockFetch((url) => {
      if (url.endsWith('/api/session/good')) {
        return jsonResponse({
          id: 'good', level: 'Beta', created_at: '2026-09-22T00:00:00Z',
          last_active_at: '2026-09-22T00:00:01Z', claim_token: 'tok-2',
        })
      }
      return undefined
    })

    const { result } = renderHook(() => useSession())
    await waitFor(() => expect(result.current.level).toBe('Beta'))

    act(() => result.current.markSuperseded())
    expect(result.current.view).toBe('superseded')

    act(() => result.current.reload())

    await waitFor(() => expect(result.current.view).toBe('editing'))
    // A fresh claim token -- reclaiming the session for this window.
    expect(result.current.claimToken).toBe('tok-2')
  })
})
