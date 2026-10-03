# The `web/` TypeScript GUI — what it is now, and what a refactor should target

**Date:** 2026-10-03 · **Status:** research only — no decisions taken, nothing implemented.
**Question:** What is `old/web/` made of, what contract does it hold against the backend the Rust
rewrite replaces, and what should a TypeScript refactor of it target?

## Summary

- **23,891 lines under `old/web/src`**, 142 files: 10,806 non-test TS/TSX, 11,803 test TS/TSX, 1,282
  lines of hand-written CSS. 72 test files against 69 source files, 799 `test(`/`it(` calls.
- **State is entirely hand-rolled React.** No zustand/redux/jotai/valtio; exactly **one**
  `createContext`, **zero** `useReducer`, zero `useSyncExternalStore` — though zustand turns out to
  be an r3f dependency already (§9).
- **Three god components:** `SessionEditor` (in `App.tsx`, 633 lines, 17 `useState` + 19
  `useCallback` + 8 `useEffect` in one function), `Viewport3D` (584, 23 props, 15 `useRef`) and
  `OrthoViewport` (468, 17 props, 15 `useRef`) — **12 props shared with identical meaning**, as the
  files themselves say nine times.
- **The contract is 21 HTTP routes + 1 WebSocket**, all in `api.ts` (587 lines, only
  `classResolver.ts` bypasses it); 19 are called, `/api/health` and the gated `/api/_boom` are not.
- **The browser runs Rust as wasm.** `resolve-core` (5,320 LOC) compiles to `wasm32-unknown-unknown`
  into `web/src/wasm/` (gitignored, built by `old/bin/ensure_wasm.sh` as npm `prebuild`/`pretest`);
  the frontend fetches **raw `.u` bytes** and resolves class schema + defaults itself, synchronously.
- **`@dimforge/rapier3d-compat` is NOT imported by `old/web/src`** — zero hits; it is in
  `package-lock.json` only as a declared dependency of `@types/three@0.186.0`.
- **Four separate `<Canvas>` elements** on one JS thread at r3f's default `frameloop="always"`; no
  `frameloop="demand"`, no `invalidate()`, no `InstancedMesh`.
- **45 GUI board items** (`gui*`, all stages: 18 done, 14 inbox, 4 someday, 3 to-build, 1 to-spec, 1
  to-plan), plus **12 more** inbox items touching `web/src` without a `gui-` name.
- **Parity is per-topic, not global**: 25 topics, **18 closed, 3 investigating, 4 open** — and
  click/hit-detection, what a refactor most likely disturbs, is one of the 3 unresolved. `GUI.md` has
  drifted from the code it documents in three places (§6).

## What we have today

| Directory | Files | Non-test LOC | Test files | Test LOC | What lives there |
|---|---|---|---|---|---|
| `src/scene/` | 90 | 7,424 | 45 | 7,160 | viewports, cameras, picking, drag, grid, geometry, markers, overlays, class resolution |
| `src/panels/` | 18 | 1,242 | 9 | 1,823 | Inspector, Sidebar, SaveBar, ConflictResolver, OrgPanel, prop display |
| `src/` | 14 | 1,444 | 8 | 2,023 | `App.tsx`, `api.ts`, `reload.ts`, `platform.ts`, `main.tsx` |
| `src/session/` | 12 | 466 | 6 | 645 | session picker/dropdown/label/rename, routing, `SessionContext` |
| `src/layout/` | 6 | 148 | 3 | 134 | collapsible panel, sidebar, selection-seen hooks |
| `src/theme/` | 2 | 82 | 1 | 18 | dark/light/system preference |
| `src/index.css` | 1 | 1,282 | — | — | 138 selectors, 56 custom properties, no framework |
| **total** | **142** | **10,806** | **72** | **11,803** | + 1,282 CSS = **23,891** |

Largest: `index.css` 1,282 · `App.test.tsx` 943 · `Viewport3D.tsx` 782 · `App.tsx` 739 ·
`tapSelect.test.ts` 718 · `Inspector.test.tsx` 689 · `OrthoViewport.tsx` 597 · `api.ts` 587.
Toolchain (from `package-lock.json`): `vite` 8.3.0, `typescript` 6.0.3, `vitest` 5.0.0, `oxlint`
1.82.0, `react`/`react-dom` 19.2.8, `three` 0.186.0, `@react-three/fiber` 9.7.0 — all nine verified
real (§9; TS 7.0.2 is `latest`, so `~6.0.2` is a major behind). `oxlint` replaces ESLint with three
rules; Vite dev-proxies `/api` and `/ws` to `127.0.0.1:8765`. **No `strict` flag is set in
any `old/web/tsconfig*.json`** — only `noUnusedLocals`, `noUnusedParameters`, `erasableSyntaxOnly`,
`noFallthroughCasesInSwitch`, `verbatimModuleSyntax` — yet the code reads as if `strictNullChecks`
were on; whether TypeScript 6.0 enables `strict` by default is **unverified**. Only 3 `any`s and 6
lint-disables; 52 `@ts-expect-error`s, **all 52 in `scene/dragGesture.test.ts`**.

