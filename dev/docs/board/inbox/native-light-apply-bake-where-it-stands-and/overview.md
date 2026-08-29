+++
priority = "p1"
kind = "debug"
summary = "Resume pointer for the native LIGHT APPLY bake. It reproduces the editor's own output on 01_NYC_UNATCOHQ to 99.0% of per-(surface,light) shadow planes byte-identical and 99.99% of lumel bits; 2518 of 3345 LightMap records are byte-identical. Three named gaps remain, all owned elsewhere. How to rebuild both oracles and re-measure in one command each."
depends-on = ["port-urender-getvisiblesurfs-so-each-light-gets", "port-the-per-leaf-permeating-light-lists-model", "unatco-verts-points-residual-after-the-zone"]
spikes = ["dev/docs/spikes/2026-08-27-native-light-apply-parity/"]
+++

# Native `LIGHT APPLY` bake: where it stands and what closes the last gaps

`UEDCLI_NATIVE_MATERIALIZE=1 level materialize` now bakes lighting with no editor anywhere in the
path: `native.materialize.gather_lights` → `build_world_model(lights=)` →
`uedcli_native.bake_lighting` → `assemble_unbuilt(light_names=)`. A full lit build of the 1437-actor
UNATCO trunk takes 12 s; the 2288-actor `09_HONGKONG_WANCHAI_MARKET` takes 37 s.

## The measurement, and how to reproduce it

The oracle must be built `MAP NEW` → `EDIT PASTE` → `MAP REBUILD` → `LIGHT APPLY` → `MAP SAVE`. Do
NOT use the production editor path (`assemble_unbuilt` + `MAP LOAD`): it builds a DIFFERENT world BSP
from the same brushes (board `map-load-and-edit-paste-build-different-world`), and every `LightMap`
record then describes a different surface, so no positional comparison means anything.

    H=dev/docs/spikes/2026-08-27-native-light-apply-parity/harness
    .venv/bin/python $H/build_ued_lit_golden.py --trunk <trunk> --out golden.dx --overwrite
    UEDCLI_NATIVE_MATERIALIZE=1 bin/uedcli --project <proj> level materialize \
        --tree level/<lvl> --out native.dx --overwrite --no-verify
    .venv/bin/python $H/lightparity.py     native.dx golden.dx   # sections + per-record + runs
    .venv/bin/python $H/bit_asymmetry.py   native.dx golden.dx   # which DIRECTION the bits err
    .venv/bin/python $H/run_diff.py        native.dx golden.dx   # which lights are extra/missing
    .venv/bin/python $H/light_geomatch.py  native.dx golden.dx   # when the two trees DISAGREE
    .venv/bin/python $H/lights_regions.py  golden.dx             # split Model.Lights' two regions
    .venv/bin/python $H/grid_formula_fit.py golden.dx            # refit the grid rule, oracle only

The golden builder derives its keep-classes filter from `gather_lights`, so it picks up
`Engine.Spotlight` and friends automatically — do not hardcode `Light`, which silently under-lights
the golden and reads as native inventing lights.

Trunks used: `_scratch/bsp-parity-proj/maps/unatco` (1437 actors, 734 world brushes) and
`dev/games/trunks/tmp-wanchai-market` (2288 actors, 1304 world brushes). Both have fully qualified
actor classes, which `gather_lights` needs.

## State on `01_NYC_UNATCOHQ` (trees identical, so records align 1:1)

| | native | editor |
|---|---:|---:|
| surfs / nodes / leaves / vectors | 3616 / 6314 / 762 / 599 | same |
| `LightMap` records | 3345 | 3345 |
| surfs `iLightMap = -1` | 271 | 271 |
| grid dims (`UClamp`/`VClamp`) exact | 3345 / 3345 | — |
| records byte-identical | 2518 / 3345 | — |
| per-(surface,light) shadow planes byte-identical | 8162 / 8246 = 99.0% | — |
| lumel bits equal | 99.988% of 3,978,275 | — |
| light runs identical incl. order | 2977 / 3345 | — |
| light actors listed on a surface | 189 | 189 (0 either-only) |

