+++
priority = "p2"
kind = "finding"
summary = "Perspective pane Lit mode renders near-black on real geometry"
+++

# Perspective pane Lit mode renders near-black on real geometry

Owner report (same session as the Front/Side blank-pane regression, `f3708467`): the Perspective
pane "looks unnaturally dark for `'Lit'` mode." Investigated while fixing the ortho camera bug;
NOT the same root cause and NOT fixed here (out of scope / time-boxed per that task).

## Repro

Live headless-browser screenshot against a real, already-built UNATCO level (1469 actors) at the
default camera pose: the Perspective pane in `'Lit'` mode is almost entirely black -- only a faint
reddish smudge and a couple of green sprite icons visible. Switching the SAME pane to `'Fullbright'`
(no camera/pose change) immediately shows full detail: a wooden crate/counter, stone floor, brick
wall, bushes, a potted plant -- all clearly lit and textured.

This isolates the bug to `'Lit'`-mode shading itself, not camera placement or geometry visibility:
the same triangles, same camera, same frame render bright in Fullbright and near-black in Lit.

## Where to look

`web/src/scene/sceneResources.ts`'s `materials` builder (around the `lit`/`lightMap` handling,
`params.lightMap = lightmapTexture`, the `intensity` variable read from `lightmap?.intensity`) is
the most likely site -- `'lit'` samples `base*color*lightMap`, so a near-zero result there could
mean the lightmap atlas is empty/black (light bake didn't actually run or didn't cover this
geometry) or the sampled UV/channel/intensity scaling is wrong. Not investigated further here.

## Ruled out

- Not caused by any of the commits in the Front/Side blank-pane regression
  (`f3708467`/the ortho camera fix): `git log` on `sceneResources.ts` shows only `fcfb9486`
  (added `depthWrite: false` for translucent/modulated materials only -- unrelated code path) and
  `37378ecf` (original slice) touch this file; neither plausibly explains a whole-pane brightness
  drop confined to `'lit'` mode.
- Not a camera-position/geometry issue (see repro above -- same view is bright in Fullbright).
- Not the `CANVAS_COLOR_MANAGEMENT` global-singleton footgun documented in `dev/docs/GUI.md`
  ("Rendering: backgrounds, color management") -- both `<Canvas>` instances in the app
  (`Viewport3D.tsx`, `OrthoViewport.tsx`) already spread the shared constant; verified by
  `grep -n "<Canvas" web/src/scene/*.tsx`.

## Next step

Confirm whether this level's lightmap bake actually ran / covers this geometry (check the
`/api/level/<name>/lightmap` payload for this actor's surfaces), then check
`sceneResources.ts`'s lit-material construction against it.

## Correction: NOT a GUI bug -- render.rs (the native reference) reproduces the identical darkness

Followed the "next step" above. `uedcli/serve/lightmap.py`'s encode/decode contract
(`value/intensity` in `[0,1]`, client does `lightMapTexel * lightMapIntensity`) is correctly
implemented in `sceneResources.ts` -- verified by reading both sides, no scale mismatch.

Decisive test: took a `level photo --native --mode lit` shot at the GUI's exact default camera
pose (`INITIAL_POSE` in `Viewport3D.tsx`: `position [0,-500,200], pitch -10, yaw 90` ->
`at:0,-500,200;look:0,484.8,26.4`). This landed on the IDENTICAL room the owner screenshotted
(soldier NPC, red/gold curtains, blue carpet, potted plant, stone wall) -- and `render.rs`, the
project's own ground-truth reference renderer, renders this room JUST AS DARK: a black ceiling,
dim floor/walls, no more detail visible than the GUI's Lit mode. Same lumel bake, same result, in
a renderer that isn't three.js and doesn't go through `sceneResources.ts` at all.