## Findings

### 1. The API contract the new Rust backend must serve

All routes in `old/uedcli/serve/app.py`. "Claim" = requires the `X-Claim-Token` header, else 409 with
`{"error": "session superseded…"}` / `"session deleted…"`. Errors are always `{"error": "…"}`, never a
traceback (`serve/errors.py::error_to_status`); `GZipMiddleware` applies above 500 bytes.

| Method | Path | Claim | Purpose | Frontend caller |
|---|---|---|---|---|
| GET | `/api/health` | — | `{"status":"ok"}` | **none** |
| GET | `/api/levels` | — | `{levels:[{name,active}], current}` | `session/SessionPicker.tsx` |
| GET | `/api/package/{package_name}/raw` | — | raw `.u` bytes, `ETag` + 304 | `scene/classResolver.ts` (own `fetch`) |
| GET | `/api/sessions` | — | session list | `SessionPicker.tsx`, `SessionDropdown.tsx` |
| POST | `/api/level/{level_name}/sessions` | — | 201, create session + first claim | `SessionPicker.tsx` |
| GET | `/api/session/{id}` | — | resolve id, **mints a fresh claim** (not idempotent), 404 if unknown | `App.tsx`, `SessionContext.tsx`, `SessionPicker.tsx` |
| POST | `/api/session/{id}/rename` | yes | rename | `SessionLabel.tsx`, `SessionPicker.tsx` |
| DELETE | `/api/session/{id}` | yes | 204; `?force=true` skips the conflict check | `SessionPicker.tsx` |
| GET | `/api/session/{id}/status` | — | `{changes_available, geometry_pinned, build_status}` | `App.tsx` (3s poll) |
| GET | `/api/session/{id}/scene` | — | `ScenePayload`: polys + actors + `geometry_pinned` | `fetchLevelState` ← `App.tsx`, `reload.ts` |
| GET | `/api/session/{id}/atlas` | — | `{width,height,manifest,png_base64}` | same |
| GET | `/api/session/{id}/lightmap` | — | lightmap atlas keyed by poly index | same |
| POST | `/api/session/{id}/load` | yes | re-read trunk, clear `changes_available`; no solve | `App.tsx` |
| POST | `/api/session/{id}/rebuild` | yes | the ~24s CSG+lighting solve; pins geometry | `App.tsx` |
| POST | `/api/session/{id}/stage` | yes | stage `{name: [x,y,z]}` moves | `Viewport3D.tsx`, `OrthoViewport.tsx`, `dragStage.ts`, `QuadLayout.tsx`, `App.tsx` |
| GET | `/api/session/{id}/staged` | — | `{name: {staged_location, baseline_location}}` | `App.tsx`, `SessionPicker.tsx` |
| POST | `/api/session/{id}/discard` | yes | drop all or named staged moves | `App.tsx`, `panels/SaveBar.tsx` |
| POST | `/api/session/{id}/save` | yes | write to trunk; `{applied, conflicts}` | `App.tsx`, `panels/SaveBar.tsx` |
| POST | `/api/session/{id}/t3d` | — | `Begin Map…End Map` for named actors | `panels/Inspector.tsx` |
| GET | `/api/_boom` | — | fault injection, only when `fault_route` is set | **none** (tests) |
| WS | `/ws?session=&claim=` | URL | live push, §2 | `reload.ts` via `api.ts` |
| GET | `/session/{id}` + `StaticFiles` at `/` | — | SPA index fallback, only when `web/dist` exists | browser navigation |

For the port: the contract is **session-scoped** — only `/api/levels` and `/api/package/{name}/raw`
sit outside `/api/session/{id}`, and the old `PUT /api/level` switch is gone. `GET /api/session/{id}`
**mutates** (mints a claim), and that is load-bearing: it is how a page reload takes a session over
from another window. Two routes break the status convention, flagged in `app.py` itself:
`GET`/`DELETE /api/session/{id}` return a literal 404, every other not-found raises `CommandError` →
422. `api.ts`'s doc comments cite **three routes that no longer exist** (lines 259, 378, 457).
`/api/package/{name}/raw` is the one binary route: `application/octet-stream`, `ETag` from
`(realpath, size, mtime_ns)`, and an explicit `Vary: Accept-Encoding` on the 304 path because
`GZipMiddleware` never sees a bodiless response.

