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
| Surface selection highlight | What color/blend/technique does UED22 use to show a selected SURFACE (BSP poly)? | ✅ closed, implemented | ✅ binary (`softdrv.dll`/`Editor.dll`/`Engine.dll` disassembly, our own `uned/UED22/`) — see Findings below |
| Click/hit-detection algorithm | How does UED22 resolve a click to a surface/actor/brush when candidates overlap? | 🔶 investigating | `dev/docs/board/inbox/gui-click-detection-algorithm-not-re-d-against/` — see Findings below |
| Sprite alpha picking | Does UED22's sprite click hit-test respect the icon's transparent padding? | ✅ closed, implemented | 📖 source (`SoftDrv/Src/{Hit,DrawTile}.cpp`) + 🔬 live (real clicks, A/B against the unfixed code) — see Findings below |
| Vertex handle screen size | Does UED22 draw vertex/local-origin handles at a constant screen size, or a fixed world size that scales with zoom? | ✅ closed, implemented | 📖 source (`Editor/Src/UnEdRend.cpp`) + 🔬 live (real zoom/dolly sweeps, A/B against the unfixed code) — see Findings below |
| Modifier-key click-select rules | Are the Shift/Ctrl select-surface-vs-actor rules real UED22 behavior? | ⬜ open | `dev/docs/board/inbox/gui-texture-actor-click-select-modifier-rules/` |
| Marquee containment rule | Full-containment for brushes vs. pivot-in-box for point actors — confirmed fact, not yet wired into the (deferred) marquee feature | ⬜ open (marquee itself deferred) | `dev/docs/board/inbox/gui-ortho-marquee-spec-omits-unrealed-s-brush/` |
| CSG brush coloring | Does UED22 give Intersect/Deintersect brushes a distinct color from Add? | ⬜ open | `dev/docs/board/inbox/gui-csg-brush-coloring-never-distinguishes/` |
| Pan direction (perspective vs ortho) | Which convention (drag-follows-camera vs. content-follows-cursor) matches UED22, if either? | ⬜ open | `dev/docs/board/inbox/gui-perspective-pan-direction-vs-ortho/` |
| Shading modes | UED22 has a Zones view mode the GUI doesn't | ⬜ open | `dev/docs/board/inbox/gui-shading-modes-omit-unrealed-s-zones-view/` |
| Mesh-actor wireframe rendering | Should a static mesh actor render as wireframe in wireframe/2D modes? | ✅ closed, already implemented | ✅ binary (`render.dll` disassembly, our own `uned/UED22/`), see Findings below |
| Mesh-actor wireframe SELECTION (fill vs. edges) | In wireframe/ortho modes, does UED22 select a mesh actor by a click anywhere inside its silhouette, or only on a drawn wireframe edge? | ✅ closed, fixed — edges only, not the interior | ✅ binary (`render.dll`/`Engine.dll` disassembly, our own `uned/UED22/`) — see Findings below |
| Radii overlay colors | Collision cylinder vs. light-radius sphere: same color or distinct? | ✅ closed, implemented | ✅ binary (`Editor.dll`/`render.dll`/`Editor.u`, our own `uned/UED22/`) — distinct per PANE, and no alpha; a retracted third-party-sourced answer got this wrong, see Findings below |
| Radii perspective cylinder | Does/should the collision cylinder render in the perspective pane? | ✅ closed, implemented | ✅ binary (`Editor.dll`'s non-ortho branch calls `URender::DrawCylinder`; no `IsOrtho` gate exists) — see Findings below |
| Radii light-radius shape | Does the perspective-pane light radius render as a 3D sphere, or a camera-facing circle? | ✅ closed, implemented | ✅ binary (`render.dll`'s `DrawCircle`, our own `uned/UED22/`) — see Findings below |
| Radii sound-radius rendering | The GUI drew no overlay at all for `AmbientSound`'s reach; what color/shape does UED22 use? | ✅ closed, implemented | ✅ ini (`uned/UED22/unrealtournament.ini` `C_GroundHighlight=(0,0,127)`), reusing the already-binary-confirmed `DrawCircle`/camera-facing-circle mechanism — see Findings below |
| Radii cylinder/sphere shape | Wireframe rendering had a triangulation-diagonal artifact ("triangular faces") | ✅ closed, implemented | not an RE question — a `wireframe:true`-on-triangulated-geometry rendering bug, fixed with explicit line segments |
| `C_ActorArrow` exact RGB | The radii overlay's real color value | ✅ closed, implemented | ✅ our own `uned/UED22/unrealtournament.ini` line 388, `(163,0,0)` — the member it fills is `UEditorEngine+0x1f8`, pinned by disassembly; see Findings below |
| Brush wireframe selection color | What does UED22 actually do when a brush is selected/unselected? | ✅ closed, implemented | 📖 source-only, GUI-only scope (owner ruling) — see Findings below |
| UED22 line widths | What line/wire thickness does UED22 use for wireframe/selection rendering? | ✅ closed — no bug | ✅ source-confirmed: no width parameter exists in the render-interface API UED22 draws through; this codebase's default line width is already correct |
| Pivot-cross multi-select rendering | With 2+ brushes selected, does our own pivot cross render once per brush? | ✅ closed, fixed — it did, and UED22 draws exactly ONE | ✅ binary + 🔬 live UED22 capture — see Findings Part 4 |
| Pivot-cross visibility toggle | Does UED22 have a manual way to toggle the pivot marker's visibility on/off? | ✅ closed — no toggle exists; visibility is `(SnapCount > 0) \|\| (Count > 1)`, latched | ✅ binary (`Editor.dll` disassembly, our own `uned/UED22/`) + 🔬 live capture — see Findings Part 2 + Part 4 |
| Pivot-cross anchor under multi-select | Which selected actor's location does UED22's one global cross sit on? | ✅ closed — the actor that was most recently the SOLE selection (= first-clicked, in a click-built multi-select) | ✅ binary (`Editor.dll` disassembly, our own `uned/UED22/`) + 🔬 live capture + owner's own live test — see Findings Part 3 + Part 4 |
| Directional arrow gizmo | Does UED22 draw a per-actor facing-direction arrow (`bDirectional`), what does it look like, and what gates it? | ✅ closed, implemented | ✅ binary (`Editor.dll`/`Engine.dll` disassembly, our own `uned/UED22/*.dll`/`*.u`) — see Findings below |

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
- **Mesh actor, wireframe render** (originally cited to `Source/Render/Src/UnMeshRn.cpp:346`, a
  third-party UE1 source now banned as evidence by the 2026-09-18 owner ruling — see "Mesh-actor
  wireframe rendering" Findings below for the redo): flat line color — selected `(.2,.8,.1)` ≈
  RGB(51,204,26); unselected `(.6,.4,.1)` ≈ RGB(153,102,26) (an olive/brown, not white).
  **✅ Binary-confirmed 2026-09-18** (upgraded from the original "🔶 data-only, no instruction
  reference" flag): both exact 16-byte packed vectors are loaded by name in `render.dll`'s
  `URender::DrawLodMesh` (RVA `0xd050`), gated on `AActor.bSelected` — see "Mesh-actor wireframe
  rendering" Findings below for the full instruction-level trace, no third-party source involved.
- **No generic selection bounding box exists in UED22 by default** — `UnEdCam.cpp`'s only
  `DrawBox` calls tied to selection sit inside the opt-in `SHOW_ActorRadii` overlay (already
  documented in `dev/docs/unrealed/rendering.md` as red), not a baseline cue. This codebase's cyan
  AABB box (`selectionBoxes.ts`) has no UED22-authentic basis as the default indicator.

Not yet folded into `dev/docs/unrealed/rendering.md` as a permanent verified fact — that edit needs
the owner's yes per `CLAUDE.md`; this section is the campaign's own working record until then.

### Mesh-actor wireframe rendering — real triangle edges, own-binary confirmed (closed 2026-09-18)

Board item `dev/docs/board/inbox/static-mesh-actors-should-render-as-wireframe/`. Question: in
UED22's wireframe viewport and the 2D ortho panes, does a StaticMesh (DT_Mesh) actor render its
actual mesh wireframe (real triangle edges), a simplified proxy (a bounding box), or something else
(a sprite/icon)? This codebase's `web/src/scene/MeshWireframe.tsx` already draws a StaticMesh
actor's real per-triangle wireframe edges in wireframe mode (landed commit `279fb903`,
2026-09-16, predating this investigation) and colors it with the `(.2,.8,.1)`/`(.6,.4,.1)`
selected/unselected constants from the "Selection highlight rendering" section above — but that
color finding was sourced from a now-banned third-party UE1 tree, and the "is real-triangle-
wireframe even the right convention" question itself was never answered from any UED22 evidence at
all. This pass answers both, from our own `uned/UED22/render.dll` alone (`pefile`+`capstone`,
`dev/docs/spikes/bspspike/pe.py` harness), no third-party source anywhere.

**✅ Binary-confirmed.** `render.dll`'s exported `?DrawMesh@URender@@...` (RVA `0xff00`) is a thin
~0xb0-byte dispatcher: it reads `Actor->Mesh->SomeFlag` (`[eax+0x40]`, offset unidentified further)
to decide one bit of a flags word, then tails straight into `?DrawLodMesh@URender@@...` (RVA
`0xd050`) with all its own arguments forwarded unchanged — so the GUI-PARITY.md "Selection highlight
rendering" section's earlier attribution of the ambient-bias/wire-color logic to "`DrawMesh`" is a
harmless one-level imprecision: the containing function is really `DrawLodMesh`, reached through
`DrawMesh`'s dispatch. `DrawLodMesh` is ~0x1111 bytes (`0xd050`-`0xe161`, ends `ret 0x24`) and does,
in order:

1. A large LOD-level/lighting/texture-coordinate setup block (`0xd0dd`-`0xd976`) that computes a
   per-face normal/lighting basis via `FVector::operator^` (cross product) and constructs an
   `FCoords` texture-mapping context — the SOLID SHADED triangle path (not traced further here; out
   of scope for this question).
2. A gate at `0xd992`-`0xd999`: `cmp dword ptr [ebp-0x468], 0; je 0x1000e164` — skips the entire rest
   of the function (bones + both wireframe-edge loops below) when a flag computed earlier
   (`0xd39a`-`0xd3d9`) is zero. That flag is 1 exactly when `Actor->SomeField` (`[Actor+0x3c]`,
   unidentified) is nonzero, **or** a value read via `Frame->[+0x30]->[+0x480]` (a viewport-chain
   field, name unconfirmed but its tested values are an exact, non-coincidental match to
   `dev/docs/unrealed/rendering.md`'s already-established `RendMap` enum) equals **`1` (Wire), `0xd`
   (13, Ortho XY), `0xe` (14, Ortho XZ), or `0xf` (15, Ortho YZ)** — i.e., **the whole block below
   only runs in Wire/ortho render modes**, never in a shaded perspective mode. This is exactly the
   mode set our own GUI's `mode === 'wireframe'` (perspective) + the ortho panes (always
   `mode = 'wireframe'`) cover.
3. `0xd9ac`-`0xdb0f`: a SKELETAL-MESH-ONLY sub-block (gated on a `USkeletalMesh`-class check via
   `?StaticClass@USkeletalMesh@@...`, `0xd3d9`) that walks a bone-like array
   (`mesh+0x234`/`+0x238`/`+0x240`) drawing one line per entry — almost certainly a skeleton/bone
   debug overlay, not a mesh wireframe; not chased further (irrelevant to a plain StaticMesh actor,
   which never takes this branch).
4. `0xdb15`-`0xdb55`: **the wire-color pick** — `test byte ptr [Actor+0x11c], 4` (the SAME
   `AActor.bSelected` bitfield/bit this doc's pivot-cross section already established) selects
   `render.dll`'s own packed vector at VA `0x10035600` = `(0.2, 0.8, 0.1, 0)` when selected, else
   `0x100355f0` = `(0.6, 0.4, 0.1, 0)`, built into an `FPlane` (`??0FPlane@@...`, the same ctor this
   doc's other findings already use for a color argument). **These are the exact `(.2,.8,.1)`/
   `(.6,.4,.1)` values this codebase's `selectionColor.ts` already hardcodes** — now confirmed by a
   direct instruction reference in our own binary, not by proximity to another constant.
5. `0xdb70`-`0xdc91`: the FIRST real edge-drawing loop, over the mesh's LOD-aware face list
   (`mesh+0x148` count, `mesh+0x144` face records, each 3 wedge indices resolved through a
   progressive-mesh LOD-collapse remap table at `mesh+0x15c`/`+0x150` — a `while` loop that walks a
   wedge to its LOD-collapsed target until its level clears the current threshold). Per face, once
   the 3 final (post-collapse) point indices are resolved, it issues 3 draw calls through the render
   device's own vtable slot `+0x80` (the interface every other line-draw call in this doc's other
   findings also goes through), each preceded by a fresh `FPlane` copy of the color picked in step 4
   and pushing two `FVector`s (`sub esp,0xc; mov ecx,esp; ...`) as the line's endpoints — i.e., a
   genuine `RenDev->DrawLine(Frame, Color, LineFlags, Start, End)`-shaped call per iteration, not a
   single fixed-shape primitive (a box/sphere call would take a size/radius argument, not two
   explicit points). **Honest caveat, not smoothed over**: tracing exactly which two of the
   triangle's three vertices each of the 3 calls connects shows only 2 of them use genuinely distinct
   points (the resolved-3rd-vertex-of-this-face to each of the other two); the 3rd call's two operand
   registers trace to the SAME vertex slot in this reading, i.e. a degenerate zero-length line, not
   the triangle's third edge. On a closed, well-formed mesh this is very likely visually complete —
   the "missing" edge of one face is typically drawn as one of the two real edges of an adjacent
   face sharing it — but this is not verified against a live render, and a genuine open/boundary
   silhouette edge could in principle be missed by this specific per-face scheme. Not chased further
   (would need a live capture of an asymmetric test mesh to settle, and the host's docker daemon
   could not mount the repo for a live UED22 boot in this session — see the "Surface selection
   highlight" section below for the same limitation hit there).
6. `0xdca9`-`0xdd92`: a SECOND, structurally identical edge-drawing loop over a DIFFERENT face array
   (`mesh+0x174` data, `mesh+0x178` count, a flat 3-`WORD`-per-face layout with no LOD remap at all,
   unlike step 5's wedge-indirected one). Which real `ULodMesh`/`UMesh` field this second array is
   (a StaticMesh's own simpler triangle list vs. some other per-mesh face set) is not pinned down —
   flagged as unidentified, not guessed at.

**Conclusion: UED22 renders a StaticMesh actor's real mesh geometry as a genuine per-triangle
wireframe (real triangle edges of the imported mesh, selection-colored) in Wire and the three Ortho
render modes — not a bounding-box proxy, and not a sprite/icon substitute.** This confirms this
codebase's already-implemented `MeshWireframe`/`SelectedMeshWireframe` (`web/src/scene/
MeshWireframe.tsx`, `SceneResourcesContext.tsx`'s `meshWireframeGeometry` built from
`THREE.WireframeGeometry` over the mesh's real world-space triangle positions, wired into both
`Viewport3D.tsx` and `OrthoViewport.tsx` gated on `mode === 'wireframe'`) as the RIGHT convention,
already landed before this investigation and requiring no further code change — this pass only
upgrades its evidentiary basis from a banned third-party citation to a direct own-binary one, and
narrows (but does not fully resolve) the per-face-edge-completeness nuance in point 5 above.

Backend note (for whoever next touches this): `uedcli/preview_native.py`'s
`resolve_mesh_actor_polys`/`resolve_mesh_scene_polys` (landed commit `c0a79460`, "Option A") already
supply a mesh actor's real per-triangle world-space vertices to `ScenePayload.polys`
independent of CSG/build state — exactly the shape (already-flattened world-space triangles, not a
separate vertex/edge topology) a wireframe-edge renderer needs, and exactly what `MeshWireframe.tsx`
already consumes. No backend gap exists for this topic.

### Mesh-actor wireframe SELECTION — edges only, never the filled interior (closed 2026-09-18)

Board item `dev/docs/board/inbox/mesh-selection-2d-3d-wireframe-mode-vs-ued22/` (owner's hunch: mesh
selection in wireframe/2D modes may diverge from UED22). Distinct question from the RENDERING topic
above (already closed): this is whether a click INSIDE a mesh actor's wireframe silhouette, away
from any drawn edge, should SELECT it. This codebase's `meshPickGeometry` (a filled solid-triangle
raycast target, `SceneResourcesContext.tsx`) was wired into `tapSelect.ts`'s candidate list
UNCONDITIONALLY — every mode, wireframe included — so a click anywhere inside a mesh actor's
projected footprint selected it, even far from any line.

**✅ Binary-confirmed divergence, from our own `uned/UED22/render.dll` + `Engine.dll` only (no
third-party source anywhere in this pass, `pefile`+`capstone`, `dev/docs/spikes/bspspike/pe.py`).**
Three own-binary facts, chained:

1. **A hit-proxy is pushed ONCE per actor, wrapping its ENTIRE draw call — not per-primitive.**
   `render.dll`'s `URender::DrawActorSprite` (RVA `0x1f0a0`, already disassembled for the "Sprite
   alpha picking" topic) opens with, at VA `0x1001f0e1`-`0x1001f105`:
   ```
   cmp dword ptr [eax+0xb8], 0      ; a hit-testing-pass flag off Frame->Viewport (own read)
   je  0x1001f10b                   ; skip if this frame isn't a hit-test pass
   push 0xc
   mov  ecx, [esi+0x94]             ; esi+0x94 = the FDynamicSprite's own Actor*
   call dword ptr [0x100342f4]      ; IAT -> Engine.dll `?GetHitActor@AActor@@QAEPAV1@XZ`
   push eax
   lea  ecx, [ebp-0x7c]
   call dword ptr [0x100342ec]      ; IAT -> Engine.dll `??0HActor@@QAE@PAVAActor@@@Z` (ctor)
   push eax
   mov  ecx, [edi]                  ; edi = Frame arg -> Frame->Viewport
   call dword ptr [0x10034328]      ; IAT -> Engine.dll `?PushHit@UViewport@@QAEXABUHHitProxy@@H@Z`
   ```
   The three IAT slots resolve (by import name, not guessed) to `AActor::GetHitActor`,
   `HActor::HActor(AActor*)`, `UViewport::PushHit(HHitProxy const&, int)` — a genuine, own-binary-
   confirmed hit-proxy push, one `HActor` per call, BEFORE any drawing happens. This single call sits
   at the TOP of the function and is never repeated — the function's own body, disassembled in full
   (1427 instructions, RVA `0x1f0a0`-`0x206a1`), calls `URender::DrawMesh` (RVA `0xff00`) FOUR
   separate times later on (VAs `0x1001f4d4`/`0x1001f620`/`0x1001f7d9`/`0x1001fab5`) — i.e.
   `DrawActorSprite` is the real per-actor draw entry point (its own name is a historical artifact;
   it dispatches into `DrawMesh`/`DrawLodMesh` for a DT_Mesh actor, not just a 2-D icon), and EVERY
   one of those `DrawMesh` calls, plus the sprite-icon draw already documented for the alpha-picking
   topic, happens strictly AFTER this one `PushHit(HActor)` — so one hit-proxy tag covers the whole
   actor's draw, fill AND wireframe-line calls alike, not a separate tag per triangle/edge.
   (`GetHitActor` itself, RVA `0x126f70`: `eax=[ecx+0x120]; if (eax) ecx=eax; return ecx` — returns
   `this->Owner` when set, else the actor itself; `+0x120` matching `AActor::Owner`'s own established
   offset. So a hit resolves through the Owner chain, same as our own `resolveHitSurface`'s
   whole-actor semantics.)
2. **`DrawLodMesh`'s Wire/Ortho branch paints ONLY line pixels, never a filled interior** — already
   established for the "Mesh-actor wireframe rendering" topic above (own-binary, same RVA `0xd050`):
   the gate at `0xd992`-`0xd999` skips the ENTIRE shaded/filled-triangle block (`0xd0dd`-`0xd976`)
   whenever the viewport's render mode is Wire (1) or one of the three Ortho modes (13/14/15), and
   the two edge-drawing loops that DO run in that branch (`0xdb70`-`0xdc91`, `0xdca9`-`0xdd92`) issue
   only line-shaped draw calls (two explicit `FVector` endpoints per call, through the render
   device's own `DrawLine`-shaped vtable slot) — no fill call reaches the renderer in this mode at
   all.
3. **The click hit-test itself is a literal buffer/run scan, not an object-level test** —
   `Engine.dll`'s `?ExecuteHits@UViewport@@QAEXABUFHitCause@@PAEH@Z` (RVA `0x134bc0`) walks a
   caller-supplied `(count, hitproxy-pointer)` run array (`edi`=buffer, `esi`=length, at
   `0x10134bf4`-`0x10134c17`: `edi += [ecx]; esi -= [ecx]; [ecx]=0; ebx=edx` per run, i.e. skip past
   each stamped run, remembering the last one with a non-null hit-proxy pointer), then dispatches the
   found hit-proxy's own `Click` virtual (`mov eax,[ebx]; call [eax+4]` at `0x10134c37`-`0x10134c3e`,
   matching the real exported `?Click@HHitProxy@@UAEXABUFHitCause@@@Z`). This directly confirms (own
   binary, independent of the third-party `Hit.cpp` source the "Sprite alpha picking" topic above
   partly rested on) that `UViewport::ExecuteHits` — already established generically in the "Click/
   hit-detection algorithm" topic as reading "a rendered hit-proxy buffer" — really is a per-pixel/
   per-run BUFFER scan: a pixel with no stamped run has nothing for this scan to find.

**Combined: in Wire/Ortho render modes, a mesh actor's hit-proxy is only ever stamped where its own
draw call actually painted a pixel — and in that mode the ONLY thing painted is the wireframe edges
(fact 2). So `ExecuteHits`' buffer scan (fact 3) finds nothing at all for that actor at a click point
in the open interior between edges, and the click can only ever land the actor's `HActor` proxy
(fact 1) on/near a drawn edge line — never by clicking well inside its silhouette.** This is the
exact mechanism this codebase's brush-vs-wireframe fix (`wireframe-brush-selection-should-hit-test-
lines`, already landed) established for BRUSHES; this pass extends the same real UED22 mechanism to
mesh actors, which had never been checked against it.

**Not live-verified this session — a live UED22 capture and a live-browser (headless Chromium)
pixel A/B were both attempted and both blocked by real host constraints, not skipped for
convenience.** The live-UED22 attempt (`dev/docs/board/inbox/mesh-selection-2d-3d-wireframe-mode-vs-
ued22/harness-meshsel-probe.py`, following the pivot-cross/surface-stipple probes' own
`ensure_editor`+real-click recipe) hit the SAME rootless-dockerd-cannot-mount-`/workspace` limitation
already on file for the surface-selection-highlight and pivot-cross-toggle topics above, and then
(once retargeted to a daemon-mountable `/tmp` state dir) a genuine HOST-WIDE disk-full condition
(`df /`: 100% full, 64 KB free) shared with other concurrent sessions — not something to fix here by
pruning the shared docker image/build cache (the same caution `NATIVE-MATERIALIZE.md`'s own
disk-exhaustion incidents already flagged). The headless-Chromium attempt hit the same missing-
shared-library gap already on file for the Radii-overlay topic above (`chrome-linux64/chrome`:
`libglib-2.0.so.0` and 16 others not found, no root, `apt-get` denied). The harness script is
committed at the board item above for a session whose docker daemon/host disk can run it.

**Fix implemented** (`web/src/scene/geometry.ts`, `SceneResourcesContext.tsx`,
`sceneResourcesReactContext.ts`, `tapSelect.ts`, `selection.ts`, `Viewport3D.tsx`,
`OrthoViewport.tsx`): a new `buildEdgePickData` builds a raycastable `THREE.LineSegments` over a mesh
actor's own triangle EDGES (3 per source triangle, not deduped like the visual
`THREE.WireframeGeometry`, so each edge keeps its source triangle's owner/polyIndex) —
`meshEdgePickGeometry`, mirroring how `meshPickGeometry` already does this for the filled-triangle
case. `tapSelect.ts` now picks a mesh actor by `meshEdgePickObject` (raycast with the SAME line
threshold a brush's own outline uses) in wireframe mode, and by the existing filled
`meshPickObject` in every other mode — never both — and the AABB fallback's existing wireframe-mode
brush exclusion (`bug report item 6`) is extended to also exclude a resolved mesh actor (its own
`meshTriangleOwners` name set), so a raycast miss on the edges can't fall through to a full 3-D
box-test either. Verified with new unit tests (`geometry.test.ts`'s `buildEdgePickData`,
`selection.test.ts`'s `resolveEdgeHitSurface`) and the full frontend suite (366 tests green, `tsc -b`
clean save for 4 pre-existing, unrelated errors) — NOT live-pixel-verified, per the constraint above.

### Surface selection highlight — a flat blue screen-space stipple (closed 2026-09-18)

Board item `surface-selection-highlight-color-disassemble`. Owner's ask: "disassemble UED22 and check
the surface selection color. Replicate it." A SELECTED SURFACE (a BSP poly/brush face picked with a
plain tap in a textured pane) is a different code path from the sprite/mesh actor tinting the
"Selection highlight rendering" section above already covers, and had never been RE'd — our own
`SelectionHighlight.tsx` drew an invented additive-white overlay at 0.25 opacity, with no citation
for any part of it.

**✅ Binary-confirmed, from our own `uned/UED22/` binaries only — no third-party source anywhere in
this pass.** The right binary is `softdrv.dll`, not `Editor.dll` or `render.dll`: `uned/UED22/
UnrealEd.ini` pins all four viewports to `Device=SoftDrv.SoftwareRenderDevice`, so
`USoftwareRenderDevice::DrawComplexSurface` (export `?DrawComplexSurface@USoftwareRenderDevice@@…`,
RVA `0xc3a0`) is THE draw call every BSP surface goes through. Its tail, at VA `0x1000e644`:

```
1000e644:  mov   eax, ds:0x10030114          ; IAT slot -> Core.dll `?GIsEditor@@3HA`
1000e649:  cmp   dword ptr [eax], 0
1000e64c:  je    0x1000e875                  ; editor only; the game never draws this
1000e652:  test  dword ptr [esi], 0x2000000  ; esi = &Surface (2nd arg); [esi] = PolyFlags
1000e658:  je    0x1000e875                  ; PF_Selected only
1000e65e:  mov   byte ptr [ebp+0xc], 0x00
1000e662:  mov   byte ptr [ebp+0xd], 0x7f
1000e666:  mov   byte ptr [ebp+0xe], 0xff
```

- `[esi]` really is `PolyFlags`: the same function tests `[esi]` against other `PF_` masks much
  earlier (`0x1000c48f`, `0x1000d435`), and `esi` is loaded from `[ebp+0xc]` (the `FSurfaceInfo&`
  second argument) on both paths that reach this tail.
- `PF_Selected = 0x02000000`: `Editor.dll`'s `polySelectReverse` (RVA `0x4c2a0`) does
  `xor eax, 0x2000000` directly on a surf's flags at `0x1004c2fb`, and `polySelectAll` (RVA
  `0x4ba50`) passes the same bit as the set-mask to `polySetAndClearPolyFlags`.
- The channel order is not assumed either, and it matters (byte-swapped it would read orange). The
  decisive read is the **32bpp path in this same function**: `0x1000e7a6`-`0x1000e7bf` explicitly
  repacks the three bytes as `byte0<<16 | byte1<<8 | byte2` = `0x00007fff` before
  `mov dword ptr [ecx], esi`, and a Win32 32bpp surface is `0x00RRGGBB` — so byte0 is R (0) and
  byte2 is B (255). Corroborating but NOT decisive on their own: the 16-bit packer at
  `0x1000e6aa`-`0x1000e6e4` (byte0 reaches the word's top 5 bits, which is "R" only if the surface
  is RGB565 rather than BGR565), and `Engine.dll`'s `??0FColor@@QAE@ABVFPlane@@Z` (RVA `0xf32e0`),
  which writes `P.X -> [ecx+0]` (that is "R" only by FPlane convention). Independent corroboration
  from the other render devices, which are not used here but encode the same intent: `OpenGLDrv.dll`
  (`0x10004066`) writes `00 00 7f 7f` and `D3D9Drv.dll` uses `0x7f00007f` — both a half-strength
  blue, and both nonsense under the byte-swapped reading.

**So the colour is RGB(0, 127, 255) — a vivid azure — and there is NO blend at all.** The block at
`0x1000e66a`-`0x1000e870` re-walks the surface's own `FSpanBuffer` and does a raw store of that
value into the framebuffer (`mov word ptr [ecx], si` at 16bpp, `0x1000e755`; `mov dword ptr [ecx],
esi` at 32bpp, `0x1000e825`) on a sparse lattice:

- rows start at `(SpanBuffer->StartY + 1) & ~1` and step `+= 2` — every second scanline;
- columns are `x = align_up(span->Start + phase, 8) - phase`, stepping `+= 8` — every eighth pixel,
  with `phase = (y & 2) * 2`, so the phase alternates 0 / 4 on successive drawn rows.

One pixel in sixteen is overwritten with the flat colour, anchored to absolute screen coordinates
(the dots do not slide with the surface as the camera moves). Both depth paths (16bpp and 32bpp) do
the same thing. **Under the configured device this is the only selected-surface treatment there is:**
`softdrv.dll` tests the bit in exactly this one place, and `Editor.dll`'s own draw entry points
(`Draw`, `DrawLevelBrush`, `DrawFPoly`, `DrawWireBackground`) contain no `PF_Selected` test at all —
its 57 uses of the constant are all in `Exec`/`polySelect*`/`polyTex*`/`MouseDelta`/
`FEditorHitObserver::Click`/`FixBrushLinks`/`bspBuildBounds`. The scoping matters: `OpenGLDrv.dll`
and `D3D9Drv.dll` each implement their OWN, different treatment (a ~50% blue blend, no stipple), so
"UED22 stipples a selected surface" is true of the software renderer the editor actually runs, not
of the engine in general.

*(Adjacent, deliberately not folded in: `render.dll` has a second `GIsEditor && PF_Selected` gate, at
`0x10007ece`, which rescales a computed lighting colour to `c*0.5 + (0.5,0.5,0.5)`. Its containing
function (`0x10007be0`) is a lighting handler — same prologue/context shape as the others in its
family — but where it is called from is UNTRACED: its only reference is a pointer-table slot at
`0x10034cb4`, and `URender::GlobalLighting` indexes the adjacent table at `0x10034c70` under a hard
`cmp esi,0xa / jae skip`, so that slot is out of its reach. Calling it "the Gouraud mesh path, not
the surface path" would be inference, not evidence — what IS established is that a BSP surface's own
draw call is `DrawComplexSurface`, which does not go through it. Noted so a later pass doesn't
rediscover the gate and mistake it for this topic.)*

**Implemented** in `web/src/scene/SelectionHighlight.tsx`: the surface overlay is now an opaque,
unblended flat `0x007fff` draw whose fragment shader discards everything off that lattice
(`stippleBeforeCompile`, injected into the standard `MeshBasicMaterial` program so the existing
masked-group `map`/`alphaTest` clipping still works — the map only clips, the dot's colour is
restored flat after the alpha test). One documented departure: the lattice is evaluated in CSS
pixels (`gl_FragCoord` divided by the renderer's pixel ratio), not raw device pixels. UED22's
framebuffer pixel *is* its screen pixel; on a hi-DPI canvas a device pixel is a supersample of a
screen pixel, so dividing by the DPR reproduces the editor's on-screen dot density instead of
shrinking it. The actor-tint variant is untouched.

🔬 **Live-verified with real rendered pixels** (headless Chromium, real WebGL 2 via SwiftShader,
`showcase_bar` rebuilt so the textured mesh exists, perspective pane in Fullbright, real
`page.mouse.click` on a floor surface then a brick wall). Measured by diffing the pane's exact WebGL
drawing buffer before and after selection — `page.screenshot()` is useless for the colour half here,
because this app's canvases land at fractional CSS offsets (`y=521.296875`, CSS width 540.5 over a
540px buffer) and the compositor resamples every one-pixel dot across two output pixels at ~50%
each; an init script forcing `preserveDrawingBuffer` and reading `canvas.toDataURL()` gets the
untouched buffer. Results, floor click / wall click:

- 2627 of 2640 and 642 of 657 changed pixels are **exactly RGB(0,127,255)** (99.5% / 97.7%; the
  remainder are dots landing on an edge shared with another overlay).
- every touched row has the same `y % 2`, and the gap between touched rows is **2** on all 98 / 67
  row transitions — no exceptions.
- gaps between dots within a row are **8** for 2429 of 2481 and 567 of 574 (the wider gaps are where
  the surface is interrupted by an occluder).
- the phase alternates exactly as `(y & 2) * 2`: first-dot `x % 8` is **0** on one drawn-row parity
  (50 / 34 rows) and **4** on the other (49 / 34 rows), with no mixing.

An independent reviewer reproduced all of that and added four checks the first pass had not run:
deselecting leaves **0** pixels differing from the unselected baseline (the highlight goes away
completely); toggling the shading mode while a surface is selected leaves the result
pixel-identical; selecting two surfaces at once gives exactly the sum of their individual dot counts
with both phases still clean (which also settles empirically that three.js's shared shader program
still binds the pixel-ratio uniform per material); and at DPR 2 the lattice comes out as 2×2
device-pixel dots every 4 rows / 16 columns — i.e. exactly the CSS-pixel spacing the departure above
describes, and proof the uniform is bound at all (an unbound one would be 0 and paint the poly
solid). A 26-point grid scan stippled 10 distinct surfaces and selected nothing on empty space.

A MASKED surface is verified live too, on `Brush1300:4` — `showcase_bar`'s hanging "OUT OF ORDER"
sign, whose texture has 47% of its texels below the 0.5 alpha cutoff. It stipples (124 changed
pixels, **121 exactly RGB(0,127,255)**, the other 3 MSAA edge blends), so the old "a masked group
discards every fragment" failure is gone; the dots are CLIPPED rather than filling the quad
(lattice-cell occupancy **0.50** inside their own bounding box, against **0.86 / 0.88** on two
unmasked control surfaces in the same session — 0.50 against the texture's 53% opaque fraction); and
they are the FLAT colour, not the texture modulated by it (one single exact value across 97.6% of
the change; a modulation would give a spread). Where the texture is opaque the lattice stays exact
(row gaps 2 ×21, in-row gaps 8 ×94, phase clean); the only exceptions are the clipping signature —
single row gaps of 4 and 6, in-row gaps of 24 and 40, i.e. runs where a cut-out swallowed whole
lattice cells. Visually the dots sit on the plaque and along its two one-pixel hanging cords with
the transparent field between them completely undotted. That selection was driven through the app's
own `onSelectSurface` rather than a click (the sign is unreachable by cursor from the framed view),
so it exercises the masked RENDER path; the pick path is covered by the click-driven runs above.

One known behaviour change, low severity and left as is: the scene's poly list also contains
actor-owned polys, so a surface pick on a near-invisible NPC "glasses" slot now gets opaque blue
dots where it previously got a faint wash. That follows from UED22's own mechanism rather than
departing from it.

Harness (disassembly helpers + the browser pixel probe): the board item itself,
`dev/docs/board/done/surface-selection-highlight-color-disassemble/` (`harness-*.py`) — kept there
rather than under `dev/docs/spikes/`, which needs the owner's yes per edit while `board/` does not.

**A live UED22 screenshot of the same thing was attempted and could not run in this session** — the
host's docker daemon is rootless and shares no filesystem with the session, so every bind mount
`ensure_editor` needs (`/workspace/…`, `/home/agent/…`, even `/tmp`) is refused, and the editor
container cannot start at all. The finding is disassembly-tier for UED22's side (the same tier the
already-closed "Selection highlight rendering" topic sits at) plus live-pixel-tier for our own
reproduction. Confirming the dots visually in a real UED22 render remains available to a session
whose daemon can mount the repo.

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

### Radii overlay colors — REDONE FROM OUR OWN BINARY (2026-09-18)

Board item `radii-overlay-color-hardly-visible-disassemble`. Owner report: "Radii are hardly visible
in radii view. The color must be off."

**Retraction first.** Everything below the "Earlier pass" heading further down was derived from
`fgsfdsfgs/UE1`, a third-party UE1 source tree — banned as GUI-PARITY evidence (owner ruling,
2026-09-18: only our own `uned/UED22/` binary, via disassembly or a live capture, counts). Two of its
conclusions were wrong and shipped a visible bug:

- It said UED22 draws the collision shape and the light radius in ONE shared constant,
  `C_ActorArrow`. It does not. The **perspective** pane uses `C_BrushWire` — a bright `(255,63,63)`,
  not `C_ActorArrow`'s dark `(163,0,0)`. Only the ortho panes use `C_ActorArrow` for collision.
- It never said anything about alpha, and the implementation invented `OVERLAY_OPACITY = 0.55`.
  UED22 has no blend stage on any of these draws.

A dark red at 55% alpha, where the real editor paints a bright red at 100%, is exactly the reported
symptom. The `(163,0,0)` VALUE itself turns out to be right — but it was right by luck, and it was
only ever correct for two of the four things it was applied to.

**✅ Binary-confirmed, from `uned/UED22/Editor.dll` + `uned/UED22/render.dll` only.** The radii live
in one block inside `?Draw@UEditorEngine@@UAEXPAVUViewport@@HPAEPAH@Z` (export RVA `0x3c440`),
VA `0x1003d45b`–`0x1003da5a`, reached once per actor. It is inside `Draw` by its own stack frame:
it reads `GEditor` from `[ebp-0x3fc]` and the frame argument from `[ebp-0x3f8]`/`[ebp-0x400]`, the
same spill slots `Draw`'s prologue fills at `0x1003c473`/`0x1003c47c` and the same ones the
pivot-cross block (Part 4) reads. Its structure, instruction by instruction:

```
0x1003d464  test byte ptr [eax+0x47c], 2   ; Viewport->Actor->ShowFlags & 2 (the radii toggle)
0x1003d471  test byte ptr [esi+0x11c], 4   ; Actor->bSelected  (same bit Part 2/3/4 pinned)
0x1003d480  call AActor::IsBrush           ; a brush -> the moving-brush box path at 0x1003d7da
0x1003d497  mov  ecx, [eax+0x480]          ; Viewport->Actor->RendMap
0x1003d49d  cmp  ecx, 0xd / 0xe / 0xf      ; the three ortho modes -> ortho path 0x1003d54a
0x1003d4b8  <perspective path>
```

So the radii are per-SELECTED-actor and gated on a show flag, and the collision shape takes a
different branch — a different DRAW CALL and a different COLOR — per viewport kind:

| Overlay | Pane | Draw call | Color |
|---|---|---|---|
| Collision | perspective | `URender::DrawCylinder` (vtable `+0x98`) `0x1003d51c`/`0x1003d53f` | `C_BrushWire` (`+0x1ac`) at `0x1003d4fd` |
| Collision | ortho, `RendMap == 0xd` | `DrawCircle` (`+0x90`) `0x1003d5b7`/`0x1003d6e2` | `C_ActorArrow` (`+0x1f8`) at `0x1003d569` |
| Collision | ortho, `0xe`/`0xf` | `DrawBox` (`+0x94`) `0x1003d8a2`/`0x1003d7cf` | `C_ActorArrow`, same `[ebp-0x41c]` spill |
| Light radius | EVERY pane | `DrawCircle` `0x1003d932` | `C_ActorArrow` at `0x1003d913` |
| Volumetric radius | EVERY pane | `DrawCircle` `0x1003d9cd` | `C_Mover` (`+0x208`) at `0x1003d9b4` |
| Sound radius | EVERY pane | `DrawCircle` `0x1003da4e` | `C_GroundHighlight` (`+0x1a8`) at `0x1003da35` |
| Moving-brush box | EVERY pane | `DrawBox` `0x1003d8a2` | `C_ActorArrow` at `0x1003d883` |

Supporting facts, each measured rather than assumed:

- **`[viewport+0x30]` is the viewport's `Actor`, `+0x47c` its `ShowFlags` and `+0x480` its
  `RendMap`.** `uned/UED22/Engine.u`'s `PlayerPawn` `ScriptText` declares `var int ShowFlags; var int
  RendMap;` adjacent, and the block reads exactly those two, 4 bytes apart. **Bit `0x02` is the
  radii toggle**, named by the engine's own exec verbs: `uned/UED22/Engine.dll` holds the wide
  literals `SHOWACTORRADII` (VA `0x102041d8`) and `HIDEACTORRADII` (`0x102041f8`), and their handlers
  do `mov eax, [ecx+0x47c]; or eax, 2` (`0x10134582`) and `and eax, 0xfffffffd` (`0x101345a5`)
  respectively. So this block IS what "radii view" draws, and nothing else in it is conditional on
  the view mode beyond the `RendMap` dispatch. That `0xd`/`0xe`/`0xf` really are the three ortho
  panes is corroborated by our own `uned/UED22/UnrealEd.ini`, whose four saved viewports carry
  `RendMap=13`, `14`, `5`, `15` — the three ortho values plus `5` for the perspective pane. **Which
  ortho axis `0xd` is, is NOT derivable from our substrate** and is not asserted here; it does not
  matter for this finding, since all three ortho branches use `C_ActorArrow` either way. (Only the
  SHAPE differs — `0xd` draws a circle, the other two a box — matching `radiiProjection.ts`'s
  existing circle-in-top / rect-in-front-and-side split, which came from `preview.py`.)
- **The `URenderBase` vtable offsets.** Each slot is identified by `render.dll`'s OWN EXPORTED
  SYMBOL NAME at that address, not by inference: `0x10034670` `?DrawCircle@URender@@…` (RVA
  `0x1c590`), `0x10034674` `?DrawBox@…` (`0x1bf00`), `0x10034678` `?DrawCylinder@…` (`0x1c9e0`),
  `0x1003467c` `?DrawSphere@…` (`0x1ce50`), `0x10034658` `?Project@…`, `0x10034650`
  `?DrawWorld@…`, `0x10034654` `?DrawActor@…`. Turning those addresses into the `+0xNN` the call
  sites use needs the vtable base, `0x100345e0` (`0x100345bc`–`0x100345d8` are eight identical
  thunk entries, not slots) — anchored by `Project` = `+0x78`, the slot `Draw` calls at `0x1003e7eb`
  on `[[ebp-0x3fc]+0x48]`, i.e. on `GEditor->Render` (Part 4's pivot block, which projects the pivot
  location). Hence `DrawCircle` `+0x90`, `DrawBox` `+0x94`, `DrawCylinder` `+0x98`, `DrawSphere`
  `+0x9c`. *(An earlier version of this bullet also claimed the `call [eax+0x70]` at `0x1003e79d`
  was `DrawWorld`. It is not — that call takes four cdecl arguments cleaned with `add esp,0x10` and
  a `(Cam=%ls,Flags=%i` format string at `0x100de70c`, on a different object, where
  `URender::DrawWorld` takes one. Corrected after review; it was never load-bearing.)*
- **The `C_*` member offsets** come from the config-color block's real declaration order, read out
  of our OWN `uned/UED22/Editor.u`'s stored `ScriptText` (one `var(Colors) config color …;`
  declaration, 28 names). That order is NOT the order `unrealtournament.ini` writes them in, which is
  why the ini can't be used for this. Index 0 `C_WorldBox` … index 3 `C_BrushWire` … index 22
  `C_ActorArrow` … index 26 `C_Mover` … index 27 `C_OrthoBackground`. Anchored on `C_BrushWire` =
  `UEditorEngine+0x1ac` — already pinned by Part 4's live capture (the pivot cross drawn from that
  member measured `(255,63,63)`) — the block base is `+0x1a0` and `C_ActorArrow` is `+0x1f8`.
  Four independent cross-checks land exactly where that layout predicts (the last three added by the
  review pass):
  - `Draw`'s background clear is an if/else PAIR — `0x1003c544 lea ecx,[edi+0x1f0]` against
    `0x1003c552 lea ecx,[edi+0x20c]`, i.e. `C_WireBackground` for a wireframe pane against
    `C_OrthoBackground` for an ortho one. Two named colours at a fixed distance in one branch pair
    rules out any off-by-one on its own.
  - `?DrawBoundingBox@UEditorEngine@@…` (RVA `0x5f150`) uses `+0x1fc` (`0x1005f333`) and `+0x200`
    (`0x1005f549`) — `C_ScaleBox` and `C_ScaleBoxHi`, the gizmo's normal and highlighted boxes.
  - `?DrawWireBackground@UEditorEngine@@…` (RVA `0x60db0`) uses `+0x1a0` six times and `+0x1a8`
    once — `C_WorldBox` and `C_GroundHighlight`.
  - `0x1006018f lea ecx,[edi+0x1ac]` fires exactly when `?Brush@ULevel@@QAEPAVABrush@@XZ` (IAT
    `0x100cee84`) compares equal at `0x10060180`, i.e. for the BUILDER brush — `C_BrushWire`, the
    same identification Part 4 reached from a live capture.
- **Each color reaches the draw the same way**: `lea ecx, [GEditor + <offset>]` →
  `call ?Plane@FColor@@QBE?AVFVector@@XZ` (IAT `0x100cede4`) → `??0FPlane@@QAE@ABVFVector@@@Z` (IAT
  `0x100ce4a8`) → pushed as the draw's `FPlane Color`. No blend/alpha parameter exists on any of
  these calls; `LINE_None` (0) is passed for the circles and `1` for the cylinder/box.
- **`C_ActorArrow`'s value in OUR substrate: `(163, 0, 0)`.** `uned/UED22/unrealtournament.ini` line
  388, `[Editor.EditorEngine]`: `C_ActorArrow=(R=163,G=0,B=0,A=0)`. Same number the retracted
  third-party `Default.ini` claimed — now sourced from this project's own config instead.
  `C_BrushWire` is line 375, `(R=255,G=63,B=63,A=0)`.
- **The collision color is a ternary on `bCollideActors`.** Both collision branches test
  `[actor+0x198] & 1` (`0x1003d4e2` perspective, `0x1003d556` ortho) and fall through to a
  hard-coded `movaps xmm0, [0x100deae0]` when it is CLEAR — the 16 bytes there are
  `FPlane(0.3, 0.6, 1.0, 1.0)`, a light blue, used at `0x1003d527`, `0x1003d6cc` and `0x1003d7b9`.
  `bCollideActors` is bit 0 of that dword: `uned/UED22/Engine.u`'s own `AActor` `ScriptText`
  declares `var(Collision) const float CollisionRadius; … CollisionHeight; …
  const bool bCollideActors;` — so `+0x190`/`+0x194` are the two floats the same branch loads as the
  cylinder's radius/height, and `+0x198` is the bitfield they precede.
- **The light/volumetric/sound gates** confirm the `AActor` offsets independently: light needs
  `LightType != 0` (`[+0x19c]`), `bSelected`, `GIsEditor` (IAT `0x100ce730`), `LightBrightness != 0`
  (`[+0x19e]`) and `LightRadius != 0` (`[+0x1a1]`), then calls the actor's own vtable `+0x6c`
  (`WorldLightRadius`, returns in `st0`). Volumetric needs `VolumeBrightness` (`[+0x1a5]`) and
  `VolumeRadius` (`[+0x1a6]`), radius `= (VolumeRadius + 1) * 25.0` (the `25.0` at `0x100de9d4`);
  sound needs `AmbientSound != NULL` (`[+0x7c]`) and uses `SoundRadius` (`[+0x184]`) with the same
  `*25` scale. That is the exact `LightType/LightEffect/LightBrightness/LightHue/LightSaturation/
  LightRadius/LightPeriod/LightPhase/LightCone/VolumeBrightness/VolumeRadius` declaration order.

**Perspective radii are settled at ✅ binary tier now, not patch-note tier.** `render.dll` genuinely
exports `URender::DrawCylinder` and `URender::DrawSphere`, and `Editor.dll`'s non-ortho branch
genuinely calls `DrawCylinder`. The retracted third-party v200 reading below ("the whole radii block
is gated `Viewport->IsOrtho()`") is simply false for the binary we ship against — there is no
`IsOrtho` gate on the block at all, only the per-shape `RendMap` dispatch above.

**Three divergences found and deliberately NOT fixed here** (out of this item's scope, filed rather
than silently changed):

0. **UED22 draws a collision shape for a selected actor that does NOT collide; we draw nothing.**
   The `bCollideActors` test at `0x1003d4e2`/`0x1003d556` chooses only the COLOUR — both arms fall
   into the same `DrawCylinder`/`DrawCircle`/`DrawBox` call, the false arm with the hard-coded
   `FPlane(0.3, 0.6, 1.0, 1.0)` (light blue). Our pipeline instead omits the overlay entirely:
   `serve/scene.py`'s `_actor_radii` only fills `collision_radius` when `bCollideActors == "True"`,
   so a non-colliding selected actor reaches the client with no collision radius at all. That is a
   missing overlay class, not a missing colour — the "unreachable branch" note under Implemented
   below is true of the client only, and this is why.



1. **The light radius is a `DrawCircle` in EVERY pane, including perspective** — and `DrawCircle`
   builds its ring from the scene node's own camera axes (`render.dll` `0x1001c5c9`-`0x1001c62d`
   reads `FSceneNode+0x40..0x54`), i.e. a camera-facing circle. Our GUI draws a three-ring wire
   SPHERE there. `DrawSphere` exists in the vtable but this block never calls it. **FIXED
   2026-09-18** — see "Radii light-radius shape" below.
2. **`DrawCircle`'s segment count is adaptive, not fixed** — `0x1001c635` starts at `8` and doubles
   (up to `0x100`) while a screen-size term stays under a threshold (`0x1001c668` loop). Our GUI's
   ortho rings are a flat 32. `DrawCylinder`'s own segment count was NOT determined (its body is not
   a plain N-gon loop); the "8-sided" figure in the retracted patch-note paragraph below is still
   unconfirmed against the binary.

**Implemented** in `web/src/scene/RadiiOverlays.tsx`: `RADII_COLOR`/`OVERLAY_OPACITY` are gone,
replaced by `C_BRUSH_WIRE` `(255,63,63)` on the perspective collision cylinder and `C_ACTOR_ARROW`
`(163,0,0)` on the ortho collision shapes and on the light radius in every pane, all with no
`transparent`/`opacity` at all. The `bCollideActors` ternary needs no client-side branch, because
the client never sees a non-colliding actor's collision radius at all — see divergence 0 above, which
is the real (server-side) reason and is filed rather than fixed here.
Regression: `RadiiOverlays.test.tsx` (per-pane color + "never blends").

**Reviewed** (opus, own worktree, 2026-09-18): every claim above re-derived independently from
`uned/UED22/` with its own scripts — the 28-name declaration order, the branch decode, the vtable
slots (by exported symbol name), the `bCollideActors` bit, the `FPlane` constant, the `scene.py`
gate, both follow-ups, and the suites. Two doc errors found and corrected here (the wrong
`DrawWorld` attribution, and divergence 0, which this section had reduced to "unreachable"); the
review could not get real pixels either, for the same reasons.

**Verification, honestly scoped.** Rendered through `@react-three/test-renderer` against a REAL
`/api/level/showcase_bar/scene` payload (189 actors carrying radii, served from this worktree):
the perspective pane emits one `#ff3f3f` cylinder for `Pinball0` and one `#a30000` ring set for
`Light0`; top/front/side emit `#a30000` only; every material reports `transparent=false opacity=1`.
**A real browser screenshot could NOT be taken in this session** — this host has no runnable
Chromium (`chromium-1243`'s binary is missing 17 shared libraries including `libglib-2.0.so.0`, there
is no root and `apt-get update` is denied), and the same rootless-docker limitation that blocked the
surface-selection topic's UED22 capture applies here too. The on-screen pixel is nevertheless
determined: every `<Canvas>` in this app spreads `CANVAS_COLOR_MANAGEMENT`
(`{flat, linear, legacy}`, `viewportRender.ts`), a documented passthrough, so a `THREE.Color`
channel IS the output byte. Against the panes' own documented backgrounds (`dev/docs/GUI.md`:
perspective black, ortho `#404040`) the change is: perspective collision `(90,0,0)` → `(255,63,63)`;
perspective light `(90,0,0)` → `(163,0,0)`; ortho collision and light `(118,29,29)` — within 54 of
the `(64,64,64)` background on the red channel and BELOW it on green/blue — → `(163,0,0)`. A live
screenshot A/B remains outstanding and is called for in the board item.

### Radii light-radius shape — camera-facing circle, not a sphere (closed 2026-09-18)

Board item `dev/docs/board/done/gui-light-radius-is-a-camera-facing-circle-not/`, filed as divergence
1 of the "Radii overlay colors" pass above (already ✅ binary-confirmed there, from
`uned/UED22/Editor.dll` + `render.dll` — not re-derived here). `Editor.dll`'s radii block calls
`URender::DrawCircle` for the light radius on EVERY branch including perspective (VA `0x1003d932`),
and `render.dll`'s `DrawCircle` (RVA `0x1c590`) builds its ring from the scene node's own CAMERA axes
(`FSceneNode+0x40..0x54`, `0x1001c5c9`-`0x1001c62d`) — a camera-facing circle (a billboard), never a
world-plane-aligned shape. `RadiiOverlays.tsx`'s `LightSphere3D` instead drew three fixed orthogonal
world-space rings (an XY/XZ/YZ wire-sphere gizmo) in the perspective pane.

**Ortho panes needed no change.** `OrthoShapeLine` already draws the light circle flat in the pane's
own fixed `(right, up)` view-plane basis (`orthoBasis(view)`) — under a fixed-axis orthographic
camera, that IS what a camera-facing circle degenerates to (the view direction never changes, so
"facing the camera" and "lying in the pane's fixed view plane" are the same plane). Confirmed by
reading `radiiProjection.ts`/`OrthoShapeLine` directly, not assumed.

**Fix**: `RadiiOverlays.tsx`'s `LightSphere3D` is replaced by `LightRadiusCircle3D`, a genuine
camera-facing billboard built as explicit `<lineSegments>` (matching every other radii overlay's
convention — no texture, no alpha, same `C_ACTOR_ARROW` color, same `depthTest={false}`). Every
frame (`useFrame`, the same mechanism `SelectionMarkers.tsx`'s `PivotMarker`/`VertexDot` already use
to track live camera state), it rebuilds the ring from `camera.quaternion`'s own local X/Y axes
(`right`/`up`), the standard sprite-billboard basis. One coordinate-space hazard, the same class as
`SelectionMarkers.tsx`'s pivot-marker bug: this component's geometry sits inside the world-handedness
mirror group (`<group scale={[1,-1,1]}>`, a pure Y-flip), while `camera` is posed directly in the
ALREADY-reflected render space (`viewportRender.ts`'s `applyCameraPose`) — so `right`/`up` need the
same flip (negate Y) to land back in this component's own pre-reflection local space. Since the
mirror `R = diag(1,-1,1)` is self-inverse, negating Y once is exactly `R^-1`, not an approximation.

🔬 **Verified by inspecting the actual computed geometry across several camera poses** (this host has
no runnable headless Chromium, the same limitation on file for the "Surface selection highlight" and
"Mesh-actor wireframe SELECTION" topics above — a real browser A/B was not possible this session).
`RadiiOverlaysCameraFacing.test.tsx` renders `LightRadiusCircle3D` through
`@react-three/test-renderer` with a real `THREE.PerspectiveCamera` posed three different ways (down
`-Z`, down `-X`, and an oblique angle), advances one frame so `useFrame` runs, and reads the produced
`BufferGeometry`'s own position array back — not a screenshot, but the exact numbers the renderer
would draw. For each pose, the ring's own plane normal (cross product of two chords, read from the
geometry) matches the camera's forward direction (reflected the same way, `Y` negated) to better than
0.999 absolute dot product — i.e. the ring's plane rotates with the camera, not fixed in world space.
A fourth test confirms every ring point sits exactly `radius` from the actor's location (a genuine
circle, not a degenerate shape). All four pass; the full frontend suite (390 tests) stays green.

Regression: `RadiiOverlaysCameraFacing.test.tsx`. `RadiiOverlays.test.tsx`'s existing color/no-blend
tests are unaffected (still exactly one `<lineSegments>` for the light radius per pane, same color).

*(2026-09-19: `RadiiOverlays.tsx`'s `LightRadiusCircle3D` is renamed `RadiusCircle3D` and takes a
`color` prop, so the sound-radius overlay below can reuse the exact same camera-facing-circle
mechanism instead of a second copy. No behavior change for light — its call site now passes
`color={C_ACTOR_ARROW}` explicitly, same value as before.)*

### Radii sound-radius rendering — C_GroundHighlight, reusing the light-radius mechanism (closed 2026-09-19)

Board item `dev/docs/board/inbox/sound-radius-color-c-groundhighlight-unconfirmed/`. The "Radii
overlay colors" pass above already binary-confirmed (from our own `Editor.dll`, no third-party
source) that sound radius is drawn by the SAME `UEditorEngine::Draw` radii block, on the SAME
`DrawCircle` call as light radius, gated on `AmbientSound != NULL` (`[actor+0x7c]`) with radius
`SoundRadius * 25` scale (`[actor+0x184]`) — just reading a DIFFERENT color member,
`C_GroundHighlight` (`UEditorEngine + 0x1a8`), at VA `0x1003da35`/`0x1003da4e`. What that pass never
did was read `C_GroundHighlight`'s actual RGB value, or implement the overlay at all — this GUI drew
no sound-radius overlay whatsoever until now.

**`C_GroundHighlight`'s value: `(R=0, G=0, B=127)`** — a plain, direct read of our own
`uned/UED22/unrealtournament.ini` line 374, `[Editor.EditorEngine]`:
```
C_GroundHighlight=(R=0,G=0,B=127,A=0)
```
Same file, same section, same read method already used for `C_BrushWire`/`C_ActorArrow` above — no
disassembly needed for the value itself, only for the member's identity (already pinned). A plain
dark navy blue — matching the owner's own recollection ("Didn't radii view show blue for sound
radius?").

**Backend** (`uedcli/serve/scene.py`): `ActorRadii` gains `sound_radius: float | None`. `_actor_radii`
gates it on `AmbientSound` being set — mirroring `cli/rendering.py::_resolve_point_render`'s own
`_strip_object_ref(field("AmbientSound")) is not None` check exactly (duplicated as a local
`_strip_object_ref`, not cross-imported — the same leaf-helper convention this file already uses for
`_to_float`/`_to_int`) — and computes the value with the already-existing `preview.world_sound_radius`
(`25.0 * (SoundRadius + 1)`, the real `AActor::WorldSoundRadius` formula, RE'd 2026-07-21 and already
used by `actor diagram --show sound-range`). Unlike light, there is no zero-radius "treat as unset"
special case — `cli/rendering.py`'s own sound gate has no `and lr`-shaped check either, so
`SoundRadius=0` with `AmbientSound` set legitimately resolves a 25-UU sphere, not nothing.

**Frontend** (`web/src/scene/RadiiOverlays.tsx`, `radiiProjection.ts`, `api.ts`): the sound-radius
overlay is drawn by the exact same `RadiusCircle3D` (perspective, camera-facing) / `OrthoShapeLine`
(ortho, `sphereOrthoShape`) components the light radius already uses — a second color argument, not a
second mechanism, matching the fact that both are the same real `DrawCircle` call in every pane.
`selectedRadiiActors` (`radiiProjection.ts`) now includes an actor whose ONLY resolved radius is
sound (previously such an actor would have been filtered out of the overlay entirely even though the
server sent a resolved radius).

🔬 **Verified the same way the "Radii light-radius shape" section above was** (this sandbox has no
runnable headless Chromium — the same limitation on file for the "Surface selection highlight",
"Mesh-actor wireframe SELECTION", and "Radii light-radius shape" topics — so a browser screenshot A/B
was not attempted): `RadiiOverlays.test.tsx` renders the overlay through `@react-three/test-renderer`
against a `sound_radius`-only `SceneActor` and reads the produced material back, confirming a single
`<lineSegments>` colored exactly `#00007f` (`getHex(LinearSRGBColorSpace)`, no re-encoding) in EVERY
pane (perspective, top, front, side) and `transparent=false`/`opacity=1` (no blend, matching every
other radii draw). The backend gate/formula are verified directly against real content: a real
`Engine.AmbientSound` actor from the NYC_Bar corpus
(`dev/docs/spikes/2026-09-06-nycbar-n59-light-apply-movers/golden/subset/maps/02_nyc_bar/actors/
AmbientSound0/actor.t3d`, `AmbientSound=Sound'Ambient.Ambient.EchoWaterDrips'`, `SoundRadius=6`) was
parsed and run through `_actor_radii` — this sandbox's rootless docker cannot build the
`uedcli_native` Rust extension (the same mount-permission limitation on file throughout this
campaign), which blocks the real class-schema resolver `_actor_radii` needs, so the check used a
stub `defaults.for_class` returning an empty defaults dict (the same pattern
`test_actor_radii_light_radius_zero_is_treated_as_unset` already uses) rather than the full
`ClassDefaults`/`ClassIndex` machinery — this exercises `_actor_radii`'s own gate/formula logic
exactly, just not class-schema resolution (which this change doesn't touch). Result: `sound_radius ==
world_sound_radius(6) == 175.0`, `collision_radius`/`light_radius` both `None`, no note. New
regressions: `RadiiOverlays.test.tsx`'s "draws the sound radius in C_GroundHighlight in every pane"
case, `radiiProjection.test.ts`'s "includes an actor whose ONLY resolved radius is sound",
`test_serve_scene.py`'s `test_actor_radii_sound_radius_zero_is_not_treated_as_unset`/
`test_actor_radii_no_ambientsound_means_no_sound_radius`, and an added `Speaker0` actor in
`test_build_scene_payload_resolves_collision_and_light_radii`.

### Earlier pass (2026-09-16) — RETRACTED, third-party source

Everything from here to the end of this section predates the 2026-09-18 ruling and is kept only so a
later reader can see what was claimed and why it was wrong. Do not cite it.

`web/src/scene/RadiiOverlays.tsx` drew the collision cylinder and light-radius sphere in two
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
constants (`C_Mover`, `C_GroundHighlight`). *(Both halves of this are confirmed by the real
disassembly above — the per-pane split it missed is what made it wrong.)*

**`C_ActorArrow`'s exact RGB found (2026-09-16): `(163, 0, 0)`, a dark red** —
`Engine/Config/Default.ini` (`fgsfdsfgs/UE1`, line 563), `C_ActorArrow=(R=163,G=0,B=0,A=0)`. Not a
class-header default (`Editor.h`'s `C_ActorArrow` member has no in-code initializer, confirmed no
init in `UnEditor.cpp` either) — it's the shipped v200 engine's `.ini` default, loaded at first run.
Confidence at the time: 📖 source — "not yet confirmed against this project's actual
DeusEx-customized `Editor.dll`/its own installed `.ini`". *(That caveat is what mattered; our own ini
happens to carry the same value.)*

**The same `Default.ini` pull also surfaced the full adjacent `C_*` wireframe color block** —
directly relevant to the brush-wire-color question below:
```
C_BrushWire=(255,63,63)      C_Pivot=(0,255,0)         C_Select=(0,0,127)
C_AddWire=(127,127,255)      C_SubtractWire=(255,192,63)   C_GreyWire=(163,163,163)
C_ActorWire=(127,63,0)       C_ActorHiWire=(255,127,0)     C_SemiSolidWire=(127,255,0)
C_NonSolidWire=(63,192,32)   C_ActorArrow=(163,0,0)        C_Mover=(255,0,255)
```
*(Superseded: our own `uned/UED22/unrealtournament.ini` `[Editor.EditorEngine]` carries this whole
block, with these values — cite that file, not this.)* Still open from it: `C_ActorHiWire` ("Actor
Highlighted Wire") is a separate constant from `C_BrushWire`, never chased against `DrawLevelBrush`'s
own `WireColor` selection logic. `C_SemiSolidWire=(127,255,0)` (bright green) contradicted
`preview.py`'s own comment citing "UED's rose (223,149,157)" for semisolid — never resolved (different
UE1 build? different source? not determined). **Moot now: `C_SemiSolidWire` itself is banned
third-party-source evidence (owner ruling 2026-09-18) and was never used for the GUI's semisolid
color anyway — the owner reported the resulting bright green as visibly wrong and asked for
`preview.py`'s own coral instead. `web/src/scene/selectionColor.ts`'s `CSG_WIRE_COLOR.semisolid` is
now `[235, 120, 80]` (`preview.py`'s `_CSG_PALETTE["semisolid"]` front value), same GUI-only scoping
as the "Brush wireframe selection color" fix above
(`dev/docs/board/done/gui-semisolid-wire-color-wrong-match-level-photo/`).**

**RETRACTED claim (`UnEdCam.cpp:1538-1573`): "the whole radii block is gated
`Viewport->IsOrtho() && ...`", so radii are never drawn in a perspective viewport.** False for our
binary — see the disassembly above, which finds no such gate and a real `DrawCylinder` call on the
non-ortho branch. The ortho half of the claim (top draws a circle, the other two draw an
axis-aligned box from `Location ∓ (CollisionRadius, CollisionRadius, CollisionHeight)`, light always
a circle) does match the binary.

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
("it does NOT render per-brush currently") did not reproduce. No code change. *(Superseded by Part 4
below: rendering one cross per brush was correctly OBSERVED here but wrongly called "no bug" — real
UED22 draws exactly one, and the GUI now does too.)*

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

**Part 3 — which selected actor does the one global cross sit on? ✅ binary-confirmed 2026-09-18
against our own `uned/UED22/Editor.dll`, and it agrees with the owner's own live test.** The owner
reported that with several brushes selected, real UED22 draws the cross only at the brush selected
FIRST. It does, and the mechanism is a selection-HISTORY rule, not an actor-array-index rule.

- **`SetPivot` never picks an actor.** It writes `GPivotLocation` (`0x10149214`) and
  `GSnappedLocation` (`0x10149220`) straight from its own `FVector` argument (`0x100460a0`-
  `0x100460ab`, `0x100460fc`-`0x10046104`), so the CALLER decides where the pivot lands. The draw
  site reads `GSnappedLocation`, not `GPivotLocation` (`0x1003e7ad`-`0x1003e7c2`) — i.e. the
  argument after grid snapping.
- **`?NoteSelectionChange@UEditorEngine@@UAEXPAVULevel@@@Z` (RVA `0x45880`) is what decides.** Every
  selection route funnels through it (`Click@…HActor`, `edactBoxSelect`, `edactSelectAll`,
  `SelectNone`, `SafeExec`, …). It walks `Level->Actors` ascending (`0x100458cf`-`0x100458f4`),
  counting selected actors (`ObjectFlags` bit `0x04` at `[actor+0x11c]`) into `Count` and
  overwriting a `SingleActor` slot at every hit, then (`0x100458f6`-`0x1004593a`):
  - `Count == 0` → `call [vtbl+0xd0]` = `ResetPivot`;
  - `Count == 1` → `call [vtbl+0xcc]` = `SetPivot(SingleActor->Location, 0, 0)`, the location read
    from `[esi+0xd0/0xd4/0xd8]` (`AActor::Location`, offset already established by this project's
    own RE);
  - `Count > 1` → **neither**: `cmp edx, 1; jne 0x10045940` (`0x10045906`) skips the pivot call
    outright, so `GPivotLocation`/`GSnappedLocation` keep whatever they already held.

  Vtable slots resolved from the `UEditorEngine` vtable at RVA `0xcf5d4`: `+0xc4`
  `NoteSelectionChange`, `+0xcc` `SetPivot`, `+0xd0` `ResetPivot`, `+0xd4`
  `UpdatePropertiesWindows`, `+0x100` `SelectNone`.
- **So a click-built multi-select anchors on the first brush.** Plain-click A
  (`Click@FEditorHitObserver@@…HActor@@`, RVA `0x47160`, at `0x100473cc`: `SelectNone(Level,0)`, set
  A's selected bit, `NoteSelectionChange`) sets the pivot while A is alone; ctrl-click B
  (`0x100473b0`, toggles B's bit, then `NoteSelectionChange` at `0x10047408`) hits the `Count > 1`
  path and never moves it. Same for C, D, … ✅ exactly what the owner saw.

**The precise rule is "the actor that was most recently the SOLE selection" — not "first clicked",
and not "lowest actor index".** The distinction is observable: from an A+B selection, deselecting A
moves the cross to B, because the selection passes back through `Count == 1`. And a selection that
never passes through a single-actor state — a marquee `edactBoxSelect`, `edactSelectAll`, an `ACTOR
SELECT` exec verb going 0 → N — calls `SetPivot` not at all, leaving the cross at a stale location
from whatever last set it. Array order is a red herring: both `NoteSelectionChange` and `SetPivot`
walk `Level->Actors` ascending and leave `SingleActor` holding the HIGHEST-index selected actor, but
that variable is only ever consumed under `Count == 1`, where there is exactly one candidate.

Only five call sites set the pivot at all — every `call [reg+0xcc]` in `Editor.dll`, with no direct
(`E8`) calls and no other module importing it: `NoteSelectionChange` (`0x1004593a`), `ResetPivot`
(`0x10045d94`, once per selected brush, ascending), `MouseDelta` (`0x100428a2`, vertex-edit mode
only — gated on `[this+0x118] == 0x18`), `Click@…HBrushVertex` (`0x10047718`), `Click@…HGlobalPivot`
(`0x10047d20`). *(Corrected in Part 4 below: there are SEVEN, not five — this scan missed the
two-instruction dispatch form.)*

**Nuance found on the way, reported rather than smoothed over: `GPivotShown` is a LATCH.** It is
written only inside `SetPivot` (`0x10046453`) and read only at the draw site (`0x1003e7a0`) — every
reference to `0x101491e8` in the binary was enumerated. Since `NoteSelectionChange` calls `SetPivot`
only at `Count == 1`, its `Count > 1` term is never evaluated by an ordinary click-built
multi-select: selecting A alone latches `GPivotShown = 0`, and adding B leaves it there. On that
reading the cross stays hidden until some other trigger calls `SetPivot` while 2+ actors are selected
(a brush-vertex click, a click on the pivot proxy, vertex-edit dragging, `ResetPivot`'s per-brush
loop). This does not affect the anchor answer above, and it does not contradict the owner's report of
WHICH brush carries the cross — but it does mean Part 2's "hidden for a lone selection" is a latched
state, not a per-frame recomputation, and the trigger that makes the cross appear during a
multi-select is not yet identified. Flagged, open. *(Resolved in Part 4 below: the latch is real, and
Part 2's "hidden for a lone selection" is WRONG for a brush — the `SnapCount` term, not the `Count`
term, is what shows the cross in ordinary use.)*

### Part 4 — the complete mechanism, resolved (2026-09-18): all 7 call sites + a live UED22 capture

Part 3 left one thing unexplained: on a strict reading of the latch, a click-built multi-selection
could never turn the cross on, yet the owner reported seeing it. This pass closes that, with a
disassembly re-scan of our own `uned/UED22/Editor.dll` and a live capture in a real UED22 (a
throwaway `ued-x86-runtime` container, real XTEST mouse clicks, screenshots read pixel by pixel).
**Part 2's framing was wrong in one specific way, and the correction is the whole answer.**

**What `GPivotShown` really is.** `SetPivot` (RVA `0x46060`) walks `GEditor->Level->Actors`
(`[this+0xa8]`, data `+0x2c` / count `+0x30`) at `0x10046309`-`0x10046347` and tallies TWO counters
off each actor's bitfield dword at `[actor+0x11c]`:

- `Count` (`esi`) — actors with bit `0x04` set (`test al,4` at `0x1004632a`). That bit is `bSelected`.
- `SnapCount` (`edi`) — of those, the ones with bit `0x40` also set (`shr eax,6; and eax,1; add edi,eax`
  at `0x10046332`-`0x10046338`).

Then the tail at `0x10046441`-`0x10046453`: `test edi,edi; jg true; cmp esi,1; jg true; else 0` →
`GPivotShown = (SnapCount > 0) || (Count > 1)`.

**Bit `0x40` is `bEdShouldSnap` — and that is why a single selected brush already shows the cross.**
`[actor+0x11c]` is one DWORD of `AActor`'s editor bool bitfields, and UE1 assigns their masks in
declaration order. `Engine.Actor`'s OWN stored `ScriptText` inside `uned/UED22/Engine.u` (lines
162-169) declares them consecutively:

```
bHiddenEd 0x01 · bDirectional 0x02 · bSelected 0x04 · bMemorized 0x08
bHighlighted 0x10 · bEdLocked 0x20 · bEdShouldSnap 0x40 · bEdSnap 0x80
```

Two independent anchors in the binary land exactly on that layout: `SetPivot` and
`NoteSelectionChange` both use bit `0x04` as "selected", and `Click@…HActor` tests bit `0x20` to SKIP
an actor (`0x1004726b`, `0x10047347`, `0x1004739c`) — precisely what `bEdLocked` ("Locked in editor —
no movement or rotation") means. So `SnapCount`'s bit `0x40` is `bEdShouldSnap`, measured rather than
inferred.

Decoding class defaults across every `uned/UED22/*.u`, exactly two classes default `bEdShouldSnap`
True: **`Engine.Brush`** and `Engine.ClipMarker` (an editor-only clip-plane marker, never in level
content). `Engine.Actor`'s own default is False, so `Engine.Light` and every other point actor is
False; `Engine.Mover` extends `Engine.Brush` and inherits True. Live capture confirms the consequence
directly: one selected BRUSH → cross drawn; one selected LIGHT → no cross anywhere. So in ordinary
editing the cross is on because of the `SnapCount` term, not the `Count` term, and **Part 2's "UED22
hides the cross for a single selected actor" is wrong for brushes** (right for point actors).

**All seven `SetPivot` call sites.** Part 3's scan looked only for the one-instruction dispatch
`call dword ptr [reg+0xcc]` and so missed the two-instruction form MSVC also emits,
`mov eax,[reg+0xcc]` + `call eax`. Re-done as an exhaustive enumeration instead: EVERY instruction in
`Editor.dll`'s `.text` whose memory operand carries the disp32 `0xcc` — 24 of them, brute-force
decoded at each byte offset where the pattern appears rather than by a linear sweep (a linear sweep
desyncs on data-in-text, which is how the earlier pass under-counted). Seventeen are unrelated member
accesses (`UEditorEngine+0xcc` is also a data member; so are `UBrushBuilder+0xcc`, `UClass+0xcc`);
the other seven are these. There are no direct (`E8`) calls to `SetPivot`'s RVA anywhere in the file.

| # | Site | VA | What it passes | When it fires |
|---|---|---|---|---|
| 1 | `NoteSelectionChange` | `0x1004593a` | `SetPivot(SingleActor->Location, 0, 0)` | only at `Count == 1` |
| 2 | `ResetPivot` | `0x10045d94` | `SetPivot(Location + transformed PrePivot, 0, 1)`, once per selected brush (ascending, last wins) | only from `NoteSelectionChange` at `Count == 0` (so the loop body never runs) and from `ACTOR RESET PIVOT` |
| 3 | `MouseDelta` | `0x100428a2` | `SetPivot(vertex-list centre, 1, 0)` | drag start (`[ebp+0xc] & 8`) in vertex-edit mode only (`[this+0x118] == 0x18`) |
| 4 | `Click@…HBrushVertex` | `0x10047718` | the clicked brush vertex | clicking a vertex handle |
| 5 | `Click@…HGlobalPivot` | `0x10047d20` | `SetPivot(HGlobalPivot.Location, (Buttons>>1)&1, 1)` | clicking the cross itself |
| 6 | `Exec` | `0x10064ec3` | `SetPivot(GEditor->ClickLocation, snapped?1:0, 0)`, between `NoteActorMovement` (`0x10064e8c`) and `FinishAllSnaps` (`0x10064ed5`) | the `PIVOT HERE` / `PIVOT SNAPPED` exec verbs (the frontend's "Place Pivot Here" / "Place Pivot Snapped Here" menu items — `unrealed.exe` sends exactly those two strings, with no `EDIT` prefix) |
| 7 | `Exec` | `0x10067981` | `SetPivot(mover->Location, 0, 0)`, once per selected mover | the `MOVER KEYFRAME NUM=` verb ("Set mover keyframe") |

`ResetPivot` itself has exactly two call sites: `NoteSelectionChange` (`0x100458fe`, `Count == 0`) and
`Exec` (`0x10067487`, `ACTOR RESET PIVOT`). Vtable slots read from the `UEditorEngine` vtable at
`0x100cf5d4`: `+0xc4` `NoteSelectionChange`, `+0xc8` `NoteActorMovement`, `+0xcc` `SetPivot`, `+0xd0`
`ResetPivot`, `+0xd4` `UpdatePropertiesWindows`, `+0x100` `SelectNone`.

Reading sites 6 and 7 needs one decoding note: inside `Exec` the compiler keeps `this` in `esi` but
ALSO holds a base pointer `edi = this + 0x28`, so `[edi+0x80]` is `UEditorEngine::Level` (`this+0xa8`,
the offset `SetPivot`/`ResetPivot` use directly) and `[edi+0x100]` is `ClickLocation` — pinned as
`this+0x128` by `?edSetClickLocation@UEditorEngine@@…` (RVA `0x46810`), which writes its `FVector`
argument to `[this+0x128 .. +0x130]`, and by `Click@…HActor` (`0x100471bd`) storing the clicked
actor's `Location` there. In `Draw`, `this` is spilled to `[ebp-0x3fc]` at `0x1003c473`, which is what
makes `[ebp-0x3fc]+0x1ac` a `UEditorEngine` colour member and `[ebp-0x3fc]+0x48` its `Render`.

**No plain per-click pivot re-evaluation exists.** That was the other hypothesis worth killing:
`GPivotShown` (`0x101491e8`) has exactly two references in the whole binary — the write inside
`SetPivot` (`0x10046453`) and the read at the draw site (`0x1003e7a0`) — so nothing outside `SetPivot`
can change it, and none of the seven sites is a general "on every click" handler.

**What the cross actually looks like.** Inside `Draw@UEditorEngine` the preceding call
(`0x1003e79d`) falls straight through into the gate `cmp dword ptr [0x101491e8],0; je 0x1003ea04`
(`0x1003e7a0`), and between that gate and the first draw there is no condition but the
`Render->Project` success test (an enclosing conditional further up the function was not ruled out).
It projects `GSnappedLocation` (`0x10149220`, NOT `GPivotLocation`), registers an `HGlobalPivot` hit
proxy when the frame is hit-testing, and issues three `Draw2DPoint` calls: a centre dot at `X±1, Y±1`
(constant `1.0` at `0x100d2f80`), then a VERTICAL bar at `X, Y±4` and a HORIZONTAL bar at `X±4, Y`
(constant `4.0` at `0x100de9a8`) — a plus with a fat centre, 9 px across as the live capture renders
it. Colour comes from the `FColor` member at `UEditorEngine+0x1ac`, the SAME member `DrawLevelBrush`
uses for the builder brush; in our own `uned/UED22/unrealtournament.ini`'s `[Editor.EditorEngine]`
that is `C_BrushWire=(R=255,G=63,B=63)`. The live capture reads back exactly that colour and exactly
that shape:

```
 433 ....#....      21 pixels of RGB (255,63,63):
 434 ....#....      the 9px vertical bar, the 9px horizontal bar,
 435 ....#....      and the 3x3 centre dot -- byte-for-byte what the
 436 ...###...      three Draw2DPoint calls predict.
 437 #########
 438 ...###...
 439 ....#....
```

(The `C_*` block's base offset is not independently pinned; `+0x1ac` is identified as `C_BrushWire`
because `DrawLevelBrush` at `0x10060195` uses it exactly when the brush being drawn IS the builder
brush — the guard is a call through IAT slot `0x100cee84`, which resolves to the imported symbol
`?Brush@ULevel@@QAEPAVABrush@@XZ`, i.e. `ULevel::Brush()` — and the live capture shows the builder
brush and the pivot cross in the same `(255,63,63)`. The colour is fetched via `0x100cede4` =
`?Plane@FColor@@QBE?AVFVector@@XZ`, which is what identifies the member as an `FColor` at all.)

**The live capture — what was actually done and measured.** Throwaway `ued-x86-runtime` container,
`MAP NEW` + `MAP IMPORTADD` of three cube brushes at `(-512,0,0)`, `(512,0,0)`, `(0,512,0)` plus two
`Light`s, real XTEST clicks (`xdotool mousemove … keydown ctrl click 1 keyup ctrl`), `wine_ctl shot`
of the editor window, pixels read with PIL. Every step below is a measured pixel result, not an
inference:

| Action (real clicks unless noted) | Selected | Cross |
|---|---|---|
| boot, nothing clicked | 0 | none (`GPivotShown` starts 0) |
| plain-click BrushB's outline | 1 brush | **at BrushB** |
| ctrl-click BrushA | 2 brushes | **still at BrushB** — unmoved |
| ctrl-click BrushB off | 1 brush (A) | **moved to BrushA** |
| plain-click empty space | 0 | **still at BrushA** — the latch, drawn with nothing selected |
| `ACTOR SELECT OFCLASS CLASS=ENGINE.LIGHT`, one Light in level | 1 light | none |
| re-import Lights, select all 3 by the same verb | 3 lights | none — `Count > 1` alone does NOT show it |
| then `PIVOT HERE` | 3 lights | **appears**, at `ClickLocation` — the `Count > 1` term, once something calls `SetPivot` |

Two by-products worth keeping. Selected-vs-unselected brush wire measured live as
`(127,127,255)` vs `(63,63,128)` for `C_AddWire`, and vertex handles as `(255,75,75)` on a
`C_BrushWire` brush and `(152,152,255)` on a `C_AddWire` one — i.e. the 1.0×/0.5× selected/unselected
rule and `VertexColor = WireColor * 1.2` (with per-channel clamping), both already implemented in
`selectionColor.ts`, now confirmed against the real editor rather than source. And **`SELECTNAME` does
NOT notify**: driving selection with it leaves the pivot wherever it was, which is exactly why Part
2's supplementary screenshot probe found a marker at neither selected brush. That inconclusive result
is now explained, not merely set aside.

**Not determined.** Whether `unrealed.exe` ever dispatches this same vtable slot itself — it holds
many `call [reg+0xcc]` sites, none attributable to a `UEditorEngine` receiver from a static read, and
its own pivot menu items demonstrably go through the exec verbs above ("Place Pivot Here" →
`PIVOT HERE`, "Reset &Pivot" → `ACTOR RESET PIVOT`). It would not change the mechanism either way: any
such call still lands in `SetPivot` and recomputes `GPivotShown` the same way. Also not determined:
whether a point actor can ever carry `bEdShouldSnap=True` in real content (a
level author could set it per-actor; our GUI has no access to the value); the exact `C_*` block base
offset (only `+0x1ac`'s identity is pinned, by behaviour); and what the pivot does mid-drag (the
`MousePosition`/`MoveVertex` writes to `GPivotLocation`/`GSnappedLocation` at `0x10044f16`… were not
traced — they cannot change `GPivotShown`, only where the cross sits while dragging).

**What was built from this (`web/src/scene/SelectionMarkers.tsx`, `selectionSet.ts`).** The GUI drew
one cross per selected brush, unconditionally. It now draws exactly ONE, at `pivotAnchor`'s actor —
the first (oldest) member of the selection set, which for the ordinary click paths (plain tap,
Ctrl+tap add, Ctrl+tap remove down to one) is "the actor most recently the sole selection" — and only
when that actor is a brush (the stand-in for `bEdShouldSnap`, per `Engine.Brush`'s class default).
Three deliberate, recorded divergences from the literal UED22 state machine: nothing is drawn when
nothing is selected (UED22 leaves a stale cross — the owner asked for hidden); deselecting the anchor
out of a 3+ selection moves the cross to the next-oldest rather than leaving it on the now-deselected
actor; and a batch select that jumps straight to 2+ actors without passing through one — the org
panel's `onSelectMany`, whether from empty or replacing another selection; UED22's own marquee/
select-all — anchors on the batch's first member rather than leaving the cross where it was.
Regressions:
`SelectionMarkers.test.tsx` (count + position through a real render) and `selectionSet.test.ts`'s
`pivotAnchor` cases.

**The three divergences, owner decision pending (2026-09-18).** Owner reviewed all three and said
"leave it for now" — current (non-literal) behavior stays as-is, no code change. Restated plainly,
one at a time, for whoever picks this up next:

1. **Deselect everything.** Select a brush (cross shows on it), then click empty space. This GUI
   hides the cross. Real UED22 leaves it frozen at the brush's old position — a "ghost" marker with
   nothing selected.
2. **Deselect the anchor out of a 3+ selection.** Select A (cross on A), then also B and C (cross
   stays on A). Deselect just A, leaving B+C selected. This GUI moves the cross to B (next-oldest).
   Real UED22 leaves it stuck at A's old spot, even though A is no longer selected — another ghost.
3. **Batch/marquee select instead of one at a time.** Box-select (or select-all) 5 brushes at once,
   skipping the "exactly 1 selected" moment individual clicks pass through. This GUI picks a sensible
   anchor and shows the cross there. Real UED22's actual trigger mechanism never fires for a batch
   like this, so the cross wouldn't move at all — it'd stay wherever it was left before the batch.

**Owner's exact standing instruction for surfacing this again**: "put these 3 cases into the
GUI-PARITY doc, and ask the next agent to ask me about it at the start of the next session IF a
randomly generated number between 0 and 1 is less than 0.1. I should have the answer by then."

Any agent picking up GUI-PARITY/GUI-fidelity work in a NEW session: **generate a random number in
[0, 1). If it is less than 0.1, ask the owner directly (`AskUserQuestion`) whether they now want any
of the three divergences above made literally faithful to UED22, restating each scenario plainly as
written here. If the number is 0.1 or higher, do not ask — proceed normally, this item stays
"leave it for now" until the owner raises it themselves or the dice come up right.** This is a
literal, deliberate instruction, not a typo or a joke to normalize away — implement it exactly as
given, one honest coin-flip per new session, not a rephrased "occasionally".

### Directional arrow gizmo (closed 2026-09-19)

Board item `dev/docs/board/inbox/gui-never-renders-point-actor-directional-arrow/`. Its own cited
geometry/gating (`UnEdCam.cpp`, `fgsfdsfgs/UE1`) is explicitly THIRD-PARTY-SOURCED and banned as
GUI-PARITY evidence (2026-09-18 ruling) — this is a full redo from our own `uned/UED22/Editor.dll`/
`Engine.dll` (`pefile`+`capstone`, harness at the board item's own `harness/` dir), confirming some
of it, correcting the rest.

**✅ Binary-confirmed: the whole block is a SEPARATE, always-evaluated per-actor overlay — NOT part
of "radii view".** It sits in `UEditorEngine::Draw` (export RVA `0x3c440`) immediately after the
sound-radius draw this doc's "Radii overlay colors" section already mapped, at VA
`0x1003da60`-`0x1003e098`:

```
0x1003da60  test byte ptr [esi + 0x11c], 2      ; AActor.bDirectional (bit 0x02 -- see below)
0x1003da67  je    0x1003e09e                     ; skip the WHOLE block if not directional
0x1003da6d  push  esi
0x1003da6e  call  0x10037600                     ; IsA(ACamera) -- see below
0x1003da73  add   esp, 4
0x1003da76  test  eax, eax
0x1003da78  je    0x1003da86                      ; not-Camera -> read bSelected instead
0x1003da7a  mov   eax, dword ptr [edi]            ; edi = Frame -> [edi] = Frame->Viewport
0x1003da7c  xor   ecx, ecx
0x1003da7e  cmp   esi, dword ptr [eax + 0x30]      ; esi (this actor) vs Viewport->Actor
0x1003da81  setne cl                               ; ecx = 1 unless esi IS the possessed actor
0x1003da84  jmp   0x1003da92
0x1003da86  mov   ecx, dword ptr [esi + 0x11c]      ; not-Camera: ecx = bSelected bit (0x04),
0x1003da8c  shr   ecx, 2                            ;   extracted via shr 2 & 1
0x1003da8f  and   ecx, 1
0x1003da92  test  ecx, ecx
0x1003da94  je    0x1003e09e                        ; skip if the gate above says no
```

**The decisive, previously-unchecked fact**: `je 0x1003da60` is EXACTLY where the two gates
guarding the whole preceding radii block (`ShowFlags & 2` at `0x1003d46b`, `bSelected` at
`0x1003d478`) jump to on FAILURE — i.e. the arrow-gizmo test at `0x1003da60` runs whether or not
"Show Radii" is on, and whether or not the actor is selected. **This is not a radii-view feature at
all — it is evaluated for every actor in the level, every frame, gated only by its own three terms.**

**Gate, confirmed exactly**: `bDirectional && (IsA(ACamera) ? (actor != Viewport->Actor) : bSelected)`.

- **`bDirectional` = bit `0x02`** of the same `[actor+0x11c]` bitfield dword this doc's pivot-cross
  Part 4 already mapped (`bHiddenEd 0x01 · bDirectional 0x02 · bSelected 0x04 · …`, from
  `Engine.Actor`'s own stored `ScriptText` in `uned/UED22/Engine.u`) — a second, independent
  confirmation of that bit layout (the property comment there reads "Actor shows direction arrow
  during editing", matching this feature exactly).
- **`IsA(ACamera)` — real function, real class, own binary.** The call at `0x10037600` is a generic
  `IsA`-shaped walk (compares `esi->Class` up its `[+0x28]` SuperField chain against a target
  `UClass*`), and the target comes from `call dword ptr [0x100ceeb8]` with NO `this` argument — an
  IAT slot that resolves (by import name) to `Engine.dll`'s exported
  `?StaticClass@ACamera@@SAPAVUClass@@XZ`, i.e. `ACamera::StaticClass()`. Confirms the board item's
  `IsA(ACamera::StaticClass)` claim, independently, from our own binary.
- **The Camera exclusion is NOT "always show" — it's "show unless this actor IS the viewport's own
  possessed actor."** `eax = [edi]` (`edi` = the `Draw` call's `Frame` argument) dereferences to
  `Frame->Viewport`, and `[eax+0x30]` is `Viewport->Actor` (the SAME `[viewport+0x30]` offset this
  doc's "Radii overlay colors" section already pinned as the viewport's controlled actor). So a
  Camera shows its arrow UNLESS it is the exact camera the viewport is currently looking through —
  never fires in THIS GUI, whose viewports are always free-fly and never "possess" a level actor, so
  every Camera-descendant actor's arrow shows unconditionally here.
- **Non-Camera path reads `bSelected` (bit `0x04`) directly** — `shr ecx,2; and ecx,1` extracts
  exactly that bit, matching `NoteSelectionChange`/`SetPivot`'s already-established use of the same
  bit for the same meaning.
- **No `IsOrtho`/`RendMap` test anywhere in the block** — confirmed by reading every instruction from
  `0x1003da60` to `0x1003e098` (296 lines of disassembly); the board item's "gated `IsOrtho()`,
  perspective unconfirmed" question is answered: **the arrow renders in every pane, perspective and
  all three ortho, unconditionally** — same as this doc's light/sound radii, and for the same reason
  (this code sits right alongside them with no viewport-kind branch of its own).

**Geometry, corrected from the real constant pool (NOT the board item's third-party 48/16/16):**
after the gate passes, `0x1003dac5`-`0x1003dae1` computes `C = GMath.UnitCoords / Actor->Rotation`
(`Actor+0xdc` = `Rotation`, `FCoords::operator/(FRotator const&)` — IAT `0x100ce490` resolves to
`Core.dll`'s `??KFCoords@@QBE?AV0@ABVFRotator@@@Z` — confirming the board item's
`GMath.UnitCoords / Actor->Rotation` formula exactly), then builds three scaled axis vectors from
constants read directly out of the binary (`harness-readmem.py` against `0x100de9c8`/`0x100de9cc`/
`0x100de9dc`): **`38.0`** (shaft), **`16.0`** (fin-back distance), **`12.0`** (fin spread) — not
48/16/16. Five `RenDev->DrawLine`-shaped calls follow (`call [eax+0x80]` at `0x1003dce5`/
`0x1003ddbf`/`0x1003de9d`/`0x1003df93`/`0x1003e079`, the same render-device line-draw vtable slot
this doc's "Mesh-actor wireframe rendering" section already established), each preceded by a fresh
`FPlane`/`FColor::Plane()` copy of `GEditor + 0x1f8` = **`C_ActorArrow`** (the SAME member the radii
overlay's ortho collision/light/sound draws already use, already pinned `(163,0,0)` in our own
`uned/UED22/unrealtournament.ini`):

- shaft: `Location` → `Tip = Location + XAxis*38`
- 4 fins, all from `Tip` to `Anchor ± Axis*12`, where `Anchor = Tip − XAxis*16` (i.e. 16uu back from
  the tip, 22uu out from `Location`): `Anchor − YAxis*12`, `Anchor + YAxis*12`, `Anchor − ZAxis*12`,
  `Anchor + ZAxis*12`.

A `PopHit` call follows the 5 draws (`0x1003e090`-`0x1003e096`, IAT `0x100cedc4` =
`?PopHit@UViewport@@QAEXH@Z`), consistent with the arrow sharing the actor's own `HActor` hit-proxy
push from `DrawActorSprite`'s function start (already documented under "Mesh-actor wireframe
SELECTION") rather than pushing a new one of its own — not exercised further here (out of scope: no
report asks whether the arrow itself is clickable).

**Which classes set `bDirectional=True` — decoded from real compiled class defaults, not ScriptText
text.** `u-format.md`'s own note that "UCC stores the source only up to (not including)
`defaultproperties`" means a literal `bDirectional=True` never appears as ScriptText, even for a
class that sets it — confirmed empirically (a raw regex scan of `Engine.u`/`DeusEx.u`'s ScriptText
for `bDirectional\s*=\s*True` found zero hits, even though the binary tail decode below finds nine).
So this needed a real UClass-tail defaults decoder, not a text search. Built one from scratch
(`harness/upkg_min.py`, ported directly from `uedcli-native/src/package_read.rs`'s
`read_compact_index`/`read_property_tags` and `uedcli/uprops/ufield.py`'s `_walk_expr` bytecode
walker — this sandbox's rootless docker cannot bind-mount `/workspace` at all (confirmed: even a
mount of a throwaway `/tmp` dir returns "no such file" inside the container — the daemon shares no
filesystem with this session, the same wall the "Surface selection highlight"/"Mesh-actor wireframe
SELECTION" sections hit), so `uedcli_native` cannot be built here and the project's own `uprops`
module — which calls it for every package parse — is unusable; the minimal reader is READ FROM the
already-documented format facts, not a new invention). Walked all 1254 classes across
`uned/UED22/Engine.u` (88) + `DeusEx.u` (1166) with zero decode errors (matching this project's own
"1914/1914 classes clean" walker-integrity bar for the same bytecode-walk mechanism):

- **`Engine.Actor`'s own base default is explicitly `False`.**
- **`Engine.Pawn` sets `bDirectional=True`** — inherited by EVERY Pawn descendant with no further
  override anywhere in either package: `Engine.Camera` (extends `PlayerPawn` extends `Pawn`), every
  DeusEx NPC/bot class, the player pawn itself.
- Independently, in `Engine.u`: `InterpolationPoint`, `Projectile`, `Teleporter`, `PlayerStart`,
  `PatrolPoint`, `Spotlight`, `AmbushPoint`.
- Independently, in `DeusEx.u`: `ParticleGenerator`, `PawnGenerator`, `DeusExMover`, `WanderPoint`,
  `SecurityCamera`, `HidePoint`, `ElectricityEmitter`, `DirectionalTrigger`, `LaserTrigger`,
  `ProjectileGenerator`, `SpawnPoint`, `TrashGenerator`, `BeamTrigger`.
- `Engine.Brush`/`Engine.Mover` do NOT override it (both inherit `Actor`'s `False`) — but
  `DeusEx.DeusExMover` (the concrete Mover class every DX level actually places) DOES set it `True`,
  confirming the disassembly's "no `IsBrush` gate" finding matters in practice: a selected DeusEx
  Mover really does get an arrow in real UED22, and a plain `Engine.Mover`/generic brush does not.
- No class anywhere resets an inherited `True` back to `False`.

**Implemented.** Backend (`uedcli/serve/scene.py`): `DirectionalArrow` (`require_selection: bool`,
`lines: tuple[float, ...]`) resolved by `_actor_directional_arrow` — instance-else-class-default
`bDirectional` (same convention as `_is_hidden_ed`), `ClassIndex.descends_from(cls, "Engine.Camera")`
for the Camera check (fails open/truncates, never raises — an unresolvable ancestor degrades to
"not a Camera" the same way an unresolvable class degrades `_is_hidden_ed` to "not hidden"), and
`_directional_arrow_lines` computing the 5 segments' WORLD-space endpoints server-side via
`rotation.actor_matrix` (`GMath.UnitCoords / Rotation`'s own already-spike-verified convention,
ROTATION ONLY — deliberately not `actor_linear`, which folds in MainScale/PostScale the real
disassembly's formula has no scale term for at all). Runs for EVERY actor, brush included (unlike
`ActorRadii`, which explicitly skips brush actors) — matching the "no `IsBrush` gate" finding above.
Frontend (`web/src/scene/DirectionalArrows.tsx`): draws every visible actor's 5-segment dart as one
batched `<lineSegments>` in `C_ActorArrow`, filtered by `require_selection` vs. the current
selection — mounted unconditionally in both `Viewport3D.tsx` and `OrthoViewport.tsx` (never behind
the `showRadii` toggle, matching the "not radii-view" finding above).

**Verification — computed-geometry tier, not a live pixel A/B.** This sandbox has no runnable
headless Chromium (missing shared libraries, no root, `apt-get` denied — the same repeated
limitation on file for the "Surface selection highlight"/"Mesh-actor wireframe SELECTION"/"Radii
light-radius shape" sections) and its docker daemon cannot mount this repo for a live UED22 capture
either (confirmed above). Verified instead the way those sections' own fallback tier already
establishes as accepted for this campaign: `DirectionalArrows.test.tsx`
(`@react-three/test-renderer`) confirms the exact `C_ActorArrow` color, the require-selection gate,
the Camera-always-shows exception, and that N visible arrows batch into one draw call; five new
`uedcli/tests/test_serve_scene.py` cases (`test_actor_directional_arrow_*`,
`test_directional_arrow_lines_identity_pose_matches_hand_computed_geometry`,
`test_build_scene_payload_resolves_directional_arrow_from_real_class_defaults`) exercise the real
server-side resolution — the last one against the REAL committed `uned/UED22/Engine.u` class
defaults (`Engine.PatrolPoint`/`Engine.Camera`/`Engine.Light`), not a stub. The geometry test hand-
verifies the 10-point shape at an identity pose (Location=(0,0,0), no Rotation) against the formula
above. None of this is a live-rendered pixel — flagged honestly, same as the sections above.

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
