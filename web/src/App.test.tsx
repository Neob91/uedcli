import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import App from './App'

/** The selection callbacks App hands the (stubbed) quad, captured so a test can drive App's own
 * real handlers without a WebGL raycast. */
interface QuadSelectionProps {
  onSelectActor: (name: string, additive: boolean) => void
  onSelectSurface: (actor: string, polyIndex: number, additive: boolean) => void
  onDeselect: () => void
}
const quadProps: { current: QuadSelectionProps | null } = { current: null }

// QuadLayout (Perspective + 3 ortho panes) pulls in react-three-fiber's <Canvas> (WebGL) four times
// over, which jsdom can't provide -- stub the whole quad so this file tests App's own state
// management (the Load/Rebuild error-banner regression below), not the 3D scene itself (covered
// separately by scene/*.test.ts). The stub also records the selection callbacks, so the
// selection-coexistence tests below exercise the real `onSelectActor`/`onSelectSurface`.
vi.mock('./scene/QuadLayout', () => ({
  QuadLayout: (props: QuadSelectionProps) => {
    quadProps.current = props
    return <div data-testid="viewport-stub" />
  },
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

describe('App: level switching', () => {
  const LEVELS_PAYLOAD = {
    levels: [
      { name: 'TestLevel', active: true },
      { name: 'OtherLevel', active: false },
    ],
    current: 'TestLevel',
  }

  /** Like `mockFetch`, plus `/api/levels` (LevelPicker's own fetch) and a caller-supplied handler
   * for `PUT /api/level` -- deferrable, so a test can inspect the blocked state mid-switch. */
  function mockFetchForSwitch(putHandler: () => Promise<Response>) {
    globalThis.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.endsWith('/api/health')) return jsonResponse(HEALTH)
      if (url.endsWith('/api/levels')) return jsonResponse(LEVELS_PAYLOAD)
      if (url.endsWith('/api/level') && init?.method === 'PUT') return putHandler()
      if (url.endsWith('/scene')) return jsonResponse(SCENE)
      if (url.endsWith('/atlas')) return jsonResponse(ATLAS)
      if (url.endsWith('/lightmap')) return jsonResponse(LIGHTMAP)
      if (url.endsWith('/status')) return jsonResponse(STATUS_UNBUILT)
      throw new Error(`unexpected fetch: ${url}`)
    }) as unknown as typeof fetch
  }

  it('unloads the old scene immediately and blocks the whole app until the new level fully loads', async () => {
    let resolvePut: (() => void) | undefined
    const putGate = new Promise<void>((resolve) => {
      resolvePut = resolve
    })
    mockFetchForSwitch(async () => {
      await putGate
      return jsonResponse({ level: 'OtherLevel' })
    })

    render(<App />)
    await waitFor(() => expect(screen.getByTestId('viewport-stub')).toBeTruthy())
    await waitFor(() => expect(screen.getByText('OtherLevel')).toBeTruthy())

    fireEvent.change(screen.getByTestId('level-picker-select'), { target: { value: 'OtherLevel' } })

    // The old scene, toolbar, and picker are gone immediately -- before the PUT even resolves --
    // and a loading indicator takes their place (reusing the existing `.status-message` pattern).
    await waitFor(() => expect(screen.queryByTestId('viewport-stub')).toBeNull())
    expect(screen.getByText('Switching level…')).toBeTruthy()
    expect(screen.queryByTestId('level-picker-select')).toBeNull()
    expect(screen.queryByRole('button', { name: 'Rebuild' })).toBeNull()

    resolvePut?.()

    // Only unblocks once the new level's full state (scene+atlas+lightmap) has loaded.
    await waitFor(() => expect(screen.getByTestId('viewport-stub')).toBeTruthy())
    expect(screen.queryByText('Switching level…')).toBeNull()
    expect(screen.getByTestId('level-picker-select')).toBeTruthy()
  })

  it('restores the old level state and unblocks if the switch itself fails', async () => {
    mockFetchForSwitch(async () => jsonResponse({ error: 'level not found: OtherLevel' }, 500))

    render(<App />)
    await waitFor(() => expect(screen.getByTestId('viewport-stub')).toBeTruthy())
    await waitFor(() => expect(screen.getByText('OtherLevel')).toBeTruthy())

    fireEvent.change(screen.getByTestId('level-picker-select'), { target: { value: 'OtherLevel' } })

    // The failed switch never changed the server-side level -- the old level's scene comes back,
    // not a page stuck blocked on nothing.
    await waitFor(() => expect(screen.getByTestId('viewport-stub')).toBeTruthy())
    await waitFor(() => expect(screen.getByText(/level not found/)).toBeTruthy())
    expect(screen.getByTestId('level-picker-select').hasAttribute('disabled')).toBe(false)
  })
})

