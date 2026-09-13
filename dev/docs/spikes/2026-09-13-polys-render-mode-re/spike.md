# Spike: what does `REN=3` ("Polys") actually render?

**Question:** `dev/docs/unrealed/commands.md`/`rendering.md` RE'd the numeric perspective-render-mode
enum (`1`=Wire, `2`=Zones, `3`=Polys, `5`=DynLight, `6`=PlainTex) but nobody had ever looked at what
mode `2` or `3` visually shows. This spike gets a real screenshot of `REN=3`, to inform a
`level photo --mode polys` design for uedcli's native (non-editor) rasterizer.

## Method

### Two dead ends hit first (both real findings, not just process notes)

1. **Bare `CAMERA OPEN`** (this dir's original `polys_probe.py`, now deleted — see git history)
   opened a standalone camera window per mode and grabbed it. In this container it came back
   stuck/stale: every mode showed the same default grid/horizon scene regardless of level content
   (even a full retail map). `rendering.md` already documents `CAMERA OPEN` as capture-once-at-a-
   fixed-default-pose and un-poseable (2026-07-06 spike, round 8); superseded here.
2. **`MAP IMPORTADD` of a hand-typed brush T3D is invisible to CSG.** `quirks.md` "How brushes enter
   the level" documents this directly: `MAP REBUILD` builds NO BSP from an `IMPORTADD`'d brush — the
   level stays solid, zero carved space. Hit live this session: with `IMPORTADD`'d geometry, EVERY
   render mode (wire, "textured") showed nothing but each brush's own always-drawn wireframe outline,
   no matter the `RendMap` ini setting — because there was never a built `Model` to render filled
   surfaces from. Fix: build geometry the way `uedcli.writes.add_actor` does — point actors via
   `MAP IMPORTADD`, brushes via `EDIT PASTE` (`writes._re_add`) — using `uedcli.builders`
   (`cube`/`make_brush_actor`), never raw T3D import for brushes.
3. **`CAMERA ALIGN NAME=<brush>` gave a degenerate framing for a large Subtract room.** Aligning to
   the room brush (or to a small Add box) left the perspective pane showing near-nothing (a thin
   horizon line + tiny corner shape) — and, oddly, a SECOND `CAMERA ALIGN` call in the same boot
   (different target) produced a byte-identical image to the first, even though the first call HAD
   visibly moved the ortho "Top" view. Root cause not fully chased (not needed once the fix below
   worked) — likely a framing-distance/pitch quirk specific to a huge hollow Subtract brush, or a
   one-shot-per-boot limitation similar to `CAMERA OPEN`'s. **Fix: `JUMPTO x,y,z`** (position only,
   per `driver.py::jumpto` — no rotation control) to a coordinate INSIDE the room. The perspective
   camera's fixed default rotation (yaw toward +X) was enough to land two landmark boxes in frame,
   live-verified before running the mode sweep.

### The working recipe

1. Boot the editor with the perspective pane's render mode baked in at LAUNCH:
   `ensure_editor(editor_id, state_dir=..., ini_overrides={"U2Viewport2": {"RendMap": "<mode>"}})`
   — runtime `RMODE` can't retarget the pane headless (the console click steals "current" away from
   it — `rendering.md`), so one boot = one mode.
2. Build the scene via `uedcli.writes._re_add` (EDIT PASTE for brushes, MAP IMPORTADD for the
   point-actor light) — see "Scene design" below.
