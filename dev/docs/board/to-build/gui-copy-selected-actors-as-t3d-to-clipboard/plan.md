# GUI: copy selected actors as T3D to clipboard — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Copy button (icon + label) next to the Inspector panel's selection header — the
single-actor name or the `{N} actors selected` line — that copies the current actor selection to
the clipboard as a `Begin Map…End Map` T3D snippet: CSG-ordered, reflecting any staged (unsaved)
`Location`, folder/label carriers included, faithfully pasteable into a real running UnrealEd 2.2.

**Architecture:** One new read-only, claim-free backend route,
`POST /api/session/{session_id}/t3d`, reusing `apply_staged_overlay` (staged-`Location` merge),
`query.resolve_actor_names` (batch name resolution), `Level.order` (CSG order), and a new thin
`emit.py` helper (`emit_map_with_carriers`, the carrier-including sibling of `emit_map`). The
frontend adds one API call (`api.ts`), one icon (`icons.tsx`), and a small `CopyButton` component
wired into both branches of `Inspector.tsx`'s `ActorSection`, threaded a `sessionId` prop it does
not have today.

**Tech Stack:** Python (FastAPI, `uedcli/serve/`), TypeScript/React (`web/src/`), Vitest, pytest.

**Spec:** `dev/docs/board/to-plan/gui-copy-selected-actors-as-t3d-to-clipboard/spec.md`

## Global Constraints

- No CLI verb — GUI-only (spec "Non-goals").
- No paste-in support — copy-out only (spec "Non-goals").
- A surface-only selection is ignored; the button acts on the actor selection only (spec
  "Non-goals").
- No pre-shift by `-32uu` — the snippet must NOT compensate for `EDIT PASTE`'s own drift (spec
  "Background" "Paste-drift: reproduce it, don't compensate").
- No Python exception reaches an HTTP caller unclassified — `query.resolve_actor_names`' bare
  `KeyError` must be caught and re-raised as `CommandError` before it can fall through to a generic
  500 (spec "Background" "Name resolution").
- A name repeated in the request's `actors` list is not an error — it names one actor, appearing
  once in the output (spec "API surface").

---

## File Structure

**Backend — modify:**
- `uedcli/emit.py` — add `emit_map_with_carriers`.
- `uedcli/serve/app.py` — add the `POST /api/session/{session_id}/t3d` route.

**Backend — test:**
- `uedcli/tests/test_emit.py` — `emit_map_with_carriers` unit tests.
- `uedcli/tests/test_serve_app.py` — the new route's tests (error cases + happy path).

**Frontend — modify:**
- `web/src/scene/icons.tsx` — add `CopyIcon`.
- `web/src/api.ts` — add `postCopyT3d`.
- `web/src/panels/Inspector.tsx` — add `CopyButton`, wire into both `ActorSection` branches, thread
  `sessionId` through `InspectorProps`.
- `web/src/panels/sidebarRegistry.ts` — thread `sessionId` through `BuildSidebarPanelsArgs` to the
  `Inspector` element it creates.
- `web/src/App.tsx` — pass `sessionId` into `buildSidebarPanels`.

**Frontend — test:**
- `web/src/panels/Inspector.test.tsx` — `CopyButton` render/click/feedback tests.
- `web/src/panels/sidebarRegistry.test.ts` — `sessionId` threading test.

---

## Backend Tasks

### Task 1: `emit.py` — `emit_map_with_carriers`

**Files:**
- Modify: `uedcli/emit.py`.
- Test: `uedcli/tests/test_emit.py`.

**Interfaces:**
- Consumes: `emit_actor_t3d` (already in `emit.py`).
- Produces: `emit_map_with_carriers(actors: list[Actor]) -> str`.

- [ ] **Step 1: Write the failing tests**

