import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import App from './App'

/** `subscribeChangesAvailable`'s real implementation (reload.ts) opens a genuine WebSocket, which
 * jsdom will try (and fail) to actually connect over the network -- irrelevant noise for these
 * App-level tests, which only care what App.tsx DOES with the two callbacks it's handed. Mocked
 * the same way `./scene/QuadLayout` already is: capture the collaborator's own inputs, let a test
 * drive them directly, instead of simulating a real socket end to end (that's reload.test.ts's job). */
const reloadSub: { current: { onChangesAvailable: () => void; onSuperseded: () => void; onClosed: () => void } | null } = { current: null }
vi.mock('./reload', () => ({
  subscribeChangesAvailable: (
    _sessionId: string,
    _claimToken: string,
    onChangesAvailable: () => void,
    onSuperseded: () => void,
    onClosed: () => void,
  ) => {
    reloadSub.current = { onChangesAvailable, onSuperseded, onClosed }
    return { unsubscribe: vi.fn() }
  },
}))

/** The selection callbacks App hands the (stubbed) quad, captured so a test can drive App's own
 * real handlers without a WebGL raycast. Extended (final review fix wave) with the Critical 2
 * staged-offset props -- a test can call `setStagedOffsets` directly, exactly the way a real
 * viewport's own Ctrl/Cmd-drag would, and read back `stagedOffsets`/`onStaged` to prove App.tsx's
 * shared state actually propagates and actually clears. */
interface QuadSelectionProps {
  onSelectActor: (name: string, additive: boolean) => void
  onSelectSurface: (actor: string, polyIndex: number, additive: boolean) => void
  onDeselect: () => void
  onStaged?: (names: string[]) => void
  stagedOffsets: Record<string, [number, number, number]>
  setStagedOffsets: (next: Record<string, [number, number, number]>) => void
  // Bug fix (found auditing for more of the Inspector/mesh-body divergence class): `frameActors`
  // (the `F`-key/org-panel camera-framing trigger, a real QuadLayout prop) used to bbox off raw
  // scene.actors, so framing a staged-moved actor flew the camera to its pre-move position.
  frameActors: (names: ReadonlySet<string>) => void
  frameRequest: { bbox: { lo: [number, number, number]; hi: [number, number, number] }; seq: number } | null
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

// Session-management-UI spec, decision 1: there is no auto-create any more. Every test below mounts
// on a CONCRETE `/session/<id>/` path (see `beforeEach`) -- `App`'s own routing (route.ts) sends
// that straight to `SessionEditor`, which resolves it via `useSession(sessionId)` -> `GET
// /api/session/{id}` (SessionContext.tsx), never `/api/levels` or a session-creating POST.
const LEVEL_NAME = 'TestLevel'
const SESSION_ID = 'sess-1'
const LEVELS_PAYLOAD = { levels: [{ name: LEVEL_NAME, active: true }], current: LEVEL_NAME }
const SESSION_RECORD = { id: SESSION_ID, level: LEVEL_NAME, created_at: '2026-09-22T00:00:00Z', claim_token: 'tok-1' }
const SESSIONS_LIST = { sessions: [{ id: SESSION_ID, level: LEVEL_NAME, created_at: '2026-09-22T00:00:00Z', last_active_at: '2026-09-22T00:00:00Z' }] }
const SCENE = { polys: [], actors: [], geometry_pinned: false }
const ATLAS = { width: 1, height: 1, manifest: [], png_base64: '' }
const LIGHTMAP = { width: 1, height: 1, intensity: 1, manifest: [], png_base64: '' }
const STATUS_UNBUILT = { changes_available: false, geometry_pinned: false, build_status: 'no_build' }

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status })
}

beforeEach(() => {
  window.history.replaceState(null, '', `/session/${SESSION_ID}/`)
  reloadSub.current = null
})

/** Routes the fixed set of GET/POST requests App.tsx (via `useSession`/`SessionDropdown`) makes on
 * mount + status polling; a caller-supplied `extra` handles a specific test's own POST /load or
 * /rebuild, or a different session/level bootstrap. */
