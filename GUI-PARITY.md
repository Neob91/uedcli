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
| Click/hit-detection algorithm | How does UED22 resolve a click to a surface/actor/brush when candidates overlap? | ⬜ open | `dev/docs/board/inbox/gui-click-detection-algorithm-not-re-d-against/` |
| Modifier-key click-select rules | Are the Shift/Ctrl select-surface-vs-actor rules real UED22 behavior? | ⬜ open | `dev/docs/board/inbox/gui-texture-actor-click-select-modifier-rules/` |
| Marquee containment rule | Full-containment for brushes vs. pivot-in-box for point actors — confirmed fact, not yet wired into the (deferred) marquee feature | ⬜ open (marquee itself deferred) | `dev/docs/board/inbox/gui-ortho-marquee-spec-omits-unrealed-s-brush/` |
| CSG brush coloring | Does UED22 give Intersect/Deintersect brushes a distinct color from Add? | ⬜ open | `dev/docs/board/inbox/gui-csg-brush-coloring-never-distinguishes/` |
| Pan direction (perspective vs ortho) | Which convention (drag-follows-camera vs. content-follows-cursor) matches UED22, if either? | ⬜ open | `dev/docs/board/inbox/gui-perspective-pan-direction-vs-ortho/` |
| Shading modes | UED22 has a Zones view mode the GUI doesn't | ⬜ open | `dev/docs/board/inbox/gui-shading-modes-omit-unrealed-s-zones-view/` |
| Mesh-actor wireframe rendering | Should a static mesh actor render as wireframe in wireframe/2D modes? | ⬜ open | `dev/docs/board/inbox/static-mesh-actors-should-render-as-wireframe/` |
| Radii overlay colors | Collision cylinder vs. light-radius sphere: same color or distinct? | ✅ closed, implemented | ✅ source (structural fact), 🔬 live (red, no hex) — see Findings below |
| Radii perspective cylinder | Does/should the collision cylinder render in the perspective pane? | ✅ closed, implemented | 🔬 wiki + UT patch notes (`dev/docs/spikes/2026-07-21-...`) + owner confirmation — see Findings below |

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

`C_ActorArrow`'s exact RGB wasn't found — its declaration isn't in any of the header/source files
checked (`EditorPrivate.h`, `Editor.h`, `UnEditor.cpp`; likely a class-member field declared
somewhere not yet located). `dev/docs/unrealed/rendering.md` already has a 🔬 live-probed fact that
the collision cylinder renders "red" when selected (no exact hex) — combined with the source fact
above, light-radius should render in that SAME red, not orange. Confidence: ✅ source (same-color
structural fact) + 🔬 live (red, family only, not exact hex).

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
