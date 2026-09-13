+++
priority = "p1"
kind = "debug"
summary = "WanChai is byte-exact N=1..57 and bails at N=58: leaf 51 carries Spotlight22 where UED22 lists only Light189. Root-caused 2026-09-13 to a one-ULP FLinePlaneIntersection tie one hop upstream (the 45->55 beam's own closing vertex) — a THIRD confirmed instance of the same open, unresolved residual as Island N=332 / UNATCO N=226. Not fixed, no mask."
spikes = ["dev/docs/spikes/2026-09-07-gather-box-verdict/"]
+++

# WanChai N=58 — leaf 51 gets one permeating light UED22 does not

The next bail after `wanchai-n45-leaf-20-permeating-light-over-included` took the level from N=44 to
N=57. Same shape, same light, a different leaf — and, importantly, a different cause: the
`FLinePlaneIntersection` fix does not cover it.

## The divergence

    leaf_perm_diff.py <native_N58.dx> <ref_N58.dx>
    leaves 103 103; Model.Lights 824 823
    leaf[51] zone=1  nat=(spotlight22, light189)  ued=(light189,)  extra=[spotlight22]
    differing leaves: 1 of 103

Per-surf runs are clean (`lmdiag.py`: 0 differing of 234), so it is `Model.Lights` region 1 again.

## Localised, but not explained

`actor_visibility_probe.py` + `perm_flood_diff.py`: 12 of the 13 lights are IDENTICAL to the live
capture, leaf for leaf and crossing for crossing. Spotlight22 differs by two crossings — `(56, 51)`
and `(51, 52)` below it — so the root is **leaf 56 → leaf 51**.

Native keeps it with a clip polygon of

    [1408,-798.64264,-121.07201] [1408,-512,-121.072014] [1408,-512,-128] [1408,-798.6428,-128]

and the margins are not close (`UEDCLI_PERM_TRACE_EDGE=56-51`: one `SP_Split` with the surviving
side 7.1 units wide out of 49, everything else `SP_Front` by 5-196 units). No degenerate edge, no
epsilon tie. So this is not N=45's rounding case.

What stands out is that the editor's own beams into leaf 56 span a different part of the portal —
its `AV_REC ... to=56` polygons run `y = -798.64 .. -848`, native's runs `y = -798.64 .. -512`.

## Next step: compare the beam POLYGONS, not just the crossings

`perm_flood_diff.py` compares which crossings each side takes. That is blind to exactly this: two
floods can agree on every crossing and disagree on the polygon carried across one. The editor's
capture already carries the polygon on every `AV_REC` line (`--verts N`); native's `PERM_FACE` line
does not print `next_poly`. Print it, extend the diff to pair polygons per crossing, and the first
hop whose beam differs will name itself — the same method that cracked N=45, one level finer.

## Repro

    ladder_run.py --dx dev/games/deusex/Maps/06_HongKong_WanChai_Market.dx --from 58 --to 58 \
        --keep-native
    dev/docs/spikes/2026-09-07-gather-box-verdict/harness/leaf_perm_diff.py \
        _scratch/actor-parity/06_hongkong_wanchai_market/{native,ref}_N58.dx

## Root cause found (2026-09-13) — a 1-ULP crossing tie, same open class as Island N=332/UNATCO N=226

