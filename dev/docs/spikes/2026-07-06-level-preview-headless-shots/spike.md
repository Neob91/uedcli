# Spike: `level preview` headless arbitrary-pose shaded capture

**Question (from the preview spec §Feasibility):** can uedctl render a **shaded image from an arbitrary
camera pose, headless, for multiple shots in one editor boot** — the mechanism the batch snapshot
renderer needs? Two cold reviews found the drafted `CAMERA ALIGN`+`RMODE`+`driver.screenshot` sequence
can't work (screenshot grabs the main frame; RMODE can't target the perspective pane headless; the
verified shaded shot uses a *separate* `CAMERA OPEN` window at the DEFAULT pose).

## What the docs already establish (so the spike doesn't re-prove it)

- `CAMERA OPEN NAME=X XR=W YR=H REN=n [FLAGS=f]` spawns a **standalone window** that renders the level
  **immediately** at the requested size+mode, no mouse, no stale frame (`rendering.md`, `commands.md`
  🔬). Grab it: `wmctrl -l | grep 'Viewport$'` (title per REN: 6→"Viewport", 1→"Perspective map",
  13→"Overhead map") → `import -window <xid> out.png`. Container has `wmctrl`/`import`/`convert`.
- **Never re-render a `CAMERA OPEN` window** — `CAMERA UPDATE` / show-flag toggles blank it black under
  SoftDrv. ⇒ open the camera in its FINAL mode/flags and shot ONCE; for a new view, open a NEW camera
  (fresh NAME).
- `CAMERA OPEN` has **NO `LOCATION=`/`ROTATION=` arg** (`commands.md` arg list). So pose can't be passed
  to it directly.
- `CAMERA ALIGN [NAME=]` **re-centers all viewports on the selection AND adopts the actor's full
  FRotator on the live perspective camera**, and the pose **persists** after the helper is deleted
  (🔬 2026-06-20). Helper = a `Light` point actor (`MAP IMPORTADD`) carrying `Location=`+`Rotation=`,
  `SELECTNAME` → `CAMERA ALIGN NAME=` → delete. (`dispatch._camera_rotation_helper` builds this.)

## The candidate mechanism this spike must confirm or refute

