import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import App from './App'

// Viewport3D pulls in react-three-fiber's <Canvas> (WebGL), which jsdom can't provide -- stub it
// so this file tests App's own state management (the Load/Rebuild error-banner regression below),
// not the 3D scene itself (covered separately by scene/*.test.ts).
vi.mock('./scene/Viewport3D', () => ({
  Viewport3D: () => <div data-testid="viewport-stub" />,
}))

afterEach(cleanup)

const HEALTH = { status: 'ok', level: 'TestLevel' }
const SCENE = { polys: [], actors: [], geometry_pinned: false }
const ATLAS = { width: 1, height: 1, manifest: [], png_base64: '' }
const LIGHTMAP = { width: 1, height: 1, intensity: 1, manifest: [], png_base64: '' }
const STATUS_UNBUILT = { changes_available: false, geometry_pinned: false, build_status: 'no_build' }

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status })
}

/** Routes the fixed set of GET requests App.tsx makes on mount + status polling; a caller-supplied
 * `extra` handles a specific test's own POST /load or /rebuild. */
function mockFetch(extra?: (url: string, init?: RequestInit) => Response | undefined) {
  globalThis.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    const overridden = extra?.(url, init)
    if (overridden) return overridden
    if (url.endsWith('/api/health')) return jsonResponse(HEALTH)
    if (url.endsWith('/scene')) return jsonResponse(SCENE)
    if (url.endsWith('/atlas')) return jsonResponse(ATLAS)
    if (url.endsWith('/lightmap')) return jsonResponse(LIGHTMAP)
    if (url.endsWith('/status')) return jsonResponse(STATUS_UNBUILT)
    throw new Error(`unexpected fetch: ${url}`)
  }) as unknown as typeof fetch
}

describe('App: Load/Rebuild failure handling', () => {
  it('shows a dismissable banner on a failed Rebuild without discarding the already-loaded scene', async () => {
    mockFetch((url, init) => {
      if (url.endsWith('/rebuild') && init?.method === 'POST') {
        return jsonResponse({ error: 'CSG solve failed: degenerate brush Foo' }, 500)
      }
      return undefined
    })

    render(<App />)

    await waitFor(() => expect(screen.getByTestId('viewport-stub')).toBeTruthy())

    fireEvent.click(screen.getByRole('button', { name: 'Rebuild' }))

    await waitFor(() => expect(screen.getByText(/CSG solve failed/)).toBeTruthy())
    // The scene stayed on screen -- a failed build action must not blank the whole page.
    expect(screen.getByTestId('viewport-stub')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: 'Dismiss' }))
    expect(screen.queryByText(/CSG solve failed/)).toBeNull()
    expect(screen.getByTestId('viewport-stub')).toBeTruthy()
  })

  it('clears a stale failure banner on the next build action, success or not', async () => {
    let rebuildCalls = 0
    mockFetch((url, init) => {
      if (url.endsWith('/rebuild') && init?.method === 'POST') {
        rebuildCalls += 1
        return rebuildCalls === 1
          ? jsonResponse({ error: 'first attempt fails' }, 500)
          : jsonResponse({ status: 'ok', geom_hash: null, light_hash: null })
      }
      return undefined
    })

    render(<App />)
    await waitFor(() => expect(screen.getByTestId('viewport-stub')).toBeTruthy())

    fireEvent.click(screen.getByRole('button', { name: 'Rebuild' }))
    await waitFor(() => expect(screen.getByText(/first attempt fails/)).toBeTruthy())

    fireEvent.click(screen.getByRole('button', { name: 'Rebuild' }))
    await waitFor(() => expect(screen.queryByText(/first attempt fails/)).toBeNull())
    expect(screen.getByTestId('viewport-stub')).toBeTruthy()
  })
})

describe('App: Reload button visibility', () => {
  it('hides the Reload button when the trunk has not diverged', async () => {
    mockFetch()

    render(<App />)

    await waitFor(() => expect(screen.getByTestId('viewport-stub')).toBeTruthy())
    expect(screen.queryByRole('button', { name: /Reload/ })).toBeNull()
  })

  it('shows a "Reload" button once the trunk has diverged (changes_available)', async () => {
    mockFetch((url) => {
      if (url.endsWith('/status')) {
        return jsonResponse({ ...STATUS_UNBUILT, changes_available: true })
      }
      return undefined
    })

    render(<App />)

    await waitFor(() => expect(screen.getByRole('button', { name: 'Reload' })).toBeTruthy())
  })
})
