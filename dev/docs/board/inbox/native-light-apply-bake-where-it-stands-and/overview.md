+++
priority = "p1"
kind = "debug"
summary = "Resume pointer for the native LIGHT APPLY bake. Wanchai now 3297/4530 (72.8%) byte-identical after a pixel-center rasterization fix (getvisiblesurfs-wanchai-run-gap-root-cause, 2026-08-30) -- was 3228/4530 (71.3%), UNCHANGED by the later repartition_frontier geometry fix (re-measured 2026-08-30). Gap 2's lumel_axes hypothesis REFUTED (80/80 live match to FCoords::Inverse); line_clear investigated next and CONFIRMED as the real cause (disagrees with the editor's real bit on the editor's own real tree, 20/40 sampled) -- the editor's real function was live-disassembled on the current build but its per-node state formula was not fully decoded, no fix yet (line-clear-shadow-ray-algorithm-gap-found-real). UNATCO table below is STILL STALE (its tree hasn't been node-exact since the repartition-frontier fix); re-measure before trusting it."
depends-on = ["port-urender-getvisiblesurfs-so-each-light-gets", "port-the-per-leaf-permeating-light-lists-model", "unatco-verts-points-residual-after-the-zone", "getvisiblesurfs-wanchai-run-gap-root-cause", "line-clear-shadow-ray-algorithm-gap-found-real"]
spikes = ["dev/docs/spikes/2026-08-27-native-light-apply-parity/"]
+++

# Native `LIGHT APPLY` bake: where it stands and what closes the last gaps

Short, checkable, cross-cutting facts from this work are logged in
`dev/docs/native-materialize-findings.md` (check it before re-deriving something already known;
follow its check/recheck process before changing an entry).

## Status 2026-08-30: Wanchai improved, and the 3 gaps' relative WEIGHT is now measured

`getvisiblesurfs-wanchai-run-gap-root-cause` shipped a `rasterize_node` pixel-center-coverage fix
(see that item + the findings ledger). Wanchai: records byte-identical 3228/4530 (71.3%) →
3297/4530 (72.8%), run differs 348→266, extra pairs 134→79, missed 350→314. UNATCO (geometry-
matched, tree still not node-exact so the table below doesn't apply): run_ok 92.0%→94.2%. No
regression on shadow-bit-equal, grid/pan/scale rates, or Wanchai's geometry exactness.

That work also measured, for the first time, how much each of the "three remaining gaps" below
actually contributes to Wanchai's non-identical records (1302 as of the fix; a record can hit more
than one gap, classified by first match in this priority order — grid, then run, then bits, then
pan/scale):

| bucket | records | gap |
|---|---:|---|
| grid (`u_size`/`v_size`) mismatch | 6 | none of the three — separate, tiny |
| run differs (whether or not pan/scale also differ) | 343 | gap 1, light runs |
| bits differ, run+grid+pan+scale all agree | 254 | NOT one of the three — per-lumel shadow-ray precision, chased+REFUTED below |
| pan/scale differ ONLY (run+grid+bits all agree) | 699 | gap 3, `Points`/geometry residual |

**Superseded by a fresh re-measurement, same day** (`light_spotcheck_wanchai.py` +
`lightparity_buckets.py`, findings ledger): on the CURRENT tree (post-`repartition_frontier`'s verts
fix, +138→+74), byte-identical count is unchanged (3297/4530, 72.8%) and the bucket shape is close but
not identical — 1233 bad records: grid 6 (0.5%), run 261 (21.2%), bits 255 (20.7%), pan/scale 711
(57.7%). Same conclusion holds (pan/scale — the `Points` residual — is still the largest bucket).

So gap 3 (`Points` residual, out of scope here — tracked in `unatco-verts-points-residual-after-
the-zone` / `wanchai-verts-points-residual-independently`) is actually the LARGEST single bucket at
54% of bad records — bigger than gap 1. Even a perfect fix for gaps 1 and the shadow-ray precision
issue caps out around (3228+343+254)/4530 ≈ 84.5% on Wanchai; closing the rest needs the geometry
fix. Gap 2 (`Model.Lights` permeating region) does NOT appear in this table at all — it's a
separate array (`Model.Lights` region 1) that `lightparity.py`'s "records byte-identical" measure
never reads, confirmed by reading `bake`'s `emit_record` (only region 2, the per-surface runs, feeds
`LightMap`). Wiring it in would not move this percentage.

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