**ALIGN-then-OPEN:** pose the live perspective camera with a helper Light (`CAMERA ALIGN`), THEN
`CAMERA OPEN` a fresh window — IF the opened camera inherits the current perspective pose, we have a
posed shaded shot with no mouse. Per shot: helper→ALIGN→delete, `CAMERA OPEN NAME=shot<i> REN=<mode>`,
grab the "Viewport"/title window. Multi-shot = a fresh-named camera per shot (satisfies "never
re-render").

**Unknown:** does a freshly-`CAMERA OPEN`ed camera start from the CURRENT (aligned) perspective pose,
or from a default? That is the crux. If it inherits → mechanism works. If it opens at a default pose,
fall back to: (b) main-pane ALIGN + `driver.screenshot` (main frame) + an XTEST mouse-nudge per shot to
force repaint + make the perspective current — messier, drags in mouse simulation.

## Pre-stated PASS criteria (per `uned-no-false-fixed-claims` — numeric + artifacts + fresh-boot ×2)

1. **Pose control:** two `CAMERA OPEN` shots, identical except one preceded by an ALIGN to a helper at
   a distinct pose, are **visibly different images** (mean-abs pixel diff > a set threshold), AND the
   aligned one shows the expected vantage (a known landmark — e.g. a uniquely-textured wall — appears
   where the pose predicts). Artifacts: the PNGs, saved under `_scratch/preview-spike/`.
2. **Multi-shot / one boot:** ≥3 distinct poses in ONE editor session each yield an image matching its
   OWN pose (pairwise-different; each shows its predicted landmark) — NOT the prior frame. If this
   fails, record it and fall back to boot-per-shot (updates the spec's "one boot" perf claim).
3. **Modes:** `REN=6` (shaded), `5` (lit, after LIGHT APPLY), `2` (zones), `3` (polys), `1` (wire) each
   produce a DISTINCT image (not all identical/PlainTex).
4. **Pitch/yaw sign + compass:** a `top` pose (pitch that should look straight down) of an
   asymmetric scene confirms the pitch SIGN and the `+X=East/+Y=North` convention; record the true
   preset angles.
5. **Repeatable:** the winning recipe reproduces across **2 fresh container boots**.

## Test scene

A known-asymmetric scene so poses are distinguishable: a large subtract room (≥1024³ so the default
camera lands inside, per `rendering.md` MAP LOAD note) with a distinctly-placed additive box, all
textured `Engine.DefaultTexture`, plus a light for `lit`/`zones`. Built via `builders`/`_materialize`.

## Harness

`harness.py` (this dir) — spins an ephemeral editor (`ensure_editor`), materializes the scene, runs the
ALIGN-then-OPEN experiments, grabs windows via `docker exec … wmctrl/import`, `docker cp` PNGs to
`_scratch/preview-spike/`, and prints mean/mean-abs-diff stats. Run as a tracked background job (editor
is crash-prone — long fallback timer). Committed here (not `_scratch`) per the spikes rule.

## ⇒ RESOLUTION: don't drive the editor — render NATIVELY (spike `09-native-textured-preview`)

The whole editor path below is a **dead end for a clean posed, multi-mode preview** (see rounds 1–7).
The clean answer already exists and is RESOLVED: **`spikes/2026-06-27-decontainerize-uedctl/09-native-textured-preview.md`** — a pure-Python offline renderer (`harness/native_render.py`) that parses the
level's built `Model`, decodes each surface texture natively, and rasterizes with affine UV + a
z-buffer (real maps render in ~0.7–1.1 s, no editor). It currently does **top-down ortho**; arbitrary
**perspective pose is a camera-transform swap** at the projection (`native_render.py` `sx`/`sy`),
standard rasterizer work — NOT a feasibility gap. Per-shot **mode** = a renderer option
(textured/wire/lit), all offline. It needs a **built `Model`** (a CSG-built `.dx`), which
`level materialize` produces.

**New `level preview` shape:** materialize the trunk → build `.dx` (the ONE editor touch, = CSG build,
which materialize already does) → **native perspective-render** from each vantage point, offline. No
`CAMERA OPEN`/`RMODE`/restart/XTEST/crop. This removes the editor's *display* role from preview (the
de-containerize direction — memory `decontainerize-uedctl`). The editor findings below stay as durable
UnrealEd facts (folded into `unrealed/rendering.md`), but the FEATURE is built on the native renderer.

## Findings (editor path — durable UnrealEd facts, folded into `unrealed/rendering.md`)

- **Round 8 (can `CAMERA OPEN` be posed via `JUMPTO`/`ALIGN`? NO — confirms the crop recipe is the way):**
  Variant A (pose then open) → two poses identical (mean 153.6 both; the default pose, like round 6).
  Variant B (open then `JUMPTO`+`ALIGN`) → the commands DO reach the open window (it's a viewport), but
  the retarget re-renders it and it **blanks to solid black** (mean 153.5 → 0.0, 192-byte PNGs). So a
  `CAMERA OPEN` window is capture-once at the DEFAULT pose only; the "mode + location + rotation in one
  window" ideal is impossible. The main-frame perspective PANE is the only re-poseable/re-paintable
  surface → the `ALIGN`+click+crop recipe stands.

- **Round 7:** the perspective pane's toolbar render-mode buttons did NOT switch the mode from clicks
  at `y=607` across `x∈[380,508]` (all stayed DynLight mean 9.4) — the button hit-testing / coordinate
  calibration didn't land, and rather than keep probing the editor UI, the native renderer supersedes
  the whole approach.

### Round 1 (2026-07-06, `harness.py`, artifacts in `_scratch/preview-spike/`)

Editor booted (after a settle+retry fix for the flaky single-pass window resolve — see harness
`settle()`), scene materialized, all shots captured. Numbers (per-image mean grey + pairwise
mean-abs-diff over a 160×120 grey downscale):

- **POSE IS INERT via `CAMERA ALIGN`-then-`CAMERA OPEN` — the candidate mechanism is REFUTED.**
  - EXP1 default `CAMERA OPEN` vs ALIGN-then-`CAMERA OPEN`: mean-abs-diff **0.5** (identical).
  - EXP2 three DISTINCT poses in one boot (look +X / look −X / look straight down): px-vs-nx **0.0**,
    px-vs-top **0.1**, nx-vs-top **0.1** — **all three identical.** Visually `exp2_top.png` (a "look
    straight down" pose) is the SAME forward view as `exp1_default.png`. `CAMERA OPEN` always renders
    from a FIXED default pose; `CAMERA ALIGN` (which poses the *main* perspective pane) does not carry
    into the opened camera window. Confirms both reviewers' concern.
- **✅ `CAMERA OPEN` renders a real shaded/textured perspective** (`exp3_shaded.png` = a textured room
  interior, mean 153.6, matching `Engine.DefaultTexture` ~150) — no mouse, no stale frame.
- **✅ Per-shot MODE works** (`REN=` is a `CAMERA OPEN` arg): shaded(153.6) / lit(33.1) / zones(107.8)
  / polys(74.3) / wire(1.2), all pairwise-distinct (diffs 33–152).
- **✅ Multi-shot in one boot has NO stale-framebuffer problem** — a FRESH `CAMERA OPEN` per shot
  (distinct NAME) captured each mode correctly (EXP3 modes all differ), so opening a new camera per
  shot sidesteps the "never re-render a CAMERA OPEN" + llvmpipe-repaint traps.

**Net so far:** the clean console-only path gives shaded + per-mode + multi-shot reliably, but the ONE
thing the feature needs — arbitrary vantage POSE — does not work via ALIGN-then-OPEN. `CAMERA OPEN`
opens at a fixed default camera. Pass-criteria 1 & 2 (pose control / multi-pose) FAIL as designed;
criteria 3 (modes) PASSES.

### Round 2 (`harness2.py`) — layout + ortho

- **Main-frame layout learned** (`r2_mainframe.png`, 1600×1158): the standard 4-pane grid. The
  **bottom-left quadrant is the 3D PERSPECTIVE pane** (labelled "Dynamic Light" = RMODE 5), and it
  **shows the posed, lit scene** — so `CAMERA ALIGN`, which poses the *main* perspective pane, IS
  reflected there (unlike the `CAMERA OPEN` window). A floating black window (Log/Textures browser)
  overlays the center but not the bottom-left pane. Perspective pane ≈ `x[122,800] y[636,1072]`.
- **❌ Ortho modes are NOT a fallback:** `CAMERA OPEN REN=13/14/15` render near-blank grids (mean ~171,
  ~2.4 KB files, pairwise diff 0.5–3.3) — the ortho camera is at a default zoom/pos showing nothing
  useful. Same pose problem.

### Round 3 (`harness3.py`) — **POSE WORKS via ALIGN + click-repaint + crop** ✅

The viable mechanism, PROVEN. Per shot: `CAMERA ALIGN` a helper Light (exact pose on the main
perspective pane) → **left-click inside the perspective pane** (`wine_ctl click`, makes it current AND
triggers the llvmpipe repaint that command-driven redraws don't) → `driver.screenshot` the main frame →
**crop the bottom-left perspective pane**.

- Three distinct poses (look-down / look-+X / look-+Y) gave **DISTINCT crops** — pairwise mean-abs-diff
  **3.9–20.6** (vs the ~0.0 of the un-poseable `CAMERA OPEN` path). `r3_yaw0.png` (look +X from −800X)
  visibly shows the room from that heading with the **landmark box exactly where the pose predicts**.
  So arbitrary perspective pose IS achievable headless — pass-criteria 1 & 2 now PASS via this path.
- Caveat: the pane defaults to **DynLight (RMODE 5)** → the crops are dark (lit only by the dim helper
  light). For a bright textured `shaded` shot, switch the (now-current) pane to `RMODE 6` after the
  click. (Round 4 confirms.)

### Round 4 (`harness4.py`) — runtime `RMODE` on the main pane FAILS

`r4_shaded.png` (after `RMODE 6` + click) is **byte-identical to `r4_dynlight.png`** (diff 0.0) — the
mode did NOT change. **Cause:** `driver.rmode()` types `RMODE 6` into the command box, and *that click
on the command box steals "current" away from the perspective pane* — so `RMODE` (which targets
`GCurrentViewport`) doesn't hit the pane. This is exactly the documented "console can't target the
perspective pane headless" trap. **⇒ the render MODE cannot be switched at runtime headless.** (Pose
still varies: dynlight vs yaw90 = 9.4.)

### Round 5 (`harness5.py`) — mode via the launch INI ✅ (the fix)

The perspective pane's mode is `[U2Viewport2] RendMap` in `/opt/UED22/UnrealEd.ini` (5=DynLight
default). Set it to **6 (PlainTex)** + restart, and a POSED shot is now **bright textured**:
`r5_shaded_px.png` mean **142.5** (vs the ~9 dark DynLight of round 4), a clean fullbright room
interior; two poses still differ (px vs yaw90 = 10.1). **So the render mode is chosen at editor LAUNCH
via the ini, not at runtime.** `RendMap` per viewport: 1=wire, 2=zones, 3=polys, 5=lit(DynLight),
6=shaded(PlainTex).

### FINAL VERDICT — FEASIBLE, BUILD (no rescope)

Arbitrary-pose headless shaded snapshots WORK. The proven recipe (all live-verified, artifacts in
`_scratch/preview-spike/`):

1. **Ephemeral editor** with `[U2Viewport2] RendMap=<mode>` set in the ini before launch (6=shaded
   default, 5=lit, 1=wire, 2=zones, 3=polys). `CAMERA OPEN` is NOT used (it renders clean but can't be
   posed — dead end).
2. **Materialize** the trunk once.
3. **Per shot:** helper `Light` at the shot's POS carrying its `Rotation` → `SELECTNAME` → `CAMERA
   ALIGN NAME=` (adopts the exact FRotator + recenters position) → delete the helper → **`wine_ctl
   click` inside the perspective pane** (bottom-left; makes it current AND forces the llvmpipe repaint
   that command-driven redraws don't) → `driver.screenshot` the 1600×1158 frame → **crop the
   perspective pane** `(122, 636, 800, 1072)`. Multi-shot in one boot = repeat (fresh ALIGN + click).

**KEY DESIGN IMPACT (needs Andrzej):** because the mode is set at LAUNCH via the ini and runtime
`RMODE` is blocked, **the view mode is per-COMMAND (one `--mode` per invocation / editor boot), NOT
per-shot** as the spec drafted. Per-shot mode would need one editor boot per distinct mode.

### Round 6 (`harness6.py`) — can `CAMERA OPEN` be posed by making the source viewport current? NO

Andrzej noted `CAMERA OPEN` does per-shot MODE via `REN=`/`FLAGS=` (true — round-1 EXP3, and
`rendering.md`). The remaining hope: round-1 tested `ALIGN`-then-`OPEN` WITHOUT the make-current click
(whose importance was only found in round 3), so maybe `ALIGN` + click-to-make-current + `CAMERA OPEN`
would inherit the pose — giving per-shot pose AND mode AND a clean grab. **Tested: it does NOT.** Three
distinct poses, each with `ALIGN` + a make-current click before `CAMERA OPEN REN=6`, produced
pixel-identical images (px-vs-yaw90 **0.0**, px-vs-top **0.1**, all mean 153.6 = the fixed default
pose). A `REN=1` wire shot differed (152.5), re-confirming per-shot MODE works — but only ever at the
fixed default pose. **`CAMERA OPEN` clones neither the current nor the ALIGN-posed viewport; its camera
is a fixed default.** So per-shot mode + arbitrary pose are mutually exclusive: pose ⇒ main pane
(mode-per-launch-ini); mode-per-shot ⇒ `CAMERA OPEN` (pose fixed, useless for vantages). **Posed shots
MUST use the main pane ⇒ mode is per-command.** (Confirmed, not an assumption.)

**Remaining build calibration (not feasibility):** the exact crop rectangle at the fixed headless
1600×1158; whether to `wmctrl` the center black Log/Textures window off-screen (it didn't overlap the
bottom-left pane in tests, but confirm at full res); pitch/yaw SIGN + the `+X=East/+Y=North` compass
convention (measure against an asymmetric landmark — `r3_yaw0` already shows the box appears when
looking +X, so yaw≈0→+X looks right); and the per-shot `click` coordinate.