```python
# uedcli/tests/test_emit.py (append)
from uedcli.emit import emit_map_with_carriers
from uedcli.model import Actor


def test_emit_map_with_carriers_wraps_begin_end_map():
    actor = Actor(name="Light0", cls="Engine.Light", location=(0, 0, 0))
    out = emit_map_with_carriers([actor])
    assert out.startswith("Begin Map\n")
    assert out.endswith("End Map\n")


def test_emit_map_with_carriers_includes_folder_and_labels():
    actor = Actor(name="Light0", cls="Engine.Light", location=(0, 0, 0),
                  folder="Lights/Hallway", labels=frozenset({"needs_review"}))
    out = emit_map_with_carriers([actor])
    assert "uedcli-folder:" in out
    assert "uedcli-labels:" in out


def test_emit_map_with_carriers_matches_emit_actor_t3d_per_actor():
    from uedcli.emit import emit_actor_t3d
    a = Actor(name="Light0", cls="Engine.Light", location=(1, 2, 3))
    b = Actor(name="Light1", cls="Engine.Light", location=(4, 5, 6))
    out = emit_map_with_carriers([a, b])
    body = "\n".join(emit_actor_t3d(x).rstrip("\n") for x in [a, b])
    assert out == f"Begin Map\n{body}\nEnd Map\n"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `bin/test -k test_emit_map_with_carriers -v`
Expected: FAIL — `ImportError: cannot import name 'emit_map_with_carriers'`.

- [ ] **Step 3: Write `emit_map_with_carriers`**

Add directly below `emit_map` in `uedcli/emit.py`:

```python
def emit_map_with_carriers(actors: list[Actor]) -> str:
    """`Begin Map…End Map`-wrapped T3D, one actor per `emit_actor_t3d` (folder/label carriers
    included) — the GUI clipboard-copy's own writer. Distinct from `emit_map` (carrier-free, the
    trunk body + editor-import map's writer): this feature's clipboard output is read by a human
    (or pasted back into uedcli), not `MAP IMPORTADD`, so the carriers are wanted, not noise."""
    body = "\n".join(emit_actor_t3d(a).rstrip("\n") for a in actors)
    return f"Begin Map\n{body}\nEnd Map\n"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `bin/test -k test_emit_map_with_carriers -v`
Expected: PASS.

---

### Task 2: `app.py` — `POST /api/session/{session_id}/t3d`

**Files:**
- Modify: `uedcli/serve/app.py`.
- Test: `uedcli/tests/test_serve_app.py`.

**Interfaces:**
- Consumes: `_require_session`, `_current_scene_inputs`, `_get_trunk`, `_staging_store.read_staged`,
  `edits.apply_staged_overlay`, `query.resolve_actor_names`, `emit.emit_map_with_carriers`,
  `cli.errors.CommandError`.
- Produces: route `POST /api/session/{session_id}/t3d`, request `{"actors": [str, ...]}`, response
  `{"t3d": str}`.

- [ ] **Step 1: Write the failing tests**

Two tests need no trunk/UED22 corpus at all (a session lookup or a body check fails before the
route ever touches `_get_trunk`); the rest DO reach `_get_trunk`, so they need the same
`_require_ued22()` gate + `_scene_inputs` monkeypatch every other trunk-touching test in this file
uses — copy `test_scene_atlas_lightmap_never_trigger_a_build` (`test_serve_app.py:327-360`) as the
literal template for that scaffolding, not an invented `client`/`session_client` fixture (this file
has none — every test builds `TestClient(app)` and `sessions.create_session(...)` inline).

