+++
priority = "p1"
kind = "debug"
summary = "Native materialize byte-parity vs UnrealEd UED22: status/index for the whole geometry+lighting effort. Wanchai lighting 3418/4530 (75.5%) byte-identical after line_clear v2; UNATCO 2797/3345 (83.6%). Geometry breadth 3/21 OG levels exact; severe-under-build family (Area51 etc.) closed by the mirrored-brush determinant fix. See below for the harness catalog and open threads."
depends-on = ["port-urender-getvisiblesurfs-so-each-light-gets", "port-the-per-leaf-permeating-light-lists-model", "getvisiblesurfs-wanchai-run-gap-root-cause", "line-clear-shadow-ray-algorithm-gap-found-real", "zone-crossing-getvisiblesurfs-gap-invisible", "smuggler-4-surf-delta-traced-to-4-pf-semisolid", "freeclinic08-nsfhq04-1-surf-under-build-root", "wanchai-verts-points-residual-independently", "pass-d-chain-link-order-native-splices-zone", "pass-d-fragment-nodes-get-ileaf-1-where", "splitwithplane-degenerate-fragment-fallback", "native-zone-over-fragmentation"]
spikes = ["dev/docs/spikes/2026-08-27-native-light-apply-parity/", "dev/docs/spikes/2026-08-29-unatco-repart-live-diff/", "dev/docs/spikes/2026-08-29-area51-underbuild/", "dev/docs/spikes/2026-08-26-editor-free-native-materialize/"]
+++

# Native materialize byte-parity: status, index, and harness catalog

**Standing goal** (owner, 2026-08-30, `dev/docs/native-materialize-findings.md`): native `level
materialize` must reproduce UnrealEd UED22's real geometry-build and lighting-bake PROCESS, not just
converge on a matching byte count — a fix ports the editor's real, live-verified algorithm, never a
tolerance fudge chosen because it measures better. Byte-identical `.dx` output on original (OG),
shipped Deus Ex levels is the bar; `Test_Castle`/non-retail fixtures are not valid evidence
(`native-materialize-findings-older-than-2-weeks`). Findings older than ~2 weeks, and every
pre-2026-08-14 native-decode/disassembly claim, are untrusted until re-derived live
(`owner-ruling-all-native-decode-spike-findings`) — re-measure before relying on anything old.

This item is the STATUS/INDEX layer for the whole effort: current state, the harness catalog, and
pointers to every open sub-thread. Blow-by-blow findings live in
`dev/docs/native-materialize-findings.md` — search it, don't duplicate it here.

## Current status (2026-08-31)

**Geometry:** breadth sweep across 21 OG retail levels
(`breadth-geometry-check-on-10-new-og-levels-1-10`, `breadth-geometry-re-check-across-11-og-levels-2`)
— 3/21 exact (Wanchai Market, and the two trivial ≤6-brush intro/logo maps `DX.dx`/Endgame4); ~1/19
excluding trivial maps. UNATCO is close but not node-exact (+7 nodes). The severe-under-build family
(Area51 Entrance and 4 other levels losing 13-27% of nodes) is CLOSED — root-caused to a mirrored-brush
determinant bug and shipped (`mirrored-brush-determinant-fix-closes-the`, commit `c7b8b0b`); remaining
deltas on those 5 levels are back in the ordinary noise range. Two other under-build families are
still open and NOT the same mechanism: `freeclinic08`/`nsfhq04` (-38 nodes/-23 leaves, a world-level
`bspBuildFPolys`/merge poly-order divergence, localized but not root-caused) and `smuggler` (+4 surf
residual, isolated to 4 `PF_Semisolid` brushes, root mechanism still open).