This rules out a GUI-side sampling/scale bug. The darkness reflects the actual baked lumel values
for this room in the native lighting engine -- either a genuine level-design dim area, or a real
lighting-BAKE bug (native-materialize's own campaign doc, `NATIVE-MATERIALIZE.md`, tracks several
open, unresolved UNATCO-specific lighting divergences at this scale -- e.g. leaf permeating-light
gaps). Either way it's not fixable in the GUI layer; the earlier "Ruled out" section's Lit-vs-
Fullbright comparison doesn't isolate a bug by itself, since Lit is EXPECTED to look darker than
Fullbright whenever the underlying bake is genuinely dim. Re-filing as a native-lighting question,
not a GUI defect -- no GUI code change needed here.

## Follow-up (2026-09-17): narrowed to `light.rs`'s render-time falloff, not the shadow-mask bake

Owner report this session: `level photo --native` renders on `bar` (`02_NYC_Bar`) and `unatco`
look "so dark" -- same symptom, CLI side. Root-cause investigation (not fixed, per this project's
"measure, stop, report, wait for the yes" rule):

- `bake_lighting`'s per-lumel shadow MASK (which lights reach which lumel -- "does light X see
  lumel Y") is the SAME core the byte-parity `level materialize` campaign ladder-verifies against
  UED22 -- not the suspect.
- `level photo --native`'s per-pixel COLOR comes from a SEPARATE, admittedly-unverified function:
  `light::radiance()` (`uedcli-native/src/light.rs`), which sums `hsv_multiplier(color) *
  falloff(dist, world_radius)` per lit light, with NO ambient/base term. `falloff()` is a plain
  linear ramp, full at the light and exactly 0 at `(LightRadius+1)*25` uu -- and the doc that
  derived it says outright it is NOT a confirmed fit: "Falloff-with-distance was NOT cleanly
  pinned... Implemented as a simple linear falloff — a reasonable default, not a confirmed fit"
  (`dev/docs/unrealed/leveldesign/kb/lighting.md` §1.4,
  `dev/docs/spikes/2026-09-11-light-color-falloff-re/`).
- `bar`'s own light actors are mostly short-radius/modest-brightness (`Light0`..`Light16`:
  `LightBrightness≈24-66`, `LightRadius≈8-16` -> world reach ≈225-425 uu) -- i.e. most surfaces sit
  well inside the falloff ramp's dim half, not at the bright near-light end. Confirmed the ceiling
  IS getting a real (non-flat-fallback) lightmap record -- the flat `KEY_LIGHT`-shaded fallback for
  a genuinely-unlit surf would read ~0.87 for a level ceiling/floor normal, well above what's
  rendered, so this isn't "no light reaches it," it's "the reached light computes too dim."
- `DeusEx.HKMarketLight` actors (the visible lamp-shade meshes near these lights) are a
  `DeusEx.HangingDecoration` subclass (`Engine.Decoration`, not `Engine.Light`) -- correctly
  excluded from `gather_lights`, not a bug (ruled out).
- Could NOT get a live `level photo --game` A/B in this session to confirm/measure the gap: the
  sandbox's rootless docker daemon refuses to bind-mount ANY path on this host (`docker run -v
  /workspace/uedcli:/test ...` and `-v $HOME:/test` both fail `mkdir ...: permission denied`), so
  the `--game` container tier cannot run here at all -- an environment limitation of this
  particular session, not a code issue. This is exactly the live oracle the falloff curve needs
  re-deriving against (same method as `2026-09-11-light-color-falloff-re`, sampled at more/wider
  distances this time) to confirm the shape and fix it faithfully.

**Not fixed.** Best-evidenced, not confirmed: `light.rs`'s linear falloff most likely UNDER-lights
relative to the real engine once the earlier RE pass's own "NOT cleanly pinned" caveat is taken at
face value combined with how short this level's actual light radii are. Re-deriving the falloff
curve from a `--game` A/B (needs a session where the docker mount actually works) is the next step,
not a guessed formula change.