### 2. WebSocket / live-reload

One socket per session, `ws(s)://<host>/ws?session=<id>&claim=<token>`, opened by
`api.ts::openChangesAvailableSocket`, managed by `reload.ts::subscribeChangesAvailable`:

| Message | Trigger | Client effect |
|---|---|---|
| `{"type":"changes_available","level":"<name>"}` | debounced trunk change on disk | **banner only** — never an auto-refetch |
| `{"type":"superseded"}` | this connection's claim is no longer current | show takeover, stop reconnecting; close 4003 follows |
| `{"type":"closed"}` | session deleted | show closed; close 4004 follows |

Backend: `serve/watch.py::TrunkWatcher` wraps `watchfiles.awatch` behind a 0.4s debounce; a settled
burst fires once, bumping a generation counter and `changes_available`, then
`_broadcast_changes_available(ctx)` iterates a **snapshot** of `ctx.connections` — iterating the live
set drops the whole broadcast when a client connects mid-`await`. Two non-obvious properties to
reproduce. **Supersession is polled, not pushed** — `ws_endpoint` re-checks the claim on every
receive-timeout tick, because `claims.mint` runs on a Starlette worker thread with no bridge into the
socket's loop; a `tokio` backend could push, but the client is written against the poll's latency.
And **close codes are contract**: `reload.ts` treats 4001 (unknown session / missing claim, rejected
*before* `accept()`) as permanent and stops; any other close reconnects after a fixed 2,000 ms.

### 3. The wasm path, and exactly what it constrains

`old/uedcli-native/resolve-wasm/` is a 28-line `cdylib` of `wasm-bindgen` shims over `resolve-core`
("zero new logic here"), exporting `WasmResolutionContext` with `add_package`, `packageImports`,
`resolveClass`. `old/bin/ensure_wasm.sh` → `_venv.sh::ensure_wasm_artifact` content-hashes
`resolve-core` + `resolve-wasm`, builds the `wasm-export` Docker stage and writes `web/src/wasm/`
(gitignored); it is npm `prebuild` and `pretest`, so **the TypeScript build and the test run already
depend on a Rust toolchain in Docker** (`wasm-bindgen` pinned exactly at `=0.2.100`).

In the browser (`scene/classResolver.ts`, 154 lines): fetch raw `.u` bytes, walk the import closure
(filtered by `resolve-core` to Class/Struct/Enum-typed imports — following every import over-fetches
~20x), then answer `resolveClassSync(fqcn)` **without awaiting anything**. `Inspector.tsx` renders
that against `SceneActor.props` (a sparse dotted-path `Record<string,string>`) via
`panels/resolveDisplayProps.ts`. There is no resolved-JSON endpoint — schema resolution was moved off
the wire into the client deliberately. Four constraints follow.

**(1)** `resolve-core` must stay `wasm32-unknown-unknown`-clean in the new
tree — no `std::fs`/`env`/`time`, no threads; it already is
(`dev/research/rust-workspace-architecture.md`), and the Inspector's "never a spinner" property is a
hard dependency on that. **(2)** `/api/package/{name}/raw` must keep serving raw bytes with ETag
semantics — not JSON, so not derivable from a typed schema. **(3)**
`ClassResolution`/`TypeShape`/`ResolvedProp` in `api.ts` are a Rust `Serialize` shape, not an HTTP
response shape, so a generator pointed only at routes misses them. **(4)** The npm scripts cannot be
decoupled from the Rust build without losing the parity tests — moving `web/` out of `old/` while
`resolve-core` stays breaks `../bin/ensure_wasm.sh` and the golden fixture path.

### 4. State architecture — what "hand-rolled" means

`SessionEditor` (`App.tsx:100-732`) owns `scene`, `atlas`, `lightmap`, `status`, `selectedNames`,
`selectedSurfaces`, `stagedNames`, `stagedOffsets`, `frameRequest`, `loadConflicts`, `busy`, three
error slots, `reloading`, `resolverTick`, `displayName` — 17 `useState` calls in one body, 19
`useCallback`s, 8 `useEffect`s. It is drilled: `App.tsx` → `QuadLayout` (its own 11 `useState`) →
`Viewport3D` + 3× `OrthoViewport`, with the 12 selection/staging/framing props arriving at both
viewport kinds identically.

