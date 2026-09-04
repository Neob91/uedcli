+++
priority = "p2"
kind = "bug"
summary = "native N8 UNATCO rotated-brush base FP diverges flipping node plane W and Region"
+++

# native N8 UNATCO rotated-brush base FP diverges flipping node plane W and Region

UNATCO `03_NYC_UNATCOHQ` fails the parity gate at N=8 (N=1-7 pass). Actor #8 = `Brush74`
(`Carter_window`, the only rotated brush in the prefix: `Rotation=(Yaw=-16384)` = 270deg,
`PrePivot=(-55.999664,-2.000244,1.000031)`, `Location=(448,64,416)`).

Three gate residuals, ONE root cause:

1. `Model Model2` body: `Vectors`(30) and `Points`(76) are BYTE-IDENTICAL; nodes/surfs/verts counts
   equal. Only node planes 29 & 30 differ, in W alone: native `-448.00006103515625` vs ued
   `-447.9998474121094` (normal exactly `(-1,0,0)` both sides).
2. `Polys Polys@Model Model2` (CSG soup) body: polys 14 & 33 (both normal `(-1,0,0)`, the x=448 face
   from Brush74's local -Y face) differ in `base` ONLY: native `(448.00006, 64.0001, 3.05e-5)` vs ued
   `(447.99985, 64.0001, 0.0)`. verts/normal/tu/tv identical.
3. `Brush74` body: sole prop diff is `Region` (PointRegion): native `(iLeaf=1, zone=1)` vs ued
   `(iLeaf=-1, zone=0)`.

## Root cause

Node plane W = `edpoly.base.dot(edpoly.normal)` (`build.rs:146`). With normal `(-1,0,0)`, W = -base.x, so
the residual is entirely in the poly BASE x: native 448.00006 vs ued 447.99985 (~2.1e-4, ~7 f32 ulp at
448).

native's soup/plane base for this face == world `Points[29]` = `(448.00006, 64.0001, 3.05e-5)` EXACTLY
(a deduplicated table point). ued's base `(447.99985, 64.0001, 0.0)` is NOT any point in the (identical)
Points table. So native's Model->Polys base and node-plane base are RECONSTRUCTED from `Surf.pBase`
(`bsp_node_to_fpoly`, `bspcsg.rs:1017` `base = points[s.p_base]`) during the repartition, i.e. snapped to
the deduped point, whereas UED22 keeps the RAW transformed FPoly base in `Model->Polys` and in the node
plane. `bspAddPoint`'s dedup threshold (~0.1) folds the raw base onto the nearby vertex-derived point 29,
losing the low mantissa bits. For all N<=7 (unrotated brushes) the raw base coincides with a table point
so the two agree; the 270deg yaw + fractional PrePivot is the first case where raw-base != any table point.

Residual 3 is DOWNSTREAM of 1/2: Brush74's origin (448,64,416) sits ON the x=448 plane, so `SetActorZone`'s
BSP descent (`materialize._model_point_region`) is decided by the sign of `pd = -1*448 - W`. The 2.1e-4 W
error flips the descent from the solid side (ued: iLeaf=-1) to air leaf 1 (native). All three residuals
resolve if the plane W matches.

## Evidence

`_scratch/cmp_nodes.py`, `_scratch/cmp_polys.py`, `_scratch/cmp_region.py`, `_scratch/diff_off.py`
(worktree `native-parity-incremental`). Fresh native_N8 rebuild reproduces. The editor DOES descend
Region for brushes (Brush777/420/418/324 non-solid values match native==ued) — the "brushes stay solid"
hypothesis is FALSE; only Brush74 flips, and only because of the plane-W FP error.

## Recommendation: FIX (not exclude)

A wrong node-plane W and a solid<->air Region flip are real geometry (BSP descent / collision / zoning),
not a GC/per-save artifact — NOT excludable. The fix is to make native carry the RAW transformed FPoly
base (as fed to CSG) into `Model->Polys` and the node plane, instead of re-deriving base from the
deduplicated `Surf.pBase` after repartition. This is an architectural change (raw bases are currently
lost when the repartition reconstructs polys from nodes via `bsp_node_to_fpoly`) and needs the exact
UED22 bspAddNode / bspBuildFPolys base-provenance confirmed before porting — not a self-authorizable
clamp/snap. Owner decision needed on approach.
