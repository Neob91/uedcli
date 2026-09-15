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

## Level switching — unload old, block, then load new

`LevelPicker.tsx`'s dropdown only reports which level was picked; `App.tsx` owns the switch itself
(`handleSwitchLevel`): the moment a switch starts it clears `scene`/`atlas`/`lightmap`/`status`/
selection (so no stale geometry lingers) and sets `levelSwitching`, which makes the app's own
`!scene` render gate — already used for the initial load — show a `"Switching level…"` message
instead of the whole app, unmounting toolbar/viewport/org-panel/picker until the new level's full
state (scene+atlas+lightmap) has loaded. If the `PUT /api/level` call itself fails, the old level's
state is refetched and restored rather than leaving the app blocked. This is a broader blast radius
than Load/Rebuild's `reloading` badge (which leaves the UI interactive): a level switch invalidates
the picker/org-panel/selection too, not just built geometry.

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
atlas. **`'flat'` and `'unlit'` are distinct** (`shadingMode.ts`'s `usesUnlitMaterials`): `'flat'`
no longer falls through to `'lit'`'s branch — fixed and regression-tested (`shadingMode.test.ts`).

## Movers

A Mover actor (`Engine.Mover` or a subclass — `SceneActor.is_mover`, the server's authoritative
`movers.is_mover` answer) always renders **wireframe-outline-only**, in every shading mode, including
`'lit'`/`'unlit'`/`'flat'` in the perspective pane — a stronger default than an ordinary brush, which
follows the pane's own shading mode. Ortho panes are always wireframe anyway, so a Mover there is
unaffected either way. This is deliberate: an animated Mover's solid geometry (a door, elevator, or
platform) clutters the view at its BASE pose and isn't what most editing tasks need to see.

`SceneResourcesContext.tsx` builds a Mover's solved polys into a SEPARATE `moverGeometry`/
`moverMaterials`, split out of the default `bufferGeometry`/`materials` every pane draws
unconditionally in a non-wireframe mode — so a Mover's solid triangles never ride the default mesh.
`brushRings.ts`'s `buildBrushRings` always includes a Mover's outline ring in `'selected-only'` mode
(the mode a non-wireframe pane uses for brush outlines), even when the Mover isn't selected — an
ordinary unselected brush gets no ring there.

**The `Movers:` toolbar toggle** (`QuadLayout.tsx`, next to `Grid:`/`Radii:`) shows/hides a Mover's
SOLID geometry, default off:

- **Off** (default): wireframe outline only, as above.
- **On**: ALSO draws the Mover's solid geometry (textured/lit per the pane's mode), in ADDITION to
  the wireframe outline — the outline never disappears when solid is shown.
- Only visible in non-wireframe panes/modes — an ortho pane (always wireframe) shows no change,
  which is expected, not a bug.
- The button stays enabled regardless of the focused pane's current mode: a click still flips the
  stored toggle, which matters the instant that pane switches to a non-wireframe mode. Unlike
  `ModeSelector`'s `buildSolved` gating, this button is never disabled/greyed based on pane state.

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

The world is left-handed (X forward, Y right, Z up), but its raw coordinates feed three.js's
right-handed renderer verbatim (no axis flip anywhere) — so a camera built from a plain, proper
rotation necessarily renders this world's `right` on the wrong screen side (confirmed live: a
world-space arrow pointing along `right` rendered on the opposite side from a `level photo
--native` render of the same pose). Building the rotation directly from `(right, up, -forward)` via
`Matrix4.makeBasis` — the obvious fix — makes it worse: that matrix is IMPROPER (determinant -1,
since `cross(right, up) == forward` here, not `-forward`) for both `Viewport3D.tsx`'s perspective
basis and `OrthoViewport.tsx`'s ortho bases, and an improper matrix breaks both ways of applying
it — `quaternion.setFromRotationMatrix` silently decomposes it into a camera facing a WRONG
direction (not merely mirrored), and writing `camera.matrix`/`matrixWorld` directly looks the right
way but still projects every point through a mirror (a determinant-(-1) transform is a reflection,
full stop).