Two escape hatches exist where drilling got too painful, both documented as such: `api.ts`'s
module-level `currentClaimToken` + `setClaimToken()` (because `postStage` is called "several props
deep under `QuadLayout`"), and `stagedOffsetsRef` — a `MutableRefObject` passed beside the state
value so viewports can read current offsets without re-rendering. The one `createContext` is
`SceneResourcesReactContext`, holding the right thing: built three.js geometry/materials shared by
four panes instead of four builds. **r3f performance idioms are otherwise absent** —
`RadiiOverlays.tsx:157-172` documents the pattern already hit once: a per-actor component each running
its own `useFrame`, recomputing the same camera basis and issuing its own draw call every frame in all
four panes on one thread; batched for radii, but still how markers/overlays are built generally.

### 5. Testing — what is actually covered

72 test files / 11,803 LOC / 799 `test(`-`it(` calls; 24 files use `@testing-library/react`, 9 use
`@react-three/test-renderer`, 12 stub `fetch` or `vi.mock`.

Covered: **picking and selection as pure logic** — `selection.ts::resolveTapAction` is a pure
function of `(rawHit, mode, shiftKey, additive)`, exercised by `selection.test.ts` (549) and
`tapSelect.test.ts` (718) with no WebGL raycast, and the same for every other `scene/` math module.
**Scene-graph assertions** via `@react-three/test-renderer` for 9 overlay/marker components, checking
emitted three.js objects and `renderOrder`, not pixels. **Forms and panels** via Testing Library;
**the wire client** (`api.test.ts`, 562) with stubbed `fetch`, including the 409 superseded/deleted
split; **cross-implementation parity** against the Rust golden. Not covered: **no real WebGL
anywhere** (jsdom only, no pixels, no headless browser) — and
`board/inbox/front-side-ortho-panes-render-blank-in-headless/` records that the ortho panes in fact
*don't* draw under headless Chromium, so the one environment that could screenshot them is itself
known-broken. **No end-to-end test against a live backend.**

### 6. Parity target and distance from it

`old/GUI-PARITY.md` (1,998 lines) is the campaign doc. Its bar is explicitly **per-topic, not one
global byte-parity target**: each topic states its own, and is CLOSED only on live evidence. Of 25
topics, **18 are closed, 3 investigating/half-answered, 4 open**.

The 18 closed are real RE against the project's **own** `uned/UED22/` binaries (selection and surface
highlight, sprite alpha picking, vertex-handle screen size, mesh wireframe, all five radii topics,
all three pivot-cross topics, the directional-arrow dart); an owner ruling bars citing any
third-party UE1 source. The 3 unresolved all touch what a viewport refactor would disturb:
**click/hit-detection algorithm** (current behavior is spec-and-convention); **modifier-key
click-select rules** (Shift-forks-to-brush and Ctrl-is-additive are disassembly-confirmed, the
AABB-fallback Shift gate and the line-hit rule are not); **actor + surface selection coexistence**
(implemented and disassembly-backed, live confirmation still owed). Open: marquee containment,
Intersect/Deintersect brush coloring, pan direction, UED22's Zones view mode.

`GUI-PARITY.md` lives at the repo root so it can be updated without per-edit doc approval while
`dev/docs/GUI.md` needs the owner's yes — and the predictable consequence happened:

| `old/dev/docs/GUI.md` says | Reality |
|---|---|
| `LevelPicker.tsx`'s dropdown reports the picked level (line 20) | no `LevelPicker.tsx` exists; `session/SessionPicker.tsx` replaced it |
| `App.tsx` calls `PUT /api/level` to switch level (line 25) | that route does not exist; a session, not a level, is the unit of navigation |
| `SceneActor.props`/`.categories` are parallel arrays (line 313) | replaced by a sparse dotted-path `Record<string,string>` + client-side resolution |

### 7. GUI board items

**45 items whose directory name contains `gui`**, across 6 stages; the 27 in open stages listed.

