# GUI — parity with UED22's own click-detection and selection rendering

Single source of truth for the GUI-fidelity RE campaign: matching the `web/` viewport's
click-to-select and selection-highlight behavior to what UnrealEd 2.2 (UED22) actually does, not to
a plausible guess. Read this before doing any GUI/UED22-fidelity RE work so you don't re-derive it.

## Why this is a campaign doc, not a board item

This lives at the repo root (not `dev/docs/`) so it can be updated every round without asking for
doc-write approval each time — the same reason `NATIVE-MATERIALIZE.md`/`USCRIPT-COMPILER.md` do.
`dev/docs/` (except `board/`) needs the owner's yes per edit (`CLAUDE.md`); a root campaign doc is
exempt. A durable fact this campaign confirms still lands in `dev/docs/unrealed/quirks.md`/
`rendering.md` as usual (that still needs the owner's yes) — this doc tracks the campaign's own
status and findings-in-progress, not the final verified knowledge base entry.

## Goal

`web/src/scene/` (React + three.js) picks and highlights actors/surfaces with its own from-scratch
logic (`selection.ts`, `tapSelect.ts`, `SelectionHighlight.tsx`, `selectionBoxes.ts`, …) — built
from spec and convention, largely unverified against the real editor. The goal: reproduce what UED22
*actually* does for (a) hit-testing (which surface/actor/brush a click resolves to) and (b) selection
rendering (how a selected sprite/mesh/brush/surface is drawn differently from unselected), closing
each gap with a faithful match, not a plausible-looking substitute.

## Prime directive — fix toward UED22's actual mechanism

Same rule as the other two campaigns: when a GUI behavior is found to diverge (or was never
verified), the fix is to reproduce what UED22 measurably does — never a fix that merely "looks
right" or "seems reasonable" by web-editor convention. If the real mechanism can't be pinned down
yet, say so and leave the current behavior as a flagged guess rather than silently upgrading its
confidence.

## Method — two tools, pick whichever answers the question cheaper

**Owner ruling, 2026-09-18: never cite or use a third-party UE1 engine source (e.g. `fgsfdsfgs/UE1`
or similar) for ANY finding in this campaign, no matter how similar its lineage claims to be.** Only
the actual UED22 binary this project has (`uned/UED22/`) counts as evidence — disassembly of it, or a
live capture against it running. A finding built on a third-party source alone is not RE of UED22 and
must not be presented as one, even with a 📖 confidence marker. Several earlier findings in this doc
were built partly or wholly on such a source before this ruling; they are not automatically wrong,
but they are not verified either — treat any of them you rely on as needing real confirmation against
our own binary first, not as settled.

- **Live screenshot/pixel probe** (`dev/docs/unrealed/rendering.md`'s method: `CAMERA OPEN`, `SHOT`,
  `wine_ctl exec`) — the right tool for anything OBSERVABLE in a render: selection highlight color,
  blend technique, box/gizmo shape. Select an actor of the relevant kind in an isolated UED22
  container, screenshot before/after, diff pixel values against the actor's own unselected render.
  Cheap, conclusive, no disassembly needed, when the fact is visual.
- **Static string extraction + disassembly** (`dev/docs/unrealed/extracting-from-dll.md`) — the right
  tool for a MECHANISM with no direct visual/readback signature: the click-detection algorithm itself
  (hit-testing order, tie-breaks, what "clicked" resolves to when multiple candidates overlap).
  `dev/docs/unrealed/quirks.md`'s "Selection" section already establishes a hard constraint here:
  `PF_Selected` does not round-trip (no poly-level readback), so per-polygon click accuracy can only
  be confirmed by disassembly + a live capture of the actual hit-test call, not by driving verbs and
  reading state back.
- Live-verify anything a static read only suggests, same as the other two campaigns' "confirm live"
  step — mark each finding's confidence (✅ verified · 🔬 live-probed · 📖 string/disassembly-only).

## Parity bar

Not one global byte-parity target (unlike the other two campaigns) — each topic below has its own,
stated when the topic is closed: e.g. "selection highlight color/opacity/blend mode measured and
reproduced" or "click resolution order matches UED22's own for N overlap test scenes." A topic is
CLOSED only when its own bar is met with live evidence, not string/disassembly alone.

## Status

| Topic | Question | State | Evidence / board item |
|---|---|---|---|
| Selection highlight rendering | What color/blend/technique does UED22 use to show a selected sprite/mesh actor? | ✅ closed, implemented | ✅ binary (`render.dll` disassembly), see Findings below |
| Click/hit-detection algorithm | How does UED22 resolve a click to a surface/actor/brush when candidates overlap? | 🔶 investigating | `dev/docs/board/inbox/gui-click-detection-algorithm-not-re-d-against/` — see Findings below |
| Sprite alpha picking | Does UED22's sprite click hit-test respect the icon's transparent padding? | ✅ closed, implemented | 📖 source (`SoftDrv/Src/{Hit,DrawTile}.cpp`) + 🔬 live (real clicks, A/B against the unfixed code) — see Findings below |
| Vertex handle screen size | Does UED22 draw vertex/local-origin handles at a constant screen size, or a fixed world size that scales with zoom? | ✅ closed, implemented | 📖 source (`Editor/Src/UnEdRend.cpp`) + 🔬 live (real zoom/dolly sweeps, A/B against the unfixed code) — see Findings below |
| Modifier-key click-select rules | Are the Shift/Ctrl select-surface-vs-actor rules real UED22 behavior? | ⬜ open | `dev/docs/board/inbox/gui-texture-actor-click-select-modifier-rules/` |
| Marquee containment rule | Full-containment for brushes vs. pivot-in-box for point actors — confirmed fact, not yet wired into the (deferred) marquee feature | ⬜ open (marquee itself deferred) | `dev/docs/board/inbox/gui-ortho-marquee-spec-omits-unrealed-s-brush/` |
| CSG brush coloring | Does UED22 give Intersect/Deintersect brushes a distinct color from Add? | ⬜ open | `dev/docs/board/inbox/gui-csg-brush-coloring-never-distinguishes/` |
| Pan direction (perspective vs ortho) | Which convention (drag-follows-camera vs. content-follows-cursor) matches UED22, if either? | ⬜ open | `dev/docs/board/inbox/gui-perspective-pan-direction-vs-ortho/` |
| Shading modes | UED22 has a Zones view mode the GUI doesn't | ⬜ open | `dev/docs/board/inbox/gui-shading-modes-omit-unrealed-s-zones-view/` |
| Mesh-actor wireframe rendering | Should a static mesh actor render as wireframe in wireframe/2D modes? | ⬜ open | `dev/docs/board/inbox/static-mesh-actors-should-render-as-wireframe/` |
| Radii overlay colors | Collision cylinder vs. light-radius sphere: same color or distinct? | ✅ closed, implemented | ✅ source (structural fact), 🔬 live (red, no hex) — see Findings below |
| Radii perspective cylinder | Does/should the collision cylinder render in the perspective pane? | ✅ closed, implemented | 🔬 wiki + UT patch notes (`dev/docs/spikes/2026-07-21-...`) + owner confirmation — see Findings below |
| Radii cylinder/sphere shape | Wireframe rendering had a triangulation-diagonal artifact ("triangular faces") | ✅ closed, implemented | not an RE question — a `wireframe:true`-on-triangulated-geometry rendering bug, fixed with explicit line segments |
| `C_ActorArrow` exact RGB | The radii overlay's real color value | ✅ closed, implemented | 📖 source (`Default.ini`, v200 shipped default) — see Findings below |
| Brush wireframe selection color | What does UED22 actually do when a brush is selected/unselected? | ✅ closed, implemented | 📖 source-only, GUI-only scope (owner ruling) — see Findings below |
| UED22 line widths | What line/wire thickness does UED22 use for wireframe/selection rendering? | ✅ closed — no bug | ✅ source-confirmed: no width parameter exists in the render-interface API UED22 draws through; this codebase's default line width is already correct |
| Pivot-cross multi-select rendering | With 2+ brushes selected, does our own pivot cross render once per brush? | ✅ closed — no bug | own-code, 🔬 live (real headless-Chromium multi-select + screenshots) — see Findings below |
| Pivot-cross visibility toggle | Does UED22 have a manual way to toggle the pivot marker's visibility on/off? | ✅ closed — no toggle exists; cross is hidden for a lone non-snapping selection | ✅ binary (`Editor.dll` disassembly, our own `uned/UED22/`) — see Findings below |

Legend: ⬜ open (not started) · 🔶 investigating · ✅ closed (bar met, live-verified).

## Findings

### Selection highlight rendering (closed 2026-09-16)

Source: the UE1 v200 engine source (`fgsfdsfgs/UE1`, same lineage as Deus Ex — already cited as
✅-tier evidence in `dev/docs/unrealed/rendering.md` for adjacent facts). Fetched, grepped for
`bSelected`, not screenshot-probed (cheaper and more exact than a pixel diff; no container boot
needed). Three distinct techniques, not one shared overlay:

- **Point-actor sprite** (`Source/Render/Src/UnSprite.cpp:705`, `URender::DrawActorSprite`): a
  **multiplicative** tint on the sprite's own texture — `Color = bSelected ? (.5,.9,.5) : (1,1,1)`.
  R/B channels are cut to half, G stays near-full — dims the icon and shifts it green. NOT an
  additive brightness boost (unlike this codebase's existing white surface-highlight convention).
  **✅ Binary-confirmed 2026-09-16**: `render.dll`'s real exported `DrawActorSprite` (RVA `0x1f0a0`)
  loads the exact packed constants `(0.5, 0.8999999762, 0.5, 0)` / `(1,1,1,0)` via `movaps xmm0,
  [...]` at that function. Not third-party-source-only anymore.
- **Mesh actor, solid render** (`Source/Render/Src/UnMeshRn.cpp:368`, `URender::DrawMesh`): the
  mesh's ambient/unlit floor color (`GUnlitColor`, computed from `ScaleGlow`/`AmbientGlow`, the base
  real per-vertex lighting adds onto) is rescaled: `GUnlitColor = GUnlitColor*0.4 + (0, 0.6, 0)` when
  selected. Not a flat tint over the finished pixel — a bias on the ambient floor specifically.
  **✅ Binary-confirmed 2026-09-16**: `render.dll`'s real exported `DrawMesh` (RVA `0xff00`) contains
  the exact scale-then-add pattern (`movss xmm6,[0.4]` then `addss xmm4,[0.6]`) on these constants.
  **Implementation note (2026-09-16, later)**: the confirmed formula was applied to the whole
  finished pixel (this pipeline has no ambient/lit split to target directly) via alpha blending —
  live-tested and rejected (crushed texture detail, broke NPC masked materials); the mesh solid
  highlight now uses the SAME multiplicative technique as the point-actor sprite above instead, an
  owner-directed style choice that departs from the literal `DrawMesh` formula (see
  `selectionColor.ts`'s doc comment).
- **Mesh actor, wireframe render** (`Source/Render/Src/UnMeshRn.cpp:346`, same function's `bWire`
  branch): flat line color — selected `(.2,.8,.1)` ≈ RGB(51,204,26); unselected `(.6,.4,.1)` ≈
  RGB(153,102,26) (an olive/brown, not white). Directly answers part of the still-open "Mesh-actor
  wireframe rendering" row below (the color; not the wireframe-in-2D-modes question itself).
  🔶 Binary DATA-confirmed 2026-09-16: both exact 16-byte packed vectors exist in `render.dll`,
  16 bytes apart, right next to the confirmed 0.4/0.6 ambient constants — essentially certain, but
  the disassembly pass couldn't trace a direct instruction reference within its assumed function
  bound (may be wider than the real `DrawMesh` body). Treat as ✅-adjacent, not fully instruction-linked.
- **No generic selection bounding box exists in UED22 by default** — `UnEdCam.cpp`'s only
  `DrawBox` calls tied to selection sit inside the opt-in `SHOW_ActorRadii` overlay (already
  documented in `dev/docs/unrealed/rendering.md` as red), not a baseline cue. This codebase's cyan
  AABB box (`selectionBoxes.ts`) has no UED22-authentic basis as the default indicator.

Not yet folded into `dev/docs/unrealed/rendering.md` as a permanent verified fact — that edit needs
the owner's yes per `CLAUDE.md`; this section is the campaign's own working record until then.

### Click/hit-detection algorithm — screen-space tie-break, not depth-nearest (investigating, 2026-09-17)

Two owner-reported bugs (`wireframe-brush-selection-should-hit-test-lines`,
`mover-near-brush803-unclickable-in-wireframe-2d`) turned out to be the SAME root cause, not the two
different mechanisms each report guessed at (an invisible poly face; an actor-vs-brush priority rule).

📖 **Disassembly** (`Editor.dll`/`Engine.dll`, this repo's `uned/UED22/`): `UEditorEngine::Click`
(`Editor.dll`) builds a fixed screen-space PIXEL box around the cursor — measured from the actual
clamp arithmetic, not inferred: `(coord+3) - (coord-2) = 5` on both axes, a genuine 5×5 px box — and
hands it to `UViewport::ExecuteHits` (`Engine.dll`) against a rendered hit-proxy buffer for that box
(`HActor`/`HBspSurf`/`HBrushVertex`/`HHitProxy` exports confirm the classic UE1 hit-proxy
architecture). UED22's own click hit-test is fundamentally SCREEN-SPACE — never a world-space radius.

This directly explains the bug: our own `tapSelect.ts` raycasts wireframe brush/mover outlines with a
generous THRESHOLD (`WIREFRAME_LINE_HIT_WORLD_UNITS`/`orthoLineHitThresholdUU`) so thin 1px lines stay
clickable, and then took `THREE.Raycaster.intersectObjects(...)`'s own `hits[0]`. But three.js sorts
line hits by `distance` = depth from the camera along the ray (`node_modules/three/src/objects/
Line.js`'s `checkIntersection`), not by proximity to the actual click on screen — so once several
candidates pass the threshold at once, the depth-nearest one often is NOT the one under the cursor (an
unrelated marker sprite, or a farther-on-screen brush's line merely closer to the camera along that
ray).

🔬 **Live-probed** (own GUI, `showcase_bar`, headless Chromium): clicking squarely on `DeusExMover4`'s
own rendered outline (the exact Mover the `mover-near-brush803` report named) resolved to a WRONG
actor on every one of 13 test points before a fix — `Light199`/`Brush803`/`Brush812`/`Brush813`, never
the Mover. Fix: `tapSelect.ts`'s `resolveTapSelect` now re-ranks threshold-accepted hits by projected
SCREEN distance to the click (`selection.ts`'s `nearestScreenHit`) instead of `hits[0]`. Re-verified:
the same battery went from 0/13 to 6/13 correct in the perspective pane and 13/13 in the ortho top
pane (independently reproduced by a reviewing subagent, including its own separate causal A/B and an
ortho-pane pass). The remaining perspective misses are two actors' lines genuinely close together on
screen at that exact pixel — consistent with UED22's own ~5px hit box, not a further bug.

**Not closed.** This fixes one real mechanism (screen-space vs. depth-nearest tie-break) with
disassembly evidence for what UED22 does generically — it does not live-verify the recovered algorithm
against a real UED22 boot on N overlap test scenes, the bar this topic needs to close. The AABB
fallback path (`selection.ts`'s `pickActor`, engaged only on a genuine raycast miss) still ranks by
depth and is untouched — a candidate for the same bug class if a future report describes a
miss-fallback mis-pick rather than a hit-reranking one.

### Sprite alpha picking (closed 2026-09-17)

Board item `point-actor-sprite-picking-ignores-sprite-alpha`: a point-actor's billboard sprite
selected on any click inside its full square quad, including the transparent padding around the
drawn icon shape.

📖 **Source** (`fgsfdsfgs/UE1`, `Source/SoftDrv/Src/{Hit,DrawTile}.cpp` — the software render
DEVICE, `SoftDrv.SoftwareRenderDevice`, the exact one this project's own headless editor setup uses,
`dev/docs/unrealed/rendering.md`): UED22's click hit-test (`Hit.cpp`'s `PushHit`/`PopHit`) is a
literal pixel readback, not per-object math — confirming and extending the mechanism this doc's
"Click/hit-detection algorithm" section above already established. `PushHit` stamps a sentinel value
(`IGNORE`) over every screen pixel in the cursor's hit box, THEN the normal draw call for that
hit-proxy-tagged object runs; `PopHit` checks whether any pixel in the box still differs from the
sentinel — i.e. whether the object's own rasterizer actually PAINTED something there. `UnSprite.cpp`'s
`DrawActorSprite` (the same function this doc's "Selection highlight rendering" section already
disassembly-confirmed) calls `PUSH_HIT(Frame, HActor, Sprite->Actor)` immediately before its own
`Canvas->DrawIcon(...)` call — the identical draw used for the actor's real on-screen render, not a
separate hit-test-only pass. `DrawTile.cpp`'s masked-texture blitter (`FlashSprite32Masked`,
`BlitMask32`) skips the screen write outright when the source texel equals the reserved transparent
palette index (`if (Texel) Screen[x] = Palette[Texel];` — no `else` branch, no write at all otherwise).
So a transparent icon pixel is invisible to the hit-proxy readback as a pure SIDE EFFECT of sharing
the real rasterizer with the real render, not a separately-coded alpha rule — confirming the hint this
board item was filed with. Cross-checked against this repo's own `Editor.dll`/`render.dll`: the
`HActor`/`HBspSurf`/`HBrushVertex`/`HHitProxy` hit-proxy classes `UnSprite.cpp`'s `PUSH_HIT` call
targets are real exported symbols there, and `DrawActorSprite`'s disassembly (already on file above)
shows the exact call structure this source predicts.

UE1's own masking is a hard BINARY test (palette index 0 or not); this codebase's atlas/marker
textures are anti-aliased PNGs with soft edges, so the fix reuses the existing masked-material
alphaTest cutoff (0.5, `sceneResources.ts`'s `resolveMaterialState`) rather than testing for exact
zero — `selection.ts`'s new `isTransparentPixel`.

**Fix**: `tapSelect.ts`'s `resolveTapSelect` now filters out any marker-sprite raycast hit whose
sampled texture alpha (at the intersection's own `uv`, read directly off the sprite's `CanvasTexture`
source canvas) is below that cutoff, BEFORE ranking hits — exactly like a genuine raycast miss on
that candidate, so the click falls through to whatever else is actually drawn underneath (or to a
real miss). A point actor's own AABB fallback can't undo this: its bbox is a zero-size point at
`Location` (`writes.py`'s `actor_bounds`), so it was never really what made a marker selectable in the
first place — the bare sprite-quad raycast was, which is exactly what's now filtered.

🔬 **Live-verified** (real synthetic `page.mouse.click`, headless Chromium, `showcase_bar`): searched
and framed a real level actor (`HKMarketLight1`, a point Light) via the org panel + `F`, then scanned
a real click along its marker's screen-space diagonal in ~2px steps. With the fix: clicks land on the
actor from the marker's center out to ~15px, then miss (`(empty)`) from ~18px outward. To confirm this
miss is the alpha filter and not merely the click straying outside the sprite's raycastable quad, the
SAME exact pixel coordinates (231,525)–(239,533) were re-clicked against the UNFIXED code (`git
stash`, no rebuild needed — Vite HMR): every one of them SELECTED `HKMarketLight1` there, proving the
click point is genuinely within the sprite's hit geometry and that the fix (not a geometric miss) is
what rejects it. Popping the stash and re-testing reproduced the exact original "miss from ~18px"
result. Full A/B transcript in the board item's `done/` writeup.

### Vertex handle screen size (closed 2026-09-18)

Board item `vertex-handles-should-be-screen-size-constant`: vertex/local-origin handle dots on a
selected brush shrank/grew with camera zoom/distance (a fixed WORLD-space sprite size), instead of
staying a constant size on screen.

📖 **Source** (`fgsfdsfgs/UE1`, `Source/Editor/Src/UnEdRend.cpp`, `UEditorEngine::DrawLevelBrush`):
UED22 draws a vertex handle as a literal 2D screen-space dot, not a 3D-space sprite at all --

```cpp
if( Render->Project( Frame, *V1, X, Y, NULL ) )
    Frame->Viewport->RenDev->Draw2DPoint( Frame, VertexColor, LINE_None, X-1, Y-1, X+1, Y+1 );
```

`Project` maps the 3D vertex to raw screen pixel coordinates `X`/`Y`; `Draw2DPoint` then draws a
fixed `X±1` box (a ~2px dot) directly in screen space, with no distance/zoom term anywhere in the
call. This settles the question directly: UED22's vertex handles are constant-screen-size BY
CONSTRUCTION (a 2D draw), not a coincidence of some other mechanism. The literal ~2px size is tuned
for a low-resolution 1990s software renderer and would be barely visible on a modern high-DPI canvas,
so the fix uses a practical modern size (6px) rather than copying the literal pixel count -- the same
kind of departure this doc already made for `DrawMesh`'s selection-highlight formula.

**Fix**: `web/src/scene/SelectionMarkers.tsx`'s new `VertexDot` component reuses the exact per-frame
rescale mechanism the existing `PivotMarker` gizmo already used (`worldUnitsPerPixelAt`, camera- and
viewport-size-aware) instead of a fixed-world-unit sprite `scale`. Applies to both the per-vertex dots
and the selected brush's local-origin dot, in both viewport kinds (perspective and ortho share the
same `useThree()`-driven mechanism).

🔬 **Live-verified** (real headless-Chromium zoom/dolly sweeps against `showcase_bar`, measuring the
dot's actual rendered pixel footprint, not reasoning about the math): selected `Brush113`, scanned its
vertex-dot size across a ~32x zoom range in the ortho top pane -- unfixed: 1px shrinking to 0px
(invisible) past a threshold; fixed: held 2-6px throughout. In the perspective pane, a 10-step dolly
sweep (camera pulled back far enough to visibly shrink a nearby actor) held 7-8px at every step with
the fix, versus visibly shrinking without it.

### Radii overlay colors (investigating, 2026-09-16)

`web/src/scene/RadiiOverlays.tsx` draws the collision cylinder and light-radius sphere in two
DIFFERENT colors (`COLLISION_COLOR` red-pink, `LIGHT_COLOR` orange) — inherited from `preview.py`'s
own offline-rasterizer convention, which deliberately deviated light to orange so the two overlays
stay visually distinct in a flat 2D CLI-rendered diagram. This was carried into the live GUI without
checking whether the real editor makes the same distinction.

Source (`fgsfdsfgs/UE1`, `Source/Editor/Src/UnEdCam.cpp:1547,1564`): the collision-radius circle AND
the light-radius circle are drawn with the exact same color constant, `C_ActorArrow`:
```cpp
Render->DrawCircle( Frame, C_ActorArrow.Plane(), LINE_None, Actor->Location, Actor->CollisionRadius );
// ...
Render->DrawCircle( Frame, C_ActorArrow.Plane(), LINE_None, Actor->Location, Actor->WorldLightRadius() );
```
Two other radii on the SAME actor (Mover volumetric radius, sound radius) use genuinely DIFFERENT
constants (`C_Mover`, `C_GroundHighlight`) — so UED22 does distinguish some radii by color, just not
collision-vs-light. Our GUI doesn't currently draw mover/sound radii at all, so that distinction is
out of scope for now.

**`C_ActorArrow`'s exact RGB found (2026-09-16): `(163, 0, 0)`, a dark red** —
`Engine/Config/Default.ini` (`fgsfdsfgs/UE1`, line 563), `C_ActorArrow=(R=163,G=0,B=0,A=0)`. Not a
class-header default (`Editor.h`'s `C_ActorArrow` member has no in-code initializer, confirmed no
init in `UnEditor.cpp` either) — it's the shipped v200 engine's `.ini` default, loaded at first run.
Matches `dev/docs/unrealed/rendering.md`'s existing 🔬 live-probed "red" fact for the collision
cylinder. Confidence: 📖 source (v200 shipped `.ini` default) — not yet confirmed against this
project's actual DeusEx-customized `Editor.dll`/its own installed `.ini` (same v200-vs-DeusEx-build
gap flagged throughout this doc). Implemented in `RadiiOverlays.tsx`'s `RADII_COLOR`.

**The same `Default.ini` pull also surfaced the full adjacent `C_*` wireframe color block** —
directly relevant to the brush-wire-color question below:
```
C_BrushWire=(255,63,63)      C_Pivot=(0,255,0)         C_Select=(0,0,127)
C_AddWire=(127,127,255)      C_SubtractWire=(255,192,63)   C_GreyWire=(163,163,163)
C_ActorWire=(127,63,0)       C_ActorHiWire=(255,127,0)     C_SemiSolidWire=(127,255,0)
C_NonSolidWire=(63,192,32)   C_ActorArrow=(163,0,0)        C_Mover=(255,0,255)
```
Not yet folded into a fix — `C_ActorHiWire` ("Actor Highlighted Wire") is a separate constant from
`C_BrushWire`, not chased against `DrawLevelBrush`'s own `WireColor` selection logic (does a SELECTED
brush's `DrawColor` ever read from `C_ActorHiWire` instead of the brush-kind color, in some code path
not yet found?). And `C_SemiSolidWire=(127,255,0)` (bright green) contradicts `preview.py`'s own
existing comment, which cites "UED's rose (223,149,157)" for semisolid as the value it deliberately
diverged from — a real discrepancy between this fresh v200 pull and that earlier research, unresolved
(different UE1 build? different source? not determined here).

**Bigger finding, same read (`UnEdCam.cpp:1538-1573`): the whole radii block is gated
`Viewport->IsOrtho() && ...` at its OUTER `if`.** Collision/light/mover/sound radii are NEVER drawn
in a perspective viewport in real UED22 — only in the three ortho panes. And even there it's not a
3D cylinder: `REN_OrthXY` (top-down) draws a flat `DrawCircle`; every OTHER ortho view draws a
`DrawBox` (an axis-aligned box, `Min/Max = Location ∓ (CollisionRadius,CollisionRadius,
CollisionHeight)`) — never a round cylinder shape at all. Light radius always draws as a circle in
every ortho pane (no box form). This matches our own `radiiProjection.ts`'s ortho-pane logic
(circle in top, rect in front/side) reasonably well — but our GUI's `CollisionCylinder3D`/
`LightSphere3D` (`RadiiOverlays.tsx`), a true 3D wireframe cylinder + sphere drawn in the
PERSPECTIVE pane, has **no basis in this source** — this source shows nothing there. Confidence: ✅
source-read, but this reading is DISPUTED. Not yet corroborated against the real UED22 binary this
project builds against (`fgsfdsfgs/UE1` is third-party UE1 v200-lineage source, not confirmed
identical to the DeusEx-customized UED22 build).

**RESOLVED (2026-09-16) — the "no perspective basis" framing above was wrong, and this project
already knew why.** Owner correction: "The radii cylinder SHOULD render in perspective view. UED22
renders it there (when enabled)" + "`actor diagram` renders the radii correctly" — should have
checked this project's own prior spikes before trusting the third-party source's implied absence.
`dev/docs/spikes/2026-07-21-unrealed-sprite-radii-rendering.md` "Version conflict: 2-D only vs 3-D
cylinder" already covers exactly this: the `fgsfdsfgs/UE1` **v200** source genuinely has no
perspective radii (the `IsOrtho()` guard is real, for v200) — but UT release notes document a
**later patch** adding it: *"Radii view will now work in the 3D window by rendering the collision
cylinder as an 8-sided wire cylinder, and will also show the radius of things like lights in the 3D
window."* Deus Ex's UED22 ships build ~1112, well after that patch — so a perspective cylinder is
expected. The spike marks this 🔬 (wiki + patch notes, not v200-source-confirmed) — the owner's
direct correction now backs it too.

**Concrete, actionable fix this surfaces**: the patch note says **8-sided**. `preview.py`'s
`_ISO_CYL_SEGMENTS = 9` (odd, deliberately — its own comment: avoids two vertical edges landing on
the same raster column in its flat 2D buffer). Our GUI's `RadiiOverlays.tsx` `CollisionCylinder3D`
uses **16** segments (`cylinderGeometry` radialSegments), inherited from neither source — a real
WebGL 3D mesh has no raster-column concern, so neither preview.py's 9 nor our own 16 is the right
number to copy; the literal patch-note value (8) is. A 16-sided cylinder reads as smoothly round: an
8-sided one is visibly faceted/octagonal — plausibly exactly the "shape looks off" complaint.
Binary disassembly against the real `Editor.dll`/`render.dll` is still running (would give ✅ tier on
existence + segment count + the `C_ActorArrow` RGB); not blocking this fix.

**Radii cylinder/sphere shape (closed 2026-09-16, not an RE question):** the perspective-pane wire
cylinder/sphere showed visible triangulation-diagonal seams ("triangular faces," owner report) —
`MeshBasicMaterial`'s `wireframe: true` draws every triangle edge of the underlying
`CylinderGeometry`/`SphereGeometry`, including the diagonal each side-quad is split into two
triangles by. Fixed with explicit line segments (top/bottom ring + struts for the cylinder, three
orthogonal circles for the sphere), computed directly in world space rather than via a local-space
`<mesh position=.../>` transform (avoids the same class of bug the pivot-marker fix hit).

### Brush wireframe selection color (closed and implemented 2026-09-16)

Owner report: "brush colors seem off, at least on highlight." Investigated via `fgsfdsfgs/UE1`
source, `Source/Editor/Src/UnEdRend.cpp`, `UEditorEngine::DrawLevelBrush`:
```cpp
DrawColor   = WireColor * (bDrawSelected ? 1.0 : 0.5);
VertexColor = WireColor * 1.2;
PivColor    = WireColor;
```
**The premise this codebase built on is backwards.** UED22 does NOT brighten a selected brush's
wireframe — it DIMS an unselected one to 50%; selected shows the brush's base `WireColor` unmodified
(1.0x). `WireColor` itself is chosen per brush kind first (builder brush / mover / `bColored`
override / `CsgOper`+`PolyFlags` for a normal content brush — Add/Subtract/Intersect/Deintersect/
Semisolid/Nonsolid each their own constant), and only THAT value is what the 1.0/0.5 selected/
unselected multiplier applies to.

Two separate elements, two separate (and different) multipliers — conflating them is the root of
both existing implementations' errors:
- `uedcli/preview.py`'s `_brighten` (`WireColor * 1.2`) — its own doc comment already correctly
  attributes this to the VERTEX-HANDLE color (`VertexColor` above), not the brush wire itself. That
  part of preview.py is fine as documented.
- This codebase's `web/src/scene/selectionColor.ts` `brightenWireColor` (lift 45% toward white) is
  applied to BOTH the brush's outline ring (`BrushOutlines.tsx`) AND its vertex-handle dots
  (`SelectionMarkers.tsx`) — one formula for two things real UED22 treats differently, and the
  formula itself matches neither `DrawColor` nor `VertexColor`. Its own doc comment already flagged
  it as an unverified invention; now confirmed wrong, not just unverified.

**Fix not yet implemented — a real decision needed first, not a mechanical swap.** This codebase's
own CSG palette (`uedcli/preview.py`'s `_CSG_PALETTE`, e.g. add=blue `(70,110,255)`) was ALREADY
explicitly tuned ("front lifted for the dark bg" per its own comment) rather than a literal copy of
raw UED22 `WireColor` values — so it's not established which UED22 state (selected/unselected, or
neither precisely) our existing palette was calibrated to represent. Confidence: 📖 source-only (UE1
v200, not yet binary/live-confirmed against this project's actual `Editor.dll` — `DrawLevelBrush`
isn't an exported symbol, so confirming it needs real call-graph work, not attempted yet).
`C_BrushWire`/`C_AddWire`/etc.'s own exact RGB values (the `UEditorEngine` member fields `WireColor`
is chosen from) also aren't pinned down yet — same open question as `C_ActorArrow` above.

**Update: found and implemented (2026-09-16).** The same `Default.ini` pull that resolved
`C_ActorArrow` also gave the real `C_AddWire`/`C_SubtractWire`/`C_SemiSolidWire`/`C_NonSolidWire`/
`C_Mover` values (see "Radii overlay colors" Findings above for the full block). Owner ruling:
scope this to the web GUI only, not `preview.py`'s shared `_CSG_PALETTE` (which also drives `actor
diagram`/`level photo`/eval screenshots). Implemented in `selectionColor.ts`'s `CSG_WIRE_COLOR`/
`resolveWireColor`/`scaleColor`: unselected brush wire dims to 0.5x (`brushRings.ts`'s
`mergeThinRings`), selected shows the plain undimmed WireColor (`BrushOutlines.tsx`'s `BoldRing`),
vertex-handle dots use `WireColor*1.2` always (`SelectionMarkers.tsx`) -- the three separate real
formulas, no longer conflated into one invented brighten-on-select function. Live-verified: the
unselected default noticeably dims across a whole level's wireframe. Intersect/Deintersect brushes
still fall back to the server's own (tuned, non-faithful) color -- this codebase doesn't yet
distinguish them from Add server-side, a separate already-tracked gap
(`gui-csg-brush-coloring-never-distinguishes`), not expanded into here.

### Pivot-cross multi-select rendering (closed) + visibility toggle (closed 2026-09-18, real RE)

Board item `brush-pivot-cross-multiselect-and-toggle`, two questions.

**Part 1 — does our pivot cross render once per selected brush under multi-select? Confirmed YES,
already correct, no bug.** `SelectionMarkers.tsx`'s `<PivotMarker>` sits inside the `.map()` over
every entry of `selectedBrushes`, unconditionally — only the separate local-origin dot is gated to
one "primary" actor (deliberately, per its own doc comment). Live-verified with a real headless-
Chromium session against `showcase_bar` (React-fiber `onSelectActor` calls driving real selection
state, then real screenshots — not a code read alone): selecting 3 brushes (`Brush1`/`Brush6`/
`Brush7`) shows 3 distinct red crosses at 3 distinct world positions; the SIDE ortho pane alone shows
two of them side by side, each centered on its own brush's own selection outline. The owner's hunch
("it does NOT render per-brush currently") did not reproduce. No code change.

**Part 2 — does UED22 have a manual visibility toggle for this marker, or hide it for a single
selection? RE-DONE FOR REAL 2026-09-18 against our own `uned/UED22/Editor.dll` — ✅ binary-confirmed,
no third-party source used anywhere in this pass.**

An earlier pass (now retracted) asserted this same mechanism but cited it from `fgsfdsfgs/UE1`, a
third-party UE1 source tree — banned as GUI-PARITY evidence (owner ruling 2026-09-18: only our own
`uned/UED22/` binary, via disassembly or a live capture, counts). This is a full redo from scratch,
disassembling our own `Editor.dll` (`pefile`+`capstone`, the `dev/docs/spikes/bspspike/` harness) —
disassembly is the primary/authoritative evidence here, not a screenshot diff (see the live-probe
caveat below for why).

**The mechanism, read directly from `Editor.dll`'s own machine code:**

- `?SetPivot@UEditorEngine@@UAEXVFVector@@HH@Z` (export RVA `0x46060`) tallies the level's own actor
  array itself (`Actor->ObjectFlags` at `[actor+0x11c]`, testing bit `0x04` = selected) into `Count`,
  and a second bit (`0x40` of the same byte, consistent with a per-actor grid-snap/drag status flag)
  into `SnapCount`. Its tail (VA `0x10046441`-`0x10046453`) is:
  ```
  test edi, edi        ; edi = SnapCount
  jg   set_true
  cmp  esi, 1          ; esi = Count
  jg   set_true
  ; else: eax = 0
  jmp  store
  set_true: eax = 1
  store: mov dword ptr [0x101491e8], eax   ; global GPivotShown
  ```
  i.e. **`GPivotShown = (SnapCount > 0) || (Count > 1)`, byte-for-byte** — for exactly one ordinary
  (non-snap-dragging) selected actor, `Count==1` and `SnapCount==0`, so `GPivotShown` is written `0`.
- The actual draw site, inside `?Draw@UEditorEngine@@UAEXPAVUViewport@@HPAEPAH@Z` (the per-viewport
  frame draw, export RVA `0x3c440`), reads that exact global before doing anything else for the
  pivot: `cmp dword ptr [0x101491e8], 0; je <skip>` (VA `0x1003e7a0`) — when `GPivotShown` is 0, this
  jump skips the ENTIRE block: projecting the pivot location to screen space, registering an
  `HGlobalPivot` hit-proxy (a real exported hit-proxy class —
  `?Click@FEditorHitObserver@@UAEXABUFHitCause@@ABUHGlobalPivot@@@Z`, RVA `0x47c80` — confirming this
  is a genuine hit-testable object in the real binary, not an invented name), and three 2D line-draw
  calls building a cross shape around the projected point. None of it runs when `GPivotShown` is
  false.
- `?NoteSelectionChange@UEditorEngine@@UAEXPAVULevel@@@Z` (RVA `0x45880`, the real
  selection-changed notifier) tallies `Count` itself and always ends by invoking the same pivot
  recompute (`ResetPivot`/`SetPivot`-equivalent vtable calls) — confirming the pivot's state is
  genuinely tied to selection-change notifications, not some unrelated global.

**Answer: UED22 has no manual visibility toggle for this marker (none exists to reproduce), and it
genuinely hides the cross for a single ordinary selected actor — shown only once 2+ actors are
selected, or while a snap/drag is active.** This is the exact mechanism the retracted pass described,
now independently re-derived from our own binary's disassembly rather than borrowed from a
third-party source — same conclusion, real evidence this time.

**Live screenshot cross-check — inconclusive, flagged honestly rather than smoothed over.** A
supplementary live probe (fresh ephemeral `uned/UED22` container, `CAMERA OPEN … REN=13` top-ortho
screenshots, pixel-diffed with PIL/numpy) drove selection via console verbs (`SELECTNAME`,
`ACTOR SELECT ALL`) on three pasted test brushes and found a small marker-like pixel cluster even
with exactly one brush selected — on its face, contradicting the disassembly. This is **not**
trusted over the disassembly: the cluster's position didn't track either selected brush's own
location in a follow-up test (it sat at neither brush's projected point), so it does not cleanly
identify as the `GPivotShown`-gated global cross at all — most likely it's `DrawLevelBrush`'s own
always-per-selected-brush vertex/local-origin dot (a different, ungated marker this doc's "Brush
wireframe selection color" section already covers), or an artifact of driving selection through
console verbs rather than a real GUI click (`NoteSelectionChange`'s call chain may not be reached the
same way `SELECTNAME`/`ACTOR SELECT ALL` mutate selection state). Not chased further: the disassembly
directly reads the exact gating condition and draw-site skip, which is a stronger, more precise claim
than a screenshot diff can settle on its own, and the two are answering the same question at very
different confidence tiers. Per this doc's own convention, disassembly is the primary/authoritative
evidence for this finding; the pixel probe is recorded here only for honesty, not as corroboration.

## Testing

Same principle as the other two campaigns: don't let tests gate the RE work. The GUI's own suite is
`web/`'s vitest run (`npm test` under `web/`, or the project's usual frontend test command) — scope
to the touched files while iterating, run the full frontend suite once before a merge. This campaign
doesn't touch Python/native code, so `bin/test` is out of scope unless a change happens to cross into
`uedcli/serve/`.

## Where the detail lives

- Board items: `dev/docs/board/inbox/gui-*` (each topic above, once filed, gets its own item — this
  doc indexes them, never absorbs their content).
- Verified UED22 facts: `dev/docs/unrealed/quirks.md` ("Selection" section), `dev/docs/unrealed/
  rendering.md` (screenshots), both require the owner's yes to edit.
- GUI's own architecture/behavior reference (what's built, not what UED22 does): `dev/docs/GUI.md`.
- RE methodology: `dev/docs/unrealed/extracting-from-dll.md` (disassembly), `dev/docs/unrealed/
  rendering.md` (screenshot capture).