```python
# uedcli/tests/test_serve_app.py (append)

def test_session_t3d_unknown_session_422(tmp_path):
    root = tmp_path / "proj"
    _write_fixture_trunk(root, "TestLevel", [_cube_room_local()])
    project = SimpleNamespace(root=str(root), maps=None)
    app = create_app(project, "TestLevel")
    c = TestClient(app)
    resp = c.post("/api/session/does-not-exist/t3d", json={"actors": ["Room"]})
    assert resp.status_code == 422


def test_session_t3d_empty_actors_422(tmp_path):
    from uedcli.serve import sessions
    root = tmp_path / "proj"
    _write_fixture_trunk(root, "TestLevel", [_cube_room_local()])
    project = SimpleNamespace(root=str(root), maps=None)
    app = create_app(project, "TestLevel")
    c = TestClient(app)
    sess = sessions.create_session(app.state.sessions_root, "TestLevel")
    resp = c.post(f"/api/session/{sess.id}/t3d", json={"actors": []})
    assert resp.status_code == 422


def test_session_t3d_unknown_actor_names_422_names_all(tmp_path, monkeypatch):
    _require_ued22()
    from uedcli.serve import app as serve_app
    from uedcli.serve import sessions
    from uedcli.tests.test_serve_scene import DEFAULTS, _ued22_index

    root = tmp_path / "proj"
    _write_fixture_trunk(root, "TestLevel", [_cube_room_local()])
    project = SimpleNamespace(root=str(root), maps=None)
    monkeypatch.setattr(serve_app, "_scene_inputs", lambda p: ([], _ued22_index(), DEFAULTS))
    app = serve_app.create_app(project, "TestLevel")
    c = TestClient(app)
    sess = sessions.create_session(app.state.sessions_root, "TestLevel")

    resp = c.post(f"/api/session/{sess.id}/t3d",
                  json={"actors": ["NoSuchActor", "AlsoMissing"]})
    assert resp.status_code == 422
    assert "NoSuchActor" in resp.json()["error"]
    assert "AlsoMissing" in resp.json()["error"]


def test_session_t3d_happy_path_csg_order_dedup_no_bselected(tmp_path, monkeypatch):
    # Fixture trunk order is [ActorA, ActorB] (`_write_fixture_trunk` sets `level.order` from list
    # order) -- request them reversed AND with ActorA repeated, and assert the response still
    # comes back CSG-ordered with ActorA appearing once.
    _require_ued22()
    from uedcli.serve import app as serve_app
    from uedcli.serve import sessions
    from uedcli.tests.test_serve_scene import DEFAULTS, _ued22_index

    root = tmp_path / "proj"
    _write_fixture_trunk(root, "TestLevel",
                        [_cube_room_local("ActorA"), _cube_room_local("ActorB")])
    project = SimpleNamespace(root=str(root), maps=None)
    monkeypatch.setattr(serve_app, "_scene_inputs", lambda p: ([], _ued22_index(), DEFAULTS))
    app = serve_app.create_app(project, "TestLevel")
    c = TestClient(app)
    sess = sessions.create_session(app.state.sessions_root, "TestLevel")

    resp = c.post(f"/api/session/{sess.id}/t3d",
                  json={"actors": ["ActorB", "ActorA", "ActorA"]})
    assert resp.status_code == 200
    t3d = resp.json()["t3d"]
    assert t3d.startswith("Begin Map\n")
    assert t3d.endswith("End Map\n")
    assert t3d.index("Name=ActorA") < t3d.index("Name=ActorB")
    assert t3d.count("Begin Actor") == 2                # ActorA not double-emitted
    assert "bSelected" not in t3d


def test_session_t3d_reflects_staged_location(tmp_path, monkeypatch):
    _require_ued22()
    from uedcli.serve import app as serve_app
    from uedcli.serve import sessions
    from uedcli.tests.test_serve_scene import DEFAULTS, _ued22_index

    root = tmp_path / "proj"
    _write_fixture_trunk(root, "TestLevel", [_cube_room_local("ActorA")])
    project = SimpleNamespace(root=str(root), maps=None)
    monkeypatch.setattr(serve_app, "_scene_inputs", lambda p: ([], _ued22_index(), DEFAULTS))
    app = serve_app.create_app(project, "TestLevel")
    c = TestClient(app)
    sess = sessions.create_session(app.state.sessions_root, "TestLevel")
    token = app.state.claims.mint(sess.id)

    c.post(f"/api/session/{sess.id}/stage", json={"actors": {"ActorA": [999, 888, 777]}},
          headers={"X-Claim-Token": token})
    resp = c.post(f"/api/session/{sess.id}/t3d", json={"actors": ["ActorA"]})
    assert "Location=(X=999" in resp.json()["t3d"]
```