| Stage | Item | P | One line |
|---|---|---|---|
| to-plan | `uedcli-human-gui` | p? | the parent spec: P1 read/audit GUI, four viewports, no trunk writes |
| to-spec | `persistent-gui-editing-sessions` | p2 | sessions as the unit of navigation + claim tokens (largely built) |
| to-build | `gui-builder-brushes` | p? | builder brushes; source of the "no special-cased props" ruling |
| to-build | `gui-inspector-effective-props-search-show-all` | p2 | effective props: search, overrides-only, struct/array expansion |
| to-build | `gui-copy-selected-actors-as-t3d-to-clipboard` | p? | duplicate of the same-named `done` item — stale stage entry |
| inbox | `gui-actor-move-final-review-wave-residual` | p? | residual papercuts from the actor-move review wave |
| inbox | `gui-click-detection-algorithm-not-re-d-against` | p2 | hit-testing never RE'd against UED22 (parity 🔶) |
| inbox | `gui-csg-brush-coloring-never-distinguishes` | p? | Intersect/Deintersect share Add's color |
| inbox | `gui-explicit-rebuild-spec-omits-paths-as` | p? | Paths is UnrealEd's third build axis, unspecced |
| inbox | `gui-ortho-marquee-spec-omits-unrealed-s-brush` | p? | marquee needs full-containment (brush) vs pivot-in-box (point) |
| inbox | `gui-perspective-pan-direction-vs-ortho` | p3 | the two panes disagree on pan direction (owner question) |
| inbox | `gui-save-doesn-t-suppress-its-own-trunk-watcher` | p? | Save triggers its own changes-available banner |
| inbox | `gui-saveable-switchable-actor-visibility-filters` | p2 | persisted visibility filter sets |
| inbox | `gui-serve-routes-take-level-name-but-watcher` | p3 | watcher binds one level while routes take any |
| inbox | `gui-shading-modes-omit-unrealed-s-zones-view` | p? | no Zones view mode |
| inbox | `gui-sprite-icons-render-mirrored` | p2 | actor sprites render mirrored |
| inbox | `gui-texture-actor-click-select-modifier-rules` | p2 | modifier rules unverified against live UED22 (owner question) |
| inbox | `gui-unlit-fast-rebuild-button` | p? | a CSG-only, no-lighting rebuild |
| inbox | `gui-wireframe-perf-remaining-marker-sprite-draw` | p3 | marker-sprite draw calls after the brush-outline merge |
| inbox | `incremental-gui-reload-only-re-resolve-actors` | p2 | re-resolve only changed actors on Load |
| inbox | `incremental-csg-checkpointing-for-gui-rebuild` | p? | checkpoint CSG so Rebuild is incremental |
| inbox | `craft-docs-are-unrealed-gui-framed` | p2 | docs teach the UnrealEd GUI, not uedcli verbs |
| someday | `gui-inspector-editing-write-back-for-props` | p2 | the write path for props + surfaces |
| someday | `gui-inspector-dynamic-arrayproperty-support` | p3 | dynamic ArrayProperty (format known, no content exercises it) |
| someday | `gui-per-surface-light-influence-inspection-nice` | someday | per-surface light influence |
| someday | `gui-zone-visualization-nice-to-have-not` | someday | zone visualization |

**12 more inbox items touch `web/src` or the viewport without a `gui-` name** — grepping `gui-` alone
misses them: `sceneactor-special-cases-location-rotation` (p1, violates the standing props ruling),
`scene-cold-load-must-return-within-5s` (p1), `rebuild-should-run-in-background-on-a-trunk-snapshot`,
`status-and-lightmap-routes-skip-the-automatic-initial-load`,
`perspective-pane-lit-mode-renders-near-black-on`, `movers-toggle-should-be-wire-full-off-mirroring`
and `q-e-vertical-move-modifier-needs-ued22-re` (both need RE first),
`rebuild-shows-wrong-textures-and-vanishing`, `ortho-marquee-drag-select-rubber-band-multi`,
`ortho-pane-silently-switches-to-textured`, `front-side-ortho-panes-render-blank-in-headless`, and
`gray-out-rebuild-when-it-would-not-change`.

**On the "absrel drag bridge".** `board/to-spec/activate-the-novnc-absrel-drag-bridge/` is **not**
about `web/`'s drag gesture: it is a p3 chore to activate `uned/vnc_input_bridge.py`'s
absolute→relative pointer translation on the standing **noVNC** sessions that drive the real UED22
container — the live-capture half of the RE method `GUI-PARITY.md` depends on. Without it, the
mouse-with-modifier interactions the 3 unresolved parity topics need cannot be captured live. Infra,
not frontend code.

### 8. Concrete refactor targets, with evidence

1. **`SessionEditor` in `App.tsx`** (633 lines, 17/19/8 hooks) — the app's de facto store, HTTP
   orchestrator, conflict flow and layout shell at once. Everything below it is prop-drilled. The
   largest single lever.
2. **`Viewport3D` (584 / 23 props) vs `OrthoViewport` (468 / 17 props)** — 12 shared props, 9
   "identical prop doc" cross-references, no shared base, and `CameraRig`/`OrthoCameraRig` plus
   `applyCameraPose`/`applyOrthoCameraPose` are the same idea twice.
3. **The four-`<Canvas>`, always-on frameloop** — four WebGL contexts re-rendering every animation
   frame whether or not anything moved, no `invalidate()`, no instancing.
4. **Backend-shape coupling in `api.ts` (587 lines)** — hand-maintained to mirror Python dataclasses
   "field-for-field", already citing 3 dead routes; `ScenePoly.flags` is documented as "unused by the
   client; dropped in Phase 2" and is still there.
5. **`SceneActor.location`/`.rotation` as bespoke fields beside generic `props`** — a p1 board item
   and a direct violation of `dev/docs/rationale/gui-editing.md`'s standing ruling. A wire change, so
   cheapest while the backend is being rewritten anyway.