The shipped fix (`Viewport3D.tsx`'s `applyCameraPose`, `OrthoViewport.tsx`'s
`applyOrthoCameraPose`) keeps the view/rotation step ordinary and proper — `camera.up.set(...)` +
`camera.lookAt(...)`, three.js's own well-tested code, always a valid rotation — then mirrors the
PROJECTION matrix's NDC-x term instead (`projectionMatrix.elements[0] *= -1`, with
`projectionMatrixInverse` kept in sync the same way since click-to-select unprojects screen points
through it). `lookAt` derives screen-right as `cross(up, eye-target)`, which for every camera basis
here is the exact negation of the intended `right`/`orthoBasis.right` — but negating the
projection's NDC-x term restores the intended screen-right without touching the already-correct
look direction, so pan direction comes out right too. **Ortho drag-to-pan (owner ruling,
2026-09-15): the view moves WITH the drag** — dragging left reveals what's on the left, the
opposite of mobile-style "content follows the finger" scrolling (`orthoPan`). A world-fixed point
already on screen therefore slides opposite the drag.

## The world-anchored grid

`web/src/scene/grid.ts`'s `orthoGridWindow` computes the ortho grid's line-placement bounds in
**absolute world u/v** (the camera center's own projection onto the axis basis), not a window
centered on 0 — otherwise the grid slides with the camera instead of staying locked to geometry.
`gridSpacingUU` snaps to a 1-2-5-10-per-decade sequence targeting ~50px on-screen spacing.

**Grid color**: `GridOverlay.tsx`'s `GRID_COLOR` is `0x808088`. It was `0x3a3d4a` (~58,61,74),
nearly the same brightness as the ortho background (`#404040`, 64,64,64) and effectively invisible
— unlike `preview.py`'s grid, this one has no major/minor tiering (below), so a single flat color
needs real contrast against the background on its own.

**Open, unreconciled with `preview.py`**: `preview.py`'s own grid (`_grid_escalation`,
`_grid_line_color`, ported from disassembled `UEditorEngine::DrawGridSection`) snaps to
power-of-two steps and gives every 8th line a distinct "major" color with odd-line fade-before-drop.
The GUI's grid has none of that tiering and a different step algorithm — `grid.ts`'s own comment
already flags this as "flagged for owner confirmation, not treated as final." Needs an explicit
decision (port `preview.py`'s algorithm for real parity, or confirm the GUI's own convention is
intentional), not a silent implementation choice either way.

## Ortho-pane draw order (grid / brushes / point actors)

Three layering rules for the ortho panes (owner ruling), all enforced via three.js `renderOrder`
(lower draws first) since every layer here uses `depthTest={false}` — with depth testing off,
draw order among siblings is otherwise scene-graph/insertion order, not guaranteed:

- **Grid is always bottom-most.** `GridOverlay`'s `<lineSegments>` sets `renderOrder={-10}` (and
  `depthWrite={false}`, so its own arbitrary plane depth can never block a depth-tested sibling
  drawn after it) — lower than everything else in the pane.
- **Point-actor markers are always on top of brushes.** `OrthoViewport.tsx`'s marker `<sprite>`s use
  `depthTest={false}` and `renderOrder={MARKER_RENDER_ORDER}` (10) — higher than brush outlines'
  default renderOrder (0), so a marker never gets hidden by a brush wireframe/highlight regardless
  of actual world depth along the view axis. Scoped to the ortho panes only; the perspective pane's
  markers are unchanged.
- **Brushes draw in CSG order.** `brushRings.ts`'s `buildBrushRings` sorts actors by `csg_rank`
  before building rings, so coincident/overlapping brush outlines resolve to the higher-CSG-rank
  actor's color — matching `SceneActor.csg_rank` (see the Inspector section above), not whatever
  order the `actors` array happens to arrive in.

## Selection & the Inspector

- **Hit-testing**: in wireframe/ortho mode, a brush is selectable only by clicking its outline
  lines — never its filled interior/silhouette (matches UED22; a bounding-box fallback there was a
  real, fixed bug).