function mockFetch(extra?: (url: string, init?: RequestInit) => Response | Promise<Response> | undefined) {
  globalThis.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    const overridden = await extra?.(url, init)
    if (overridden) return overridden
    if (url.endsWith('/api/levels')) return jsonResponse(LEVELS_PAYLOAD)
    if (url.endsWith(`/api/session/${SESSION_ID}`) && (!init || !init.method)) {
      return jsonResponse({ ...SESSION_RECORD, id: SESSION_ID, last_active_at: '2026-09-22T00:00:00Z', name: null })
    }
    if (url.endsWith('/api/sessions')) return jsonResponse(SESSIONS_LIST)
    if (url.endsWith('/scene')) return jsonResponse(SCENE)
    if (url.endsWith('/atlas')) return jsonResponse(ATLAS)
    if (url.endsWith('/lightmap')) return jsonResponse(LIGHTMAP)
    if (url.endsWith('/status')) return jsonResponse(STATUS_UNBUILT)
    if (url.endsWith('/staged')) return jsonResponse({})
    throw new Error(`unexpected fetch: ${url}`)
  }) as unknown as typeof fetch
}

// Session-management-UI spec, decision 1: `App`'s own routing (route.ts) is what decides between
// the two screens, not `SessionContext` -- these prove that split directly, rather than assuming it
// from the describe blocks above/below which all mount straight onto a `/session/<id>/` path.
describe('App: routing', () => {
  it('a bare "/" renders the session picker, not the editor', async () => {
    window.history.replaceState(null, '', '/')
    mockFetch()
    render(<App />)
    await waitFor(() => expect(screen.getByRole('combobox')).toBeTruthy())
    expect(screen.queryByTestId('viewport-stub')).toBeNull()
  })

  it('/session/<id>/ renders the editor', async () => {
    mockFetch()
    render(<App />)
    await waitFor(() => expect(screen.getByTestId('viewport-stub')).toBeTruthy())
  })
})

// Task 6/7/15: a "closed" push/409 means the session was actually DELETED, not merely claimed
// elsewhere -- a distinct message from the superseded-takeover banner (`describe('App: superseded
// takeover', ...)` below), and `markClosed` (SessionContext.tsx) is the shared primitive both the
// live WS push and the mutating-call 409 fallback route through.
describe('App: deleted vs superseded', () => {
  it('a "closed" WS push shows the closed message, not the superseded takeover banner', async () => {
    mockFetch()
    render(<App />)
    await waitFor(() => expect(screen.getByTestId('viewport-stub')).toBeTruthy())

    act(() => reloadSub.current?.onClosed())

    expect(screen.getByText(/this session was closed/i)).toBeTruthy()
  })

  it('a "deleted" 409 from Load/Rebuild shows the closed message too', async () => {
    // Fixed from the plan's own snippet, which mocked `/load` while clicking Rebuild -- a 409 from
    // *this* build action has to come from the endpoint it actually posts to (`/rebuild`) for
    // `runBuildAction`'s catch branch to ever see it.
    mockFetch((url, init) => {
      if (url.endsWith('/rebuild') && init?.method === 'POST') return jsonResponse({ error: 'session deleted' }, 409)
      return undefined
    })
    render(<App />)
    await waitFor(() => expect(screen.getByTestId('viewport-stub')).toBeTruthy())

    fireEvent.click(screen.getByRole('button', { name: /rebuild/i }))

    await waitFor(() => expect(screen.getByText(/this session was closed/i)).toBeTruthy())
  })
})