**Lighting:** `LIGHT APPLY` runs fully offline (`UEDCLI_NATIVE_MATERIALIZE=1 level materialize`, no
editor in the path). After the `line_clear` threaded-state shadow-ray port (round 8, commit `9827f07`,
shipped): Wanchai `LightMap` records byte-identical 3418/4530 (75.5%); UNATCO 2797/3345 (83.6%,
geometry-matched spot-check, not the item's own full re-run). The largest remaining bucket on Wanchai
is the `Points`/geometry residual (~54% of bad records, gap 3 below) — lighting parity is gated on
geometry parity more than on the bake algorithm itself at this point.

## Harness catalog

Reusable measurement/verification scripts for this effort. All live under `dev/docs/spikes/*/harness/`
and import the production `.dx` decoder (`uedcli/native/umodel.py`) or drive the real editor via
`ensure_editor`. No unified parity-report/verify tool has landed yet — `git log` on master shows no
such merge as of 2026-08-31; treat any reference to one elsewhere as aspirational, not shipped.

| script | path | what it checks |
|---|---|---|
| `regression_gate.py` | `2026-08-29-unatco-repart-live-diff/harness/` | UNATCO + Wanchai node/surf/leaf exactness against their committed goldens — the standard "did this change regress anything" gate, run before/after every `bspcsg.rs`/`zones.rs` edit |
| `breadth_gate.py` | `2026-08-29-unatco-repart-live-diff/harness/` | node/surf/leaf/vert/point/vector counts for `uedcli_native.build_geometry_bspcsg` vs an editor `MAP REBUILD`-only golden, across the whole `geo-confirm-*` corpus — the breadth/30%-floor measurement |
| `geo_golden_driver.py` / `geo_golden_resume_structural.py` | `2026-08-29-unatco-repart-live-diff/harness/` | drives the real editor (`MAP NEW` → `EDIT PASTE` → `MAP REBUILD` → `MAP SAVE`, chunked) to build a fresh geometry-only golden `.dx` from a trunk |
| `build_ued_golden.py` | `2026-07-15-native-materialize/harness/` | canonical `--world-only --no-light [--no-obj-load]` golden builder; the one referenced by nearly every geometry-parity item as the correct provenance (never `MAP LOAD` — see `map-load-and-edit-paste-build-different-world`) |
| `build_ued_lit_golden.py` | `2026-08-27-native-light-apply-parity/harness/` | same, but runs `LIGHT APPLY` too, for a lighting-bake golden |
| `lightparity.py`, `bit_asymmetry.py`, `run_diff.py`, `light_geomatch.py`, `lights_regions.py`, `grid_formula_fit.py` | `2026-08-27-native-light-apply-parity/harness/` | `LightMap`-record-level comparison suite: byte-identical %, which direction bits err, which (surf,light) pairs are extra/missing, geometry-tree divergence at mismatched records, `Model.Lights`'s two regions split apart, the lumel-grid sizing rule |
| `light_spotcheck_unatco.py`, `light_spotcheck_wanchai.py` | `2026-08-29-unatco-repart-live-diff/harness/` | fast bounded spot-check of an existing lit golden (no fresh editor build) — the "get today's number" script, used every round instead of a full re-run |
| `broad_shadow_sweep.py` | `2026-08-29-unatco-repart-live-diff/harness/` | full-level (whole Wanchai, ~900K+ bits) shadow-bit sweep, v1-vs-v2-vs-golden — the only harness that exhausts a level rather than sampling |
| `lumel_axes_live_check.py`, `line_clear_algorithm_check.py`, `line_clear_v2_algorithm_check.py`, `linecheck_*.py` | `2026-08-29-unatco-repart-live-diff/harness/` | live-gdb capture and offline cross-check of the shadow-ray walker (`linecheck.rs`/`line_clear`) against the real editor, function-by-function |
| `mergewith_live_check.py` | `2026-08-29-unatco-repart-live-diff/harness/` | live capture of `FSpanBuffer::MergeWith`, confirms `merge_into`'s port is faithful |
| `zone_crossing_pairs.py`, `wanchai_descendant_slots.py` | `2026-08-29-unatco-repart-live-diff/harness/` | `GetVisibleSurfs`/zone-crossing pair-level diffing |
| `prepart_tree_unatco.py`, `prepart_tree_wanchai.py`, `fbs_root_poly_order.py`, `fbs_world_poly_order.py`, `fpolys_stage_order.py` | `2026-08-29-unatco-repart-live-diff/harness/` | live capture of the real editor's `FindBestSplit`/`bspRepartition`/`bspBuildFPolys` poly order at various stages — the toolkit for any future repartition-order investigation |
| `smuggler_*.py` | `2026-08-29-unatco-repart-live-diff/harness/` | brush/poly-scoped descent+leaf tracer for `bspcsg.rs`'s `filter_ed_poly`/`leaf_func` (env-gated `UEDCLI_BSPCSG_DESCENT_ACTOR`/`_POLY`), built for the smuggler residual but reusable for any brush-scoped CSG classification question |
| `a51_*.py` | `2026-08-29-area51-underbuild/harness/` | per-brush attribution, isolation, and prefix-replay toolkit that root-caused the Area51 under-build (over-carve misclassification at a specific brush index) — the pattern to reuse for any future "which brush causes this delta" investigation |
| `umodel_parser.py` / `umodel_serialize.py` | `dev/docs/spikes/bspspike/` | frozen, independent `.dx` decode/encode copies (stale naming only — nothing imports them; the live decoder every other harness uses is `uedcli/native/umodel.py`) |

Known harness defects, not yet fixed: `umodel-parser-harness-pf-portal-constant-is` (a `bspspike`
harness has `PF_PORTAL` wrong, `0x0080` is actually `FakeBackdrop`); `breadth_gate.py` segfaults
intermittently across a full 13-case back-to-back run (not reproduced in isolation, not investigated).

## Open threads

Lighting (detail below this section, and in `dev/docs/native-materialize-findings.md`):

- **Light runs** (`port-urender-getvisiblesurfs-so-each-light-gets`) — extra/missed (surf,light)
  pairs, much smaller after the DFS-order and `PF_Invisible` fixes but not closed.
- **`Model.Lights` per-leaf permeating region** (`port-the-per-leaf-permeating-light-lists-model`) —
  first port attempt lands the right leaf SET, not yet the right per-leaf content; not wired in.
- **`Points`/geometry residual** feeding `Pan`/`UScale`/`VScale` mismatches — tracked as a geometry
  thread below (`wanchai-verts-points-residual-independently`); the largest single lighting bucket.

Geometry:

- `smuggler-4-surf-delta-traced-to-4-pf-semisolid` — +4 surf residual, root mechanism not found.
- `freeclinic08-nsfhq04-1-surf-under-build-root` — world-level poly-order divergence, localized to
  before `bspBuildFPolys` even runs, not root-caused further.
- `wanchai-verts-points-residual-independently` — +16/+19 verts/points residual on Wanchai,
  "exhausted across 4 rounds", explicitly recommends stopping and redirecting to lighting instead.
- `pass-d-chain-link-order-native-splices-zone`, `pass-d-fragment-nodes-get-ileaf-1-where` — two
  distinct zone-split fragment-ordering/leaf-assignment gaps in `zones.rs`'s Pass D, both untouched
  since filed.
- `splitwithplane-degenerate-fragment-fallback` — `FPoly::SplitWithPlane` degenerate-cut fallback
  behavior differs from native's.
- `native-zone-over-fragmentation` — the flood-fill half of a zone over-fragmentation bug is fixed;
  a CSG-tree-shape cause remains, called "the real bottleneck".
- `two-overlapping-add-boxes-panic-dead-root-no` — `build_geometry_bspcsg` panics on a specific
  two-box synthetic case; found incidentally, not investigated.
- `native-materialize-silently-ignores-postscale` — materialize's brush-input gate reads `MainScale`
  only, silently mis-building brushes with `PostScale`/`SheerRate`.
- `self-package-rewrite-turns-a-map-embedded` — latent (no shipped map hits it) package-self-ref bug
  in the `assemble_unbuilt` path.

Methodology / infrastructure:

- `map-load-and-edit-paste-build-different-world` — the editor builds a genuinely different world BSP
  via `MAP LOAD` vs `MAP NEW`+`EDIT PASTE` from the same brushes; every golden in this effort must use
  the paste path, never `MAP LOAD`.
- `no-reproducible-recipe-for-the-index-aligned` — the original node-for-node-aligned UNATCO golden
  (6314 nodes) that early parity work was measured against lived in `/tmp` and is gone; `level
  materialize` now produces a differently-ordered 6254/6321-node tree, so that specific historical
  comparison can't be re-run.
- `clean-map-import-crashes-the-editor-container` — a bare `MAP IMPORT` (no CSG paste) crashes the
  editor container regardless of level size; blocks the export/import-table-ordering question in
  `unrealed-geometry-build-map-rebuild-bsp-rebuild` §12.1/§20.3.
- `dx-lum-uned-image-missing-rendering-md-editor` — the container image never baked the documented
  headless-rendering fixes, so a real GUI editor pixel render is unobtainable here (does not block the
  `ExecCommandlet`-only path this effort actually uses).
- `dev-docs-states-fbspsurf-izone-where-the-field` — `dev/docs` still documents the on-disk
  `FBspSurf` u16 pair as a zone index; it is `PanU`/`PanV`. Code already fixed; docs need the owner's
  yes.
- `lean-classify-trees` — perf-only, owner-question open on whether an empirically-(not provably-)
  byte-identical optimization is acceptable.

Reference (not action items, cite before re-deriving):

- `owner-ruling-all-native-decode-spike-findings`, `native-materialize-findings-older-than-2-weeks` —
  the two standing process rulings this whole effort runs under.
- `unrealed-geometry-build-map-rebuild-bsp-rebuild` — the reverse-engineered spec of UnrealEd's
  geometry/lighting/paths build, the primary algorithmic reference for any new port.
- `editor-free-native-world-bsp-map-assembly` — current architecture note: `level materialize` builds
  a whole `.dx` with no UnrealEd behind `UEDCLI_NATIVE_MATERIALIZE=1`; still needs a permanent CLI
  flag once this effort's remaining gaps close.
- `done/unatco-verts-points-residual-after-the-zone`, `done/mergewith-fully-decoded-confirms-merge-into`
  — already-closed geometry/lighting sub-threads with detail worth reading before re-opening either.

## Superseded / retired items

~60 older board items (mostly filed 2026-07-xx, before the pre-2026-08-14 decode findings were ruled
untrustworthy, plus a handful of this session's superseded measurement rounds) were folded into
`dev/docs/board/done/` in the same change that wrote this item, each with a one-line supersession
note. Git history has the full text if any of them turns out to hold something not captured here or
in the findings ledger.

---

The lighting-bake detail below predates this restructure and is kept for its checkable tables and
reproduction recipe; treat "Status" dates within it as the most recent for the LIGHTING thread
specifically, not for the whole effort (see "Current status" above for that).

## Status 2026-08-30 (latest): `GetVisibleSurfs` DFS-order bug fixed (far_child was interleaved
before the coplanar chain)

`zone-crossing-getvisiblesurfs-gap-invisible`'s open tail ("zone1's span buffer is GLOBALLY exhausted
by DFS order before traversal reaches it") was a real traversal-order bug, not just occlusion
precision: `traverse` recursed into `far_child` one loop-turn too early (right after the head's own
surface, before the rest of the `i_plane` coplanar chain), contra the documented real order (near
child -> own surface -> iPlane chain -> far child). Fixed, TDD-pinned, geometry unaffected. UNATCO
byte-identical 2739/3345 (81.9%) → **2769/3345 (82.8%)**; Wanchai 3319/4530 (73.3%) →
**3408/4530 (75.2%)**, run-identical 4290→4414, extra pairs 77→31. Full detail: findings ledger +
`zone-crossing-getvisiblesurfs-gap-invisible`.

## Status 2026-08-30 (earlier): zone-crossing `PF_Invisible` bug fixed

`zone-crossing-getvisiblesurfs-gap-invisible`: `PF_Invisible` was wrongly gating the whole raster/
span-test/portal-crossing step for `GetVisibleSurfs` (not just the surf's own emission into the
light's run) — since a real `PF_Portal` surface is near-universally ALSO `PF_Invisible`, this silently
blocked most/all invisible-portal zone-crossings. Fixed (`visible_surfs.rs::traverse`), TDD-pinned.
Wanchai records byte-identical 3297/4530 (72.8%) → 3319/4530 (73.3%); UNATCO (geometry-matched)
2692/3345 (80.5%) → 2739/3345 (81.9%). Geometry unaffected. Does not close the full zone-crossing
share — some zone-crossing misses remain, cause not yet identified.

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

So gap 3 (`Points` residual, out of scope here — tracked in
`wanchai-verts-points-residual-independently`) is actually the LARGEST single bucket at 54% of bad
records — bigger than gap 1. Even a perfect fix for gaps 1 and the shadow-ray precision issue caps out
around (3228+343+254)/4530 ≈ 84.5% on Wanchai; closing the rest needs the geometry fix. Gap 2
(`Model.Lights` permeating region) does NOT appear in this table at all — it's a separate array
(`Model.Lights` region 1) that `lightparity.py`'s "records byte-identical" measure never reads,
confirmed by reading `bake`'s `emit_record` (only region 2, the per-surface runs, feeds `LightMap`).
Wiring it in would not move this percentage.

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

## State on `03_NYC_UNATCOHQ` — STALE, trees no longer identical, records do NOT align 1:1

(Was mislabeled `01_NYC_UNATCOHQ` throughout this session's docs until 2026-08-31 —
`unatco-baseline-trunk-is-actually-03-nyc` confirmed the `_scratch/bsp-parity-proj/maps/unatco`
trunk this whole investigation uses is actually `03_NYC_UNATCOHQ.dx`, not `01_`.)

Table below measured 2026-08-29 AM after the `GetVisibleSurfs` self-occlusion fix (`9c148d4`),
back when UNATCO's tree was still node-exact. Later the same day, `04986a2` (repartition-frontier)
moved UNATCO's nodes to 6321 (was 6314) — the table's premise ("trees identical, records align
1:1") no longer holds, so these specific numbers are not a meaningful current measurement.
Full re-run afterward: 1627/3345 (48.6%) byte-identical, but that number conflates real bake
differences with pure record-misalignment noise now that the trees disagree, so it isn't
trustworthy as a bake-quality number either — needs UNATCO's node-exactness restored (see
`done/unatco-verts-points-residual-after-the-zone`'s "CORRECTION" section) before this table means
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

**2026-08-31 (round 9 of `line-clear-shadow-ray-algorithm-gap-found-real`): the same bounded
spot-check re-run after that item's round-8 `line_clear` fix (commit `9827f07`) — real, positive
gain, same golden, same harness, no tree change since the note above.** Records byte-identical
2692/3345 (80.5%, the number just above) → **2797/3345 (83.6%)**, +105 records; shadow-bit agreement
99.23% → 99.27%. Consistent with Wanchai's own smaller gain from the same fix (3408/4530→3418/4530).
Geometry unaffected (still 3616/6314/762/599 exact). This is still the bounded spot-check, not this
item's own full methodology (`lightparity.py`+`bit_asymmetry.py`+`run_diff.py`+`light_geomatch.py`)
— that re-run is still the concrete next step if this item is picked up again. Full detail:
`dev/docs/native-materialize-findings.md` and `line-clear-shadow-ray-algorithm-gap-found-real`'s own
round 9 section (which also found and fixed a small non-monotonic tail in `line_clear` v2 via a
full-level broad sweep — logged there, not a fix to this item).

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
   UNATCO). See `done/unatco-verts-points-residual-after-the-zone` and
   `wanchai-verts-points-residual-independently` — the UNATCO causal story is flagged unreliable by
   `owner-ruling-all-native-decode-spike-findings`, needs re-diagnosis from fresh live capture if
   picked up again. No lighting change can move these; they follow for free when Points reaches
   parity.

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
* **CHASED 2026-08-30 (same day), CONFIRMED, then SHIPPED (round 8) and re-verified clean through
  round 10.** The real cause of the bits-only bucket was `linecheck::line_clear`; the ported
  threaded-state walker is now shipped (`9827f07`) and independently re-verified against a full-level
  sweep, a 203-case regression population traced to a `broad_shadow_sweep.py` measurement artifact
  (not a real defect), and confirmed not to reproduce against native's own built tree. Full 10-round
  writeup: `line-clear-shadow-ray-algorithm-gap-found-real`. One open, explicitly-not-chased footnote:
  the real editor's per-surface timing for when it sets `NF_BrightCorners` during `LIGHT APPLY` is
  undecoded — dormant today (native never sets that bit, matching the editor's at-cast-time state),
  but would need decoding before native could set it without risking a real regression.
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