- **Vertex + pivot markers** (`SelectionMarkers.tsx`) port `preview.py`'s `_draw_vertex_dot`/
  `_draw_pivot_marker`: a small square dot (`VERTEX_DOT_SIZE = 2` world units — tuned down from an
  earlier `6`, which read as an oversized blob against the 2px selection outline) per poly vertex in
  the brush's own brightened CSG wire color, plus a red (`_PIVOT_RED`, `(255,63,63)`) crosshair+square
  at the actor's true `Location`. A third dot, the same square glyph as the poly vertices, marks the
  brush's PrePivot-shifted "local origin" (`BrushHighlight.local_origin`, `Location - R·PrePivot`,
  computed server-side in `scene.py`'s `_brush_highlight` the same way `preview.py` does — coincides
  with the pivot only when `PrePivot=0`). This dot renders for at most ONE actor even when several
  brushes are selected: UED22's real GUI has exactly one pivot WIDGET per selection (it drops onto
  whichever actor a human click lands on, not one per selected actor —
  `dev/docs/spikes/2026-06-19-multiactor-rotate-groundtruth.md` "Pivot caveat"). `selectionSet.ts`'s
  `primarySelection` (the last name in the selection Set's insertion order — `toggleSelection` always
  appends a freshly-selected name last) stands in for "the actor last clicked." The pre-existing red
  pivot crosshair still renders per selected actor; the same real-UED22 evidence suggests it may have
  the same one-widget-per-selection mismatch, not yet addressed here.
- **The pivot marker is a gizmo, not a geometry marker**: it holds a constant on-screen pixel size
  regardless of zoom/distance (`PivotMarker`'s per-frame rescale from live camera/viewport state via
  `worldUnitsPerPixelAt`), unlike the vertex dots, which stay world-scaled (they mark a precise
  point on already-drawn geometry).
- **Selection line width**: 2px, matching `preview.py`'s real `weight=2` for a highlighted edge —
  not a rounder "looks about right" value.
- **Surface highlight**: a selected brush's drawn surface brightens (`SelectionHighlight.tsx`), an
  additive-white overlay over just that brush's own triangles (`selectedTriangles.ts`'s
  `selectedTriangleIndices`, filtered from `sceneResources.ts`'s `triangleOwners`) — a brightness
  boost on the actor's own material/hue, not a new tint color, matching `BrushOutlines`' "same hue,
  just bolder" selected-ring convention. Real UnrealEd's exact selected-surface render rule isn't
  pinned by a citable fact in `unrealed/quirks.md`/`rendering.md` (checked); this is the closest
  citable in-codebase convention. Only drawn when the mode also draws the solid mesh (not
  `'wireframe'`, which has no surface).
- **Brush-selection click modifier is SHADING-MODE-gated, not viewport-gated** (corrected owner
  ruling 2026-09-15 — an earlier pass had this backwards as 3D-vs-2D): in **wireframe** mode, plain
  LMB selects a brush directly — true in every ortho pane (always wireframe) and in the perspective
  pane whenever it's in wireframe mode too. In a **non-wireframe** perspective mode (`unlit`/`flat`/
  `lit`), a brush needs **Shift+LMB**, because plain LMB-drag there is camera-fly (dolly+turn) and
  would otherwise be ambiguous with an incidental camera nudge. Point actors are unaffected — always
  plain-tap-selectable everywhere. `selection.ts`'s `canSelectBrushTap(mode, shiftKey)` is the gate;
  `dragGesture.ts`'s `onTap` threads the release-time `shiftKey` for it.

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

- No sound-range overlay (`preview.py --show sound-range` has no GUI equivalent). Collision-cylinder
  and light-radius overlays are built (`RadiiOverlays.tsx`, `radiiProjection.ts`,
  `SceneActor.radii`/`uedcli/serve/scene.py::ActorRadii`) — a global toggle (`QuadLayout`'s
  `Radii:` button, default off) that, when on, draws radii only for the currently-selected actor(s)
  (nothing selected draws nothing), in both 3D and every 2D ortho pane.
- Grid major/minor tiering (above).

## Future direction (not yet scoped)

Owner note: the Inspector should be able to show **effective** props (own + inherited class
defaults resolved), let the user hide a prop whose value equals its class default, and visually
flag a shown value that IS the class default. Not built, no spec yet — noted here so it isn't lost.