6. Cheap and low-risk: the **two drilling escape hatches**, **`index.css`**, **`GUI.md`'s three
   drifted statements** (§6).

Non-targets: the pure math modules in `scene/` (`selection.ts`, `camera.ts`, `orthoCamera.ts`,
`grid.ts`, `geometry.ts`, `brushRings.ts`, `winding.ts`, `selectionSet.ts`) are small, pure,
individually tested, and encode RE'd UED22 facts calibrated against `old/uedcli/preview.py` —
rewriting them risks un-closing parity topics for no gain.

### 9. External practice

**Method caveat:** the `WebSearch` budget was exhausted (200/200) before this pass; everything below
is from direct fetches of the npm registry, library source, official docs and the GitHub API, so the
practitioner-opinion layer is thin. **Versions are all real** (control: `vite/8.3.99` → 404); latest
seen: `vite` 8.3.2, `typescript` **7.0.2**, `vitest` 5.0.3, `oxlint` 1.86.0, `react` 19.3.0, `three`
0.186.1, `@react-three/fiber` 9.8.1 (peering `react: ">=19 <19.4"`), both testing packages pinned.

**zustand is not merely the ecosystem default — r3f depends on it.** `@react-three/fiber@9.8.1` lists
`zustand ^5.0.3` and `use-sync-external-store`; `useThree(sel)` *is* a zustand selector hook, and
zustand's binding is literally `React.useSyncExternalStore` — so "zustand vs `useSyncExternalStore`"
is a false choice. Transient updates are first-class (`subscribe` binds a component to a state
portion "without forcing re-render on changes", plus `subscribeWithSelector` and `getState()` outside
React) — exactly what `old/web/src`'s per-viewport `useRef`s and module-global token hand-roll.

**r3f's guidance matches what `RadiiOverlays.tsx` discovered the hard way:** "You might be tempted to
setState inside `useFrame` but there is no reason to" — fast updates are "carried out in `useFrame` by
mutation". The scaling page names the levers absent here: `frameloop="demand"` + `invalidate()`,
instancing, a draw-call budget under ~1000, LOD, `PerformanceMonitor`/`regress()`.

**Is r3f still right for an editor viewport?** The live data point is **Triplex**, a visual r3f scene
editor under pmndrs (1.3k stars, pushed 2026-06-11); the older `pmndrs/react-three-editor` is
**archived** (2023-03). r3f editors do ship, but the pattern is React for chrome/props plus
mutation-and-`invalidate` for the viewport — a vote for A + C over a rewrite to plain three.js.

**Transform gizmos.** three.js r186's `TransformControls` already has `translationSnap`/
`rotationSnap`/`scaleSnap`, `space` local/world, per-axis visibility, `dragging-changed` events and
explicit orthographic handling. Two limits land here: **single-object only** (`attach` takes one
`Object3D`; multi-object and pivot gizmos are open three.js requests, so a multi-selection needs a
proxy group you build), and **its event plumbing is separate from r3f's** (own pointer handlers with
`setPointerCapture` and own raycaster, so gizmo picking must be reconciled with `tapSelect.ts`).
Known gaps: setting state in `useFrame` recreates the gizmo and makes it flicker/undraggable; axis
clamping and `stopPropagation` are missing; `Line2` is incompatible with `OutlinePass` (relevant —
`tapSelect.ts` uses a `Line2` bold ring). drei's `PivotControls` is the better primitive for a custom
pipeline (`autoTransform={false}` hands you the matrix in `onDrag`), but drei is not a dependency.

**Typed client generation from Rust:**

| Tool | Version / activity | Scope | CI drift check | `serde` tagged-on-`kind` | WS messages |
|---|---|---|---|---|---|
| `utoipa` + `utoipa-axum` | 6.0.0 / 0.3.0, pushed 2026-10-02, 4.1k★ | routes **and** types; `routes!(h)` collects `#[utoipa::path]` handlers | yes — dump spec + `git diff --exit-code`; TS side `openapi-typescript --check` | **partial by design**; docs warn `tag` "cannot be used with tuple types" | no |
| `aide` | 0.15.1 (2026-04-14), pushed 2026-09-21, 678★ | routes + types, **axum only** | same | yes, via `schemars` | no |
| `ts-rs` | 12.0.1, pushed 2026-10-02, 1.9k★ | **types only** | strong — `#[ts(export)]` emits a test, `cargo test export_bindings` writes `bindings/`, then diff | yes (`tag`/`content`/`untagged`) | yes, implicitly |
| `specta` / `tauri-specta` | **still `2.0.0-rc.25`** (rc since 2024); stable is 1.0.5 | types + fn signatures; `tauri-specta` also exports events | export then diff; no built-in check | yes (all four modes) | yes; nearest prior art |