// An actor selection and a surface selection COEXIST, and only a PLAIN (non-additive) pick clears
// the other kind -- UED22's own mechanism: `AActor.bSelected` and `FBspSurf.PolyFlags & PF_Selected`
// are independent, and the single point where they meet is `UEditorEngine::SelectNone`, which the
// plain-LMB branch of each click handler calls and the Ctrl branch of each skips (GUI-PARITY.md
// "Actor + surface selection coexist; only a plain click clears both"). These drive App's real
// handlers through the stubbed quad and read the result off the Inspector.
describe('App: actor + surface selection coexistence', () => {
  // The unified sidebar persists its active-tab/collapse choice to localStorage (useSidebar.ts) --
  // clear it so the batch-select test's tab switching below can't leak into another test's default
  // "Selection tab active" assumption, regardless of file execution order.
  beforeEach(() => {
    localStorage.clear()
  })

  const ACTOR = {
    name: 'Room',
    cls: 'Engine.Brush',
    bbox_lo: [-256, -256, -128],
    bbox_hi: [256, 256, 128],
    location: [0, 0, 0],
    rotation: [0, 0, 0],
    folder: null,
    labels: [],
    order_value: 'm',
    csg_rank: 1,
    props: [],
    categories: [],
    brush: null,
    sprite: null,
    radii: null,
    is_mover: false,
    directional_arrow: null,
  }
  const POLY = {
    verts: [0, 0, 0, 1, 0, 0, 1, 1, 0],
    base: [0, 0, 0],
    tu: [1, 0, 0],
    tv: [0, 1, 0],
    pan: [0, 0],
    tex_index: 3,
    masked: false,
    two_sided: false,
    blend: 'opaque',
    flags: 0,
    lightmap: null,
    owner: 'Room',
    i_brush_poly: 4,
  }

  async function renderSelectable() {
    quadProps.current = null
    mockFetch((url) => (url.endsWith('/scene')
      ? jsonResponse({ polys: [POLY], actors: [ACTOR], geometry_pinned: false })
      : undefined))
    render(<App />)
    await waitFor(() => expect(quadProps.current).not.toBeNull())
    return quadProps.current!
  }

  it('keeps an actor selected when a surface is added with Ctrl (additive)', async () => {
    const quad = await renderSelectable()
    act(() => quad.onSelectActor('Room', false))
    act(() => quad.onSelectSurface('Room', 4, true))
    expect(screen.getByTestId('inspector-sections')).toBeTruthy()
    expect(screen.getByTestId('inspector')).toBeTruthy()
    expect(screen.getByTestId('inspector-surface')).toBeTruthy()
  })

  it('keeps a surface selected when an actor is added with Ctrl (additive)', async () => {
    const quad = await renderSelectable()
    act(() => quad.onSelectSurface('Room', 4, false))
    act(() => quad.onSelectActor('Room', true))
    expect(screen.getByTestId('inspector-sections')).toBeTruthy()
  })

  it('a PLAIN surface pick clears the actor selection (the editor calls SelectNone first)', async () => {
    const quad = await renderSelectable()
    act(() => quad.onSelectActor('Room', false))
    act(() => quad.onSelectSurface('Room', 4, false))
    expect(screen.getByTestId('inspector-surface')).toBeTruthy()
    expect(screen.queryByTestId('inspector')).toBeNull()
    expect(screen.queryByTestId('inspector-sections')).toBeNull()
  })

  it('a PLAIN actor pick clears the surface selection (same SelectNone)', async () => {
    const quad = await renderSelectable()
    act(() => quad.onSelectSurface('Room', 4, false))
    act(() => quad.onSelectActor('Room', false))
    expect(screen.getByTestId('inspector')).toBeTruthy()
    expect(screen.queryByTestId('inspector-surface')).toBeNull()
  })

  // A batch actor select never clears surfaces, additive or replacing: UED22's actor batch verbs
  // don't -- `edactBoxSelect` clears `bSelected` in its own inline loop and never touches a surf,
  // and `edactSelectAll`/`edactSelectOfClass`/`mapSelect*` never mention `PF_Selected` at all.
  //
  // `QuadLayout` no longer hosts the org panel (unified-sidebar migration: `OrgPanel` moved into
  // `Sidebar`, a sibling of `QuadLayout` in `App.tsx`), so it no longer receives `onSelectMany` as a
  // prop at all -- the batch-select control this test needs to drive now lives in the real
  // `Sidebar`'s Org panel (rendered for real here, same as `Inspector` already is; only the WebGL
  // quad is stubbed). Switch to the Org tab, click the "no folder" bucket (Room has `folder: null`)
  // the same way `sidebarRegistry.test.ts` already does, then switch back to the Selection tab to
  // read the result off the Inspector.
  it('a batch actor select keeps surfaces, additive or replacing', async () => {
    const quad = await renderSelectable()
    act(() => quad.onSelectSurface('Room', 4, false))

    fireEvent.click(screen.getByTestId('sidebar-rail-org'))
    fireEvent.click(screen.getByTestId('org-folder-no-folder'), { ctrlKey: true }) // additive
    fireEvent.click(screen.getByTestId('sidebar-rail-selection'))
    expect(screen.getByTestId('inspector-sections')).toBeTruthy()

    fireEvent.click(screen.getByTestId('sidebar-rail-org'))
    fireEvent.click(screen.getByTestId('org-folder-no-folder')) // replacing
    fireEvent.click(screen.getByTestId('sidebar-rail-selection'))
    expect(screen.getByTestId('inspector-sections')).toBeTruthy()
    expect(screen.getByTestId('inspector-surface')).toBeTruthy()
  })

  it('a miss/Esc still clears both kinds (the editor\'s own SELECT NONE)', async () => {
    const quad = await renderSelectable()
    act(() => quad.onSelectActor('Room', false))
    act(() => quad.onSelectSurface('Room', 4, true))
    act(() => quad.onDeselect())
    expect(screen.getByTestId('inspector-empty')).toBeTruthy()
  })
})