// Final review fix wave, Important 3: notfound/closed used to be dead ends -- only the browser's
// own Back button, which doesn't always have anywhere to go. Both views need an in-app way back to
// the picker. `./session/route` isn't mocked in this file, so these drive the real `navigate` and
// assert its real, observable effect (the URL actually changes to "/"), the same way every other
// test in this file exercises real routing rather than a mocked one.
describe('App: notfound/closed have a way back to the picker', () => {
  it('the closed view\'s "Back to sessions" button navigates to "/"', async () => {
    mockFetch()
    render(<App />)
    await waitFor(() => expect(screen.getByTestId('viewport-stub')).toBeTruthy())

    act(() => reloadSub.current?.onClosed())
    await waitFor(() => expect(screen.getByText(/this session was closed/i)).toBeTruthy())

    fireEvent.click(screen.getByRole('button', { name: /back to sessions/i }))
    expect(window.location.pathname).toBe('/')
  })

  it('the notfound view\'s "Back to sessions" button navigates to "/"', async () => {
    const badId = 'does-not-exist'
    window.history.replaceState(null, '', `/session/${badId}/`)
    mockFetch((url) => {
      if (url.endsWith(`/api/session/${badId}`)) return jsonResponse({ error: `session not found: '${badId}'` }, 404)
      return undefined
    })
    render(<App />)
    await waitFor(() => expect(screen.getByText(`Session not found: ${badId}`)).toBeTruthy())

    fireEvent.click(screen.getByRole('button', { name: /back to sessions/i }))
    expect(window.location.pathname).toBe('/')
  })
})

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

// Task 10: Load's conflict check (uedcli/serve/edits.py `check_load_conflicts`) surfaces through
// the extended `POST /load` response's `conflicts` field -- this drives the SAME shared
// `ConflictResolver` SaveBar mounts, with Load's own "Accept trunk" label and its accept-load-only
// resolution mapping.
describe('App: Load conflict resolution', () => {
  const LOAD_CONFLICT = { name: 'Light0', staged_location: [10, 0, 0], trunk_location: [20, 0, 0] }

  it('a postLoad response with conflicts mounts ConflictResolver; picking "Accept trunk" and confirming calls postLoad again with {name: "accept-load"}', async () => {
    let loadCallCount = 0
    const loadCalls: unknown[] = []
    mockFetch((url, init) => {
      if (url.endsWith('/status')) {
        return jsonResponse({ ...STATUS_UNBUILT, changes_available: true })
      }
      if (url.endsWith('/load') && init?.method === 'POST') {
        loadCallCount += 1
        loadCalls.push(init.body ? JSON.parse(String(init.body)) : null)
        const conflicts = loadCallCount === 1 ? [LOAD_CONFLICT] : []
        return jsonResponse({ status: 'ok', conflicts })
      }
      return undefined
    })

    render(<App />)
    await waitFor(() => expect(screen.getByRole('button', { name: 'Reload' })).toBeTruthy())

    fireEvent.click(screen.getByRole('button', { name: 'Reload' }))

    await waitFor(() => expect(screen.getByText('Light0')).toBeTruthy())
    expect(screen.getByText('Accept trunk')).toBeTruthy()

    fireEvent.click(screen.getByLabelText('Accept trunk'))
    fireEvent.click(screen.getByRole('button', { name: /apply/i }))

    await waitFor(() => expect(loadCallCount).toBe(2))
    expect(loadCalls[1]).toEqual({ resolutions: { Light0: 'accept-load' } })
    await waitFor(() => expect(screen.queryByText('Light0')).toBeNull())
  })

  // Important 4, final review fix wave: `mapToAcceptLoadOnly` used to drop every "mine" pick
  // entirely, so choosing "Keep my move" for every conflicting actor and clicking Confirm posted an
  // EMPTY `resolutions` -- the backend re-reported the identical unresolved conflict, and the banner
  // reappeared with no way to dismiss it short of abandoning the edit via "Accept trunk". Fixed: an
  // all-"mine" resolution is now a pure client-side dismiss, no network call at all.
  it('picking "Keep my move" for every conflict dismisses the banner locally, with NO second /load call', async () => {
    let loadCallCount = 0
    mockFetch((url, init) => {
      if (url.endsWith('/status')) {
        return jsonResponse({ ...STATUS_UNBUILT, changes_available: true })
      }
      if (url.endsWith('/load') && init?.method === 'POST') {
        loadCallCount += 1
        return jsonResponse({ status: 'ok', conflicts: [LOAD_CONFLICT] })
      }
      return undefined
    })

    render(<App />)
    await waitFor(() => expect(screen.getByRole('button', { name: 'Reload' })).toBeTruthy())

    fireEvent.click(screen.getByRole('button', { name: 'Reload' }))
    await waitFor(() => expect(screen.getByText('Light0')).toBeTruthy())
    expect(loadCallCount).toBe(1)

    fireEvent.click(screen.getByLabelText('Keep my move'))
    fireEvent.click(screen.getByRole('button', { name: /apply/i }))

    // The banner clears -- this used to re-show the IDENTICAL conflict, a dead end.
    await waitFor(() => expect(screen.queryByText('Light0')).toBeNull())
    // ...without ever posting a second /load -- declining to resolve already keeps the staged edit
    // server-side, so there is nothing to tell the backend.
    expect(loadCallCount).toBe(1)
  })
})

