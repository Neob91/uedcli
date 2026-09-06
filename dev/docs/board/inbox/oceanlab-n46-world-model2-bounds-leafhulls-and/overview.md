+++
priority = "p2"
kind = "debug"
summary = "OceanLab N46 FAILS: world Model2's Bounds, LeafHulls and the per-leaf permeating-light region all diverge -- a leaf/bound-pass divergence, not a lighting-run one."
+++

# OceanLab N46 world Model2 bounds, leafhulls and permeating lights differ

OceanLab's ladder now reaches N=45 (the gather plane-test fix,
`oceanlab-n44-world-model2-lights-array-has-2`) and bails at N=46, which adds `Brush1427`.

`model_dump.py native_N46.dx ref_N46.dx model2` — same array counts throughout, contents differ:

| array | verdict |
|---------------|---|
| vectors, points, zones, leaves, lightbits | SAME |
| nodes, surfs, verts | DIFF |
| bounds (298) | DIFF from index 19 |
| leafhulls (2989) | DIFF from index 221 |
| lights (486) | DIFF from index 0 — the per-leaf permeating region, not a per-surf run |

Unlike N=44 this is not a lighting-run divergence: `LightBits` is byte-identical and the very first
`Lights` entry already differs, so the divergence is in the leaf/bound pass
(`passes.rs` bounds + leaf hulls) and `permeating_lights.rs`, feeding everything downstream.

## Repro

    ladder_run.py --dx <…>/Maps/14_OceanLab_Lab.dx --from 46 --to 46 --keep-native
    model_dump.py <…>/native_N46.dx <…>/ref_N46.dx model2
