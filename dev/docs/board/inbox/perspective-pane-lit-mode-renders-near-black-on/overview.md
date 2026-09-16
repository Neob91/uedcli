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