// Plan Task 16: replaces the old in-process `PUT /api/level` level switch (LevelPicker) with
// session identity carried in the URL (SessionContext) + a session dropdown (SessionDropdown).
// A session switch writes the picked id into the URL and re-resolves it via `GET
// /api/session/{id}` -- NOT a level-switch endpoint -- so these tests drive that dropdown and
// mock the session-resolve GET, mirroring the old suite's own "deferrable, so a test can inspect
// the blocked state mid-switch" shape.
describe('App: session switching', () => {
  const OTHER_SESSION_ID = 'sess-2'
  const OTHER_LEVEL_NAME = 'OtherLevel'
  const SESSIONS_LIST_TWO = {
    sessions: [
      { id: SESSION_ID, level: LEVEL_NAME, created_at: '2026-09-22T00:00:00Z', last_active_at: '2026-09-22T00:00:00Z' },
      { id: OTHER_SESSION_ID, level: OTHER_LEVEL_NAME, created_at: '2026-09-22T00:00:01Z', last_active_at: '2026-09-22T00:00:01Z' },
    ],
  }

  /** Like `mockFetch`, plus the two-session `/api/sessions` listing above and a caller-supplied
   * handler for `GET /api/session/{OTHER_SESSION_ID}` -- deferrable, so a test can inspect the
   * in-between state while a session switch's own resolve GET is still in flight. */
  function mockFetchForSwitch(resolveOtherSession: () => Promise<Response>) {
    mockFetch((url) => {
      if (url.endsWith('/api/sessions')) return jsonResponse(SESSIONS_LIST_TWO)
      if (url.endsWith(`/api/session/${OTHER_SESSION_ID}`)) return resolveOtherSession()
      return undefined
    })
  }

  it('switching sessions in the dropdown loads the newly-picked session, replacing the old one', async () => {
    let resolveGet: (() => void) | undefined
    const getGate = new Promise<void>((resolve) => {
      resolveGet = resolve
    })
    mockFetchForSwitch(async () => {
      await getGate
      return jsonResponse({
        id: OTHER_SESSION_ID, level: OTHER_LEVEL_NAME,
        created_at: '2026-09-22T00:00:01Z', last_active_at: '2026-09-22T00:00:01Z', claim_token: 'tok-2',
      })
    })

    render(<App />)
    await waitFor(() => expect(screen.getByTestId('viewport-stub')).toBeTruthy())
    // Waits for the dropdown to have LOADED the second session as an option, before switching to
    // it -- checked by `title` (an option's own display text is its name-or-level, `OtherLevel`
    // here, never the raw id; SessionDropdown.tsx sets `title={s.id}` on every option for this).
    await waitFor(() => expect(screen.getByTitle(OTHER_SESSION_ID)).toBeTruthy())

    fireEvent.change(screen.getByTestId('session-dropdown-select'), { target: { value: OTHER_SESSION_ID } })

    // Unlike the old level switch (which unloaded the OLD scene the instant a switch started, at
    // the picker's own click), a session switch's `sessionId` state doesn't move until the resolve
    // GET above actually settles -- so the previous session's scene stays on screen while it's in
    // flight. A deliberate difference from the old mechanism, not an oversight: see App.tsx's own
    // doc comment on the scene-fetch effect.
    expect(screen.getByTestId('viewport-stub')).toBeTruthy()

    resolveGet?.()

    // Once the switch resolves, the dropdown reflects the new session and its own scene loads.
    await waitFor(() => expect(screen.getByTestId('viewport-stub')).toBeTruthy())
    await waitFor(() => expect((screen.getByTestId('session-dropdown-select') as HTMLSelectElement).value).toBe(OTHER_SESSION_ID))
  })

  it('switching to a session that no longer exists shows the notfound view, naming the id', async () => {
    mockFetchForSwitch(async () => jsonResponse({ error: `session not found: '${OTHER_SESSION_ID}'` }, 404))

    render(<App />)
    await waitFor(() => expect(screen.getByTestId('viewport-stub')).toBeTruthy())
    // Waits for the dropdown to have LOADED the second session as an option, before switching to
    // it -- checked by `title` (an option's own display text is its name-or-level, `OtherLevel`
    // here, never the raw id; SessionDropdown.tsx sets `title={s.id}` on every option for this).
    await waitFor(() => expect(screen.getByTitle(OTHER_SESSION_ID)).toBeTruthy())

    fireEvent.change(screen.getByTestId('session-dropdown-select'), { target: { value: OTHER_SESSION_ID } })

    // The failed resolve is for an id this hook has never successfully resolved before --
    // `notfound`, not `closed` (SessionContext.tsx's own `resolvedIdsRef` distinction) -- naming
    // the dead id rather than silently restoring the old session or leaving the page blocked.
    await waitFor(() => expect(screen.getByText(`Session not found: ${OTHER_SESSION_ID}`)).toBeTruthy())
    expect(screen.queryByTestId('viewport-stub')).toBeNull()
  })
})

