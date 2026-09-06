+++
priority = "p2"
kind = "debug"
summary = "OceanLab is byte-exact N=1..12 and FAILS at N=13: one CSG-soup split vertex is 1 ULP off in x and 2^-15 off in y, where UED22 lands exactly on the y=-256 brush plane."
+++

# OceanLab N=13 CSG-soup split vertex off by 1 ULP

Found 2026-09-05 extending the ladder (OceanLab was recorded byte-exact only to N=3). N=1..12 PASS;
N=13 FAILS against a **freshly editor-built** ref, one gate residual class in world `Model2` and its
`Polys`.

## The divergence

World CSG soup (`Model2`'s `Polys`), 226 polys both sides, exactly **two** differ — polys 175 and 178,
both fragments of the same brush poly (`iBrushPoly` 153), sharing ONE vertex:

    native (516.5463256835938, -255.99996948242188, -2560.0)
    UED22  (516.5462646484375, -256.0,               -2560.0)

x differs by 1 float32 ULP; y by exactly `2^-15` (3.0517578125e-05). Poly 175 is a `z=-2560` floor
fragment whose vertex[0] is `(-317.38336, -256.0, -2560.0)` — exactly on `y=-256` on BOTH sides. So
the same split against the same `y=-256` plane lands exact for one endpoint and 2^-15 off for the
other, only in native.

The value propagates: the same wrong vertex is the only difference in the built `Model2` Points/Nodes/
Verts too (`points` 499=499, `nodes` 333=333, `surfs` 162=162, `verts` 3945=3945 — counts all equal).

## Where to look

`fpoly.rs::split_with_plane` (line ~335) and its `line_plane_intersection` (line ~55) are structurally
faithful to UE1's `FPoly::SplitWithPlane` / `FLinePlaneIntersection`, and Rust does not auto-contract
to FMA — so with identical inputs the outputs would be identical. The divergence is therefore in the
**inputs**: the splitting plane's `base`/`normal`, or the edge endpoints, differ by a hair.

Leading hypothesis (unverified): the editor's `SplitWithNode` splits with the node plane rebuilt from
the POOLED `Model->Points(Surf.pBase)` / `Model->Vectors(Surf.vNormal)` — values that have been through
`bspAddPoint`/`bspAddVector` dedup — while native splits with the `FPoly`'s own base/normal. A pooled
base a hair away changes `t` by ~1 ULP. Same family as the `a56f6dc` `FindNearestVertex` work.

Second candidate: `SplitWithPlane`'s "previous vertex is inside the ±T band, so IT is the cut point"
arm (`0x151c97`) firing in the editor and not in native (or vice versa) for this edge.

The value is not authored — it appears in NEITHER build's brush `Polys`, only in the world soup — so
it is computed on both sides. Poly 175 is a `z=-2560` quad whose `v0` and `v3` are the two cut points
on `y=-256`; `v0` comes out exactly `-256` on both sides, `v3` only in UED22. Every other vertex of
the poly is byte-identical, so the differing input is the edge's OTHER endpoint — a vertex discarded
by this split, i.e. the real first divergence is an EARLIER split. A split-by-split trace of that
brush poly's descent is the way in.

## Repro

    ladder_run.py --dx <…>/Maps/14_OceanLab_Lab.dx --from 13 --to 13 --force-ref --keep-native
    token_diff.py <…>/native_N13.dx <…>/ref_N13.dx model2

## Resolved

Fixed by `db85703` (MergeNearPoints remaps `FBspSurf.pBase` too) — OceanLab now byte-exact N=1..16,
covering this item's N=13. Not a separate cause; same welded-point-survives-refresh bug as WanChai N40.

OceanLab reaches N=1..33 after `a762617` (repartition point dedup takes the nearest pool point);
`--to 33` was the run's limit, not a bail.
