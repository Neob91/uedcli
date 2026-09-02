# `level build` (paths) + a `--quality` knob — DRAFT spec

Two related build-pipeline additions: a BSP-quality knob on `level materialize`, and pathfinding
(reachspec) generation, which materialize does not do today.

## Goal

- Let a build choose BSP quality (`LAME`/`GOOD`/`OPTIMAL`) instead of the one hardcoded pass.
- Generate the AI-navigation reachspec graph (`PATHS BUILD`), which no verb does now, so a
  materialized map is playable but has no working pathfinding.

## Current state

- `level materialize` builds via FULL RE-IMPORT then one `driver.rebuild()` = `MAP REBUILD`
  (`apply.py:286-289`, `materialize.py:159`, `driver.py:485`). `MAP REBUILD` == `BSP REBUILD GOOD`
  (`unrealed/commands.md:272`). Then `light_apply()` (`LIGHT APPLY`). **No quality choice, no paths.**
- `BSP REBUILD` accepts `LAME` (fastest, skips coplanar detection) / `GOOD` (default) / `OPTIMAL`
  (more merge passes), plus `BALANCE=`/`PORTALBIAS=`/`ZONES`/`OPTGEOM` (`commands.md:272-287`, all
  live-confirmed 2026-06-23).
- `PATHS BUILD` builds the reachspec graph (define markers → create `FReachSpec`s → prune);
  `LOWOPT`/`HIGHOPT` set opt level 0/2 (default 1) (`commands.md:292-302`). `PATHS DEFINE` alone
  yields no edges. Reachspecs live in `ULevel.ReachSpecs`; **they are NOT wiped by `MAP REBUILD`**,
  but a `MAP NEW` + FULL RE-IMPORT (what materialize does) drops everything, so paths must be the
  LAST build step, on the already-rebuilt map.
- **Paths are build output** (regenerable, not authored), the same class as lighting/BSP
  (`materialize.md`, `safety.md`). They belong in the map file, never in the trunk.
- **Post-verify tension.** materialize's post-verify compares the re-exported map against the trunk
  over typed effective values + brush geometry (`normalize.py` compare view;
  `apply.py:291`). `PATHS BUILD` auto-spawns marker NavigationPoints (`InventorySpot`,
  `WarpZoneMarker` — `commands.md:296`) that are NOT in the trunk, so a verify AFTER a paths build
  would fail on extra actors. Reachspecs and `next/prevNavigationPoint` links are already stripped as
  computed (`normalize.py:41-46`), but the spawned marker ACTORS are not. So paths must run AFTER
  the post-verify, and their output is unverified build output (like lighting).
- BSP quality does NOT affect post-verify: the compare is over authored brush polys + typed props,
  not the built BSP Model.

## Design

### Part A — `--quality` on `level materialize`

`driver.rebuild(quality=...)` emits `BSP REBUILD <LAME|GOOD|OPTIMAL>` instead of `MAP REBUILD`;
thread `quality` through `apply.run_materialize` → `materialize.materialize`'s `rebuild` callable.

```
level materialize --quality {lame,good,optimal}
    "BSP build quality (default: <Q1>). lame = fastest, skips coplanar detection (fast
     iteration); good = coplanar-merge pass; optimal = extra merge/optimize passes (final/ship)"
```

Default: **Q1** — the overview proposes `lame`; current behavior is `good`. Real owner call (Q1).

### Part B — pathfinding

Two shapes for how paths reach the map (Q2):

- (i) **`level build` = a superset build**: materialize (re-import, BSP, light, verify, save) THEN
  `PATHS BUILD` on the saved map and re-save. One verb, `--out` like materialize. "paths only" then
  means "the build that also does paths", distinct from `level materialize` (no paths).
- (ii) **`--paths` flag on `level materialize`**: same pipeline, opt-in paths stage after verify. No
  second verb.
- (iii) **`level build` as a pure post-process** over an existing `--map`: `MAP LOAD`, `PATHS BUILD`,
  `MAP SAVE`. Standalone and cheap to re-run, but adds a second editor round-trip and a load path.

Recommend (ii): paths are just another optional build stage, and a separate verb duplicates
materialize's whole `--out`/`--overwrite`/container surface for one extra editor command. If the
owner wants paths decoupled from a full rebuild, (iii) is the fallback.

Whichever shape: `PATHS BUILD` runs AFTER the post-verify (its spawned markers would fail the
compare), and a `--paths-opt {low,default,high}` maps to ``/`LOWOPT`/`HIGHOPT` (Q3 — or fold into
`--quality`).

## Edge cases & errors

- `--quality bogus` → argparse choices error (exit 2).
- A level with no NavigationPoints (PathNodes/PlayerStarts) authored in the trunk: `PATHS BUILD`
  produces an empty/trivial graph — not an error, but worth a stderr note (paths need authored
  markers to connect).
- Paths build failure / editor wedge → the existing materialize driver-error path (exit 2, nothing
  swapped in) — paths run before the atomic swap, or on a copy, so a failed paths build never leaves
  a half-pathed map at `--out`.
- `--paths`/`level build` with `--no-verify`: still runs paths (paths are independent of verify).

## Tests

- `driver.rebuild(quality=)` emits the right `BSP REBUILD <Q>` string (offline, mocked driver).
- `run_materialize` threads `--quality` to the rebuild callable; default is Q1's value.
- Paths stage runs AFTER verify (order asserted on a mocked driver); a paths-only failure aborts
  before the swap.
- Integration (default-deselected, real editor): a level with two PathNodes gains reachspecs; a
  `level import` of the built map shows the graph.
- docs: `docs/usage.md` gains `--quality` and the paths verb/flag; `docs/leveldesign/` note that
  pathing is a build step (owner-approval-gated craft claim — propose, don't self-add).

## Open questions

- Q1 — `--quality` default: `lame` (overview) vs `good` (current) (`questions/quality-default.md`).
- Q2 — paths delivery shape: `level build` superset / `--paths` flag / post-process a `--map`
  (`questions/paths-verb-shape.md`).
- Q3 — path-optimization knob: separate `--paths-opt` vs folded into `--quality` vs always default
  (`questions/paths-opt-knob.md`).
