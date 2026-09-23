import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { SessionPicker } from './SessionPicker'

const navigate = vi.fn()
vi.mock('./route', () => ({ navigate: (...args: unknown[]) => navigate(...args) }))

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status })
}

afterEach(() => {
  cleanup()
  navigate.mockReset()
})

const LEVELS = { levels: [{ name: 'Alpha', active: true }, { name: 'Beta', active: false }], current: 'Alpha' }
const SESSIONS = {
  sessions: [
    { id: 's1', level: 'Alpha', created_at: 'c1', last_active_at: '2026-09-23T00:02:00Z', name: 'My Session' },
    { id: 's2', level: 'Alpha', created_at: 'c2', last_active_at: '2026-09-23T00:01:00Z', name: null },
  ],
}

function mockFetch(extra?: (url: string, init?: RequestInit) => Response | Promise<Response> | undefined) {
  globalThis.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    const overridden = await extra?.(url, init)
    if (overridden) return overridden
    if (url.endsWith('/api/levels')) return jsonResponse(LEVELS)
    if (url.endsWith('/api/sessions')) return jsonResponse(SESSIONS)
    throw new Error(`unexpected fetch: ${url}`)
  }) as unknown as typeof fetch
}

describe('SessionPicker', () => {
  it('lists sessions sorted by last_active_at descending, name-or-level as the primary label', async () => {
    mockFetch()
    render(<SessionPicker />)
    await waitFor(() => expect(screen.getByText('My Session')).toBeTruthy())

    const rows = screen.getAllByTestId('session-picker-row')
    // No @testing-library/jest-dom in this codebase's test setup -- use textContent directly.
    expect(rows[0].textContent).toContain('My Session')
    expect(rows[1].textContent).toContain('Alpha') // s2, unnamed, falls back to level
  })

  it('clicking a row (not the name or delete button) navigates to /session/<id>/', async () => {
    mockFetch()
    render(<SessionPicker />)
    await waitFor(() => expect(screen.getByText('My Session')).toBeTruthy())

    fireEvent.click(screen.getAllByTestId('session-picker-row')[0])

    expect(navigate).toHaveBeenCalledWith('/session/s1/')
  })

  it('creating a session: pick a level, click Create, navigate to the new session', async () => {
    mockFetch((url, init) => {
      if (url.endsWith('/api/level/Beta/sessions') && init?.method === 'POST') {
        return jsonResponse({ id: 'new-id', level: 'Beta', created_at: 'c', claim_token: 't' }, 201)
      }
      return undefined
    })
    render(<SessionPicker />)
    await waitFor(() => expect(screen.getByText('My Session')).toBeTruthy())

    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'Beta' } })
    fireEvent.click(screen.getByRole('button', { name: /create session/i }))

    await waitFor(() => expect(navigate).toHaveBeenCalledWith('/session/new-id/'))
  })

  // Regression: a failed session creation used to only console.error, with nothing shown on
  // screen -- same "no silent half-answers" bar as the other five catch sites' own tests below.
  it('a failed session creation shows the error message on screen', async () => {
    mockFetch((url, init) => {
      if (url.endsWith('/api/level/Beta/sessions') && init?.method === 'POST') {
        return jsonResponse({ error: 'level Beta is locked by another process' }, 409)
      }
      return undefined
    })
    render(<SessionPicker />)
    await waitFor(() => expect(screen.getByText('My Session')).toBeTruthy())

    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'Beta' } })
    fireEvent.click(screen.getByRole('button', { name: /create session/i }))

    await waitFor(() => expect(screen.getByText(/level beta is locked by another process/i)).toBeTruthy())
    expect(navigate).not.toHaveBeenCalled()
  })

  it('delete on a session with no unsaved edits shows the plain confirm copy', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false)
    mockFetch((url) => {
      if (url.endsWith('/api/session/s1/staged')) return jsonResponse({})
      return undefined
    })
    render(<SessionPicker />)
    await waitFor(() => expect(screen.getByText('My Session')).toBeTruthy())

    fireEvent.click(screen.getAllByRole('button', { name: /delete/i })[0])

    await waitFor(() => expect(confirmSpy).toHaveBeenCalledWith('Delete this session?'))
    expect(navigate).not.toHaveBeenCalled()
  })

  it('delete on a session WITH unsaved edits shows the different confirm copy', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false)
    mockFetch((url) => {
      if (url.endsWith('/api/session/s1/staged')) {
        return jsonResponse({ Light0: { staged_location: [0, 0, 0], baseline_location: [0, 0, 0] } })
      }
      return undefined
    })
    render(<SessionPicker />)
    await waitFor(() => expect(screen.getByText('My Session')).toBeTruthy())

    fireEvent.click(screen.getAllByRole('button', { name: /delete/i })[0])

    await waitFor(() => expect(confirmSpy).toHaveBeenCalledWith('This session has unsaved edits. Delete anyway?'))
  })

  it('confirming delete acquires a fresh claim then DELETEs, and removes the row without a re-fetch', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    let deleteCalled = false
    mockFetch((url, init) => {
      if (url.endsWith('/api/session/s1/staged')) return jsonResponse({})
      if (url.endsWith('/api/session/s1') && (!init || init.method === undefined)) {
        return jsonResponse({ id: 's1', level: 'Alpha', created_at: 'c', last_active_at: 'a', claim_token: 'fresh-tok', name: 'My Session' })
      }
      if (url.endsWith('/api/session/s1') && init?.method === 'DELETE') {
        deleteCalled = true
        return new Response(null, { status: 204 })
      }
      return undefined
    })
    render(<SessionPicker />)
    await waitFor(() => expect(screen.getByText('My Session')).toBeTruthy())

    fireEvent.click(screen.getAllByRole('button', { name: /delete/i })[0])

    await waitFor(() => expect(deleteCalled).toBe(true))
    await waitFor(() => expect(screen.queryByText('My Session')).toBeNull())
  })

  it('inline-renaming a row calls renameSession via an acquired claim, and updates that row', async () => {
    mockFetch((url, init) => {
      if (url.endsWith('/api/session/s1') && (!init || init.method === undefined)) {
        return jsonResponse({ id: 's1', level: 'Alpha', created_at: 'c', last_active_at: 'a', claim_token: 'fresh-tok', name: 'My Session' })
      }
      if (url.endsWith('/api/session/s1/rename') && init?.method === 'POST') {
        return jsonResponse({ id: 's1', level: 'Alpha', created_at: 'c', last_active_at: 'a', name: 'Renamed' })
      }
      return undefined
    })
    render(<SessionPicker />)
    await waitFor(() => expect(screen.getByText('My Session')).toBeTruthy())

    fireEvent.click(screen.getByText('My Session'))
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Renamed' } })
    fireEvent.click(screen.getByRole('button', { name: /confirm|✓/i }))

    await waitFor(() => expect(screen.getByText('Renamed')).toBeTruthy())
    expect(navigate).not.toHaveBeenCalled()
  })

  // Regression for a real bug a review caught: acquireClaim fetched a fresh claim token but never
  // applied it via setClaimToken -- renameSession/deleteSession read the token from api.ts's own
  // module-level variable (withClaimToken), not from acquireClaim's resolved value, so the mutating
  // call went out with whatever token (if any) happened to already be set, not the freshly-fetched
  // one. Assert on the real request header, not just that the call eventually succeeds.
  it('rename applies the freshly-acquired claim token to the mutating call header', async () => {
    let renameHeaders: HeadersInit | undefined
    mockFetch((url, init) => {
      if (url.endsWith('/api/session/s1') && (!init || init.method === undefined)) {
        return jsonResponse({ id: 's1', level: 'Alpha', created_at: 'c', last_active_at: 'a', claim_token: 'freshly-acquired-tok', name: 'My Session' })
      }
      if (url.endsWith('/api/session/s1/rename') && init?.method === 'POST') {
        renameHeaders = init.headers
        return jsonResponse({ id: 's1', level: 'Alpha', created_at: 'c', last_active_at: 'a', name: 'Renamed' })
      }
      return undefined
    })
    render(<SessionPicker />)
    await waitFor(() => expect(screen.getByText('My Session')).toBeTruthy())

    fireEvent.click(screen.getByText('My Session'))
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Renamed' } })
    fireEvent.click(screen.getByRole('button', { name: /confirm|✓/i }))

    await waitFor(() => expect(screen.getByText('Renamed')).toBeTruthy())
    expect(renameHeaders).toEqual(expect.objectContaining({ 'X-Claim-Token': 'freshly-acquired-tok' }))
  })

  // Regression: a failed rename used to only console.error, with nothing shown on screen -- a
  // real 409 (e.g. a claim race) produced no visible change at all. Assert the message renders.
  it('a failed rename shows the error message on screen', async () => {
    mockFetch((url, init) => {
      if (url.endsWith('/api/session/s1') && (!init || init.method === undefined)) {
        return jsonResponse({ id: 's1', level: 'Alpha', created_at: 'c', last_active_at: 'a', claim_token: 'tok', name: 'My Session' })
      }
      if (url.endsWith('/api/session/s1/rename') && init?.method === 'POST') {
        return jsonResponse({ error: 'session claimed by another connection' }, 409)
      }
      return undefined
    })
    render(<SessionPicker />)
    await waitFor(() => expect(screen.getByText('My Session')).toBeTruthy())

    fireEvent.click(screen.getByText('My Session'))
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Renamed' } })
    fireEvent.click(screen.getByRole('button', { name: /confirm|✓/i }))

    await waitFor(() => expect(screen.getByText(/session claimed by another connection|409/i)).toBeTruthy())
  })

  it('delete applies the freshly-acquired claim token to the mutating call header', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    let deleteHeaders: HeadersInit | undefined
    mockFetch((url, init) => {
      if (url.endsWith('/api/session/s1/staged')) return jsonResponse({})
      if (url.endsWith('/api/session/s1') && (!init || init.method === undefined)) {
        return jsonResponse({ id: 's1', level: 'Alpha', created_at: 'c', last_active_at: 'a', claim_token: 'freshly-acquired-tok-2', name: 'My Session' })
      }
      if (url.endsWith('/api/session/s1') && init?.method === 'DELETE') {
        deleteHeaders = init.headers
        return new Response(null, { status: 204 })
      }
      return undefined
    })
    render(<SessionPicker />)
    await waitFor(() => expect(screen.getByText('My Session')).toBeTruthy())

    fireEvent.click(screen.getAllByRole('button', { name: /delete/i })[0])

    await waitFor(() => expect(deleteHeaders).toEqual(expect.objectContaining({ 'X-Claim-Token': 'freshly-acquired-tok-2' })))
  })
})