TS consumers: `openapi-typescript` 7.13.0 (types only, `--check` for CI drift), with `openapi-fetch`
0.17.0, `orval` 8.39.0 or `oazapfts` 7.5.0 as runtime clients. Two caveats: `openapi-typescript`'s
docs say TypeScript unions "don't map directly to `oneOf`" and treat `discriminator.propertyName` as
optional, so narrowing on `kind` only works if the Rust side emits literal-typed tags (`api.ts` has
three such unions); and **OpenAPI covers no WebSocket messages**, while this contract has three plus
four meaningful close codes. OpenAPI-first buys route coverage and a CI `--check` at the cost of a
lossy enum round-trip and zero WS coverage; `ts-rs` covers the envelope but not routes — so **both**.

## Options

| Option | Pros | Cons |
|---|---|---|
| **A. Extract a state container** (zustand, or a store over `useSyncExternalStore`) | kills the prop-drilling and both escape hatches; zustand is **already an r3f dependency**, so no new third-party surface; its transient-update API is what the 30 viewport `useRef`s hand-roll | does not by itself fix the viewport duplication |
| **B. Unify the two viewport components** behind one pane contract | removes ~450 lines of parallel logic and 12 duplicated props | touches the picking path, where 3 parity topics are unresolved — risk lands on the least-verified behavior |
| **C. Single `<Canvas>` with four scissored viewports** + `frameloop="demand"`/`invalidate()` | one WebGL context, one render loop, redraw on change only; r3f's own documented lever | largest blast radius: per-pane color management, backgrounds and `renderOrder` are per-Canvas today and all documented as load-bearing. `frameloop="demand"` alone is a smaller version that may capture most of the win |
| **D. Generate the wire types from Rust** instead of hand-maintaining `api.ts` | the contract stops drifting; the resolver types come from the same source as the wasm | needs the new backend first; OpenAPI covers no WS messages and round-trips tagged enums lossily, so the practical answer is two tools, not one |
| **E. Enable `strict`** (and settle whether TS 6 already does) | removes a class of uncertainty before restructuring | fallout unknown until measured; pairs with a TS 7 upgrade, since `~6.0.2` is a major behind |
| **F. Fix the doc drift** in `GUI.md` and `api.ts`'s comments | cheapest item here; stops a refactor being reviewed against a wrong reference | `dev/docs/` edits need the owner's yes per edit |
| **G. Do nothing to `web/` during the Rust rewrite** | zero risk while the backend churns; `api.ts` keeps working as long as the new backend serves the same 21 routes | drift and the god components compound; every new GUI item lands in the old shape |
| **H. Adopt a gizmo for actor transform** (drei `PivotControls`, or a `TransformControls` proxy group) | replaces the hand-rolled Ctrl-drag path with a maintained primitive that has snapping and axis constraints | drei is not a dependency and is mid-v11; single-object attach needs a proxy group; its events bypass r3f's; UED22 has no such gizmo, so it is a **departure from parity** — an owner question, not a refactor |