`_cube_room_local` is this file's own helper (`test_serve_app.py:216` already uses it with a name
argument) — confirm its exact name/signature before pasting; use `cube_room` from
`uedcli.tests.conftest` instead if `_cube_room_local` turns out private to a different test's scope.

- [ ] **Step 2: Run tests to verify they fail**

Run: `bin/test -k test_session_t3d -v`
Expected: FAIL — `404 Not Found` (route doesn't exist yet) for every test that reaches the route;
the two no-trunk tests fail the same way once past `_require_session`/the empty-body check.

- [ ] **Step 3: Write the route**

Add to `uedcli/serve/app.py`, near the other read-only `/api/session/{session_id}/...` routes
(`/scene`/`/atlas`/`/lightmap`), after imports gain `from ..emit import emit_map_with_carriers` and
`from .. import query` (add `query` to the existing `from .. import config, packages, trunk` import
if not already present — check first, `query` may already be imported elsewhere in this file):

```python
@app.post("/api/session/{session_id}/t3d")
def session_t3d(session_id: str, body: dict) -> dict:
    # Read-only: no claim-token check, matching /scene, /atlas, /lightmap -- this route mutates
    # nothing (spec "API surface" "Deliberate departure from house convention").
    session = _require_session(session_id)
    requested = body.get("actors") or []
    if not requested:
        raise CommandError("no actor names given")
    search_files, index, defaults = _current_scene_inputs(session.level)
    trunk_state = _get_trunk(session.level, search_files, index, defaults)
    staged = _staging_store.read_staged(session_id)
    level = edits.apply_staged_overlay(trunk_state.level, staged)
    try:
        resolved = set(query.resolve_actor_names(level, requested))
    except KeyError as exc:
        raise CommandError(str(exc.args[0])) from exc
    ordered = [n for n in level.order if n in resolved]
    return {"t3d": emit_map_with_carriers([level.actors[n] for n in ordered])}
```

Confirm `edits` is already imported in `app.py` (it is — `session_save`/`session_discard` already
use `edits.save_staged`/`edits.discard_staged`); add `from . import edits` only if missing.

- [ ] **Step 4: Run tests to verify they pass**

Run: `bin/test -k test_session_t3d -v`
Expected: PASS.

- [ ] **Step 5: Run the full backend suite**

Run: `bin/test`
Expected: PASS, no regressions.

---

## Frontend Tasks

### Task 3: `icons.tsx` — `CopyIcon`, `api.ts` — `postCopyT3d`

**Files:**
- Modify: `web/src/scene/icons.tsx`, `web/src/api.ts`.
- Test: none new (covered by Task 4's `CopyButton` tests, which exercise `postCopyT3d` via a
  mocked `fetch`).

- [ ] **Step 1: Add `CopyIcon` to `icons.tsx`**

Follow the file's existing `STROKE_PROPS` convention (see `WireframeIcon` for the pattern):

```tsx
export function CopyIcon() {
  return (
    <svg {...STROKE_PROPS} aria-hidden="true">
      <rect x="4" y="4" width="12" height="12" rx="1.5" />
      <path d="M9 4 V2.5 A1 1 0 0 1 10 1.5 H19.5 A1 1 0 0 1 20.5 2.5 V16 A1 1 0 0 1 19.5 17 H16" />
    </svg>
  )
}
```

- [ ] **Step 2: Add `postCopyT3d` to `api.ts`**

Follow the existing claim-free-GET siblings' pattern (`fetchScene`), but as a POST with a body,
following `postDiscard`'s body-shape convention — no `withClaimToken` (this route takes none):

```ts
/** Fetches a `Begin Map…End Map` T3D snippet for the given actors, in CSG order, reflecting any
 * staged Location (uedcli/serve/app.py `session_t3d`). Read-only: no claim token. */
export function postCopyT3d(sessionId: string, actors: string[]): Promise<{ t3d: string }> {
  return request(`/api/session/${encodeURIComponent(sessionId)}/t3d`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ actors }),
  })
}
```

---

### Task 4: `Inspector.tsx` — `CopyButton`, wired into both selection headers

**Files:**
- Modify: `web/src/panels/Inspector.tsx`, `web/src/panels/sidebarRegistry.ts`, `web/src/App.tsx`.
- Test: `web/src/panels/Inspector.test.tsx`, `web/src/panels/sidebarRegistry.test.ts`.

**Interfaces:**
- Consumes: `postCopyT3d` (Task 3), `CopyIcon` (Task 3), `navigator.clipboard.writeText`.
- Produces: `CopyButton` (local to `Inspector.tsx`, not exported — same visibility as
  `ActorSection`); `InspectorProps.sessionId: string | null`;
  `BuildSidebarPanelsArgs.sessionId: string | null` (see Step 3's note on why NOT plain `string`).

- [ ] **Step 1: Write the failing tests**

Add `vi`, `beforeEach` to this file's existing `vitest` import and `waitFor` to its existing
`@testing-library/react` import (today: `import { afterEach, describe, expect, it } from 'vitest'`
and `import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'` —
`Inspector.test.tsx:1-2`). Build actors with the file's own `fixtureActor` helper (line 138), not
bare undefined identifiers.

```tsx
// web/src/panels/Inspector.test.tsx (append)
import { postCopyT3d } from '../api'
vi.mock('../api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api')>()),
  postCopyT3d: vi.fn(),
}))

describe('CopyButton', () => {
  const actorA = fixtureActor({ name: 'ActorA' })
  const actorB = fixtureActor({ name: 'ActorB' })

  beforeEach(() => {
    vi.mocked(postCopyT3d).mockReset()
    Object.assign(navigator, { clipboard: { writeText: vi.fn().mockResolvedValue(undefined) } })
  })

  it('renders next to the single-actor header', () => {
    render(<Inspector selected={[actorA]} sessionId="s1" resolveClass={() => 'pending'} />)
    expect(screen.getByRole('button', { name: /copy/i })).toBeInTheDocument()
  })

  it('renders next to the multi-actor header', () => {
    render(<Inspector selected={[actorA, actorB]} sessionId="s1" resolveClass={() => 'pending'} />)
    expect(screen.getByRole('button', { name: /copy/i })).toBeInTheDocument()
  })

  it('posts the current selection and writes the result to the clipboard', async () => {
    vi.mocked(postCopyT3d).mockResolvedValue({ t3d: 'Begin Map\n...\nEnd Map\n' })
    render(<Inspector selected={[actorA, actorB]} sessionId="s1" resolveClass={() => 'pending'} />)
    fireEvent.click(screen.getByRole('button', { name: /copy/i }))
    await waitFor(() => expect(postCopyT3d).toHaveBeenCalledWith('s1', [actorA.name, actorB.name]))
    await waitFor(() =>
      expect(navigator.clipboard.writeText).toHaveBeenCalledWith('Begin Map\n...\nEnd Map\n'))
    expect(await screen.findByText(/copied/i)).toBeInTheDocument()
  })

  it('shows an error state when the request fails', async () => {
    vi.mocked(postCopyT3d).mockRejectedValue(new Error('boom'))
    render(<Inspector selected={[actorA]} sessionId="s1" resolveClass={() => 'pending'} />)
    fireEvent.click(screen.getByRole('button', { name: /copy/i }))
    expect(await screen.findByText(/failed|error/i)).toBeInTheDocument()
  })

  it('is disabled and does not call the endpoint when sessionId is null', () => {
    render(<Inspector selected={[actorA]} sessionId={null} resolveClass={() => 'pending'} />)
    const button = screen.getByRole('button', { name: /copy/i })
    expect(button).toBeDisabled()
    fireEvent.click(button)
    expect(postCopyT3d).not.toHaveBeenCalled()
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd web && npx vitest run Inspector -t CopyButton`
Expected: FAIL — no `Copy` button rendered yet, `sessionId` prop doesn't exist.

- [ ] **Step 3: Add `sessionId` to `InspectorProps`, add `CopyButton`, wire into both branches**

`InspectorProps` (near the top of `Inspector.tsx`, alongside `resolveClass`): add
`sessionId: string | null` — NOT plain `string`. `App.tsx`'s own `sessionId` (from `useSession`,
`SessionContext.tsx:19`) is `string | null` until the session resolve settles, and the
`sidebarPanels` `useMemo` that builds the `<Inspector>` element (`App.tsx:558-579`) runs BEFORE the
function's only null-check (`if (!sessionId || !level || ...)`, `App.tsx:625`) — moving the memo
after that check is illegal (conditional hook execution). So `sessionId` really can be `null` at
the point `buildSidebarPanels`/`Inspector` receive it, even though by the time anything renders it,
the "Loading…" branch has already returned instead. `CopyButton` treats `null` as "nothing to copy
into yet" (disabled, not omitted — see below) rather than fighting this with a cast or an assertion.

Thread `sessionId` into `ActorSection`'s own props the same way `resolveClass` already is, and into
the top-level `Inspector` function's destructured args. Add value imports
`import { postCopyT3d } from '../api'` and `import { CopyIcon } from '../scene/icons'` — today
`Inspector.tsx` only has a type-only import from `../api` and none from `icons.tsx`. Also extend
the existing `import { useState } from 'react'` (`Inspector.tsx:12`) to
`import { useEffect, useRef, useState } from 'react'` for `CopyButton`'s unmount-safe timer below.

A new required prop still breaks every EXISTING call site that doesn't pass it (its TYPE changed,
even though it's now nullable rather than defaulted) — `tsc -b` (the real `build` script,
`web/package.json`), not just Vitest, is what catches this, since Vitest transpiles per-file and
doesn't type-check unrelated call sites. Fix every one now:

