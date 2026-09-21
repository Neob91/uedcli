import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import App from './App'

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
    if (url.endsWith('/staged')) return jsonResponse({})
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
      if (url.endsWith('/staged')) return jsonResponse({})
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