// Task 15 review finding: the `name`/`displayName` wiring (SessionContext.tsx's `name` field,
// App.tsx's `displayName` state + sync effect, SessionLabel's `name`/`onRenamed` props) had zero
// coverage -- every other test's bootstrap fixture returns `name: null`, so none of them ever
// exercise a real name reaching the toolbar, or `onRenamed` updating it WITHOUT a full reload
// (the entire reason `displayName` exists as its own state instead of just reading `session.name`
// directly). `SessionLabel` isn't mocked in this file (unlike `QuadLayout`), so this drives its
// real rename UI (`InlineRename`) rather than capturing/calling a prop.
describe('App: SessionLabel display name', () => {
  it("shows the session's real name once loaded, and a rename updates it without a full reload", async () => {
    let sessionGetCount = 0
    mockFetch((url, init) => {
      if (url.endsWith(`/api/session/${SESSION_ID}`) && (!init || !init.method)) {
        sessionGetCount += 1
        return jsonResponse({ ...SESSION_RECORD, id: SESSION_ID, last_active_at: '2026-09-22T00:00:00Z', name: 'My Session' })
      }
      if (url.endsWith(`/api/session/${SESSION_ID}/rename`) && init?.method === 'POST') {
        return jsonResponse({
          id: SESSION_ID, level: LEVEL_NAME,
          created_at: '2026-09-22T00:00:00Z', last_active_at: '2026-09-22T00:00:02Z', name: 'Renamed Session',
        })
      }
      return undefined
    })

    render(<App />)
    await waitFor(() => expect(screen.getByTestId('viewport-stub')).toBeTruthy())

    // The toolbar label shows the real name from `GET /api/session/{id}`, not the level placeholder
    // `InlineRename` falls back to when `name` is null (every other test's fixture).
    expect(screen.getByText('My Session')).toBeTruthy()
    expect(sessionGetCount).toBe(1)

    // Drive SessionLabel's own rename UI: click the display span to start editing, type a new
    // name, confirm.
    fireEvent.click(screen.getByText('My Session'))
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Renamed Session' } })
    fireEvent.click(screen.getByRole('button', { name: 'confirm rename' }))

    // The displayed name updates to the rename response's own name...
    await waitFor(() => expect(screen.getByText('Renamed Session')).toBeTruthy())
    expect(screen.queryByText('My Session')).toBeNull()
    // ...via `onRenamed` setting `displayName` directly, NOT by re-fetching the session -- still
    // exactly the one GET from mount.
    expect(sessionGetCount).toBe(1)
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

  // Bug fix (reported live, post-merge): the Inspector kept showing an actor's PRE-move Location
  // after a Ctrl/Cmd-drag staged a new one, because `selectedActors` (App.tsx) filtered raw
  // `scene.actors` directly instead of the staged-offset-applied array the viewports already draw
  // from. `ACTOR.location` is `[0,0,0]`; staging `[10,0,0]` (the same call a real viewport's
  // drag-end makes) must move what the Inspector shows too, not just what's drawn in the 3D pane.
  it('the Inspector reflects a staged move, not the pre-move trunk Location', async () => {
    const quad = await renderSelectable()
    act(() => quad.onSelectActor('Room', false))
    expect(screen.getByText('0.00, 0.00, 0.00')).toBeTruthy()
    act(() => quad.setStagedOffsets({ Room: [10, 0, 0] }))
    // Perf fix: setStagedOffsets now coalesces its React-state commit to one requestAnimationFrame
    // (see App.tsx's own doc comment) -- stagedOffsetsRef updates synchronously, but the re-render
    // this assertion needs waits on that rAF, hence waitFor rather than a bare synchronous assert.
    await waitFor(() => expect(screen.getByText('10.00, 0.00, 0.00')).toBeTruthy())
    expect(screen.queryByText('0.00, 0.00, 0.00')).toBeNull()
  })

  // Bug fix (found auditing for more of the same divergence class): frameActors used to bbox off
  // raw scene.actors -- ACTOR's own bbox_lo/bbox_hi are [-256,-256,-128]/[256,256,128], so framing
  // it after staging a [10,0,0] move must produce a bbox shifted by that same delta, not the
  // original one.
  it('frameActors bboxes off the staged position, not the pre-move trunk bbox', async () => {
    await renderSelectable()
    act(() => quadProps.current!.setStagedOffsets({ Room: [10, 0, 0] }))
    // Perf fix: frameActors reads `stagedOffsets` from its own React-state closure, which only
    // picks up the new value once setStagedOffsets' throttled rAF commit has fired and re-rendered
    // App -- see App.tsx's own doc comment on setStagedOffsets. Waiting for that re-render here
    // (rather than calling frameActors synchronously right after) is a test-only accommodation: real
    // callers (the org panel, the F key) never fire back-to-back with a drag's own setStagedOffsets
    // calls in the same tick the way this test does.
    await waitFor(() => expect(quadProps.current!.stagedOffsets).toEqual({ Room: [10, 0, 0] }))
    act(() => quadProps.current!.frameActors(new Set(['Room'])))
    expect(quadProps.current!.frameRequest).not.toBeNull()
    expect(quadProps.current!.frameRequest!.bbox).toEqual({ lo: [-246, -256, -128], hi: [266, 256, 128] })
  })

  // Perf fix (live report: "moving actors is still jittery -- can we recompute/rewrite the position
  // less often?"): a real drag calls setStagedOffsets once per native pointermove event, which can
  // fire faster than the display can paint. `setStagedOffsets` now coalesces its React-state commit
  // to at most one requestAnimationFrame (App.tsx's own doc comment on setStagedOffsets) -- proving
  // the exact rAF call COUNT deterministically needs either fake timers (which fought
  // testing-library's own real-timer-based `waitFor` badly enough in this environment to not be
  // worth it -- `waitFor` refused to run under faked `requestAnimationFrame`) or a race against the
  // mount-time `GET /staged` effect's own real, asynchronously-timed setStagedOffsets/rAF call (which
  // one a spy installed here catches is not deterministic). Not pinned as its own test; the two tests
  // above (and Critical 2's below) already cover that the throttled value is always eventually
  // correct, which is what actually matters -- the coalescing itself is a straightforward guard
  // (`if (rafPendingRef.current) return`) readable directly in App.tsx.
})

// Critical 2, final review fix wave: `stagedOffsets` (the Ctrl/Cmd-drag "confirmed staged" visual
// position) used to be a private useState INSIDE each of Viewport3D.tsx/OrthoViewport.tsx, so
// Discard could never actually clear what was rendered, and a drag in one pane was invisible in the
// others. Fixed by lifting ownership here (App.tsx) and threading it down as props -- these tests
// drive App's real setter (exactly what a real viewport's own drag-end does) and its real SaveBar
// (not mocked, unlike QuadLayout) to prove the state is genuinely shared and genuinely clearable.
describe('App: staged Ctrl/Cmd-drag position ownership (Critical 2)', () => {
  it('threads ONE shared stagedOffsets/setStagedOffsets to QuadLayout, not a per-pane copy', async () => {
    mockFetch()
    render(<App />)
    await waitFor(() => expect(quadProps.current).not.toBeNull())

    // Mirrors what a real Viewport3D/OrthoViewport's own Ctrl/Cmd-drag onDrag does at every frame --
    // writing through the SAME prop-passed setter every pane shares. Re-applied on every poll (not
    // a one-shot `act()` before a single `waitFor`): the mount-time `GET /staged` effect resolves
    // asynchronously to `{}` and would otherwise race a single write, occasionally clobbering it
    // right back to `{}` depending on exactly when that fetch settles.
    await waitFor(() => {
      act(() => quadProps.current!.setStagedOffsets({ Light0: [10, 0, 0] }))
      expect(quadProps.current!.stagedOffsets).toEqual({ Light0: [10, 0, 0] })
    })
  })

  it("Discard clears the shared stagedOffsets state, reverting every pane's rendered position", async () => {
    mockFetch((url, init) => {
      if (url.endsWith('/discard') && init?.method === 'POST') return jsonResponse({ status: 'ok' })
      return undefined
    })
    render(<App />)
    await waitFor(() => expect(quadProps.current).not.toBeNull())

    // Simulate a completed Ctrl/Cmd-drag: `onStaged` (stagedNames bookkeeping, what makes SaveBar
    // render) + `setStagedOffsets` (the visual position, this fix's own subject) -- re-applied on
    // every poll for the same mount-effect-race reason as the test above, until BOTH have visibly
    // taken (the Save bar is up AND stagedOffsets reads back what was just written).
    await waitFor(() => {
      act(() => {
        quadProps.current!.onStaged?.(['Light0'])
        quadProps.current!.setStagedOffsets({ Light0: [10, 0, 0] })
      })
      expect(screen.getByRole('button', { name: 'Discard' })).toBeTruthy()
      expect(quadProps.current!.stagedOffsets).toEqual({ Light0: [10, 0, 0] })
    })

    fireEvent.click(screen.getByRole('button', { name: 'Discard' }))

    await waitFor(() => expect(screen.queryByRole('button', { name: 'Discard' })).toBeNull())
    // This is the regression: before the fix, nothing ever called setStagedOffsets on Discard, so
    // the pane kept drawing the actor at the abandoned position indefinitely.
    //
    // Perf fix: `stagedNames` (what makes the Discard button disappear, above) and `stagedOffsets`
    // now settle at DIFFERENT times -- stagedNames synchronously, stagedOffsets only after
    // setStagedOffsets' throttled rAF commit (App.tsx's own doc comment) -- so this needs its own
    // waitFor rather than a bare assertion right after the button's.
    await waitFor(() => expect(quadProps.current!.stagedOffsets).toEqual({}))
  })
})

// Important 5, final review fix wave: a successful Save only cleared `stagedNames` -- the Inspector
// and any non-dragged pane kept showing the PRE-SAVE Location until the user manually clicked Load,
// and the GUI's own trunk write could trip its own file-watcher into a spurious "reload available"
// prompt. Fixed by routing Save's success through the SAME `runBuildAction('load', ...)` path the
// Load button itself uses.
describe('App: Save success refreshes the trunk view (Important 5)', () => {
  it('a clean Save triggers an actual Load afterward (not just a local state clear)', async () => {
    let loadCallCount = 0
    let saveCallCount = 0
    mockFetch((url, init) => {
      if (url.endsWith('/save') && init?.method === 'POST') {
        saveCallCount += 1
        return jsonResponse({ applied: ['Light0'], conflicts: [] })
      }
      if (url.endsWith('/load') && init?.method === 'POST') {
        loadCallCount += 1
        return jsonResponse({ status: 'ok', conflicts: [] })
      }
      return undefined
    })

    render(<App />)
    await waitFor(() => expect(quadProps.current).not.toBeNull())

    // Re-applied on every poll -- see the Critical 2 tests above for why a one-shot `act()` races
    // the mount-time `GET /staged` effect.
    await waitFor(() => {
      act(() => quadProps.current!.onStaged?.(['Light0']))
      expect(screen.getByRole('button', { name: 'Save' })).toBeTruthy()
    })

    fireEvent.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => expect(saveCallCount).toBe(1))
    // The regression: `onSaved` used to only call `setStagedNames(new Set())` -- no network call at
    // all, so the scene/atlas/lightmap/status stayed exactly as they were before the Save.
    await waitFor(() => expect(loadCallCount).toBe(1))
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Save' })).toBeNull())
  })
})

// Task 17: another window taking this session's claim (or the session being deleted) is signaled
// two ways -- a live `/ws` "superseded" push (the primary signal), and a 409 from any mutating
// call (the fallback, for whenever that push was lost). Both must show the SAME full-page takeover
// and leave the way back (Reload) open, not dead-end the tab.
describe('App: superseded takeover', () => {
  const TAKEOVER_TEXT = /This session is now open in another window\. Reload to keep using it here\./

  it('a WS "superseded" push shows the full-page takeover', async () => {
    mockFetch()
    render(<App />)
    await waitFor(() => expect(reloadSub.current).not.toBeNull())

    act(() => reloadSub.current!.onSuperseded())

    expect(screen.getByText(TAKEOVER_TEXT)).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Reload' })).toBeTruthy()
    // The rest of the page (the viewport, the toolbar) is gone -- a genuine takeover, not a banner
    // layered over the still-live scene.
    expect(screen.queryByTestId('viewport-stub')).toBeNull()
  })

  it('clicking Reload in the takeover re-resolves the session and returns to editing', async () => {
    mockFetch((url) => {
      if (url.endsWith(`/api/session/${SESSION_ID}`)) {
        return jsonResponse({
          id: SESSION_ID, level: LEVEL_NAME, created_at: '2026-09-22T00:00:00Z',
          last_active_at: '2026-09-22T00:00:02Z', claim_token: 'tok-reclaimed',
        })
      }
      return undefined
    })
    render(<App />)
    await waitFor(() => expect(reloadSub.current).not.toBeNull())

    act(() => reloadSub.current!.onSuperseded())
    await waitFor(() => expect(screen.getByText(TAKEOVER_TEXT)).toBeTruthy())

    fireEvent.click(screen.getByRole('button', { name: 'Reload' }))

    await waitFor(() => expect(screen.getByTestId('viewport-stub')).toBeTruthy())
    expect(screen.queryByText(TAKEOVER_TEXT)).toBeNull()
  })

  it('a 409 from Rebuild also shows the takeover (the fallback path)', async () => {
    mockFetch((url, init) => {
      if (url.endsWith('/rebuild') && init?.method === 'POST') {
        return jsonResponse({ error: 'session superseded' }, 409)
      }
      return undefined
    })
    render(<App />)
    await waitFor(() => expect(screen.getByTestId('viewport-stub')).toBeTruthy())

    fireEvent.click(screen.getByRole('button', { name: 'Rebuild' }))

    await waitFor(() => expect(screen.getByText(TAKEOVER_TEXT)).toBeTruthy())
    // Not the ordinary build-error banner -- the 409 is recognized specifically, not just any failure.
    expect(screen.queryByText(/session superseded/)).toBeNull()
  })

  it('a 409 from Save also shows the takeover (the fallback path, via SaveBar)', async () => {
    mockFetch((url, init) => {
      if (url.endsWith('/save') && init?.method === 'POST') {
        return jsonResponse({ error: 'session superseded' }, 409)
      }
      return undefined
    })
    render(<App />)
    await waitFor(() => expect(quadProps.current).not.toBeNull())

    await waitFor(() => {
      act(() => quadProps.current!.onStaged?.(['Light0']))
      expect(screen.getByRole('button', { name: 'Save' })).toBeTruthy()
    })

    fireEvent.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => expect(screen.getByText(TAKEOVER_TEXT)).toBeTruthy())
  })
})