Sequencing (**the owner's open question in `.../questions/web-refactor-sequencing.md` — not answered here**):

| Where the refactor happens | Pros | Cons |
|---|---|---|
| **In `old/web/` in place** | nothing moves; `../bin/ensure_wasm.sh` and the golden fixture path keep working; the wasm build and parity test keep running as-is | needs an explicit ruling that the `old/` freeze (scoped to the Python binary's *behavior*, to protect the differential-testing oracle) does not extend to `web/`; leaves the frontend inside a tree whose purpose is to be deleted |
| **Move `web/` back to the new root early** | `web/` gets its own timeline, independent of verb-by-verb porting; the new root stops being Rust-only, matching the end state | breaks `prebuild`/`pretest` and the parity test's fixture path until `resolve-core`/`resolve-wasm` are reintroduced at the new root; the frontend briefly straddles two trees |
| **Move it late, after the routes are ported** | the refactor can be generated against the real new backend (option D becomes available); one move, not two | the longest period with the GUI's code frozen in `old/` |

Non-deciding facts: `web/` is not part of the strangler fallback and cannot affect
`old/bin/uedcli`'s output, so freezing it buys the oracle nothing — but its build *does* depend on
`old/uedcli-native/` (wasm) and `old/uedcli/tests/fixtures/` (golden), so moving it early moves a
dependency edge, not a leaf.

## Proposal (owner's call — not decided)

Suggested order, as a proposal: **F → E → A → B**, with D opened only once the new backend serves
real routes, C held back as its own decision, and H sent to the board rather than into a sequence.
F and E are cheap and remove uncertainty that would otherwise contaminate review of everything after.
A is the highest-value change and the only one touching no RE'd behavior. B should wait until §6's
three unresolved parity topics are closed or explicitly accepted as frozen, because it rewrites
exactly the code they govern; the noVNC bridge chore is the unblocker. C's cheap half
(`frameloop="demand"` on the existing four Canvases) can be measured before committing to the full
version. Whatever is decided, §1's table is the contract to hold fixed: it is what makes the backend
swap invisible to the frontend.

## Open questions / what to verify next

- **Does TypeScript 6.0 enable `strict` by default?** No `tsconfig*.json` under `old/web/` sets it,
  yet the code reads as if `strictNullChecks` were on. Decides whether E is one line or a migration.
- **React Compiler's effect on r3f mutation patterns is unknown** — no authoritative source found. It
  matters because the hot path lives in `useFrame` and refs, outside React's memoization scope, and
  extra re-renders are already known to break gizmos.
- **AsyncAPI as the WS-schema complement to OpenAPI was not verified** — "OpenAPI covers no WS
  messages" is spec-level reasoning, not a cited source.
- **What is the real object count per pane on a real level?** Every external performance claim is
  thresholded and nothing here counts `ScenePoly`/`SceneActor`, so the C win is unquantified.
- **Does any consumer other than `web/` read these routes?** If not, the contract can change *with*
  the frontend rather than be preserved — which changes option D's value considerably. Separately,
  `gui-copy-selected-actors-as-t3d-to-clipboard` sits in both `done/` and `to-build/`: one is stale.

## Sources

Internal, relative to the repo root: `old/dev/docs/board/to-plan/rewrite-uedcli-in-rust/spec.md` and
`.../questions/web-refactor-sequencing.md` · `old/web/src/api.ts` · `old/uedcli/serve/app.py` (21
routes + `/ws`; claim checks at 677, 873, 923, 957, 980, 1111, 1140; `_broadcast_changes_available`
306; `ws_endpoint` 1184) · `old/uedcli/serve/watch.py` ·
`old/uedcli-native/resolve-wasm/{Cargo.toml,src/lib.rs}`, `old/bin/ensure_wasm.sh`,
`old/bin/_venv.sh`, `old/.gitignore:66-68`, `old/web/src/scene/classResolver.ts` (the wasm path) ·
`old/GUI-PARITY.md` · `old/dev/docs/GUI.md` (drifted at lines 20, 25, 313) ·
`old/dev/docs/rationale/gui-editing.md` · `old/dev/docs/board/to-plan/uedcli-human-gui/spec.md` ·
`old/dev/docs/board/done/gui-reload-rebuild-slow-memoize-scene/overview.md` ·
`old/web/src/scene/RadiiOverlays.tsx:157-172` · `old/web/package-lock.json` · `dev/research/rust-workspace-architecture.md`.

External, all fetched directly (no search budget, so no blog/discussion sweep):

- npm registry `/vite/8.3.0`, `/typescript`, `/vitest/5.0.0`, `/oxlint`, `/react/19.2.8`,
  `/three/0.186.0`, `/@react-three%2ffiber`, `/@testing-library%2freact`,
  `/@react-three%2ftest-renderer` — all named versions exist; TS 7.0.2 is `latest`; r3f depends on
  `zustand ^5.0.3` + `use-sync-external-store`.
- https://github.com/pmndrs/zustand, `src/react.ts#L30` (the binding *is* `useSyncExternalStore`);
  https://r3f.docs.pmnd.rs/advanced/pitfalls and `/advanced/scaling-performance`.
- https://github.com/pmndrs/triplex + https://triplex.dev (active r3f editor);
  https://github.com/pmndrs/react-three-editor (archived 2023-03);
  https://github.com/pmndrs/react-three-fiber/issues/3274 (the only React Compiler statement found).
- https://github.com/mrdoob/three.js/blob/dev/examples/jsm/controls/TransformControls.js + three.js
  issues /25619, /15965, /30718, /19158;
  https://github.com/pmndrs/drei/blob/master/src/core/TransformControls.tsx +
  https://drei.docs.pmnd.rs/gizmos/pivot-controls + drei issues /2226, /2337, /1681, /2804.
- https://openapi-ts.dev/cli (`--check`), https://openapi-ts.dev/advanced (unions vs `oneOf`);
  `utoipa` 6.0.0 / `utoipa-axum` 0.3.0, `aide` 0.15.1, `ts-rs` 12.0.1, `specta` 2.0.0-rc.25 per
  registry/GitHub metadata and their own docs.
- **Unverified:** AsyncAPI as the WS-schema complement; practitioner consensus beyond official docs;
  React Compiler + r3f; whether TS 6.0 defaults `strict` on.