3. `MAP REBUILD`, optionally `LIGHT APPLY`.
4. `JUMPTO -1600,0,-400` (inside the room, off the −X wall, mid-height) to pose the camera.
5. A real `driver.click()` inside the bottom-left perspective pane (makes it current AND forces the
   llvmpipe repaint that command-driven redraws skip — the stale-framebuffer trap) →
   `driver.screenshot()` the main frame → crop the pane rect `(122, 636, 800, 1072)` (this editor
   build's fixed headless main-frame size is 1600×1158; rect verified live against the "Top"/"Front"/
   "Side" panes' known positions).

Harness: `harness/polys_re_probe.py`. Run: `python3 harness/polys_re_probe.py <out-dir> [tags]`
(tags: `wire,zones,polys,polys_nolight,plaintex`, comma-separated; defaults to all five). Needs
`UEDCLI_HOME` pointed at a docker-daemon-visible directory (see `NATIVE-MATERIALIZE.md`-style
stub-cache note) and the `uedcli` venv (`PIL` for the crop).

### Scene design

One Subtract room (4096×4096×2048, all 6 faces `Engine.DefaultTexture`) + two ADD boxes, separate
brushes: **BoxA** shares the room's texture (`Engine.DefaultTexture`); **BoxB** uses a different
texture (`Engine.Border`). A `Light` for the light-vs-no-light comparison. This layout separates
three hypotheses for how a debug-color mode might key its color: per-BRUSH (BoxA would differ from
the room despite sharing its texture), per-TEXTURE (BoxA would match the room; BoxB would differ),
or per-POLY (the room's own 6 faces — one brush, one texture — would differ from each other).

## Findings

All four modes rendered the SAME scene from the SAME pose (`JUMPTO -1600,0,-400` + click), one editor
boot per mode. Evidence in `evidence/` (crops) and `evidence/polys_full.png` (one uncropped main
frame, showing the full 4-pane editor and the recipe in context — the black rectangle in the
upper-middle is the floating Log Window/Textures browser overlaying part of the top panes, per
`rendering.md`'s documented floating-black-window trap; it does not reach the cropped pane below).

| Mode | `RendMap` | Pane's own title | What it shows |
|------|-----------|-------------------|----------------|
| Wire | 1 | **"Wireframe"** | Edge-only outlines, CSG-classification-coloured: the Subtract room's edges are orange/gold, the Add box's edges are blue — matching `rendering.md`'s own documented UnrealEd brush-wire palette (subtract=gold, add=blue), now confirmed from a live render rather than only from prior source-level RE. |
| Zones | 2 | **"Zone/Portal"** | Filled flat-ish color **per Zone**, shaded by face normal (a simple directional/Lambertian cue for depth — the near wall is a lighter blue, the far wall/ceiling darker navy, the floor a third shade). No zones were authored in this scene (no `ZoneInfo`/portal brushes), so everything — room AND the unrelated box — landed in the one default zone and reads as one blue hue family, differentiated only by per-face shading, not by a distinct color per object. |
| **Polys** | **3** | **"Texture Use"** | **A flat, UNSHADED solid color per unique TEXTURE — a texture-usage debug view, not a per-polygon or per-brush view, and not a wireframe.** All 6 faces of the room (floor, ceiling, 4 walls — one brush, `Engine.DefaultTexture`) render as ONE uniform dark-green fill, with **zero** per-face-orientation shading (unlike Zones). BoxA — a SEPARATE brush but the SAME texture as the room — blends seamlessly into that same green (confirms per-TEXTURE, not per-brush). BoxB — a separate brush AND a different texture (`Engine.Border`) — renders in a distinct flat pink/rose. Identical whether or not `LIGHT APPLY` had run (`polys.png`/`polys_nolight.png` are byte-identical, md5 `2b735b58ee2b98185c1aa40bd7025498`) — this mode does not need lighting built, consistent with it not being a lighting-related view at all. |
| PlainTex | 6 | **"Textured"** | The real texture images, fullbright (no lighting needed) — confirms the scene/recipe (visibly the checkered `Engine.DefaultTexture` pattern on the room, a distinctly darker `Engine.Border`-textured box), matching the already-documented PlainTex behavior. Used here only as a sanity-check reference, not new information. |

The commands.md name "Polys" is misleading — the pane's own UI label is **"Texture Use"**, and the
render has nothing to do with individual polygons: it is keyed purely by which `Texture` object a
surface's `Material`/skin points at. Two surfaces sharing a texture (regardless of which brush or
which face they belong to) get the exact same flat swatch; two surfaces on the same brush with
different textures do not. This is consistent with a texture-atlasing/optimization debug view (see
which polys in a level still share which textures), not a CSG or BSP-structure view.

## Final verdict

**`REN=3` = UnrealEd's "Texture Use" mode: one flat, unlit, unshaded solid color per unique texture
reference, applied per BUILT SURFACE (needs a `MAP REBUILD`; does NOT need `LIGHT APPLY`).** Design
implication for a native `--mode polys` (or better, `--mode texture-use`, matching the real UI label
rather than the possibly-wrong `commands.md` name) on uedcli's software rasterizer:

- Assign each surface a fill color derived from a stable hash/index of its resolved texture
  reference (package+name) — same texture anywhere in the level ⇒ same color; no lighting term, no
  per-face shading, no BSP/zone/CSG classification involved.
- An untextured surface (no `Texture=`) needs its own bucket/fallback color — not tested live here
  (this scene had no untextured faces); worth a quick follow-up probe if the feature is actually
  built, but not blocking this RE finding.
- Distinct from Zones (`REN=2`, "Zone/Portal": per-zone color + per-face normal shading) — if a
  `--mode zones` is ever wanted too, it needs the shading term this mode does NOT have.

Minor bonus, not the target of this spike but confirmed as a side effect: the real UnrealEd wireframe
brush-wire palette (subtract=gold/orange, add=blue) matches what `rendering.md`/uedcli's own offline
`actor diagram` already documents from source-level RE (`spikes/2026-07-22-unrealed-brush-wire-
colors.md`) — this is now also confirmed from one live render, not acted on further here.

## Test / pinning note

Per `dev/docs/rules/spikes.md`'s escape hatch: this is empirical knowledge about the real editor's
UI (a render-mode's literal pixel behavior), not a fact uedcli's own code currently computes or
asserts — there is no `test_engine_facts.py`-style assertion to write against a binary or a golden,
since nothing in the codebase implements this mode yet. If/when `level photo --mode texture-use` (or
`polys`) is actually built, ITS OWN test should assert the per-texture-color/no-shading/no-lighting-
dependency behavior described above against this spike's evidence.