- `Inspector.test.tsx`: every `render(<Inspector .../>)` call (there are ~5, including a
  `renderInspector` default helper if one exists) needs `sessionId="test-session"` added.
- `App.test.tsx`: any direct `<Inspector>` render (grep first — most of this file likely goes
  through `App`, not `Inspector` directly, in which case Task 4 Step 4's `App.tsx` fix covers it).

Place `CopyButton` directly above `ActorSection` in the file (this project's "helpers above their
callers" convention — `ActorSection` is `CopyButton`'s only caller):

```tsx
function CopyButton({ sessionId, names }: { sessionId: string | null; names: string[] }) {
  const [state, setState] = useState<'idle' | 'copied' | 'error'>('idle')
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  useEffect(() => () => { if (timerRef.current) clearTimeout(timerRef.current) }, [])
  const handleClick = async () => {
    if (sessionId === null) return   // unreachable once rendered (App.tsx's own Loading… guard),
                                      // but keeps this component correct on its own terms.
    try {
      const { t3d } = await postCopyT3d(sessionId, names)
      await navigator.clipboard.writeText(t3d)
      setState('copied')
    } catch {
      setState('error')
    } finally {
      // Cleared on unmount (above) so a click followed by a fast unmount (e.g. the selection
      // changes before the timer fires) never calls setState on an unmounted component.
      timerRef.current = setTimeout(() => setState('idle'), 2000)
    }
  }
  return (
    <button type="button" className="inspector-copy-button" onClick={handleClick}
            disabled={sessionId === null}>
      <CopyIcon />
      {state === 'idle' && 'Copy'}
      {state === 'copied' && 'Copied'}
      {state === 'error' && 'Copy failed'}
    </button>
  )
}
```

In `ActorSection`'s multi-actor branch (`actors.length > 1`), which already destructures
`sessionId` from its own props (added above, alongside `resolveClass`):

```tsx
<h2>{actors.length} actors selected</h2>
<CopyButton sessionId={sessionId} names={actors.map((a) => a.name)} />
```

In the single-actor branch, same file, same component:

```tsx
<h2>{actor.name}</h2>
<CopyButton sessionId={sessionId} names={[actor.name]} />
```

Both branches live in the same `ActorSection` function (`Inspector.tsx:209-`, the `actors.length >
1` early-return above vs. the single-actor code below it) — one `sessionId` prop on `ActorSection`
covers both call sites, nothing to thread twice.

(Thread `sessionId` down from `Inspector` into `ActorSection`'s existing props list.)

- [ ] **Step 4: Thread `sessionId` through `sidebarRegistry.ts` and `App.tsx`**

`sidebarRegistry.ts`: add `sessionId: string | null` to `BuildSidebarPanelsArgs`, pass it into the
`createElement(Inspector, {...})` call's prop object. `sidebarRegistry.test.ts` has ~7
`buildSidebarPanels({...})` calls — add `sessionId: 'test-session'` to each.

`App.tsx`: add `sessionId` to the `sidebarPanels` `useMemo`'s call to `buildSidebarPanels({...})`
(`App.tsx:558-579`) — it's already in scope as `string | null` (destructured from `useSession`,
same variable every other `/api/session/{sessionId}/...` call in this file already uses), so this
is a value that's ALREADY there, not a new one to compute; no cast needed now that the prop type is
nullable. Also add `sessionId` to that `useMemo`'s own dependency array (currently
`[selectedActors, selectedSurfaceInfos, hasUnseenSelection, scene, selectedNames,
handleOrgSelect, atlas, resolverTick]`, missing it) — without it, the `<Inspector>` element (and so
`CopyButton`'s `disabled` state) would not be guaranteed to recompute the instant `sessionId`
resolves from `null` to a real id, since nothing else in that dependency list is guaranteed to
change at exactly that moment. This also fixes any `App.test.tsx` call site that renders `<App>`
and reaches `Inspector` indirectly — nothing new to pass there.

Add one regression test for this dependency, modeled directly on the existing sibling regression
`App.test.tsx`'s `describe('App: Inspector props refresh once a pending class resolves', ...)`
(`App.test.tsx:867-943`, added when `resolverTick` was missing from this SAME dependency array —
that test's own comment explains the exact failure mode a missing dependency here causes:
`sidebarPanels`'s memoized `<Inspector>` element goes stale and never gets recreated). Render
`<App>` with a session id resolved from `null` to a real value (mock the session-resolve fetch the
way that test mocks `/scene`/package fetches), and assert the `Copy` button transitions from
disabled to enabled once `sessionId` resolves — without asserting on anything else that would also
change at that moment (so the test would actually fail if `sessionId` were dropped from the deps
array again, not pass for an unrelated reason).

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd web && npx vitest run Inspector sidebarRegistry App`
Expected: PASS.

- [ ] **Step 6: Type-check and run the full frontend suite**

Run: `cd web && npx tsc -b && npx vitest run`
Expected: PASS, no regressions. The `tsc -b` step is required here, not optional — it's the only
check in this plan that catches a missed `sessionId` call site (Vitest's per-file transpilation
does not type-check unrelated callers).

---

## Self-Review Notes (for whoever executes this plan)

- Task 2 Step 3's route body is a sketch, not a diff — re-check the exact current import list and
  helper names in `app.py` before pasting (this file changes often; Task 2's own "Interfaces"
  section names what to confirm still exists).
- `emit_map_with_carriers`'s test 3 (`matches_emit_actor_t3d_per_actor`) is the one guarding against
  the two functions drifting apart on a per-actor basis — keep it even if the other two look
  redundant with it.
