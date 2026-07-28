# UnrealEd 2.2 — rendering & getting pixels out

Producing an image from the headless editor: GL setup, render modes, the traps that make a
viewport go black, and how to take a shaded screenshot. Command syntax is in
[`commands.md`](commands.md); general gotchas in [`quirks.md`](quirks.md).

> **`level preview` no longer uses any of this (2026-07-16).** The editor-screenshot preview
> backend (`preview_render.py` + the auto-frame recipe below) was retired for the offline
> `--native` software rasterizer (`architecture.md` "level preview" / "Preview internals").
> The rest of this doc is still true editor behavior, kept for other editor drivers (debugging,
> future tooling); only the claim that this is how `level preview` works is historical.

## GL / device setup (baked into the inis)
- Needs i386 Mesa GL (`libgl1:i386` …), `WindowedColorBits=32` (Xvfb depth-24 has no 16-bit GLX
  config), and `LIBGL_ALWAYS_SOFTWARE=1` (llvmpipe).
- Each saved viewport pins its own render device. Panes pinned to `D3D9Drv`/`XOpenGLDrv` render
  gray/unpainted under wine — normalize every `[U2Viewport*] Device=` to
  `SoftDrv.SoftwareRenderDevice`. The old `Ued2` editor crashed on repaint under llvmpipe; UED22
  survives, so use UED22, not Ued2.

## Render modes (`RendMap` / `REN=` / `RMODE`)
Numeric enum, shared by the `[U2Viewport*] RendMap` ini key, `RMODE <n>`, and `CAMERA … REN=`:
`1`=Wire, `2`=Zones, `3`=Polys, `5`=DynLight, `6`=PlainTex (textured fullbright),
`13/14/15`=Orth XY/XZ/YZ, `16`=TexView, `17`=TexBrowser, `18`=MeshView.
- PlainTex (6) is visible with no lighting — use it for a textured shot.
- DynLight (5) is black until a light exists and lighting is built (see below).

## The stale-framebuffer trap
- llvmpipe repaints a software viewport only on a real interaction (a mouse pan), not on
  command-driven redraws (`REDRAWALLVIEWPORTS`, `JUMPTO`, `RMODE` all change state without
  painting). A `shot` then captures the previous frame. Tell: byte-identical PNGs, or a black
  rectangle that survives camera moves and deletes — it is not geometry.
- `RMODE <n>` only re-targets the current viewport, and the console cannot make the perspective
  pane current: `RMODE` hits `GCurrentViewport`, which under wine switches to the perspective only
  on a real click inside it. With no click, `RMODE 5` lands on an ortho and the perspective keeps
  its prior mode (it kept reading as PlainTex fullbright, RGB ~140/149/131 for `DefaultTexture`, no
  matter how many `RMODE 5` calls). So `RMODE`+click works but needs a mouse.

## Perspective pane black ≠ broken geometry/CSG
Two independent causes, neither is the level:
1. DynLight with no built lighting (the saved `[U2Viewport2] RendMap=5`).
2. Floating black windows on boot — the Log Window (spawned by `-log`) and the Textures/master
   browser (always floated; ignores `Active=0`/`Docked=`) paint solid black over the viewports.
   Move them off-screen at runtime: `wmctrl -i -r <id> -e 0,2000,2000,640,480` for every window
   whose title isn't exactly the main editor (catches `"… Log Window"` and `"Textures"`).
   Permanent fix: drop `-log` from `entrypoint.sh` + `X=2000/Y=2000` on every `[* Browser]` ini
   section.

## DynLight: building lighting
- Add a `Light` point actor (`MAP IMPORTADD`; `LightBrightness`/`LightRadius`/`LightHue`/
  `LightSaturation`), then `LIGHT APPLY` (geometry needn't be rebuilt; `MAP REBUILD` wipes
  lighting). `LightSaturation` is inverted: lower = more vivid color, `255` = white.
- A bright light in a small room reads near-fullbright; for a visible falloff use a dim light
  (`LightBrightness` ~80) with a modest radius in a larger room.

## Recommended: `CAMERA OPEN` — clean shaded shot, no mouse
Get a perspective render in a known mode/size with no click and no stale frame: open a dedicated
camera, capture just its window.
```
exec  CAMERA OPEN NAME=ShotCam XR=480 YR=360 REN=6     # 6=PlainTex, 5=DynLight, 1=Wire
# find the window and grab it (no editor interaction):
xid=$(wmctrl -l | grep 'Viewport$' | tail -1 | awk '{print $1}')
import -window "$xid" out.png        # or: xwd -id "$xid" | convert xwd:- out.png
```
- It renders immediately at the requested resolution and mode. The log confirms
  `ResizeViewport(0, 480, 360, 4)` (the `4`=32bpp) and `Galaxy SetViewport: ShotCam`.