## State on `09_HONGKONG_WANCHAI_MARKET` (re-measured 2026-08-29, trees now node-exact after `5b0a022`)

The old approximate (geometry-matched) numbers below are superseded — the tree gap that forced
approximate matching (`native-bsp-matches-the-editor-on-unatco-but-not`) is fixed, so records now
align 1:1 like UNATCO's. Exact-tree measurement:

| | native | editor |
|---|---:|---:|
| surfs / nodes / leaves | 5284 / 11648 / 3371 | same |
| points | 16807 | 16791 |
| vectors | 479 | 487 |
| `LightMap` records | 4530 | 4530 |
| surfs `iLightMap = -1` | 754 | 754 |
| records byte-identical | 3229 / 4530 = 71.3% | — |
| run identical (same set+order) | 4165 / 4530 = 91.9% | — |
| extra (surf,light) pairs native adds / misses | 526 / 12 | — |
| shadow bits on grid+run-matched records | 1007920 / 1018504 = 98.96% | — |
| light actors listed on a surface | 229 | 229 (0 either-only) |

Same shape as UNATCO's 618-extra/7-missing light-run gap (gap 1 below) and the same Points/Vectors
residual (gap 3), both roughly proportional to level size — confirms the two known gaps generalize
rather than being UNATCO-specific artifacts. `Lights` entries (13477 vs 31613) also confirm gap 2
(permeating region) scales the same way. Reproduced with
`_scratch/wanchai-relight-2026-08-29/{golden,native}.dx`, `lightparity.py`/`run_diff.py` logs alongside.

## The three remaining gaps, none of them in `light.rs`

1. **Light runs — 368 records, one-sided: native adds 618 (surface, light) pairs and misses 7.** The
   editor picks each light's surface set by RASTERIZING six 1024x1024 cube-map faces from the light
   and keeping whatever survives per-zone span buffers. Fully decoded in
   `port-urender-getvisiblesurfs-so-each-light-gets`, including a port sketch. This is the only gap
   that is genuinely the bake's own.
2. **`Model.Lights` is 11368 vs 16263 entries** — the missing 5405 is the per-leaf permeating region,
   produced by the ZONING build, not the bake: `port-the-per-leaf-permeating-light-lists-model` has the
   whole algorithm. `zones.rs` also still stubs every leaf's `iPermeating` to `0`, which is wrong data
   rather than missing data.
3. **`Pan` / `UScale` / `VScale` differ on 160 / 111 / 94 records** — exactly the records whose surf
   base point or texture vector differs from the editor by f32, i.e. the `Points` residual (native
   10758 vs 10752). See `unatco-verts-points-residual-after-the-zone`. No lighting change can move
   these; they follow for free when Points reaches parity.

## Two smaller leads, not chased

* The 466 lumels the editor lights and native does not are 487-vs-24 shadow-edge versus solid-blob, so
  they are f32 rounding at shadow boundaries, not a rule. The likeliest single cause: `lumel_axes`
  computes `det = tu·(tv×normal)` while `FCoords::Inverse` (`core 0x509c0`) expands the same
  determinant in a different term grouping — algebraically equal, not f32-identical, and every
  accumulated lumel position inherits the ulp.
* `FovAngle` for the editor's temp visibility viewport is not pinned (it is `Actor+0x304`, never set by
  the gather pass, and `SpawnViewActor` reuses a free `Camera`). Six 90°-apart faces only cover the
  sphere at FOV 90. Needed before a `GetVisibleSurfs` port can claim fidelity.

## Doc corrections awaiting the owner

`lightmap-grid-rule-ceil-extent-scale-is-wrong` carries a `questions/` file with the exact proposed
text for four corrections to `spikes/2026-07-15-native-materialize/sections/20-lighting-bake.md` (the
grid rule, the within-run order, both §6 residuals, and `PF_BrightCorners`, which the doc does not
mention at all) plus an offer to write the new spike's `spike.md`. `dev/docs/architecture.md` (its
"removed 2026-08-23" list and the native-materialize paragraph) and
`dev/docs/direction/materialize.md` ("has no lighting yet") also now contradict the code.
