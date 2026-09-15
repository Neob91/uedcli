# Spec — GUI Slice 2: quad layout, ortho views, organization panel, level picker

Written for a reader with no prior context. Elaborates the "P1 GUI — settled details" section of
the main spec (`dev/docs/board/to-plan/uedcli-human-gui/spec.md`) into a buildable design, and adds
one new, owner-specified requirement not previously written down: **ortho views must match `actor
diagram`'s rendering, especially selected-brush highlighting.**

## Goal and non-goals

**Goal.** Complete the P1 viewer: the classic UnrealEd quad (Top/Front/Side ortho + Perspective),
shading-mode switching, non-brush actor rendering already built extended to ortho, an organization
panel (folder tree + label facets + find), an in-GUI level picker, grid/coordinate readout, and
dark/light theme — per the main spec's "P1 GUI — settled details" section, which this spec turns
into concrete tasks.

**New requirement, settled 2026-09-14, not in the main spec:** ortho views must render brushes the
way `actor diagram` does — every brush wireframed in its own CSG-classification color (not a single
flat wire color), and a selected brush highlighted with the SAME "own vivid hue, bolder line"
treatment `actor diagram --highlight` uses and the 3D Perspective pane already implements.

**Non-goals.**
- Not Slice 3 (audit: snapshot store, semantic diff, timeline) or Slice 4 (git-read layer).
- Not P2 editing, the explicit-rebuild model (separate spec,
  `gui-explicit-rebuild-pinned-build-state-mode`, sections 1-4 land independently — this spec's mode
  gating hooks into that item's backend signal but does not re-specify it), or the saveable
  visibility-filter presets (a separate, smaller board item layered on top of this one's org panel
  once it exists).
- The "flat" shading mode's exact definition is still an open item (main spec, "Also open") —
  this spec treats it as an opaque fourth mode to wire up, not something to define here.

## Key architectural fact this spec leans on

**Ortho views are not a new rendering pipeline — they are the SAME already-built three.js scene,
viewed through a different camera.** `Viewport3D.tsx`'s `bufferGeometry`/`materials` (the solved,
textured+lit world), the marker sprites, and the brush-highlight system are all camera-agnostic
Three.js objects already. `actor diagram` is a separate, stdlib-only, offline 2D rasterizer
(`uedcli/preview.py`) that produces static PNGs — the GUI does NOT reuse its code (different tech
stack, live/interactive vs. static/offline) — it reuses its *visual conventions* (CSG-classification
colors, the highlight treatment), which the backend ALREADY computes and ships for every brush actor
today: `uedcli/serve/scene.py`'s `build_scene_payload` calls `_brush_highlight(actor, index)` **for
every actor**, not just a selected one (confirmed by reading the current code — `scene.py:224`) —
`SceneActor.brush.color`/`csg_class`/`polys` already exist client-side for every brush, right now.
The Perspective pane's `SelectionHighlight`/`BrushRingOutline` (`Viewport3D.tsx`) just currently only
*draws* this data for the selected actor — that's a frontend filtering choice, not a backend gap.

**Consequence for the new requirement:** rendering every brush in its CSG color in ortho mode needs
**no new backend field** — extend the existing draw logic to render every actor's `brush.color`
wireframe (not just the selected one) when in a CSG-colored mode, and keep the existing bolder/
highlighted treatment for whichever one is selected. This is a frontend task.

## Design

### 1. Orthographic cameras + quad layout