- ⚠️ Capture on first paint only — never re-render it. A `CAMERA OPEN` window paints correctly only
  on initial creation. Any re-render blanks it to solid black under headless SoftDrv:
  `CAMERA UPDATE NAME=…` (🔬 ortho control: mean 169 → 0), and show-flag toggles on the current
  viewport (`SHOWACTORRADII`/`RMODE`/…). So open the camera in its final mode + size + `FLAGS=` and
  `shot` it once; to change anything, open a new camera rather than `UPDATE` the old one. (Window
  title encodes the view: `REN=6`→"Viewport", `REN=1`→"Perspective map", `REN=13`→"Overhead map" —
  `wmctrl -l | grep` the right one.)
- ⚠️ And it cannot be re-posed (🔬 2026-07-06, round 8). `JUMPTO`/`CAMERA ALIGN` do reach a
  `CAMERA OPEN` window (it's a viewport, so they re-center/re-rotate it), but that retarget is a
  re-render, so it blanks the window to solid black (🔬 mean 153.5 → 0.0). Setting the pose before
  the open doesn't carry either: the fresh window opens at the default camera; two distinct poses →
  identical images (🔬 mean 153.6 both). So a `CAMERA OPEN` window is capture-once, at the default
  pose, in whatever mode/flags it was opened with; it can never show an arbitrary vantage. For a
  posed shot use the main-frame perspective pane (which survives a re-pose + click-repaint; see
  "Posed shots" below) and crop it.
- Verified live (isolated container): a 1024³ carved room textured with `Engine.DefaultTexture`
  renders cleanly via `REN=6`; a dim hue-40/sat-24 light renders a yellow-green falloff via
  `REN=5`. Full `CAMERA` arg reference in [`commands.md`](commands.md).

## Viewport `FLAGS=` — the ShowFlags bitfield
`CAMERA OPEN …/UPDATE … FLAGS=<int>` sets the viewport's ShowFlags. Only the low ~11 bits are
valid: `FLAGS` up to `0x7FF` (2047) are accepted; `≥~0x1000` (e.g. 8191, 65535) make `CAMERA OPEN`
silently fail (no window). Bits (🔬 = confirmed by parallel bit-knockout from `0x7F`; rest are the
standard Unreal ShowFlags, consistent with what we saw):

| Bit | Flag | Effect (observed) |
|---|---|---|
| `0x01` | SHOW_Frame | 🔬 the editor grid + axes + chrome |
| `0x02` | SHOW_ActorRadii | 🔬 actor collision radius/height + light radius as wireframe (selected = red) |
| `0x04` | SHOW_Backdrop | no effect in ortho (sky/backdrop — perspective only) |
| `0x08` | SHOW_Actors | 🔬 the actors themselves (remove it → actor + its radii vanish) |
| `0x10` | SHOW_Coords | 🔬 the coordinate readout text |
| `0x20` | SHOW_Brush | 🔬 brushes (here just the builder-brush speck) |
| `0x40` | SHOW_StandardView | no static visual |
| `0x80`–`0x400` | Menu / MovingBrushes / PlayerCtrl / Paths / RealTime | valid but no observed static effect headless (Paths needs pathnodes; RealTime is a refresh mode) |

Radii view recipe: `CAMERA OPEN NAME=Cam XR=W YR=H REN=<13 top|14 side|1 wire-persp> FLAGS=127`
with the target actor selected (`SELECTNAME NAME=…`) draws a red collision cylinder (circle in
top-ortho, rectangle in side-ortho, 3-D cylinder in perspective). `127` (`0x7F`) gives a
fully-chromed view; minimal is `FLAGS=0x0A` (`ActorRadii|Actors`).

## Alternative: `MAP LOAD` (no-mouse, but resets the camera)
`MAP LOAD <file>` (a) resets each viewport to the ini's `RendMap` (5=DynLight here) and (b)
repaints every pane — no click. But it resets the camera to a default outside a small room (→
black, buried in solid; make the carved room ≥1024³ so the default camera lands inside, and it does
not persist a `JUMPTO`'d camera), and the repaint is deferred (sleep ~3–5 s before `shot` or you
capture the stale pre-load frame). `CAMERA OPEN` is simpler — prefer it.

## Posed shots — ⛔ superseded: camera rotation is unrenderable headless; auto-frame a brush instead ✅ 🔬
> ⛔ Correction (live 2026-07-12, `spikes/2026-07-12-preview-pose-calibration/`). The
> "main-perspective-pane `CAMERA ALIGN`" recipe below poses camera position only — the helper
> `Light`'s `Rotation` FRotator never reaches the rendered pixels. A 9-pose calibration (yaw
> {0,90,180,270} × pitch {−89…+89}) rendered the identical view every time; the 2026-07-06
> "distinct posed images" differed by the helper's position, not its aim, and the 2026-06-20 "adopts
> the full FRotator" only verified the stored value via a `MAP SAVE` readback, never an image. So
> there is no arbitrary-pose headless shot. The one console path that actually re-aims the render is
> `CAMERA ALIGN NAME=<BRUSH>` — aligning to a brush repositions and aims the camera to frame that
> brush (distance ∝ the brush's size, canonical angle). `level preview` uses this: it auto-frames a
> named brush, or the largest `CSG_Subtract` (the enclosing room) for `all`, a wide interior
> overview. See `decisions.md` 2026-07-12. The rest of this section (the ALIGN mechanics, wmctrl
> sweep, chrome crop, per-viewport ini) is still accurate for position and the render plumbing; only
> the claim that rotation yields arbitrary posed shots is wrong.

Established live over a 6-round spike (2026-07-06,
`spikes/2026-07-06-level-preview-headless-shots/`, artifacts in `_scratch/preview-spike/`):

- ⚠️ `CAMERA OPEN` renders only from a fixed default camera pose; it cannot be aimed. `CAMERA ALIGN`
  (which poses the main perspective pane, below) does not carry into a `CAMERA OPEN` window, even
  when the perspective pane is made current (a click) before the open. 🔬 three distinct poses →
  pixel-identical `CAMERA OPEN` images (mean-abs-diff 0.0). `REN=`/`FLAGS=` still select the mode per
  shot (wire vs shaded differ by 152), but always at that one default pose. So `CAMERA OPEN` is good
  for a fixed-viewpoint mode gallery, useless for arbitrary vantage points. Ortho `REN=13/14/15`
  render near-blank at the default zoom (mean ~171, ~2.4 KB).
- The only way to get an arbitrary-pose shot headless is the main perspective pane. In the standard
  4-pane layout the bottom-left quadrant is the 3D perspective pane. Recipe (🔬 verified — distinct
  posed images, mean-abs-diff 3.9–20.6, landmark appears where the pose predicts):
  1. Pose it with `CAMERA ALIGN`: `MAP IMPORTADD` a `Light` helper at the desired `Location`
     carrying the desired `Rotation`, `SELECTNAME` it, `CAMERA ALIGN NAME=` it (adopts the full
     FRotator and recenters position), delete the helper. (Same mechanism as `commands.md`
     `CAMERA ALIGN` / memory `uned-camera-rotate-via-align` — it poses the main perspective pane.)
  2. Force a repaint: a real `wine_ctl click` inside that pane makes it current and triggers the
     llvmpipe repaint that command-driven redraws (`CAMERA ALIGN`/`RMODE`/`REDRAWALLVIEWPORTS`) do
     not produce (the stale-framebuffer trap, above). Without the click you capture the pre-pose
     frame.
  3. Capture: `driver.screenshot` grabs the whole editor frame (main-window only, by design); crop
     the bottom-left pane (at the fixed headless 1600×1158 the pane is ≈ `(122, 636, 800, 1072)`,
     toolbar row trimmed).
- Bigger/cleaner: make one pane full-window and sweep the black browser windows (🔬 2026-07-06,
  rounds 9–10). Set `[U2Viewport2]` to fill the window in the ini (`PctLeft/Top=0`,
  `PctRight/Bottom=1`) and `Active=0` the other three; the perspective pane is then the whole window
  (still the same re-poseable pane). The floating Log Window + Textures browser paint black over it —
  move them off-screen by window ID (the Log Window's title contains the main title, so a
  title-substring filter wrongly keeps it): `MID=$(wine_ctl status | grep -oE 'window=[0-9]+' | cut
  -d= -f2); MHEX=$(printf '0x%08x' $MID); wmctrl -l | awk -v m=$MHEX 'tolower($1)!=tolower(m){print
  $1}' | xargs -I{} wmctrl -i -r {} -e 0,3200,3200,200,150`. Then `driver.screenshot` + a
  chrome-border crop `(104,92,1596,1104)` → a clean 1492×1012 posed textured shot. ✅ This is the
  shipped `level preview` recipe, live-verified end-to-end 2026-07-06 (`test_preview_integration.py`:
  two distinct poses, mean-abs-diff 9.9 > 3.0, both bright mean ~146). `ACTOR SELECT NONE` is issued
  before each shot to clear the selection gizmo; the `wmctrl` sweep is re-run per shot because
  `MAP IMPORTADD` can re-raise the browser windows.
- Show-flags/overlays are per-viewport ini keys set at boot (`[U2Viewport2]`): `ShowBackdrop` (🔬 the
  skybox/backdrop — needs a sky-zone level to see through solid geometry), `ShowPaths`,
  `ShowCoordinates`, and `ShowActors=<enum>` (the Full/Icon/Radii/Hide actor-view mode — the radii
  value is TBD; the un-posed `CAMERA OPEN FLAGS=127` radii recipe is the fallback). Runtime
  `SHOWACTORRADII` blanks the pane black (a re-render), so overlays must be set in the ini at boot.
- The perspective pane's render mode is fixed at editor launch via `[U2Viewport2] RendMap` in
  `/opt/UED22/UnrealEd.ini` (per-viewport: `U2Viewport0`=13 top-ortho, `1`=14, `2`=5 DynLight = the
  perspective pane, `3`=15). Setting `[U2Viewport2] RendMap=6` (PlainTex) + relaunch gave a bright
  textured posed shot (🔬 mean 142.5 vs ~9 for DynLight). `RendMap` values = the `REN=` enum (1 wire /
  2 zones / 3 polys / 5 lit / 6 shaded).
- ⚠️ Runtime `RMODE` cannot switch the perspective pane's mode headless. `RMODE` targets
  `GCurrentViewport`, but sending it through the console types into the bottom command box, and that
  click on the command box steals "current" away from the perspective pane — so `RMODE 6` after
  posing does nothing (🔬 shaded == dynlight, diff 0.0). So render mode for a snapshot tool is
  per-editor-boot (chosen via the ini), not switchable per shot from the console. (An untested
  cleaner path: click the render-mode button on the pane's own toolbar — it targets that pane
  directly, no command box. Under investigation.)

## uedcli's offline `actor preview` — what UnrealEd draws, matched host-side

`actor preview` (`preview.py`) is our own stdlib rasterizer, not the editor, but its colours and
sizes are chosen to match what UnrealEd's viewports show, so a preview reads like the editor.

- Brush wire colours by CSG classification — UnrealEd colours each brush's wireframe by its CSG
  role. uedcli reproduces the legend (hue preserved, luminance re-tuned for our light-grey
  background, since UED tunes for a grey/black viewport): added-solid = blue, subtracted =
  yellow/gold, semi-solid = warm coral, non-solid = green, mover = magenta/purple. Red is UED's
  builder brush (not rendered here), so it is free — a highlighted poly (`--highlight`) uses its
  brush's own vivid hue + a bolder line, not red; a highlighted point actor (`--highlight <name>`)
  gets corner brackets (a selection reticle) framing its sprite/marker. Classification = `CsgOper`
  (subtract) refined by the actor-level solidity `PolyFlags` (`PF_Semisolid`/`PF_NotSolid` on the add
  side) and mover-class. `semi-solid` diverges from UED's rose (223,149,157) to a warm coral on
  purpose: UED's semisolid and mover are both in the red/purple family, told apart only by saturation
  against its black viewport — a cue that dies on our white bg (they conflate). Coral (warm) vs
  magenta (cool) stays distinct on any background. See
  `spikes/2026-07-22-unrealed-brush-wire-colors.md` for the source-verified UE1 `C_*` brush-wire
  RGBs. Otherwise adapted from the Andrzej-provided UED legend (ergonomics spec 2026-07-21 §4), not
  binary-mined — the hues are a design choice matching UED, so no confidence marker applies. The
  actual RGB values are uedcli's own white-bg re-tuning; `test_preview.py` pins the
  classify→palette→render wiring (a subtracted brush renders in the `subtract` pair, a point actor is
  never painted CSG-additive), not the literal RGB numbers.
- Point-actor sprites + radii/reach overlays ✅ source — sizes are source-exact from the UE1 v200
  tree (`spikes/2026-07-21-unrealed-sprite-radii-rendering.md`), pinned in `test_engine_facts.py`:
  - DT_Sprite footprint = `DrawScale·USize × DrawScale·VSize` (1 texel = 1 UU at DrawScale 1),
    billboarded at Location (`UnSprite.cpp` `FDynamicSprite::Setup`).
  - Collision cylinder (`--show collision`, gated on `bCollideActors` like UED's `SHOW_ActorRadii`) —
    circle radius `CollisionRadius` in TOP, a `2·CollisionRadius × 2·CollisionHeight` rect in
    FRONT/SIDE (`CollisionHeight` is a half-height), an 8-sided wire cylinder in ISO; always upright,
    world-axis-aligned regardless of actor rotation (`UnEdCam.cpp`).
  - Light/sound reach (`--show light-range`/`--show sound-range`) — spheres of `25·(LightRadius+1)` /
    `25·(SoundRadius+1)` UU (the `+1` is real: `LightRadius=0` still reaches 25 UU) (`AActor.h`
    `WorldLightRadius`/`WorldSoundRadius`). UED draws collision+light both dark red and sound dark
    blue; uedcli keeps collision red / sound blue but deviates light to orange so the two red overlays
    (separate toggles) stay distinguishable.

## Texture swatches → PNG
See [`commands.md`](commands.md) "Textures → LLM-viewable images" (`UCC batchexport`).
`Engine.DefaultTexture` is the brightest surface texture in the stripped substrate.
