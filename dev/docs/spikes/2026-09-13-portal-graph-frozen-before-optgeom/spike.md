# The three-site 1-ULP permeating-light tie — root cause and fix

Continues `dev/docs/spikes/2026-09-13-crossing-vertex-live-capture/`, which traced Island N=332's
decisive beam-clip crossing to a 1-ULP mismatch in one of its two INPUT vertices (a Pass-B
portal-quad corner), not the crossing formula itself, and left "find which ancestor crossing inside
Pass B produces this mismatched vertex" as the open next step. Same open residual also blocked
UNATCO N=226 and WanChai N=58 (`NATIVE-MATERIALIZE.md`'s "Open blockers" section, three board items).

## Method

Extended `zones.rs::make_portals_clip` with two env-gated hex-precision trace modes (native-side,
no live editor capture needed once the shape was known):

- `UEDCLI_PORTAL_TRACE_NEAR="x,y,z[,eps]"` (`*` wildcards an axis): dumps every ancestor-plane split
  whose poly touches a vertex near the target, in raw hex `u32` bit patterns — finds WHICH node/
  ancestor-index pair is responsible without knowing it ahead of time.
- `UEDCLI_PORTAL_TRACE_NI=<node>`: dumps a named node's entire `make_portals_clip` ancestor loop
  unconditionally (surf/point indices included), for once the node is known.

Ran both against the cached Island N=332 subset (`_scratch/actor-parity/01_nyc_unatcoisland/N332/`)
via `harness/run_portal_trace.py` (calls `parity_compare.build_native_lit_dx` directly on a cached
subset trunk — no live editor container needed for this half).

## Finding

`zones::collect_leaf_portals` runs TWICE in the native pipeline for the exact same node tree:

1. Once inside `zones::assign_leaves_and_zones` (Pass B, called from `bspcsg.rs::zone_pass`,
   itself called "between the repartition and the detail-brush loop" — i.e. at TestVisibility time,
   matching the real editor's own `csgRebuild -> TestVisibility` call order).
2. Again, fresh, from `permeating_lights::leaf_portal_map`, called much later from `light::bake`.

Between these two moments, `bspoptgeom::bsp_opt_geom` runs (`bspcsg.rs` line ~3619, "step 5" of
`csgRebuild`, confirmed by disassembly to be the real `bspOptGeom`) and its first sub-step,
`merge_near_points`, is a faithful port of the editor's `ShrinkModel`-style point de-dup
(`Editor.dll 0x33dc0`): it remaps `surf.pBase` to the nearest EARLIER point within 0.25 units.

Traced node 849's ancestor at `i_anc=847` (the wall at `y≈4080`) across both calls:

    call 1 (Pass B, pre-optgeom):  surf=144  pBase=540  point=(…, 0x457f0001, …) = 4080.000244140625
    call 2 (bake time, post-optgeom): surf=588 pBase=487  point=(…, 0x457f0000, …) = 4080.0 exact

Same node, same plane (`node.plane` is untouched by the remap — it's `surf.pBase` that moves), same
ancestor stack — but a DIFFERENT resolved base coordinate, because `merge_near_points` ran in
between and remapped `pBase` 540 → 487 (an earlier, exact-grid point close enough within 0.25 units).

**Call 1's value (4080.000244140625) is exactly what the live editor capture measured** in
`2026-09-13-crossing-vertex-live-capture/spike.md` for this same crossing. **Call 2's value
(4080.0 exact) is what the FINAL saved package's `Model.Points` holds** (already confirmed
byte-identical between native and UED22 by `model_dump.py`, long before this investigation).

This is the whole bug: the real editor's `MakePortals` (part of TestVisibility) runs ONCE, before
its own `bspOptGeom`'s point-merge, and its beam-clip flood (during `LIGHT APPLY`) reuses that
one-time portal graph unrefreshed — so the flood sees the PRE-merge coordinate even though the
FINAL saved geometry is POST-merge. Native's `permeating_lights` module recomputed portal geometry
fresh at bake time (explicitly, per its own prior doc comment: "the node tree is unchanged by the
time lighting runs, so recomputing here is cheap and exact") — true for the node TREE, false for the
POINTS array, which `bspOptGeom` mutates in between. Recomputing after that mutation reads a
different (post-merge, exact-grid) coordinate than the real editor's flood ever computed, occasionally
turning a genuine near-tie into an exact tie (or vice versa) at a shared-vertex coincidence — which is
exactly the "right formula, sub-ULP residual" symptom all three board items chased into `SafeNormal`/
`FLinePlaneIntersection` precision without success.

## Fix

`Model` gains `leaf_portals: Option<Vec<zones::Portal>>`. `assign_leaves_and_zones` freezes its
Pass-B portal list into it right after computing it (before Pass D/optgeom can touch anything).
`permeating_lights::leaf_portal_map` reads `model.leaf_portals` instead of calling
`collect_leaf_portals(model)` fresh; the fresh recompute stays only as a fallback for hand-built
test models that never ran `assign_leaves_and_zones`.

No formula, threshold, or precision model changed — this is a computation-ORDER fix (use the
snapshot from when the real editor's equivalent code ran), not a numerical one.

## Verification

- `cargo test`: 235 passed, 0 failed, 2 pre-existing ignored (was 234/0/2 before — one new
  regression test added, see below).
- New regression: `permeating_lights::tests::
  leaf_portal_map_is_frozen_at_pass_b_not_recomputed_from_current_points` — builds a stepped-room
  fixture, calls `assign_leaves_and_zones`, mutates every point afterward (simulating
  `merge_near_points`), and asserts a portal face's clipped VERTS (not its `base`, which is
  derived from the generating node's own `plane` field and is untouched by a `pBase` remap either
  way) are unchanged. Verified this test FAILS on the pre-fix code (reverted `leaf_portal_map` to
  call `collect_leaf_portals(model)` directly) and PASSES on the fix, both confirmed by hand before
  committing.
- `ladder_run.py` re-verification (`dev/docs/spikes/2026-09-03-incremental-actor-parity/harness/`):
  - Island: N=330..335 all PASS (was FAIL at 332); pushed further, byte-exact past N=349 before this
    session stopped (see `NATIVE-MATERIALIZE.md` for the final confirmed ceiling).
  - UNATCO: N=220..239 all PASS (was FAIL at 226).
  - WanChai: N=55..58 all PASS (was FAIL at 58); now bails at a NEW, unrelated N=59 mover-`Polys`
    divergence — filed separately, `dev/docs/board/inbox/wanchai-n59-mover-polys-model2-diverges/`.
  - Spot-checks (unaffected levels, per campaign convention — ceiling + 2 points below, not a full
    sweep): NYC_Bar N=50/100/152 all PASS; OceanLab N=50/100/202 all PASS.

## What this closes

`island-n-332-leaf-273-permeating-light-vertex-tie`, `unatco-n-226-leaf-12-gets-a-permeating-light157`,
and `wanchai-n58-leaf-51-permeating-light-over-included` are all FIXED (not masked, not excluded) —
moved to `dev/docs/board/done/`. The "x87 vs SSE" / `SafeNormal` FPU-precision investigations those
items record (2026-09-12/13, refuted by a live `fctrl` probe) and the crossing-vertex hex-capture
that narrowed it to Pass B (`2026-09-13-crossing-vertex-live-capture/`) were all real, necessary
groundwork — the bug was one level further upstream than any of them individually reached, in WHEN
the portal graph gets read relative to `bspOptGeom`, not in any formula.