Add three `OrthographicCamera`-driven views (Top: looking down -Z; Front: looking down -Y; Side:
looking down -X — UE1 is Z-up, matching this codebase's existing world convention, see `camera.ts`),
each pannable (drag) and zoomable (scroll + both-button-drag per the main spec's "Camera" section),
sharing the SAME `bufferGeometry`/`materials`/marker/highlight objects the existing Perspective
`Viewport3D` builds — do not rebuild geometry per pane.

**Dependency flag (review finding): `@react-three/drei` is NOT currently a dependency**
(`web/package.json` has only `@react-three/fiber`/`react`/`react-dom`/`three`). Using its `<View>`
component (multiple viewports into one shared WebGL context) means adding a new dependency —
call this out explicitly at plan/build time (version pin, quick check it doesn't drag in unwanted
transitive weight), not silently. The alternative, 4 separate `<Canvas>` elements each re-uploading
the same geometry to the GPU, avoids the new dependency at the cost of ~4x GPU memory for one
level's geometry — a real tradeoff to make at plan time with real numbers (how big is a typical
level's buffer?), not assumed away here.

Quad grid layout (2x2), double-click a pane to maximize/restore (CSS/state only, no new rendering
logic).

**Also a real refactor, not just geometry (review finding, 2026-09-14 second pass):** today's
`Viewport3D.tsx` owns ALL pointer/drag/tap handling for its one perspective camera — `onPointerDown`/
`onPointerMove`/`onPointerUp`, `e.currentTarget.setPointerCapture`, and `requestPointerLock` on the
first real drag movement (avoiding `movementX/Y` screen-edge clamping) — in one component (lines
~501-602). An ortho pane needs the SAME lock/capture/tap-vs-drag plumbing (a different drag
INTERPRETATION — pan instead of dolly+turn — but identical DOM-level mechanics). Plan/build must
extract this plumbing into a shared hook consumed by both perspective and ortho panes, or explicitly
justify and scope a second hand-rolled copy — this section's own framing (ortho reuses everything
camera-agnostic already built) applies to the interaction layer, not only the geometry.

### 2. Ortho brush rendering — matches `actor diagram`

- **Default (non-selected) brushes in ortho panes**: wireframe, colored by `SceneActor.brush.color`
  (already shipped per-actor, confirmed by review — `_brush_highlight` runs for every actor, not
  just a selected one) — reuse the exact palette semantics already established for the Perspective
  pane's `BrushRingOutline` (`web/src/scene/Viewport3D.tsx`), just applied to every brush actor's
  `brush.polys` instead of only the selected one's.
- **Selected brush**: the existing bolder/vivid highlight treatment (already built,
  `BrushRingOutline`) — reused, drawn in ortho panes the same way it's drawn in Perspective today.
  **Real risk found in review**: `BrushRingOutline` sets `linewidth={2}` on `THREE.LineBasicMaterial`
  — WebGL (via ANGLE/OpenGL Core Profile on virtually all desktop browsers) ignores
  `LineBasicMaterial.linewidth` above 1px. `actor diagram`'s PIL-based bolder line has no such
  limit; the GUI's current implementation may already be silently rendering at 1px everywhere,
  meaning "bolder" is carried by color alone today, not width. Plan/build must either confirm the
  bolder width genuinely renders (test in a real browser, not just unit tests) or switch to a
  WebGL-safe approach (three.js's `Line2`/`LineMaterial` from the `lines` addon, which does support
  width, or a duplicated/slightly-offset second ring as a cheap width fake) — do not assume
  "reuse `BrushRingOutline` verbatim" solves this without checking.
- **Non-brush actors** in ortho panes: same marker sprites / real mesh rendering already built for
  Perspective (`markers.ts`, the sprite-texture work) — no new mechanism, just drawn through the
  ortho camera too.
- **Real refactor, not a trivial extraction (review finding)**: today's `bufferGeometry`/materials
  construction, texture-loading hooks, and ALL pointer/raycast state live inside one
  `Viewport3D` component instance that owns a single camera and a single mesh
  (`web/src/scene/Viewport3D.tsx`). Sharing one built scene across 4 camera views means hoisting
  geometry-building out of `Viewport3D` into a shared hook/context consumed by 4 separate
  camera+interaction components — plausible (the geometry-building logic, `buildGeometryData`, is
  already pure/framework-free) but a genuine restructuring of `Viewport3D.tsx`, not "just don't
  duplicate a loop." Plan this as its own task with real effort budget, not a one-liner.

### 3. Shading modes per pane

Wireframe / textured-unlit / flat / textured+lit, selectable independently per pane (`1`-`4`
keybinds per the main spec, focused-pane-scoped). Wireframe mode is what section 2 describes (CSG-
colored brush rings, no fill). The other three reuse the EXISTING `resolveMaterialState`/
`buildGeometryData` machinery already built for Perspective — no new material logic, just make sure
it's driven by a per-pane mode state instead of being Perspective-only. **Gating**: textured-unlit /
flat / textured+lit require a solved build (per the explicit-rebuild spec's mode-gating signal,
landing independently) — wireframe is always available (renders from `ScenePoly`/`brush.polys`
data, no solve dependency, matching the explicit-rebuild spec's own "wireframe always available"
rule). This spec consumes that gating signal; it does not redefine it.

### 4. Non-brush actor meshes in ortho

Already built for Perspective (mesh-actor triangles via `owner`-tagged polys, point-actor sprite
markers). Ortho panes draw the same objects through their own camera — no new mechanism.

### 5. Organization panel

Folder tree (primary hierarchy, `SceneActor.folder`) + label filter facets (`SceneActor.labels`,
OR-combined toggle chips, mirroring `actor find --label`) + a find box mirroring `actor find`
(name/class glob, folder globstar, label glob). "(no folder)"/"(no label)" nodes reach the unset
sets. Selecting a folder-tree node REPLACES the current selection with that folder's full actor set
(mirroring a plain viewport tap's replace semantics) and frames their union bbox; Ctrl-clicking a
folder node ADDS its actors to the current selection instead (mirroring Ctrl+tap's additive
semantics, section 9). This is now literally a multi-actor selection, not a single-actor
camera-framing gloss — see section 9, which section 5 depends on (review finding, 2026-09-14 second
pass: the org panel's selection behavior can't be pinned down before section 9's selection model
exists).

**Focus-search keybinding (review finding, third pass: settled in the main spec, absent here).**
The main spec's "Keybindings" section settles "`/` or `Ctrl+F` focus search" — this is the org
panel's own find box. In scope for this slice: pressing `/` or `Ctrl+F` (preventing the browser's
own find-in-page) focuses the find box, unless a text input already has focus (so `/` typed while
already typing a query does not steal focus from itself). No new mechanism — the find box and its
keydown handling are part of this section's own scope.

### 6. Level picker

**Rewritten after review — the first draft's recommendation didn't work.** It proposed "the picker
triggers a client-side navigation/reload against a `?level=` query param, and `create_app` reads it
fresh" — but `uedcli/cli/commands/serve.py` calls `create_app(project, args.level)` exactly ONCE at
process startup, then `uvicorn.run(app, ...)` serves that one object for the process's whole
lifetime. A browser reload cannot re-invoke Python `create_app` or restart the process — that
recommendation was simply wrong, not just an alternative to a bigger option.

**The real scope is also smaller than the first draft's two options implied** (review finding):
`/api/level/{level_name}/scene`, `/atlas`, `/lightmap` (`uedcli/serve/app.py`) are **already
parameterized per-request** by `level_name`, validated by `_require_level` against `maps_root` —
independent of the `level` argument `create_app` was given at startup. They can already serve ANY
level in the project today with zero changes. Only three things are actually bound to the
startup-time `level`: the `TrunkWatcher(maps_root / level, ...)` instance, `/api/health`'s reported
`level`, and the WS reload message's `level` field. (`create_app`'s own docstring — "fixed for the
app's lifetime" — is stale relative to its routes; don't trust it without checking the routes, as
the first draft of this spec didn't.)

**Design:** add in-process, explicit level-switch state: a small mutable "current level" holder in
`create_app`'s closure (same holder-cell pattern as the scene-cache spec's `_trunk_ref`/
`_geometry_ref`), a new route (e.g. `PUT /api/level` or `POST /api/switch-level`) that validates the
requested level exists, stops and restarts `TrunkWatcher` bound to the new level's directory, and
updates the holder — no process restart, no page reload trick. `GET /api/levels` enumerates
available levels: **reuse `uedcli/cli/level_sources.py`'s existing `list_levels(maps_dir)`** (already
used by the `level list` CLI verb, `uedcli/cli/commands/level.py`) — do not write a second
enumeration (review finding: the first draft didn't mention this existing function and risked
reinventing it).

