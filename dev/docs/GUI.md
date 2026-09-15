# uedcli GUI — architecture & conventions

`uedcli serve` (FastAPI, `uedcli/serve/`) serves a read-mostly JSON API over a level's built
scene/wireframe/atlas/lightmap; `web/` (React + react-three-fiber/three.js) renders it in a
browser as a classic UnrealEd-style quad view. This doc is the durable reference for how the GUI
is built and why — see `dev/docs/board/` for in-flight and open items, `uedcli/preview.py` for the
offline `actor diagram` renderer this GUI is calibrated against wherever the two overlap.

## Explicit Load/Rebuild — no auto-build

Geometry never builds automatically. `GET /scene`/`/atlas`/`/lightmap` are read-only; only
`POST /rebuild` runs the CSG+lighting solve (`uedcli/serve/app.py`'s `_build_and_publish_geometry`).
`POST /load` re-reads the trunk without solving. The toolbar (`App.tsx`'s `BuildToolbar`) shows
"Reload" only when the trunk has diverged from what the GUI has loaded (`status.changes_available`)
and "Rebuild" always. This mirrors real UnrealEd: opening a level doesn't rebuild its BSP, and the
GUI must not pretend otherwise.

## Layout: the classic quad

`web/src/scene/QuadLayout.tsx` renders Perspective + Top/Front/Side ortho panes in a 2x2 CSS grid
(default view, not opt-in) with drag-to-resize splitters between rows/columns (plain component
state, not persisted). Double-clicking a pane maximizes/restores it. Per-pane shading mode defaults
(`DEFAULT_MODES`): Perspective opens `'lit'`, the three ortho panes open `'wireframe'` — their
long-standing UnrealEd role, not merely feature parity.

## Shading modes

`web/src/scene/shadingMode.ts` defines four: `'wireframe'` (always available — draws from
`ScenePoly`/`brush.polys` directly, no solve dependency), `'unlit'`, `'flat'`, `'lit'` (all three
need a solved build, else the pane falls back to `'wireframe'` — `resolveEffectiveMode`). Keys
`1`-`4` set the focused pane's mode.

**Owner ruling: the ortho panes can never change mode — they are always `'wireframe'`.** Only the
perspective pane can switch (`canChangeMode`, `applyModeKey`'s own check); the visible
`ModeSelector` control (below) isn't even rendered for an ortho pane, since there's no choice to
make. This is a real constraint, not just a default — don't reintroduce a path (keyboard or click)
that lets an ortho pane's mode change.

`'unlit'` reproduces `preview.py --mode fullbright`'s flat `_KEY_LIGHT`-dot-product shade with the
lightmap dropped (`sceneResources.ts`'s parallel `unlitMaterials` array, same geometry/group
indexing as `materials`, built once and shared across panes). `'lit'` samples the baked lightmap
atlas. **`'flat'` is currently dead code** — it falls through to the same branch as `'lit'` instead
of `'unlit'`, contradicting its own doc comment; open bug, not yet fixed.

## Rendering: backgrounds, color management

- **2D ortho panes**: `#404040` (`OrthoViewport.tsx`'s `<Canvas>`), matching `actor diagram`'s own
  `BG = 64` (`preview.py`, owner ruling 2026-08-30 — deliberately not pure black).
- **3D/wireframe perspective pane**: pure black (`Viewport3D.tsx`), matching real UED22.

Both are explicit `<color attach="background">` on the Canvas, not left to CSS — a transparent
canvas over the wrong CSS layer is a real, previously-shipped bug class here.

**Color-management gotcha (load-bearing, easy to reintroduce):** every `<Canvas>` in this app MUST
spread `CANVAS_COLOR_MANAGEMENT` (`Viewport3D.tsx:63`, `{ flat: true, linear: true, legacy: true }`).
React-three-fiber's `configure()` reasserts `THREE.ColorManagement.enabled` — a **process-wide
singleton** — on every render of every mounted Canvas. One Canvas that omits this constant silently
flips it back for every OTHER Canvas too, brightening baked textures and darkening hardcoded color
literals (`THREE.Color(hex)`) away from their true values. This isn't per-component isolation; it's
global mutable state fought over on every frame.

## Camera & projection

`web/src/scene/orthoCamera.ts`'s `ORTHO_BASIS` is calibrated against `preview.py`'s own
`_DEPTH`/`_framing` (never re-derive from scratch): **top** looks down -Z (+X screen-right, +Y
screen-down); **front** looks along +Y ("looking south", +X screen-**left**, +Z screen-up);
**side** looks along +X ("looking east", +Y screen-right, +Z screen-up).

Ortho drag-to-pan: content follows the cursor (`orthoPan`). Build the camera's rotation via
`Matrix4.makeBasis(right, up, -forward)`, **not** `camera.up` + `lookAt` — `lookAt` derives
screen-right as `cross(up, eye-target)`, which is the exact negation of `orthoBasis.right` for
every one of the three axes here, silently inverting horizontal pan.

## The world-anchored grid

`web/src/scene/grid.ts`'s `orthoGridWindow` computes the ortho grid's line-placement bounds in
**absolute world u/v** (the camera center's own projection onto the axis basis), not a window
centered on 0 — otherwise the grid slides with the camera instead of staying locked to geometry.
`gridSpacingUU` snaps to a 1-2-5-10-per-decade sequence targeting ~50px on-screen spacing.

**Open, unreconciled with `preview.py`**: `preview.py`'s own grid (`_grid_escalation`,
`_grid_line_color`, ported from disassembled `UEditorEngine::DrawGridSection`) snaps to
power-of-two steps and gives every 8th line a distinct "major" color with odd-line fade-before-drop.
The GUI's grid has none of that tiering and a different step algorithm — `grid.ts`'s own comment
already flags this as "flagged for owner confirmation, not treated as final." Needs an explicit
decision (port `preview.py`'s algorithm for real parity, or confirm the GUI's own convention is
intentional), not a silent implementation choice either way.

## Selection & the Inspector

- **Hit-testing**: in wireframe/ortho mode, a brush is selectable only by clicking its outline
  lines — never its filled interior/silhouette (matches UED22; a bounding-box fallback there was a
  real, fixed bug).
- **Vertex + pivot markers** (`SelectionMarkers.tsx`) port `preview.py`'s `_draw_vertex_dot`/
  `_draw_pivot_marker`: a small square dot per poly vertex in the brush's own brightened CSG wire
  color, plus a red (`_PIVOT_RED`, `(255,63,63)`) crosshair+square at the actor's true `Location`.
  Known gap: `SceneActor` carries no `PrePivot`, so the separate PrePivot-shifted origin dot isn't
  reproduced (coincides with the pivot only when `PrePivot=0`).
- **The pivot marker is a gizmo, not a geometry marker**: it holds a constant on-screen pixel size
  regardless of zoom/distance (`PivotMarker`'s per-frame rescale from live camera/viewport state via
  `worldUnitsPerPixelAt`), unlike the vertex dots, which stay world-scaled (they mark a precise
  point on already-drawn geometry).
- **Selection line width**: 2px, matching `preview.py`'s real `weight=2` for a highlighted edge —
  not a rounder "looks about right" value.

**Inspector props/categories** (`web/src/panels/Inspector.tsx`): draws exactly what the backend
sends, no model logic of its own — `SceneActor.props`/`.categories` (parallel arrays) are the raw
stored T3D property list plus its resolved UnrealEd category, grouped into collapsible sections.
`Location` is a deliberate exception: `uedcli/model.py`'s T3D parser keeps `Location` OUT of
`Actor.props` (the typed `actor.location` field is the sole source of truth, so a stored-props copy
can't drift from it when a move/rotate verb mutates it) — but it's still a bona-fide property, so
`scene.py`'s `_with_synthetic_location` prepends it server-side, in the same `(X=..,Y=..,Z=..)`
syntax `emit.py`'s `fmt_loc` writes, under UnrealEd's real "Movement" category. The synthesis lives
at the wire boundary, never in the frontend — the Inspector's whole design point is staying dumb.

## Known open gaps (not yet built — see `dev/docs/board/`)

- `'flat'` mode dead code (above).
- Translucent/modulated materials don't set `depthWrite: false` — can incorrectly occlude geometry
  drawn after them (`sceneResources.ts`'s `resolveMaterialState`).
- No sound-range overlay (`preview.py --show sound-range` has no GUI equivalent). Collision-cylinder
  and light-radius overlays are built (`RadiiOverlays.tsx`, `radiiProjection.ts`,
  `SceneActor.radii`/`uedcli/serve/scene.py::ActorRadii`) — a global toggle (`QuadLayout`'s
  `Radii:` button, default off), in both 3D and every 2D ortho pane.
- Grid major/minor tiering (above).

## Future direction (not yet scoped)

Owner note: the Inspector should be able to show **effective** props (own + inherited class
defaults resolved), let the user hide a prop whose value equals its class default, and visually
flag a shown value that IS the class default. Not built, no spec yet — noted here so it isn't lost.
