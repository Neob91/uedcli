# Plan — GUI Slice 2: quad layout, ortho views, organization panel, level picker

**Spec:** `dev/docs/board/to-plan/uedcli-human-gui/spec.md` ("P1 GUI — settled details") elaborated by
`dev/docs/board/to-spec/gui-slice-2-quad-layout-ortho-views-matching/spec.md` (read it — this plan
argues from its CURRENT text, post-review, including its new section 9). **Template:** Slice 1's plan
(`dev/docs/board/to-plan/uedcli-human-gui/plan.md`) for granularity/style; this one has more tasks
because Slice 2's scope is larger.

**For agentic workers:** follow `dev/docs/rules/building-features.md` (worktree, verify, review,
squash-merge) and `dev/docs/rules/tests.md`. Frontend commands run in `web/`; backend in the repo
root via `bin/test`.

Code read in full before writing this plan: `web/src/scene/Viewport3D.tsx`, `geometry.ts`,
`markers.ts`, `camera.ts`, `selection.ts`, `touchGesture.ts`, `web/src/panels/Inspector.tsx`,
`web/src/App.tsx`, `web/src/reload.ts`, `web/src/api.ts`, `web/package.json`, `uedcli/serve/app.py`,
`scene.py`, `watch.py`, `uedcli/preview_cache.py`, `uedcli/cli/level_sources.py`,
`uedcli/cli/commands/level.py`, `uedcli/folderlib.py`, the sibling
`gui-explicit-rebuild-pinned-build-state-mode/spec.md`, and the OTHER sibling
`uedcli-serve-share-one-in-process-scene-cache/plan.md` (its `_trunk_ref`/`_geometry_ref` holder-cell
shape, ~lines 137-183 — the correct source for Part 7's holder cell, see Task 25).

---

## Part 0 — Foundation refactor (prerequisite to everything below)

**Why first:** every later pane (3 ortho + perspective) must draw the SAME built geometry/materials/
textures/markers without rebuilding them per pane (spec §1) or re-uploading them 4x, AND must share
the same pointer-lock/capture/tap-vs-drag plumbing (spec §1's second-review addition) rather than a
second hand-rolled copy. Today all of that lives inside one `Viewport3D` instance (`useTextures`,
`useLightmapTexture`, `useMarkerTexture`, the `buildGeometryData` memo, `triangleOwners`,
`markerActors`, and ALL of `onPointerDown`/`onPointerMove`/`onPointerUp`/pointer-lock) alongside its
perspective-only camera. This must be hoisted out BEFORE any ortho camera exists, or ortho work would
be built against a component that's about to be restructured underneath it.

### Design decision: `@react-three/drei`'s `<View>` vs. four separate `<Canvas>` elements

**Decision: four separate `<Canvas>` elements. No new dependency.**

Reasoning (grounded in the code just read, not asserted):

- `<View>` renders multiple logical viewports into ONE shared WebGL context via scissor/viewport
  tricks, with drei's own tracking-`<div>` mechanism deciding where each view draws. That is the
  textbook fix for the GPU-memory half of this problem (one real upload, not four).
- But `Viewport3D.tsx`'s camera/interaction model is NOT drei's `OrbitControls` — it is fully
  hand-rolled: `onPointerDown`/`onPointerMove`/`onPointerUp` on the Canvas's own container div,
  `e.currentTarget.setPointerCapture`, and `requestPointerLock`/`exitPointerLock` scoped to that
  SAME container (see `Viewport3D.tsx` lines ~501-602). Pointer lock is a property of one real DOM
  element capturing the mouse; with `<View>` there is only ONE real `<canvas>` element in the DOM
  for all four logical viewports, so "which of the 4 logical views owns the lock/capture right now"
  would have to be reconciled by hand on top of drei's tracking-div indirection — a nontrivial
  integration with code that already works today, for a component (`OrthoViewport`, Part 1) that
  otherwise wants to be a near-verbatim sibling of the already-built, already-tested perspective
  pointer handling.
- The cost of 4 separate `<Canvas>`es is real but BOUNDED, not open-ended: each canvas's WebGL
  context re-uploads the SAME `BufferGeometry`/texture JS objects (built once, shared via context —
  Part 0 below), so the CPU-side cost (parsing, `buildGeometryData`) is paid once; only the GPU
  buffer/texture upload happens 4x. A Deus Ex / UE1 level's BSP+atlas geometry (this tool's own
  domain) is not in the regime where a 4x upload risks exhausting a modern desktop GPU's memory —
  no in-repo benchmark of a typical level's vertex/texture byte size was found to attach a hard
  number to this, which is exactly the missing data point the spec's "What is open" section
  anticipated; call this a judgment call made without hard numbers, not a measured one.
- Net: 4-`<Canvas>` avoids both the new dependency AND a real interaction-model integration risk,
  at a bounded, plausible-to-be-negligible GPU cost. If a real level later turns out to have
  surprisingly large geometry, this is the one decision in this plan worth revisiting first (see
  Open Questions).

### Task 1: extract the scene-building hooks, unchanged

**Files:** new `web/src/scene/sceneResources.ts`; modify `web/src/scene/Viewport3D.tsx` (import
instead of locally defining).

**Interfaces:** move `useTextures(atlas)`, `useLightmapTexture(lightmap)`, `useMarkerTexture()`, and
a new `useBuiltGeometry(scene, atlas, lightmap, textures, lightmapTexture)` wrapping the existing
`useMemo` (build `bufferGeometry`/`materials`/`triangleOwners` via `buildGeometryData`) + its dispose
`useEffect`, verbatim out of `Viewport3D.tsx` into `sceneResources.ts`. No behavior change.

**Test:** this is a pure move — the existing suite (`geometry.test.ts`, `camera.test.ts`,
`markers.test.ts`, `selection.test.ts`, `material.test.ts`, `Inspector.test.tsx`, `reload.test.ts`,
`api.test.ts`) is the regression net; there is no new *behavior* to pin with a fresh unit test for
the move itself. Add ONE new smoke test, `web/src/scene/sceneResources.test.tsx`, using
`@testing-library/react`'s `renderHook`: `useBuiltGeometry` over a small fixture `ScenePoly[]`
(reuse `geometry.test.ts`'s `quad()` helper) returns a `THREE.BufferGeometry` whose position count
matches calling `buildGeometryData` directly — this is a real assertion (catches a wiring mistake in
the extraction), not a placeholder.
- [ ] Write the smoke test, watch it FAIL (module doesn't exist yet).
- [ ] Move the hooks; make `Viewport3D.tsx` import them.
- [ ] PASS.

**Verify:** `npx vitest run`, `npx tsc -b` (both in `web/`).

**Commit:** `extract Viewport3D's texture/geometry hooks into scene/sceneResources.ts`

### Task 2: `SceneResourcesContext` — build once, share via context

**Files:** new `web/src/scene/SceneResourcesContext.tsx`.

**Interfaces:** `<SceneResourcesProvider scene atlas lightmap>{children}</SceneResourcesProvider>`
calls Task 1's hooks exactly once; `useSceneResourcesContext(): { bufferGeometry, materials,
triangleOwners, textures, markerTexture, markerActors }` for descendants, throwing a clear error
(naming the missing provider) if called outside one.

**Test failing-first:** render two SIBLING consumer components under one `SceneResourcesProvider`
and assert both receive the SAME `bufferGeometry` object (`Object.is` — reference equality), and
that a re-render of one consumer (state change unrelated to `scene`/`atlas`/`lightmap`) does not
change the OTHER consumer's `bufferGeometry` reference. This is the literal "share one built scene,
don't rebuild per pane" property (spec §1/§2). Write it first — with no context yet, there is nothing
to render, so it fails on import; then implement.
- [ ] FAIL → implement `SceneResourcesProvider`/`useSceneResourcesContext` → PASS.

**Verify:** `npx vitest run`, `npx tsc -b`.

**Commit:** `add SceneResourcesContext so multiple panes share one built geometry`

### Task 3: wire `Viewport3D` through the context (geometry/textures only — no behavior change)

**Files:** modify `web/src/scene/Viewport3D.tsx` (drop its local `useMemo`/hook calls for geometry/
textures/markers; read them from `useSceneResourcesContext()` instead — camera, pointer handling,
click-to-select, and the (still Task-9-pending) selection highlight are UNCHANGED in THIS task);
modify `web/src/App.tsx` to wrap `<Viewport3D>` in `<SceneResourcesProvider scene atlas lightmap>`.

**Interfaces:** `Viewport3DProps` unchanged (still `scene`/`atlas`/`lightmap`/`selectedName`/
`onSelectActor` — `scene` is still needed directly for actor metadata: `orbitPivot`, `selectionBox`,
`performTapSelect`'s AABB fallback).

**Note:** this task is deliberately scoped to geometry/texture sharing only. The pointer-lock/
capture/tap-vs-drag plumbing this same component owns is hoisted SEPARATELY, in Task 4 — splitting
them keeps each task's diff reviewable and matches the spec's own framing that geometry-sharing and
interaction-sharing are two different (if related) extractions, not one.

**Test:** no new unit test — this is a pure structural refactor of an already fully-tested component,
and inventing one would just re-test Task 1/2. Verified instead by (a) the full existing suite
passing unchanged, and (b) a manual smoke check per `building-features.md`: `uedcli serve
<fixture-level>` renders/navigates/selects exactly as before.

**Verify:** `npx vitest run`, `npx tsc -b`, manual smoke check above.

**Commit:** `wire Viewport3D through SceneResourcesContext (no behavior change)`

### Task 4: extract `useDragGesture` — shared pointer-lock/capture/tap plumbing

**Fixes spec §1's second-review finding directly: pointer-lock/capture, not just geometry, needs to
be shared (or an ortho copy explicitly justified) before Part 1 builds `OrthoViewport`. Decision made
here: EXTRACT a shared hook.** Reasoning: the mouse-only half of `Viewport3D.tsx`'s pointer handling
(`setPointerCapture` on down; lazy `requestPointerLock` on the first real drag movement, avoiding
`movementX/Y` screen-edge clamping; accumulating total drag distance; `isTap`-gated tap-vs-drag on
up, with `exitPointerLock`) is IDENTICAL machinery an ortho pane needs — only what a drag/tap MEANS
differs (dolly+turn/look/pan/orbit via `camera.ts` for Perspective; pan/zoom via `orthoCamera.ts`,
Task 5, for ortho). Touch handling stays Viewport3D-local and is NOT extracted here — ortho touch
parity is explicitly deferred (Task 6's own note, below), so generalizing touch now would be
speculative.

**Files:** new `web/src/scene/dragGesture.ts`, test `web/src/scene/dragGesture.test.ts`; modify
`web/src/scene/Viewport3D.tsx` (replace its inline mouse `onPointerDown`/`onPointerMove`/
`onPointerUp`/`onWheel`/`onContextMenu` with `useDragGesture`'s returned handlers; touch branches stay
inline, gated the same way they are today).

**Interfaces:**
```ts
export interface DragGestureCallbacks {
  onDrag: (dx: number, dy: number, buttons: number, altKey: boolean) => void
  onTap: (clientX: number, clientY: number, additive: boolean) => void
  onWheel?: (deltaY: number) => void
}
export function useDragGesture(callbacks: DragGestureCallbacks): {
  containerRef: MutableRefObject<HTMLDivElement | null>
  onPointerDown, onPointerMove, onPointerUp, onWheel, onContextMenu  // same handler shapes Viewport3D wires onto its container div today
}
```
`onTap`'s `additive` flag is `e.ctrlKey || e.metaKey` at pointerup — threaded through NOW so Part 3's
multi-select (Ctrl+click) doesn't need to touch this plumbing again; `Viewport3D`'s OWN `onTap`
callback ignores the flag until Part 3 rewires it (matches this plan's existing stage-interface-then-
behavior pattern, e.g. Task 19's `useBuildStatus` stub).

**Tap-suppression gate (review finding: the original extraction silently dropped this).** Today's
`onPointerUp` is `if (!d || e.button !== 0 || e.altKey) return` before calling `performTapSelect` —
an RMB release or an Alt+LMB release never taps, even under the movement threshold.
`useDragGesture` REPLICATES this exact gate INTERNALLY, before calling `onTap` — it is never
delegated to the caller via an extra `onTap` parameter, which would just relocate the same
silent-gap risk to every future call site. `onTap` fires only when `e.button === 0 && !e.altKey` AND
the accumulated movement stayed within `isTap`'s threshold; `DragGestureCallbacks.onTap`'s signature
stays `(clientX, clientY, additive) => void` — `button`/`altKey` are consumed inside the hook, never
exposed.

**Test failing-first:** drive the hook's returned handlers with synthetic pointer-event objects
(`setPointerCapture`/`requestPointerLock`/`exitPointerLock`/`document.pointerLockElement` stubbed as
no-ops/getters, same technique any DOM test in this repo needs for browser APIs jsdom doesn't
implement): a down→move(dx,dy)→up sequence below the tap threshold calls `onTap(x, y, false)` and
never `onDrag`... no — a move ALWAYS calls `onDrag` per movement (matching today's behavior: drag
callbacks fire on every move regardless of whether the gesture turns out to be a tap); the assertion
is that `onTap` fires on release only when the ACCUMULATED movement stayed within `isTap`'s
threshold, and carries the right `additive` flag from `ctrlKey`. A move exceeding the threshold
suppresses `onTap` on release (drag, not a tap) — the exact `isTap`-gated behavior `Viewport3D.tsx`
has today, now pinned as a regression test on the extracted hook instead of only implicitly on the
whole component. Two further cases pin the button/altKey gate above: a right-button
(`e.button === 2`) down-up sequence within the tap threshold never calls `onTap`; an Alt+left-button
down-up sequence within the tap threshold never calls `onTap` either — both must fail against a
naive extraction that drops the gate (button/altKey were previously invisible to the hook's
interface) and pass once the gate is replicated internally.

**Verify:** `npx vitest run`, `npx tsc -b`; manual: fixture level, confirm Perspective drag/tap/
pointer-lock feels identical to before this task (regression check — this task changes WHERE the
logic lives, not what it does).

**Commit:** `extract useDragGesture (pointer-lock/capture/tap, mouse-only) for perspective+ortho panes`

---

## Part 1 — Ortho cameras, quad layout, double-click maximize (spec §1)

### Task 5: pure ortho camera math

**Files:** new `web/src/scene/orthoCamera.ts`, test `web/src/scene/orthoCamera.test.ts`.

**Interfaces:** `export type OrthoAxis = 'top' | 'front' | 'side'` (Top looks down -Z, Front down -Y,
Side down -X — the world convention `camera.ts` already documents, Z-up); `orthoBasis(axis):
{ forward: Vec3; right: Vec3; up: Vec3 }`; `interface OrthoPose { center: Vec3; worldUnitsPerPixel:
number }`; `orthoPan(pose, axis, dxPx, dyPx): OrthoPose` (drag-pan, scaled by
`worldUnitsPerPixel` so pan speed is zoom-independent in screen terms); `orthoZoom(pose,
wheelDeltaY): OrthoPose`; `screenToWorld(pose, axis, viewportPx: {w,h}, screenX, screenY): Vec3`
(projects a screen point onto the axis's world plane through `pose.center` — this doubles as the
click-to-select ray origin/direction builder AND the cursor-coordinate readout, Part 8).

**Test failing-first:** known-input table tests mirroring `camera.test.ts`'s style — a Top-axis pan
of `(dx, dy)` moves `center`'s X/Y by the expected screen-to-world-scaled delta and never touches Z;
`screenToWorld` at the exact viewport center returns `pose.center`; `orthoZoom` halves/doubles
`worldUnitsPerPixel` as expected; each axis's `orthoBasis` matches the stated look direction.

**Verify:** `npx vitest run`.

**Commit:** `add pure ortho camera pan/zoom/projection math`

### Task 6: `OrthoViewport.tsx`

**Files:** new `web/src/scene/OrthoViewport.tsx`.

**Interfaces:** `<OrthoViewport axis selectedName onSelectActor />` — consumes
`useSceneResourcesContext()` for geometry/materials/markers (no local rebuild) and Task 4's
`useDragGesture` for pan/zoom/tap plumbing (its `onDrag` branches on `buttons` per the main spec's
ortho "Camera" section — drag-pan, scroll + both-button-drag zoom — via `orthoCamera.ts`'s
`orthoPan`/`orthoZoom`; its `onTap` feeds an ortho ray from `screenToWorld` into
`resolveHitActor`/`pickActor`, unchanged); click-to-select reuses `selection.ts` verbatim.

**This is the plan's explicit answer to spec §1's "state explicitly which one it is" requirement:
extraction (Task 4), not a second hand-rolled pointer-lock/capture copy.**

**Touch/gesture parity (spec §1's second-review finding, explicitly resolved here): DEFERRED,
desktop-first.** `touchGesture.ts`'s one-finger-rotate / two-finger-pan-zoom convention is a
PERSPECTIVE-specific interpretation (`Viewport3D.tsx`'s touch branches: one finger "rotates in
place," matching mobile-3D-viewer conventions) — an ortho pane's touch equivalent (one/two-finger
pan+zoom, no "rotate" concept for a fixed-axis camera) is a different design, not a reuse, and is not
specified anywhere in the main spec or this one. `OrthoViewport` ships MOUSE-ONLY input in this
slice; touch on ortho panes is a follow-up, not silently unstated.

**Test failing-first:** confirm `resolveHitActor`/`pickActor` — written against a generic `Ray`
(origin+direction), never assuming perspective divergence — resolve correctly for a PARALLEL
(orthographic) ray too: a new case in `selection.test.ts` with a ray whose direction is the SAME
axis-aligned vector regardless of screen position (the ortho case) still finds the nearest AABB hit.
If this passes with zero changes to `selection.ts` (expected, since `pickActor`'s slab test and
`resolveHitActor`'s triangle lookup are ray-shape-agnostic), say so plainly in the test's own comment
— it is a confirming regression test, not invented busywork.

**Verify:** `npx vitest run`, `npx tsc -b`; manual: fixture level, pan/zoom/click-select in one ortho
pane, confirm correct selection.

**Commit:** `add OrthoViewport (pan/zoom/select through an ortho camera, desktop input only)`

### Task 7: `QuadLayout.tsx` + maximize/restore state

**Files:** new `web/src/scene/paneLayout.ts` (pure), test `web/src/scene/paneLayout.test.ts`; new
`web/src/scene/QuadLayout.tsx`.

**Interfaces:** `type PaneId = 'perspective' | 'top' | 'front' | 'side'`; `toggleMaximize(current:
PaneId | null, clicked: PaneId): PaneId | null` — double-click the currently-maximized pane restores
the grid (`null`); double-click a DIFFERENT pane while one is maximized switches the maximized pane
to the clicked one (a judgment call — the spec doesn't say; see Open Questions); double-click any
pane when none is maximized maximizes it. `<QuadLayout scene atlas lightmap selectedName
onSelectActor />` wraps all four panes in ONE `SceneResourcesProvider` and renders a 2x2 CSS grid,
toggling a CSS class / `[hidden]` on non-maximized panes when one is maximized. **This task's
`selectedName`/`onSelectActor` are the single-actor baseline; Part 3 (Task 13) upgrades them to a
multi-actor `selectedNames` set — not designed twice, just staged.**

**Test failing-first:** `paneLayout.test.ts` covers `toggleMaximize`'s three cases above.

The grid/maximize RENDERING itself is pure layout CSS — explicitly not meaningfully unit-testable.
Manual verification instead: load the fixture level, double-click each of the four panes in turn,
confirm it fills the area and a second double-click restores the 2x2 grid with no stale-canvas-size
glitch (a `<Canvas>` resized by CSS needs its renderer to pick up the new size — R3F does this via
`ResizeObserver` automatically, but confirm it live rather than assume it).

**Verify:** `npx vitest run` (paneLayout only), `npx tsc -b`; manual maximize/restore check above.

**Commit:** `add QuadLayout (2x2 grid, double-click maximize/restore)`

### Task 8: wire `QuadLayout` into the app

**Files:** modify `web/src/App.tsx` — replace the single `<Viewport3D>` with `<QuadLayout>`, keeping
the already-lifted `selectedName`/`setSelectedName` shared across all four panes (this is also the
plumbing Part 3's cross-pane multi-select-highlight requirement rides on, once it upgrades this state
to a set).

**Test:** none new (integration wiring). Manual: `uedcli serve <fixture>` shows all four panes, none
crash. Full cross-pane HIGHLIGHT parity (single AND multi-select) is verified once Part 3 and the
final verification task (31) land.

**Verify:** `npx vitest run`, `npx tsc -b`, manual check above.

**Commit:** `wire QuadLayout into App`

---

## Part 2 — Ortho brush CSG-coloring for ALL brushes (spec §2)

### Task 9: extract `buildBrushRings` (every-brush vs. selected-only)

**Note:** this task's `selectedName: string | null` is the SINGLE-selection baseline. Part 3 (Task
14) generalizes it to a `selectedNames: ReadonlySet<string>` for multi-select — build this task's
shape first; it's the foundation Part 3 extends, not a dead end.

**Files:** new `web/src/scene/brushRings.ts`, test `web/src/scene/brushRings.test.ts`.

**Interfaces:** `interface BrushRing { actorName: string; color: [number, number, number]; verts:
number[]; bold: boolean }`; `buildBrushRings(actors: SceneActor[], selectedName: string | null, mode:
'csg-all' | 'selected-only'): BrushRing[]`. `'selected-only'` reproduces TODAY's Perspective-pane
behavior byte-for-byte (exactly one ring, for the selected brush, always `bold: true`) — a regression
pin. `'csg-all'` is the new requirement: one ring per brush actor in its own `brush.color`, `bold:
true` only on the selected one. Generalized with a mode flag now (not hardcoded "ortho-only") so
Part 4's wireframe-mode task can also flip Perspective to `'csg-all'` in wireframe mode without a
second implementation — spec §2's "matches `actor diagram`" framing suggests CSG-all should apply
wherever wireframe is the active representation, not only in ortho panes (flagged in Open Questions
for confirmation).

**Test failing-first:** 3 brush actors with distinct `brush.color`, one selected — `'csg-all'`
returns 3 rings, correct colors, only the selected one `bold`; `'selected-only'` returns exactly 1
ring, for the selected actor only, matching today's `SelectionHighlight` output shape.

**Verify:** `npx vitest run`.

**Commit:** `extract buildBrushRings (every-brush vs selected-only CSG ring logic)`

### Task 10: verify (and if needed, fix) the bolder-line WebGL risk

This task is a VERIFICATION step with a conditional implementation — per the spec, do not assume
"reuse `BrushRingOutline` verbatim" solves this without checking in a real browser (WebGL line width
is invisible to jsdom/unit tests).

**Files:** new `web/src/scene/BrushOutlines.tsx` (replaces `Viewport3D.tsx`'s inline
`SelectionHighlight`/`BrushRingOutline`, consuming `buildBrushRings`), built first with the
straightforward port of today's `<lineLoop><lineBasicMaterial linewidth={2} /></lineLoop>` per ring.

**Step A — real-browser check (not a unit test):** run `uedcli serve <fixture>` in an actual
Chromium-family browser. Select a brush; visually compare the selected ring's on-screen pixel width
against an unselected ring at the same camera distance/zoom (screenshot before/after selecting).
Confirm the selected ring is VISIBLY thicker, not merely a different color.

**Step B — fallback (only if Step A shows no visible width difference):** swap `bold` rings to
`Line2`/`LineMaterial` from three.js's `lines` addon — `three/examples/jsm/lines/*`, already inside
the pinned `three` package (a deeper import path, NOT a new npm dependency), which supports real
pixel width via a `resolution` uniform that must track the canvas's pixel size on resize (a real
added-complexity cost if this path triggers — call it out in the commit if it does). Non-`bold` rings
stay on the cheap `LineBasicMaterial` path; they don't need width.

**Test:** no unit test can observe rendered line width (that's exactly the untestable half); Task 9
already covers which ring is tagged `bold` (the testable half). This task's "test" IS the Step A
manual check.

**Verify:** the Step A browser comparison (Step B's comparison too, if triggered); `npx tsc -b`.

**Commit:** `add BrushOutlines (CSG-colored rings for every brush)` — amend the message to note
whether Step B's `Line2` fallback was needed, based on the actual Step A finding.

### Task 11: wire `BrushOutlines` into every pane

**Files:** modify `web/src/scene/OrthoViewport.tsx` (mount `BrushOutlines` with `mode='csg-all'` —
ortho panes had no brush-highlight drawing before this); modify `web/src/scene/Viewport3D.tsx`
(replace the old inline `SelectionHighlight` with `BrushOutlines` `mode='selected-only'`, preserving
today's Perspective look exactly); delete the now-dead `SelectionHighlight`/`BrushRingOutline` from
`Viewport3D.tsx`.

**Test:** existing selection-related tests continue to pass unchanged (regression pin for
Perspective's preserved look); no new test beyond Task 9/10's.

**Verify:** `npx vitest run`, `npx tsc -b`; manual: fixture level, select a brush, confirm all three
ortho panes now show every brush wireframed in its CSG color with the selected one bold, Perspective
unchanged from before this task.

**Commit:** `draw CSG-colored brush rings in ortho panes; route Perspective through BrushOutlines`

---

## Part 3 — Multi-select, frame, deselect, cross-pane consistency (spec §9)

**New Part, added in this correction pass — fixes a real gap: neither the original spec nor plan
mentioned the main GUI spec's settled "Selection & inspector"/"Keybindings" requirements
(Ctrl+tap/Ctrl+click multi-select, `F` frame, `Esc` deselect, one selection highlighted identically
across all four panes) despite Slice 2's own goal being "completes the P1 viewer."**

**Scope decision (spec §9): Ctrl+add-to-selection, `F`, `Esc`, and multi-actor cross-pane highlight
are IN SCOPE below — they compose out of machinery this plan already builds (Task 4's drag hook,
Task 9's `buildBrushRings`) with no new interaction-model decision needed. Ortho MARQUEE-select is
explicitly DEFERRED** to `dev/docs/board/inbox/ortho-marquee-drag-select-rubber-band-multi/` — it
needs a genuinely new screen-projection hit-test mechanism AND collides with the already-settled
ortho "drag-pan" binding (main spec, "Camera") in a way that needs an owner ruling, not a plan-time
guess. This is a deliberate, documented partial scope cut, not a silent omission — see this plan's
Revision history.

### Task 12: `selectionSet.ts` — pure multi-select membership logic

**Files:** new `web/src/scene/selectionSet.ts`, test `web/src/scene/selectionSet.test.ts`.

**Interfaces:** `toggleSelection(current: ReadonlySet<string>, name: string, additive: boolean):
Set<string>` — `additive=false` always REPLACES the set with exactly `{name}` (a plain tap's
semantics, regardless of what was previously selected); `additive=true` toggles `name`'s membership
in `current` (add if absent, remove if present — Ctrl+tap's "multi-selects" semantics, spec §9).
`clearSelection(): Set<string>` — always `new Set()` (trivial, but named so callers read as intent,
matching `Esc`'s own semantics rather than inlining `new Set()` at each call site).

**Test failing-first:** `additive=false` yields `{name}` regardless of the starting set (including
when `name` was already the sole member — a re-tap is a no-op reselect, not a toggle-off);
`additive=true` adds `name` when absent; `additive=true` removes `name` when present, including when
it's the LAST member (yields an empty set, not `null` — `Esc`, not a Ctrl-toggle, is the explicit
"nothing selected" action, but toggling off the last item is still a legal empty result).

**Verify:** `npx vitest run`.

**Commit:** `add selectionSet (toggle/replace/clear multi-select membership logic)`

### Task 13: lift `selectedName` → `selectedNames` across every pane

**Files:** modify `web/src/App.tsx`, `web/src/scene/QuadLayout.tsx`, `web/src/scene/Viewport3D.tsx`,
`web/src/scene/OrthoViewport.tsx`.

**Interfaces:** `Viewport3DProps`/`OrthoViewportProps`'s `selectedName?: string | null` →
`selectedNames: ReadonlySet<string>`; `onSelectActor?: (name: string | null) => void` →
`onSelectActor: (name: string, additive: boolean) => void`. `App.tsx` holds `selectedNames:
Set<string>` state and passes `(name, additive) => setSelectedNames((s) => toggleSelection(s, name,
additive))` down through `QuadLayout`. `performTapSelect` (Viewport3D) and its ortho equivalent
(OrthoViewport) now call `onSelectActor(hitActor.name, additive)` where `additive` is the flag Task
4's `useDragGesture.onTap` already threads through.

**Deliberate behavior change, called out explicitly (not a silent regression): a tap/click that hits
NOTHING now calls neither `onSelectActor` nor anything else — it no longer clears the selection.**
Today's code calls `onSelectActor(null)` on a miss; spec §9 states `Esc` is the deselect action and
neither settled main-spec paragraph mentions click-away-to-deselect, so a miss becomes a true no-op
(the selection is unaffected) and `Esc` (Task 15) becomes the ONLY way to clear it.

**Test failing-first:** `Viewport3D`'s tap handler — a plain tap on a hit actor calls
`onSelectActor(name, false)`; a Ctrl-tap on a hit actor calls `onSelectActor(name, true)`; a tap that
hits nothing calls `onSelectActor` zero times (pins the deliberate behavior change above). Mirror all
three cases for `OrthoViewport`.

**Verify:** `npx vitest run`, `npx tsc -b`.

**Commit:** `lift selectedName to a selectedNames set (Ctrl+tap/Ctrl+click add-to-selection)`

### Task 14: multi-actor highlight across every pane

**Files:** modify `web/src/scene/brushRings.ts` (`buildBrushRings(actors, selectedNames:
ReadonlySet<string>, mode)` — `'selected-only'` now returns ONE ring per selected BRUSH actor, ALL
`bold: true`; the single-selection case (`selectedNames.size === 1`) must reproduce Task 9's original
one-ring output exactly — a regression pin, not a new shape); modify `web/src/scene/BrushOutlines.tsx`
(prop rename); modify `web/src/scene/Viewport3D.tsx`/`OrthoViewport.tsx` (the non-brush selection
fallback — today's single `box3Helper` — becomes one `box3Helper` per selected non-brush actor).

**Test failing-first:** `buildBrushRings` with 2 selected brush actors (of 3) returns 2 bold rings,
correctly colored; 1 selected reproduces Task 9's exact single-ring shape (regression pin); 0
selected returns 0 rings (today's "no selection" case, regression pin).

**Verify:** `npx vitest run`, `npx tsc -b`; manual: fixture level, Ctrl-click a second brush, confirm
BOTH highlight identically (bold) in every pane simultaneously.

**Commit:** `draw one highlight ring/box per selected actor (multi-select cross-pane highlight)`

### Task 15: `frame.ts`/`unionBBox` + `F`/`Esc` keybinds

**Files:** new `web/src/scene/frame.ts`, test `web/src/scene/frame.test.ts`; new
`web/src/scene/SelectionKeys.tsx`; modify `web/src/scene/QuadLayout.tsx` (own a `framedBBox` state
and a `frameActors(names: ReadonlySet<string>)` callback passed to every pane: Perspective retargets
`orbitPivot` to the bbox center and backs the camera off far enough to fit it; ortho recenters
`OrthoPose.center` on the bbox and sets `worldUnitsPerPixel` to fit its extent on that axis).

**Interfaces:** `unionBBox(actors: SceneActor[]): { lo: Vec3; hi: Vec3 } | null`.
`<SelectionKeys selectedNames onFrame onDeselect />` — a window-keydown listener mirroring
`Viewport3D.tsx`'s `FlyKeys` component pattern (same `isTypingTarget` guard against stealing
keystrokes from a focused text input): `F` calls `onFrame(selectedNames)` (a no-op if empty); `Esc`
calls `onDeselect()` (`selectionSet.ts`'s `clearSelection`).

**Reused, not re-specified, by Part 6's org panel:** `unionBBox`/`frameActors` are built HERE,
ahead of Part 6, specifically so the org panel's folder-node framing (spec §5) reuses this exact
mechanism instead of inventing a second one.

**Test failing-first:** `unionBBox([]) === null`; a two-actor union matches the box enclosing both
(known-input check). `SelectionKeys`: pressing `F` while a text input has focus is a no-op; pressing
`F` elsewhere calls `onFrame` with the current `selectedNames`; `Esc` calls `onDeselect`
unconditionally (even outside a text input — matches the main spec's plain, unmodified `Esc`
binding).

**Verify:** `npx vitest run`, `npx tsc -b`; manual: select 2 actors, press `F`, confirm all four panes
recenter/refit on their union bbox; press `Esc`, confirm the highlight clears in every pane.

**Commit:** `add unionBBox/frame + F-frame/Esc-deselect keybinds`

### Task 16: Inspector multi-select summary

**Files:** modify `web/src/panels/Inspector.tsx`, `web/src/panels/Inspector.test.tsx`.

**Interfaces:** `InspectorProps`'s `actor: SceneActor | null` → `selected: SceneActor[]`. 0 selected →
today's "No selection" (same `data-testid="inspector-empty"`); exactly 1 → today's full detail view,
UNCHANGED (same markup/testids — existing `Inspector.test.tsx` assertions keep passing against the
new prop shape with no behavior change); 2+ → a lightweight summary: an actor count
(`"<N> actors selected"`) and the list of selected names. **Judgment call, flagged in Open
Questions:** neither settled main-spec paragraph defines the N-selected inspector view; this is the
simplest thing that satisfies "highlighted ... + inspector" without guessing at a multi-actor
property-diff view that isn't asked for anywhere.

**Test failing-first:** `selected=[]` → "No selection" (regression pin); `selected=[oneActor]` →
today's existing assertions, unchanged (regression pin, prop-shape-only change); `selected=[a, b, c]`
→ renders "3 actors selected" and all three names.

**Verify:** `npx vitest run`, `npx tsc -b`.

**Commit:** `add Inspector multi-select summary (N actors selected)`

### Task 17: cross-pane selection-consistency test — the spec's own acceptance criterion, automated

**Fixes the review's issue 4 directly: the spec's stated acceptance criterion ("a brush selected in
any pane highlights identically in all four panes") had only a manual verification step, no
automated test.**

**Files:** new `web/src/scene/QuadLayout.test.tsx`.

**Approach, matching this codebase's established RTL pattern (`Inspector.test.tsx`: render, query by
testid/role, assert):** `vi.mock('./Viewport3D')` and `vi.mock('./OrthoViewport')` with lightweight
stub components that (a) render their received `selectedNames` into the DOM as text under a
`data-testid` keyed by pane id (e.g. `pane-top-selected`, `pane-perspective-selected`) and (b) expose
a button that calls their own `onSelectActor('ActorA', false)` prop — simulating "a selection
originating from any one pane" without needing a real WebGL context (R3F's `Canvas` has no jsdom
support in this repo today, confirmed by grepping for an existing Canvas-in-test pattern and finding
none — mocking the pane components at this boundary is the right altitude: `QuadLayout`'s job is
PROP PLUMBING, not rendering, so this tests exactly that job).

Render `<QuadLayout>` with a small fixture scene (2-3 actors); click the mocked stub's select-button
for ONE pane (e.g. `top`); assert ALL FOUR panes' stub-rendered `selectedNames` text now reads
`ActorA` — proving `QuadLayout` threads one lifted selection state to every pane, not four
independent ones. This is the automated half of the spec's acceptance criterion; the live-pixel half
(actual bold/CSG-color rendering) stays a manual check (Task 32).

**Test:** this task IS the test. If it fails, that's a real Task 13/14 wiring bug — fix it here, not
a pre-accepted red.

**Verify:** `npx vitest run`.

**Commit:** `add QuadLayout cross-pane selection-consistency test (mocked panes)`

---

## Part 4 — Shading modes per pane (spec §3)

**External dependency, called out per instructions:** textured-unlit / flat / textured+lit require a
"solved build" signal owned by the SEPARATE, not-yet-built
`gui-explicit-rebuild-pinned-build-state-mode` item — its own spec explicitly defers "where the
rebuild/load status gets exposed" to planning (its "What is open" section), so this plan cannot wire
against a real endpoint that doesn't exist yet. Wireframe alone needs no such signal (renders from
`brush.polys`/`ScenePoly` data directly, per that item's own "wireframe always available" rule).

### Task 18: per-pane shading-mode state + gating logic

**Files:** new `web/src/scene/shadingMode.ts`, test `web/src/scene/shadingMode.test.ts`.

**Interfaces:** `type ShadingMode = 'wireframe' | 'unlit' | 'flat' | 'lit'`; `isModeAvailable(mode,
buildSolved: boolean): boolean` (wireframe always `true`; the other three require `buildSolved`);
`resolveEffectiveMode(requested, buildSolved): ShadingMode` (falls back to `'wireframe'` if the
requested mode isn't available — e.g. a pane left on `'lit'` before a level with no solved build
loads).

**Test failing-first:** `isModeAvailable('wireframe', false) === true`; the other three `=== false`
when `buildSolved` is false, `=== true` when true; `resolveEffectiveMode` falls back correctly in
both directions.

**Verify:** `npx vitest run`.

**Commit:** `add per-pane shading-mode state and solved-build gating logic`

### Task 19: stub the `buildSolved` signal

**Files:** new `web/src/scene/buildStatus.ts` — one hook, `useBuildStatus(level: string): boolean`,
body returns `true` unconditionally today, with a comment naming the sibling board item and pointing
at Task 18's `isModeAvailable` as the one call site to change once that item's real endpoint exists;
modify `web/src/App.tsx` to call it and thread `buildSolved` down to `QuadLayout`.

**Test:** none meaningful for a hardcoded stub — stated explicitly rather than faked.

**Verify:** `npx tsc -b`.

**Commit:** `stub useBuildStatus(true) pending the explicit-rebuild item's real signal`

### Task 20: mode selector + `1`-`4` keybinds (focused pane)

**Files:** modify `web/src/scene/QuadLayout.tsx` (add `focusedPane: PaneId` state, set on
pointerdown inside any pane; add per-pane `mode: Record<PaneId, ShadingMode>` state); modify
`web/src/scene/shadingMode.ts` (add `applyModeKey(current: Record<PaneId, ShadingMode>, focused:
PaneId, key: '1'|'2'|'3'|'4', buildSolved: boolean): Record<PaneId, ShadingMode>`); modify
`OrthoViewport.tsx`/`Viewport3D.tsx` to accept a `mode` prop: `'wireframe'` draws ONLY
`BrushOutlines(mode='csg-all')` (no solid mesh); `'unlit'`/`'lit'` draw the existing solid mesh as
today; `'flat'` renders IDENTICALLY to `'unlit'` for now — the main spec's own "Also open" section
says "flat"'s exact definition isn't pinned down, so this is a placeholder, not a silent redefinition
(flagged in Open Questions).

**Test failing-first:** `applyModeKey` — pressing `'3'` while `focused==='top'` changes only `top`'s
mode to `'flat'`; is a no-op (state unchanged) when `resolveEffectiveMode` would fall back (e.g.
`buildSolved=false` and the requested mode isn't wireframe).

**Verify:** `npx vitest run`, `npx tsc -b`; manual: click a pane to focus it, press `1`-`4`, confirm
only that pane's mode changes. (Full gating behavior can only be manually verified once Task 19's
stub is replaced by the real signal — noted, not faked here.)

**Commit:** `add per-pane shading mode selection + 1-4 keybinds (focused pane)`

---

## Part 5 — Non-brush actor meshes in ortho (spec §4)

### Task 21: verification checkpoint (no new mechanism expected)

Per the spec, this needs no new code: once `OrthoViewport` (Task 6) draws the shared
`markerActors`/sprite group sourced from `SceneResourcesContext`, non-brush actors already render in
every ortho pane through the ortho camera, same objects as Perspective.

**Verify (manual only, no automated test — there is no new code to test):** load a fixture level
with at least one point actor (light/trigger) and one mesh actor; confirm all three ortho panes AND
Perspective show it identically (sprite/marker or mesh triangles), with world-space (not
screen-clamped) size that scales correctly as ortho zoom changes.

If this passes with zero code changes (expected), record that here rather than manufacture a task.
If a real gap turns up (e.g. the fallback dot marker's fixed `MARKER_SIZE` reading illegibly small/
large at extreme ortho zoom), split it into its own small task/commit at that time — its shape isn't
known until the gap is actually seen, so it is not pre-specified here.

**Commit:** none expected for this checkpoint itself.

---

## Part 6 — Organization panel (spec §5)

### Task 22: pure folder-tree + label-facet + find filter logic

Folder paths are `.`-segmented (confirmed by reading `uedcli/folderlib.py` directly — case-insensitive,
segment-boundary-prefix subtree matching, `*`/`**` globstar query tokens; NOT assumed). Port
`folderlib.py`'s NORMATIVE match algorithm to TypeScript (the client has no Python runtime) rather
than re-deriving it — a faithful port, not a fresh design.

**Files:** new `web/src/scene/orgFilter.ts`, test `web/src/scene/orgFilter.test.ts`.

**Interfaces:** `interface FolderNode { path: string | null; children: FolderNode[]; actors:
SceneActor[] }`; `buildFolderTree(actors: SceneActor[]): FolderNode` (root has a `(no folder)` bucket
for `folder === null`, matching `actor find --no-folder`'s "only way to query them" story translated
to a UI bucket rather than a glob); `matchesLabelFacets(actor, activeLabels: ReadonlySet<string>):
boolean` (OR-combined; empty set matches everything); `interface FindQuery { name?: string; cls?:
string; folder?: string; label?: string }`; `matchesFind(actor, query): boolean` — `name`/`cls`:
whole-name-anchored, case-insensitive fnmatch-style glob (port, don't shell out); `folder`: bare =
subtree, `*` = one segment, `**` = any depth (the asymmetry `folderlib.py` documents); `label`: `*`
is the only wildcard.

**Test failing-first:** fnmatch-style name glob matches/doesn't (`'Helper*'` etc.); folder
subtree-vs-glob asymmetry (`'castle'` matches the whole subtree, `'**.roof'` matches only `roof`
nodes, not their contents); `(no folder)`/`(no label)` buckets reachable only via their own
predicate, never via a glob (mirrors the CLI's mutual-exclusivity).

**Verify:** `npx vitest run`.

**Commit:** `add client-side folder-tree/label-facet/find filter logic (mirrors actor find)`

### Task 23: `OrgPanel.tsx` — folder-node selection, reconciled with multi-select

**Resolves the review's issue 5 directly.** The original version of this task justified
camera-framing-only against spec §2 without engaging spec §5's "multi-actor set instead of one"
language, because no multi-actor selection model existed yet in this plan. Part 3 now provides one
(`selectedNames`, `selectionSet.ts`, `unionBBox`/`frameActors` from Task 15) — so this task can (and
per spec §5, must) make folder-node selection a REAL multi-actor selection, not just a framing
gesture.

**Files:** new `web/src/panels/OrgPanel.tsx`; modify `web/src/scene/QuadLayout.tsx` to wire
`OrgPanel`'s selection events into the same `selectedNames`/`onSelectActor`-shaped state Part 3
built (no second selection model).

**Interfaces:** clicking a folder-tree node REPLACES `selectedNames` with that folder's full actor-
name set (mirrors a plain viewport tap's replace semantics, spec §5's rewritten sentence) and calls
`frameActors` (Task 15, reused verbatim — NOT recreated here) on the same set; Ctrl-clicking a folder
node ADDS its actors to the current `selectedNames` instead (mirrors Ctrl+tap's additive semantics).
This is a plain `additive ? union : replace` over sets, spelled out inline in `OrgPanel`/`QuadLayout`
— `selectionSet.ts`'s `toggleSelection` is a single-NAME toggle and doesn't need to grow a bulk form
for this one call site.

**Focus-search keybinding (review finding, third correction pass: settled in the main spec's
"Keybindings" section — `/`/`Ctrl+F` focus search — but absent from both this plan and its spec
until now).** `OrgPanel` owns a `ref` to its find `<input>`. A window-keydown listener (the same
`isTypingTarget` guard pattern `SelectionKeys`, Task 15, already established) focuses that input on
`/` or `Ctrl+F`/`Cmd+F`, calling `e.preventDefault()` for `Ctrl+F` (to stop the browser's own
find-in-page) but NOT for a bare `/` (so `/` still works as an ordinary character once a DIFFERENT
text input has focus). If a text input already has focus, both keys are a no-op (never steals focus
from an in-progress edit, and `/` types normally there).

**Test failing-first:** `unionBBox`/`frame.ts` already covered by Task 15 — no new test needed for
the framing math itself. New: an `OrgPanel` RTL test (matching `Inspector.test.tsx`'s style) — clicking
a folder node calls `onSelectActor` with every actor name under that folder and `additive=false`;
Ctrl-clicking calls it with `additive=true`; pressing `/` with nothing focused focuses the find input;
pressing `Ctrl+F` does the same and calls `preventDefault`; pressing `/` while a text input already
has focus does not move focus (the input keeps typing `/` as a character).

**Verify:** `npx vitest run`, `npx tsc -b`; manual: click a folder node in `OrgPanel`, confirm all
four panes select AND recenter/refit on that folder's actors; toggle a label chip and type in the
find box, confirm the tree/result set filters as `actor find` would for the equivalent flags; press
`/` from elsewhere in the page, confirm focus jumps to the find box.

**Commit:** `add OrgPanel (folder tree + label facets + find), folder-node select reuses selectedNames`

---

## Part 7 — Level picker (spec §6)

Per the spec's corrected design: in-process current-level holder + watcher rebind, `list_levels`
reused (not reinvented).

### Task 24: `GET /api/levels` (backend)

**Files:** new `uedcli/serve/levels.py`; modify `uedcli/serve/app.py` (register route); test
`uedcli/tests/test_serve_levels.py`.

**Interfaces:** `levels_payload(maps_root: Path, current: str) -> dict` → `{"levels": [{"name": n,
"active": n == current} for n in list_levels(maps_root)], "current": current}` — mirrors `level list
--json`'s existing `{name, active}` shape (`uedcli/cli/commands/level.py::_level_list`) rather than
inventing a divergent one. Route `GET /api/levels`.

**Test failing-first:** a project with 3 level dirs, one of them the app's current level — `GET
/api/levels` returns all 3 names in `list_levels`'s sort order, exactly the current one flagged
`active: true`.

**Verify:** `bin/test -k serve`.

**Commit:** `add GET /api/levels (reuses level_sources.list_levels)`

### Task 25: `PUT /api/level` — in-process switch (backend)

**Files:** modify `uedcli/serve/app.py`.

**Corrected source for the holder-cell pattern (review finding, issue 2): the spec's
`_trunk_ref`/`_geometry_ref` idiom does NOT exist in `preview_cache.py`** (that module only has
disk-cache load/store functions — `load_geometry`/`store_geometry`/`load_scene`/`store_scene` — no
in-process holder of any kind). **It exists in the SIBLING, also-unbuilt item's plan**,
`dev/docs/board/to-spec/uedcli-serve-share-one-in-process-scene-cache/plan.md` (~lines 137-183): a
`list[X | None]` single-element list held in `create_app`'s closure, mutated BY INDEX (`_ref[0] =
...`) rather than reassigned — a plain local-variable reassignment inside a nested function needs
`nonlocal`; mutating a list element in place doesn't. Read that file's exact pattern before
implementing this task; do not grep `preview_cache.py` for it (it isn't there).

**Sequencing (review finding, issue 2): this task does NOT depend on the sibling scene-cache item
landing first — verified against `app.py`'s actual current structure, not assumed.** The two holder
cells solve independent problems. The sibling's `_trunk_ref`/`_geometry_ref` cache a PARSED TRUNK and
BUILT GEOMETRY across requests — expensive, CSG-solve-shaped state, invalidated by a trunk-change
generation counter. This task's holder cells are just "which level name is open right now" and "which
`TrunkWatcher` instance is running" — cheap, no solve involved. Reading `app.py` (lines 42-90) today:
`create_app` already builds `level`, `solve_lock`, and `watcher` directly in its own closure with
ZERO reference to any trunk/geometry cache, and the `/scene`/`/atlas`/`/lightmap` routes call
`_scene_inputs`/`_build_scene` fresh per request (no cache to invalidate yet). This task builds its
OWN independent holder cell in `app.py`, in whichever order the two items actually land.

**This route must be `async def`, the one exception to this file's sync-route convention (review
finding, confirmed bug).** Every route above is deliberately sync `def` because Starlette runs a
sync route in its threadpool (see `/scene`'s own comment in `app.py`) so the blocking CSG solve
never freezes the event loop. But `TrunkWatcher.start()`/`stop()` (`watch.py`) call
`asyncio.ensure_future(...)`/`task.cancel()`, which need the event loop THIS request runs on — a
threadpool worker thread has no running event loop, so a sync `PUT /api/level` following the
established convention here would raise `RuntimeError: There is no current event loop in thread
...` the moment it called `new_watcher.start()`. Write it `async def`.

**Interfaces:** `_current_level: list[str] = [level]` and `_watcher: list[TrunkWatcher] = [watcher]`
(issue 6, below) inside `create_app`'s closure; `PUT /api/level` body `{"level": "<name>"}` →
`{"level": "<name>"}` on success (validated via the existing `_require_level`, so an invalid/missing
name gets the same structured 4xx as today's `/scene` validation). On success: `_watcher[0].stop()`,
construct `new_watcher = TrunkWatcher(maps_root / new_level, _broadcast_reload)`, `new_watcher.start()`,
`_watcher[0] = new_watcher`, `_current_level[0] = new_level`, then broadcast the existing `reload` WS
message with the NEW level's name. `/api/health` and `_broadcast_reload`'s WS payload read
`_current_level[0]` from then on — not the `level` parameter `create_app` was constructed with.

**Issue 6 — the `watcher` object itself needs holder-cell treatment, not just the level string
(review finding, spelled out explicitly).** `app.py:80`'s `watcher = TrunkWatcher(maps_root / level,
_broadcast_reload)` is a plain local variable closed over by `_lifespan` (`watcher.start()`/
`watcher.stop()`) and nowhere else today. A level switch must STOP that exact watcher instance and
START a new one bound to the new level's directory — but `_lifespan` is defined once, at `create_app`
time, and its `finally: watcher.stop()` closes over whatever `watcher` NAMED at that moment unless it
instead reads through a holder cell the switch route also writes to. So `watcher` the bare local is
retired in favor of `_watcher: list[TrunkWatcher]`, and `_lifespan`'s `finally: watcher.stop()`
becomes `finally: _watcher[0].stop()` — reading the CURRENT watcher at shutdown time, not the
startup-time one.

**Test failing-first:** with a second fixture level dir present, `PUT /api/level {"level": "Other"}`
then `GET /api/health` reports `"level": "Other"`; a filesystem change under the OLD level's dir no
longer fires a WS reload (old watcher stopped); a change under the NEW level's dir does (reuses
`test_serve_watch.py`'s watcher-testing pattern). This drives a REAL `TrunkWatcher` end to end (no
mocking it) — `new_watcher.start()` runs inside the route handler itself, so the test fails loudly
with the `RuntimeError` above if the route is written `sync def` instead of `async def`, pinning the
async requirement as a real regression rather than a comment nobody re-checks.

**Verify:** `bin/test -k serve`.

**Commit:** `add PUT /api/level (in-process level switch: holder cell + watcher rebind)`

### Task 26: `LevelPicker.tsx` (frontend)

**Files:** modify `web/src/api.ts` (`fetchLevels(): Promise<{levels: {name: string; active:
boolean}[]; current: string}>`, `switchLevel(name: string): Promise<{level: string}>`); new
`web/src/panels/LevelPicker.tsx`; modify `web/src/App.tsx` (own `level` via the picker instead of
only `/api/health`'s one-time value).

**`reload.ts` itself needs NO changes and is NOT added to this task's Files (review finding, third
correction pass: the original "reuse reload.ts's existing swap" line was ambiguous about how).**
Verified against `App.tsx`'s actual current code (lines ~40-53): its live-reload subscription is
already `useEffect(() => { const sub = subscribeReload(level, ...); return () =>
sub.unsubscribe() }, [level])` — keyed on `level` in the dependency array. React already
unsubscribes the OLD subscription (the cleanup function) and calls `subscribeReload(newLevel, ...)`
FRESH the moment `level` state changes — this is already exactly the "unsubscribe old, subscribe
fresh" design a level switch needs, with no resubscription logic to add. (The scene-fetch `useEffect`
right above it, also keyed on `[level]`, gets the same free re-fetch-on-switch for the same reason.)
This task's only change is making `level` itself settable: `LevelPicker`'s `switchLevel(name)` call,
on success, calls `setLevel(name)` — the existing effects do the rest. `subscribeReload`'s discarding
of the server-sent `msg.level` field is harmless here: the OLD level's socket is closed (by the
cleanup) at the same point the NEW one opens, so there is no window where a stale socket's reload
push could be misattributed to the new level.

**Test:** extend `web/src/api.test.ts` mocking `/api/levels`/`PUT /api/level`, asserting the typed
client's request/response shapes; new `web/src/panels/LevelPicker.test.tsx` (RTL) asserting picking a
different level in the dropdown calls `switchLevel` with the right name.

**Verify:** `npx vitest run`, `npx tsc -b`; manual: with 2+ fixture levels under the project's maps
dir, open the picker, switch, confirm the viewport reloads the new level's geometry with no blank
flash (the existing reload swap semantics).

**Commit:** `add in-GUI level picker (GET /api/levels, PUT /api/level)`

---

## Part 8 — Grid & coordinates (spec §7)

### Task 27: adaptive grid spacing

**Files:** new `web/src/scene/grid.ts`, test `web/src/scene/grid.test.ts`.

**Interfaces:** `gridSpacingUU(worldUnitsPerPixel: number): number` — a 1-2-5-10 log-scale stepping
(the common CAD/level-editor convention) chosen as the DEFAULT since the spec explicitly leaves
log-2-vs-log-10 open as "cosmetic, planning-time"; flagged in Open Questions for owner confirmation,
not silently treated as final. `gridLines(spacingUU: number, viewBoundsWorld: { uMin: number; uMax:
number; vMin: number; vMax: number }): { axis: 'u' | 'v'; at: number }[]` — evenly-spaced lines
covering the given bounds at the chosen spacing (the pure piece `GridOverlay`, Task 28, consumes).
Cursor-to-world projection reuses `orthoCamera.ts`'s `screenToWorld` (Task 5) — not duplicated here.

**Test failing-first:** `gridSpacingUU` returns coarser steps as `worldUnitsPerPixel` grows and finer
as it shrinks, snapping to the 1-2-5-10 sequence at each order of magnitude (known-input table);
`gridLines` produces lines exactly covering the bounds at the given spacing, none outside them.

**Verify:** `npx vitest run`.

**Commit:** `add adaptive grid-spacing + grid-line generation (1-2-5-10 log steps)`

### Task 28: `GridOverlay.tsx` + cursor readout + grid toggle

**Files:** new `web/src/scene/GridOverlay.tsx`; modify `web/src/scene/OrthoViewport.tsx` (mount
`GridOverlay`; track pointer position, project via `screenToWorld`, display the UU coordinate; a
grid-visibility toggle in local/lifted state).

The "selected actor's location/size shown" clause is treated as ALREADY satisfied by the existing
`Inspector.tsx` (it already renders `Location`/bbox-derived fields) — not duplicated as a second,
per-pane readout. Flagged in Open Questions in case a floating per-pane readout (distinct from the
side inspector) was actually intended.

**Test failing-first:** covered by Task 27's `gridLines` test for the line-generation math; the
rendering itself (actual line placement in the DOM/canvas, the cursor-following label) is NOT
meaningfully unit-testable — pure positional rendering. Manual verification: zoom in/out in an ortho
pane, confirm grid density adapts; confirm the cursor readout tracks the mouse in UU; toggle grid
visibility off/on.

**Verify:** `npx vitest run`, `npx tsc -b`; manual checks above.

**Commit:** `add GridOverlay + cursor UU coordinate readout + grid toggle`

---

## Part 9 — Theme (spec §8)

### Task 29: CSS custom-property token system

**Files:** modify `web/src/index.css` — introduce `:root { --bg, --fg, --border, ... }` replacing
today's hardcoded hex values (`#16171d`, `#e5e4e7`, `#2e303a`, `#f87171`, `#9ca3af`), plus the
Slice-3-forward semantic tokens named in the main spec: `--sem-added` (green), `--sem-removed` (red),
`--sem-prop` (amber), `--sem-poly` (violet), `--sem-order` (teal), `--sem-folder` (blue),
`--sem-label` (magenta), `--sem-other` (gray), `--sem-selection` (cyan/white) — wired now even though
nothing but the org panel/level picker consume any of them yet, per the spec's explicit instruction
(Slice 3 shouldn't need a parallel theme-system change later). `:root[data-theme='light']` overrides;
a `prefers-color-scheme: light` media block for the system-follow case.

**Test:** not unit-testable (CSS values). Manual verification: toggle the OS theme and the in-app
switch (Task 30), confirm every existing surface (viewport panes, inspector, org panel, level picker)
re-colors via the tokens with no leftover hardcoded hex.

**Verify:** `npx tsc -b` (unaffected); manual visual check in both themes.

**Commit:** `add CSS custom-property theme tokens (dark-first + light + Slice-3 semantic colors)`

### Task 30: theme preference (dark/light/system) + toggle

**Files:** new `web/src/theme/useTheme.ts`, test `web/src/theme/useTheme.test.ts`; a small toggle
control added to `web/src/App.tsx`'s toolbar area.

**Interfaces:** `type ThemePreference = 'dark' | 'light' | 'system'`; `resolveEffectiveTheme(pref:
ThemePreference, prefersDarkMedia: boolean): 'dark' | 'light'` (pure — the part worth unit-testing);
`useTheme()` wraps it with `matchMedia('(prefers-color-scheme: dark)')` + `localStorage` persistence
and sets `data-theme` on `<html>`.

**Test failing-first:** `resolveEffectiveTheme('system', true) === 'dark'`;
`resolveEffectiveTheme('system', false) === 'light'`; an explicit `'light'`/`'dark'` preference wins
over the media query regardless of its value.

**Verify:** `npx vitest run`, `npx tsc -b`; manual: toggle works, persists across a reload.

**Commit:** `add theme preference toggle (dark/light/system) with persistence`

---

## Part 10 — Final verification (not an afterthought)

### Task 31: the spec's concrete cross-pane proof + full pre-merge gate

**Files:** none (verification only — any real bug found here gets its own task/commit at build time,
not pre-specified).

**Steps:**
1. `cd web && npx tsc -b && npx vitest run` — full frontend suite.
2. `bin/test -k serve` scoped, then a full `bin/test` once before merge (repo convention).
3. **Manual, per the spec's own testing criterion:** load a real level with the quad layout. Confirm
   all four panes show consistent geometry. Select a brush in EACH of the four panes in turn (not
   just once) and confirm it highlights identically — CSG-classified color, visibly bolder — in ALL
   FOUR panes simultaneously, every time. This is the concrete, observable proof the spec's new
   requirement (§2) is met; a pass in only some panes, or only for the pane clicked in, is a failure.
4. **Manual, spec §9:** Ctrl-click/Ctrl-tap a second and third actor in different panes, confirm all
   three highlight identically across all four panes; press `F`, confirm all four panes frame the
   union bbox; press `Esc`, confirm every pane's highlight clears.
5. Exercise shading-mode switching, the org panel's filter/frame/multi-select, the level picker's
   switch, the grid toggle, and the theme toggle once each, live, per `building-features.md`.

**Commit:** none (this is the pre-merge checkpoint, not a code change).

---

## Open questions (left for the build phase to confirm, not silently decided here)

- **View vs. 4-Canvas (Part 0):** resolved to 4 `<Canvas>` on architectural-risk reasoning (the
  hand-rolled pointer-lock/capture model), NOT a measured GPU-memory number — no benchmark of a
  typical level's vertex/texture byte size exists in this repo. If a build-phase spike or a real
  large level shows the 4x upload actually matters, revisit before committing further to this path.
- **Grid stepping (Part 8, Task 27):** picked 1-2-5-10 log steps; the spec calls the exact algorithm
  "cosmetic, planning-time" — confirm no different convention is preferred.
- **Level-picker response shape (Part 7, Task 24):** picked `{levels: [{name, active}], current}`,
  mirroring `level list --json`'s existing per-entry shape; confirm this is what the frontend
  actually wants (vs., say, a bare name array).
- **`buildBrushRings`'s `'csg-all'` scope (Part 2, Task 9):** generalized so wireframe-mode
  Perspective could also use it, not just ortho panes — confirm this reading of "matches `actor
  diagram`" against the owner's intent before Task 20 wires wireframe mode.
- **QuadLayout double-click-a-different-pane semantics (Part 1, Task 7):** picked "switches the
  maximized pane" over "no-op until restored first" — not stated in the spec either way.
- **Cursor/selection readout duplication (Part 8, Task 28):** treated "selected actor's location/size
  shown" as already satisfied by the existing side `Inspector.tsx`, not a new floating per-pane
  readout — confirm.
- **Shading-mode gating's real backend shape (Part 4):** entirely owned by the separate
  `gui-explicit-rebuild-pinned-build-state-mode` item, itself still undecided on "where... the
  rebuild/load status gets exposed" (that item's own "What is open"). Task 19's `useBuildStatus`
  stub is the ONE place to change once that lands — do not let it drift into a second, ad-hoc gating
  path elsewhere in this codebase.
- **"Flat" shading mode (Part 4, Task 20):** implemented identical to unlit as a placeholder, per the
  main spec's own "Also open" — not a real definition.
- **Inspector multi-select summary format (Part 3, Task 16):** picked a plain count + name list;
  neither settled spec paragraph defines the 2+-selected inspector view — confirm this is enough, or
  whether a richer multi-actor view (shared-property rollup, say) was actually wanted.
- **Org-panel folder-click replace-vs-add convention (Part 6, Task 23):** mirrored the viewport's own
  plain-tap-replaces / Ctrl-click-adds convention onto folder nodes — confirm a whole-subtree
  selection is meant to follow the same modifier convention as a single-actor tap, rather than, say,
  always being additive (building up a working set folder by folder).
- **Tap-on-empty-space no longer deselects (Part 3, Task 13):** a deliberate behavior change from
  today's click-away-to-clear — confirmed against both settled main-spec paragraphs (neither mentions
  it; `Esc` is stated as the deselect action) but flagged since it changes observable behavior an
  existing user might be used to from Slice 1.

## Self-review

- Every spec section maps to a Part above: Part 0 (prerequisite, spec §1/§2's restructuring finding,
  NOW covering interaction plumbing too, not just geometry), Parts 1/2/4/5/6/7/8/9 map to spec
  §1/§2/§3/§4/§5/§6/§7/§8 respectively, Part 3 maps to the NEW spec §9 (multi-select/frame/deselect),
  and Part 10 is the spec's own manual-verification criterion made an explicit final task.
- Every task carries Files + Interfaces + either a real failing-test-first step or an explicit,
  named manual-verification substitute (WebGL line width, CSS layout, cursor-following rendering,
  theme visuals) — none faked as a unit test where one can't exist. Part 3's cross-pane consistency
  test (Task 17) closes the one place this plan previously WOULD have faked coverage (a manual-only
  check for the spec's own stated acceptance criterion).
- The three genuinely new backend surfaces (`GET /api/levels`, `PUT /api/level`) reuse
  `list_levels`/`_require_level`/the existing `TrunkWatcher`/reload-broadcast machinery and (Task 25)
  a holder-cell pattern correctly sourced from the sibling scene-cache item's PLAN (not
  `preview_cache.py`, which has no such pattern) — no second enumeration, no second watcher
  mechanism, and an explicit, verified sequencing note that this item doesn't wait on the sibling.
- The one external dependency this plan cannot resolve on its own (shading-mode gating's real
  signal) is isolated behind one hook (`useBuildStatus`) rather than threaded ad hoc through every
  mode-aware component.
- Multi-select's scope is deliberately partial: Ctrl+add/`F`/`Esc`/multi-highlight are fully
  specified with failing-test-first tasks (12-17); ortho marquee-select is explicitly deferred to its
  own board item with a stated, non-arbitrary reason (a real interaction-binding conflict needing an
  owner ruling, not an implementation detail) — see this plan's Revision history.

## Revision history

- Second adversarial review (2026-09-14) found four confirmed gaps, fixed here:
  1. **Pointer-lock/capture hoisting was silent.** The original Task 3 explicitly left "camera,
     pointer handling, click-to-select" unchanged and the original Task 5 (`OrthoViewport`) never
     addressed pointer-lock/`setPointerCapture`/whether ortho drag reuses shared plumbing or
     hand-rolls a third copy. Fixed: new Task 4 extracts `useDragGesture` (mouse-only; touch stays
     Viewport3D-local) as the shared plumbing both Perspective (Task 4 itself) and ortho (Task 6,
     now stating explicitly it consumes Task 4 rather than a second copy) use.
  2. **Task 18 (now 25) pointed at the wrong file.** `preview_cache.py` has no `_trunk_ref`/
     `_geometry_ref` holder-cell idiom — that pattern lives in the sibling
     `uedcli-serve-share-one-in-process-scene-cache` item's PLAN. Fixed: Task 25 now cites the
     correct file/line range and states, with evidence from reading `app.py`'s actual structure, that
     this item's level-switch holder cell is independent of the sibling item and does not need it to
     land first.
  3. **Missing P1-settled multi-select/frame/deselect scope.** Neither this plan nor its spec
     mentioned the main spec's settled Ctrl+tap/Ctrl+click multi-select, `F` frame, `Esc` deselect, or
     cross-pane multi-highlight, despite this slice's goal being "completes the P1 viewer." Fixed:
     new Part 3 (Tasks 12-17) implements all of it EXCEPT ortho marquee-select, which is explicitly
     deferred to `dev/docs/board/inbox/ortho-marquee-drag-select-rubber-band-multi/` — a real,
     stated reason (a new screen-projection mechanism plus an unresolved button-binding conflict with
     the already-settled ortho drag-pan gesture, needing an owner ruling) rather than a silent
     omission. Task 23 (org panel, was 16) is rewritten to use the resulting `selectedNames` model
     instead of camera-framing-only, resolving the review's issue 5 (it previously cited spec §2
     without engaging §5's multi-actor-set language, because no multi-actor model existed yet).
  4. **No automated cross-pane consistency test.** The spec's own acceptance criterion had only a
     manual verification step. Fixed: Task 17 adds an RTL test (mocked pane components, matching
     `Inspector.test.tsx`'s established style) asserting all four panes' `selectedNames` stay in
     sync after a selection change from any one pane.

  All subsequent tasks renumbered (old 4-24 → new 5-11, 18-32 minus the Part-3 insertion; see the
  Part headers for the old→new task-number cross-references now embedded inline, e.g. Task 9's note
  that Task 14 generalizes it). Three further minor fixes folded in per the same review: Task 6 (was
  5) now states explicitly that ortho touch/gesture parity is DEFERRED, desktop-first (previously
  unstated); Task 25 (was 18) spells out that the `watcher` object itself, not just the level-name
  string, needs holder-cell treatment (`app.py:80`'s closure).
- Third adversarial review (2026-09-15) found four confirmed gaps, fixed here:
  1. **Task 25's `PUT /api/level` silently followed the file's sync-route convention**, which would
     make `TrunkWatcher.start()`/`stop()` raise `RuntimeError: There is no current event loop in
     thread ...` (they need the event loop of the request thread; a sync route runs in Starlette's
     threadpool, which has none). Fixed: Task 25 now states this route must be `async def` with the
     one-sentence reason, and its existing failing-test-first (real level switch, real watcher
     rebind, no mocking) is called out as the regression guard — it fails loudly if the route
     reverts to sync.
  2. **Task 4's `useDragGesture` extraction dropped the `e.button !== 0 || e.altKey` tap-suppression
     gate** — an RMB or Alt+LMB release never selects today, and the hook's `onTap` signature had no
     way to see either. Fixed: the gate is now explicitly replicated INSIDE the hook (never
     delegated to the caller), with two new failing-test-first cases (RMB tap, Alt+LMB tap — both
     must not fire `onTap`).
  3. **The main spec's settled `/`/`Ctrl+F` focus-search keybinding was absent from both files.**
     Fixed: folded into Task 23 (`OrgPanel.tsx`) as a small addition — a window-keydown listener
     reusing `SelectionKeys`'s `isTypingTarget` guard, with three new failing-test-first cases.
  4. **Task 26's "reuse `reload.ts`'s existing swap" was ambiguous.** Fixed: clarified that
     `reload.ts` needs no changes at all — `App.tsx`'s existing `useEffect(..., [level])` already
     unsubscribes the old subscription and calls `subscribeReload(newLevel, ...)` fresh whenever
     `level` state changes, verified against the actual current code; Task 26's only real change is
     making `level` settable via the picker.
