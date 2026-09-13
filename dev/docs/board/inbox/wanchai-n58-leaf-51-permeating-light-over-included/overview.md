+++
priority = "p1"
kind = "debug"
summary = "WanChai is byte-exact N=1..57 and bails at N=58: leaf 51 carries Spotlight22 where UED22 lists only Light189. Localised to one crossing (56 -> 51) against a live capture, but unlike N=45 it is NOT a near-tie — native's beam POLYGON entering leaf 56 differs from the editor's."
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