Re-derived fresh against the current binary; confirms and extends the "compare beam polygons, not
crossings" plan above. Method: `UEDCLI_PERM_DUMP_LEAF` (new, `permeating_lights.rs`) to check the
portal GRAPH topology first (ruled out — native's `collect_leaf_portals` graph for leaves 19/13/9/10
matches the live editor's real adjacency exactly, portal-for-portal); then a new probe,
`split_fast_probe.py`, live-capturing `FPoly::SplitWithPlaneFast`'s own call site inside
`ActorVisibility` (`Editor.dll 0x100a7158`, right after `call [0x100cee30]`) — the return value (`eax`,
`SP_Back`=2/`SP_Split`=3) plus the `Front` poly it computes, for every beam-clip edge test in the
whole `MAP REBUILD`. Paired hop-by-hop against native's own `UEDCLI_PERM_TRACE_EDGE` trace.

**The beam polygon carried into leaf 55 (via the `45->55` portal, native's OWN computation) matches
the live editor's capture at 4 of its 5 vertices exactly, and differs at the 5th by exactly one ULP:**

    native:  [1344,-512,-128] [1408,-512,-128] [1408,-798.6428,-128] [1344.0,      -848,-128] [1344,-848,-128]
    editor:  [1344,-512,-128] [1408,-512,-128] [1408,-798.6427,-128] [1343.99988,  -848,-128] [1344,-848,-128]

`1343.99988` is `f32::from_bits(1344.0f32.to_bits() - 1)` exactly — one ULP below the grid value
`1344.0`, the same signature as the already-documented `FLinePlaneIntersection` sub-ULP residual
(`NATIVE-MATERIALIZE.md`'s Island N=332 / UNATCO N=226 entries; `dev/docs/spikes/
2026-09-13-crossing-vertex-live-capture/spike.md`). This vertex is the crossing of clip-poly edge
`(1344,-848,-159.99997)->(1344,-848,-128)` against face vertex `(1408,-848,-128)->(1344,-848,-128)`
(`permeating_lights.rs::line_plane_intersection`, the P2 endpoint of that edge already sitting almost
exactly ON the clip plane) — landing bit-for-bit on the far endpoint in native's exact f32 arithmetic,
one ULP off it in the live editor's.

**This one ULP is the whole divergence's cause**, traced forward:
- Native's clip poly for this hop has an EXACT duplicate closing vertex (`[...,(1344,-848,-128),
  (1344,-848,-128)]`); the editor's has a near-duplicate (`(1343.99988,...)`, `(1344,...)`).
- Testing the `55->56` portal quad against this beam: both native and the live editor agree on the
  first 4 real edges (verified byte-for-byte via `split_fast_probe.py`'s captured `Front` output at
  each edge — including the LAST real edge, whose survivor is bit-identical to native's:
  `[1408,-798.642639,-121.072006] [1408,-512,-121.072014] [1408,-512,-128] [1408,-798.6427,-128]`).
- The 5th edge (native: `(1344,-848,-128)->(1344,-848,-128)`, zero-length -- `safe_normal` correctly
  returns `None` and native skips it as "no constraint", same formula, faithful) is, in the editor,
  `(1343.99988,-848,-128)->(1344,-848,-128)` — NOT zero-length (the cross product with `Light` scales
  the tiny 1-ULP gap by the light's distance, landing well above `SMALL_NUMBER`). The editor computes
  a real (if numerically noisy) plane from it and tests the survivor against it: **`SP_Back` — the
  whole `55->56` crossing is REJECTED**, live-captured directly (`SPF ... eax=2`, immediately following
  the matching `eax=3`/`Front` step above). Native has no such 5th edge to reject with, keeps the
  4-vertex survivor, and goes on to (wrongly) admit `Spotlight22` into leaf 51.

So the leaf-51 divergence is a real, large-margin consequence (a genuinely rejected vs. kept portal
crossing) — but its ROOT is the same irreducible-so-far one-ULP tie the campaign already has two open,
unresolved instances of. Per `NATIVE-MATERIALIZE.md`'s own account of those two, the formula
(`line_plane_intersection`) is disassembly-verified correct and reproduces native's own output by
hand; the residual is an unreplicated register/operation-order effect that has resisted two prior
gdb-based investigation sessions (Island N=332, UNATCO N=226) and needs single-stepping the compiled
`FLinePlaneIntersection`/`SafeNormal` chain to pin down, not a formula fix.

**Not fixed. No mask added** (masking a beam-clip topology decision is out of scope per the parity
bar — this is not a per-save-random field or dead bookkeeping bit). Per the task brief given for this
investigation: stop here rather than guess. This item is a THIRD confirmed occurrence of the same open
residual (after Island N=332 and UNATCO N=226) — first time seen changing which PORTAL survives a
beam clip, not just which vertex it carries a permeating-light leaf gets. Whoever next attempts the
register-level single-step should treat this as a third reproducer, at a different crossing.

New tooling committed for the next attempt: `dev/docs/spikes/2026-09-07-gather-box-verdict/harness/
split_fast_probe.py` (live `SplitWithPlaneFast` call-site capture); `UEDCLI_PERM_DUMP_LEAF=<leaf>` in
`permeating_lights.rs` (portal-graph-topology dump, independent of any light's flood — rules out a
missing-portal-edge hypothesis in one call).