## State on `01_NYC_UNATCOHQ` — STALE, trees no longer identical, records do NOT align 1:1

Table below measured 2026-08-29 AM after the `GetVisibleSurfs` self-occlusion fix (`9c148d4`),
back when UNATCO's tree was still node-exact. Later the same day, `04986a2` (repartition-frontier)
moved UNATCO's nodes to 6321 (was 6314) — the table's premise ("trees identical, records align
1:1") no longer holds, so these specific numbers are not a meaningful current measurement.
Full re-run afterward: 1627/3345 (48.6%) byte-identical, but that number conflates real bake
differences with pure record-misalignment noise now that the trees disagree, so it isn't
trustworthy as a bake-quality number either — needs UNATCO's node-exactness restored (see
`unatco-verts-points-residual-after-the-zone`'s "CORRECTION" section) before this table means
anything again. Wanchai's table below is unaffected (its nodes stayed exact) and still current.

**2026-08-30: UNATCO's node-exactness is now restored** — `repartition_frontier` rewritten
(`done/unatco-verts-points-residual-after-the-zone`, `dev/docs/native-materialize-findings.md`),
nodes/surfs/leaves all byte-exact against golden for the first time. A bounded spot-check (not a
full re-run of this item's own table/methodology) against the existing lit golden
(`_scratch/native-visgate-2026-08-29/golden_unatco_lit.dx`,
`dev/docs/spikes/2026-08-29-unatco-repart-live-diff/harness/light_spotcheck_unatco.py`) confirms the
bake now completes cleanly (it crashed before that fix, on an unrelated latent bug also found and
fixed the same round — see the findings ledger): surfs/nodes/leaves/vectors/LightMap-record-count
all exact both sides (3616/6314/762/599/3345), 2692/3345 records fully identical, 99.23% shadow-bit
agreement on grid+run-matched records. This table's own STALE numbers above were NOT re-measured —
that's this item's own full methodology (`build_ued_lit_golden.py` + `lightparity.py` +
`bit_asymmetry.py` + `run_diff.py` + `light_geomatch.py`), a bigger undertaking than the spot-check
run here. Re-running it properly is the concrete next step if this item is picked up again — the
tree is finally in a state where it would mean something.

| | native | editor |
|---|---:|---:|
| surfs / nodes / leaves / vectors | 3616 / 6314 / 762 / 599 | same |
| `LightMap` records | 3345 | 3345 |
| surfs `iLightMap = -1` | 271 | 271 |
| records byte-identical | 2628 / 3345 = 78.6% | — |
| run identical (same set+order) | 3080 / 3345 = 92.1% | — |
| extra (surf,light) pairs native adds / misses | 151 / 233 | — |
| shadow bits on grid+run-matched records | 3161574 / 3185728 = 99.24% | — |
| light actors listed on a surface | 189 | 189 (0 either-only) |

## State on `09_HONGKONG_WANCHAI_MARKET` (re-measured 2026-08-29, trees node-exact after `5b0a022`)

Re-measured again after the self-occlusion fix (`9c148d4`):

| | native | editor |
|---|---:|---:|
| surfs / nodes / leaves | 5284 / 11648 / 3371 | same |
| points | 16807 | 16791 |
| vectors | 479 | 487 |
| `LightMap` records | 4530 | 4530 |
| surfs `iLightMap = -1` | 754 | 754 |
| records byte-identical | 3228 / 4530 = 71.3% | — |
| run identical (same set+order) | 4182 / 4530 = 92.3% | — |
| extra (surf,light) pairs native adds / misses | 131 / 347 | — |
| shadow bits on grid+run-matched records | 1069024 / 1079832 = 99.00% | — |
| light actors listed on a surface | 229 | 229 (0 either-only) |

Byte-identical count is essentially FLAT vs the pre-fix measurement (3229→3228) — extra pairs
dropped a lot (526→131) but missed rose (12→347), unlike UNATCO where every metric improved. The
self-occlusion fix (`getvisiblesurfs-self-occlusion-regresses-missed`) is a clear win on UNATCO and
a wash on Wanchai; `merge_into`'s fidelity to the undecoded `MergeWith` is the leading suspect for
the difference (Wanchai has more zones/portal crossings). Reproduced with
`_scratch/wanchai-relight-2026-08-29/{golden,native_occl}.dx`, `lightparity.py`/`run_diff.py` logs.

## The three remaining gaps, none in `light.rs`'s per-lumel bake itself

1. **Light runs — much smaller after `9c148d4`, still open.** UNATCO: was 618 extra/7 missed, now
   151/233. Wanchai: was 526/12, now 131/347. `port-urender-getvisiblesurfs-so-each-light-gets` has
   the resume state. `MergeWith` (`render.dll 0x1001e3b0`) is now fully decoded and confirmed correct
   as ported (`mergewith-fully-decoded-confirms-merge-into`, `dev/docs/board/done/`) — ruled out as
   the cause of the residual, not the source of it; the ~20% zone-crossing share of Wanchai's missed
   pairs still needs a real explanation.
2. **`Model.Lights` is 11368 vs 16263 entries on UNATCO** — the missing 5405 is the per-leaf
   permeating region, produced by the ZONING build, not the bake:
   `port-the-per-leaf-permeating-light-lists-model` has a first port attempt (not wired in — leaf
   SET matches exactly but per-leaf content doesn't yet). `zones.rs` no longer stubs every leaf's
   `iPermeating` to a bogus `0` (fixed to the correct `-1`, `8d7fe30`).
3. **`Pan` / `UScale` / `VScale`** differ on exactly the records whose surf base point or texture
   vector differs from the editor by f32, i.e. the `Points` residual (native 10758 vs 10752 on
   UNATCO). See `unatco-verts-points-residual-after-the-zone` — its causal story is flagged
   unreliable by `owner-ruling-all-native-decode-spike-findings`, needs re-diagnosis from fresh live
   capture. No lighting change can move these; they follow for free when Points reaches parity.

## Two smaller leads

* **CHASED 2026-08-30, REFUTED.** The suspected cause of the "bits differ, run/grid/pan/scale agree"
  bucket (255 Wanchai records) was: `lumel_axes` computes `det = tu·(tv×normal)` while
  `FCoords::Inverse` (`core.dll 0x509c0`) expands the same determinant in a different term grouping,
  "algebraically equal, not f32-identical". Fresh disassembly of the full routine (not this old note)
  shows every cofactor is a single product-minus-product, bit-identical to `light.rs`'s direct
  cross-product term by IEEE754 float-multiplication commutativity, and the determinant's 3-term sum
  is bit-identical too by IEEE754 addition commutativity (different pairing, same value) — a
  closed-form proof, not an approximation. Confirmed LIVE: `lumel_axes_live_check.py` breaks at
  `Editor.dll 0x100a5570` (right after the real `FCoords(0,TU,TV,N).Inverse().Transpose()` chain
  returns) during a real Wanchai `LIGHT APPLY`, captures the editor's REAL `u_dir`/`v_dir` for 80
  surfaces, diffs against `light.rs::lumel_axes`'s own formula on the same inputs: **80/80 match, 0
  mismatches**. `lumel_axes` needs no fix.
* **CHASED 2026-08-30 (same day), CONFIRMED (not a fix yet).** The real cause of the bits-only bucket
  is `linecheck::line_clear` — offline cross-check (`line_clear_algorithm_check.py`) shows the ported
  algorithm disagrees with the editor's real bit 20/40 sampled times even when fed the editor's OWN
  real BSP tree and real ray endpoints (self-consistency against native's own output verified faithful
  first, 40/40). Live-disassembled the real editor shadow-ray function on the current build
  (`linecheck_target_disasm.py`): refutes an old ±0.001 epsilon-tolerance hypothesis (the real test is
  a strict `>=0.0`, same as native's), rules out a plane-dot summation-association hypothesis for the
  one traced exemplar (axis-aligned plane, provably bit-identical either way), and cross-validates the
  existing `FBspNode` layout assumptions (`+0x20`/`+0x24`/`+0x37`, stride 0x40) live. The per-node
  state-threading bit formula was NOT fully decoded (dense SSE register reuse; needs a single-step
  trace, not more static reading) — no fix shipped, per the standing rule. Full writeup:
  `dev/docs/board/inbox/line-clear-shadow-ray-algorithm-gap-found-real/overview.md`.
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