### 7. Grid & coordinates

Ortho panes: an adaptive Unreal-Units grid (denser as you zoom in, coarser as you zoom out — a
standard log-scale grid-spacing algorithm, no UE1-specific fact needed) and a UU coordinate readout
following the cursor (project the cursor's ortho-plane position back to world UU). Selected actor's
location/size shown. Grid visibility toggle.

### 8. Theme

Dark-first (already the de facto look from today's live demo work) with a light + system-follow
toggle, and the semantic color tokens already specified in the main spec (added=green, removed=red,
prop/moved=amber, poly/retextured=violet, order=teal, folder=blue, label=magenta, other=gray,
selection=cyan/white) — these are Slice 3 (audit) colors, wire the TOKENS now (a CSS/theme-variable
system) even though nothing uses most of them until Slice 3 lands, so Slice 3 doesn't need a parallel
theme-system change later.

### 9. Selection & inspector — multi-select, frame, deselect

**Added 2026-09-14, second review pass.** The main spec's "P1 GUI — settled details" section already
settles this (not something this spec invents): "**Selection & inspector**" says "LMB tap ... selects
in any pane; Ctrl+tap multi-selects; ortho marquee; ... One selection, highlighted across all four
panes + tree + inspector"; "**Keybindings**" adds "`F` frame selected; ... `Ctrl+click` multi-select;
`Esc` deselect." Slice 2's own goal is "completes the P1 viewer" — omitting a settled P1 requirement
here would leave the viewer incomplete, not merely trim scope.

**In scope for this slice:**
- **Ctrl+tap (touch) / Ctrl+click (mouse) multi-select**: toggles one actor's membership in the
  current selection (add if absent, remove if present). A plain tap/click REPLACES the selection with
  just the tapped actor. A tap/click that hits nothing (no actor under the cursor) is now a no-op —
  it does NOT clear the selection (see "Esc", below); neither settled paragraph mentions
  click-away-to-deselect, and overloading a miss to mean "deselect" would collide with `Esc`'s own,
  explicitly separate binding for that.
- **`F` frames the current selection**: the union bbox of every selected actor (one actor today,
  several once multi-select is used) — the SAME framing mechanism section 5's folder-node selection
  now uses.
- **`Esc` deselects**: clears the selection entirely. The only deselect path (see above).
- **Multi-actor highlight, consistent across all four panes**: every selected actor's ring (brush) or
  box (non-brush) draws in the bold/highlighted treatment already built for one actor (spec section
  2) — extended to draw one such ring/box per selected actor, not just one.
- **Inspector**: 0 selected → today's "No selection"; exactly 1 → today's full detail view,
  unchanged; 2+ → a lightweight summary (actor count + names) — neither settled paragraph defines the
  N-selected inspector view, so this is a judgment call, flagged for confirmation (plan's Open
  Questions).

**Deferred, explicitly, not silently (review finding: full scope was too large to fold in safely
alongside everything else in this slice): ortho marquee drag-select.** Filed as its own board item,
`dev/docs/board/inbox/ortho-marquee-drag-select-rubber-band-multi/`. Two reasons this one piece
doesn't fit here even though the main spec settles it as P1:
1. It needs a genuinely NEW mechanism — projecting every candidate actor's AABB into an ortho pane's
   screen space and testing it against a dragged rectangle — nothing in this codebase does that kind
   of projection today (`selection.ts`'s existing pickers resolve one screen POINT to an actor, never
   a region).
2. It collides with an ALREADY-SETTLED camera binding this same main spec fixes: "Ortho: drag-pan +
   both-button-drag zoom" (the "Camera" paragraph) already claims plain drag for panning. Classic
   UnrealEd uses plain LMB-drag for marquee in ortho views and a different gesture for pan — which
   button/modifier triggers which here is a genuine unresolved fork, not a planning-time detail this
   spec can pick silently. It needs an explicit owner ruling before it can be planned, let alone built.

Every OTHER piece above (Ctrl+add, `F`, `Esc`, multi-highlight) needed no new interaction-model
decision — they compose cleanly out of mechanisms this slice already builds (the shared drag hook,
section 1; `buildBrushRings`, section 2; `unionBBox`/frame, section 5) — so they stay in scope.

## What is open / left to planning

- Exact `@react-three/drei` `<View>` API usage and whether it handles 4 independent orthographic
  cameras + 1 perspective cleanly, or whether 4 separate `<Canvas>` elements (accepting the
  duplicated-upload cost) is simpler/more robust in practice — a real technical spike may be needed
  at plan/build time; note it, don't guess the answer here.
- The adaptive-grid exact spacing algorithm (log-2 vs log-10 steps) — cosmetic, planning-time.
- Level-picker backend shape (`GET /api/levels` exact response) — planning-time detail.

## Testing

- Frontend: extend `web/src/scene/geometry.test.ts`/new tests for the shared "draw every brush's
  CSG ring" extraction (section 2) — pure logic, testable without WebGL, matching this codebase's
  established pattern (`camera.ts`, `markers.ts`, `touchGesture.ts` are all pure/tested this way).
  Org-panel folder/label filtering logic (pure set operations) similarly testable without a DOM.
- Backend: a test for the new `GET /api/levels` endpoint (section 6).
- Cross-pane consistency (section 9's own stated acceptance criterion): an RTL test rendering the
  quad layout and asserting all four panes' selection-highlight props stay in sync after a selection
  change originating from any one pane — the automated half of the manual proof below.
- Manual/live verification (per `dev/docs/rules/building-features.md`'s "run the new behavior and
  watch it work"): load a real level with the quad layout, confirm all four panes show consistent
  geometry, confirm a brush selected in ANY pane highlights identically (CSG color, bolder) in ALL
  FOUR panes simultaneously — this is the concrete, observable proof the new requirement is met.

## Revision history

- First adversarial review (2026-09-14) found section 6's level-picker recommendation
  technically broken (a page reload cannot re-invoke `create_app`/restart the uvicorn process) and
  its scope misdiagnosed (the scene/atlas/lightmap routes are already level-parameterized; only the
  watcher and two cosmetic fields are level-fixed) — rewrote section 6 with a real mechanism
  (in-process level-switch state + watcher rebind) and pointed at the existing
  `level_sources.list_levels` instead of a new enumeration. Also flagged: `@react-three/drei` is a
  genuinely new dependency (not previously noted as one), the "extract into a shared component"
  claim undersold a real `Viewport3D.tsx` restructuring, and `BrushRingOutline`'s `linewidth={2}`
  likely renders as 1px on WebGL (a real risk to the "bolder line" half of the actor-diagram-parity
  requirement) — all three now called out explicitly rather than assumed trivial.
- Second adversarial review (2026-09-14) found 4 more gaps, fixed here: (1) section 1 didn't address
  that pointer-lock/capture/tap handling, not just geometry, lives inside `Viewport3D.tsx` and needs
  the same hoist-or-justify treatment — added a bullet requiring a shared drag hook or an explicit
  second copy. (2) neither this spec nor the plan mentioned the main spec's settled Ctrl+tap/
  Ctrl+click multi-select, ortho marquee, or `F`/`Esc` keybindings at all, despite this slice's own
  goal being "completes the P1 viewer" — added new section 9 (Ctrl+add-to-selection, `F` frame, `Esc`
  deselect, multi-actor cross-pane highlight) and rewrote section 5's selection sentence to depend on
  it instead of a vague "multi-actor set" aside. Ortho marquee-select is explicitly DEFERRED (not
  silently dropped) to its own board item,
  `dev/docs/board/inbox/ortho-marquee-drag-select-rubber-band-multi/` — it needs both a new
  screen-projection mechanism and an owner ruling on a real button-binding conflict with the
  already-settled ortho drag-pan gesture, neither a planning-time detail this spec can decide alone.
  (3) added a cross-pane consistency automated test to the Testing section (the spec's own
  acceptance criterion previously had only a manual verification step). (4) the plan's Task 18 named
  `preview_cache.py` as the source of the `_trunk_ref`/`_geometry_ref` holder-cell pattern — that
  pattern actually lives in the sibling scene-cache item's plan; corrected there (this spec never
  named the wrong file directly, so no spec.md text changed for this one).
- Third adversarial review (2026-09-15) found one gap in this file: the main spec's settled `/`/
  `Ctrl+F` focus-search keybinding had zero mentions here despite section 5 (org panel) being exactly
  where its find box lives — added a paragraph to section 5 folding it in as in-scope, no new
  mechanism needed. (The pass's other three findings — Task 25 needing `async def`, Task 4's tap
  gate, Task 26's `reload.ts` ambiguity — are plan-level task detail with no corresponding spec.md
  text to change.)
