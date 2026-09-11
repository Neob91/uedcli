# Light color + falloff RE — for `level photo --native`'s new radiometric lumel bake

Board item: `bake-lighting-into-level-photo-native`. Byte parity NOT required (owner ruling
2026-09-11) — this is a conceptual, live-probed fit, not a disassembly-level derivation. Findings
folded into `dev/docs/unrealed/leveldesign/kb/lighting.md` §1.4.

## Method

A test level (`_scratch/lightprobe/`, not committed — gitignored scratch) with a flat floor and one
`Engine.Light`, one property varied at a time, rendered with `level photo --game` (the real in-game
renderer — correct ground truth; `--native` is what this whole effort is fixing, so it's useless as
a reference). Camera fixed, aimed at a known floor point directly under the light; center-pixel
sampled with `harness/sample.py`.

## Raw data

`harness/results.csv`. Driver: `harness/probe.sh <tag> <brightness> <hue> <saturation> <light_z>`.

## Findings

See `dev/docs/unrealed/leveldesign/kb/lighting.md` §1.4 for the write-up. Summary:

- Brightness: linear, then an overbright clamp — solid, clean data.
- Hue: standard HSV wheel, red at 0 rising toward yellow — 2 points, direction solid.
- Saturation: confirmed inverted (255=white), but the curve is strongly non-linear/front-loaded;
  `G`≠`B` at `Hue=0` at partial saturation hints at the classic `FGetHSV` hue-offset quirk.
- Falloff-with-distance: NOT cleanly pinned. Widening the sample box on the same captures showed the
  raw non-monotonic distance reading is very likely a sampling-footprint artifact (a close light
  makes a tight, steep-gradient pool; a far light makes a wide, flat one), not necessarily the true
  on-axis curve. Implemented as a simple linear falloff — a reasonable default, not a confirmed fit.

## What this blocks / doesn't block

Good enough for `level photo --native`'s v1 (visibly lit, not byte-exact). NOT good enough for a
future byte-parity project — that effort should re-derive this from disassembly (`Render.dll`'s
light-color/attenuation code), the same way `light.rs`'s existing structural bake was derived.
