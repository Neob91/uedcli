+++
priority = "p2"
kind = "debug"
summary = "After the N=2 point-order/soup/Region fixes, WanChai N=2 has exactly 2 residuals, both deep CSG-core: a 1-ULP covariant texture-V vector and orphan-vert stale iVertex (9 vs 10). Neither is editor-nondeterministic; neither is a safe surgical fix."
+++

# WanChai N=2: two CSG-core residuals

State after `ba2703f` (point-order default + CSG soup + Region recompute). UNATCO N=2 and NYC_Bar
N=2 PASS; WanChai N=2 = 2 residuals (the Sky/sky texture-name case is separately gate-excluded by
the main session and no longer shows).

Both residuals are on the world `Model2` (one also on its `Polys`/soup). All other Model2 fields
(Points byte-identical, all surfs' pBase/vNormal/vTU/iBrushPoly/pan/flags, node tree) match.

## Residual A — texture-V vector off by 1 ULP (`vec[8]`, and the soup's tv)

Ground truth (ref `06_HongKong_WanChai_Market` N=2, `Model2` Vectors[8]):
- ued  = `-0.008928571827709675` (bits `bc124925`) = exactly `f32(-1.0/112.0)`.
- native = `-0.0089285708963871` (bits `bc124924`) = 1 ULP smaller.

Cause: the face's authored `TextureV=(0,0,-1)` under the subtract brush's `PostScale Z=112`. The
editor forms `VectorXform = (L⁻¹)ᵀ` and transforms the axis once → a direct `-1.0/112.0`. Native
(`brush_marshal._axis`) pre-multiplies the axis by `tex_cov = (LᵀL)⁻¹` (Python f32) and the Rust
`FPoly::transform` then multiplies by the forward `L` (f32) — the two-step `(LᵀL)⁻¹` then `·L` in
f32 rounds 1 ULP below the editor's single `(L⁻¹)ᵀ` division. The face NORMAL already uses the
editor-faithful `NT`=`(L⁻¹)ᵀ` (`vec_xform`); the texture axes do not.

Fix direction (NOT done — corpus-wide risk): route the texture axes through the same editor-faithful
`(L⁻¹)ᵀ` (one inverse, transposed) instead of the `(LᵀL)⁻¹`+forward-`L` pre-cancel. This changes
texture-vector float bits for EVERY scaled brush on EVERY level; needs editor goldens for scaled-brush
textures across the corpus to verify no regression. UNATCO N=2's brush is unscaled, so unaffected.

## Residual B — orphan-vert stale `iVertex` 9 vs 10

Model2 verts[28], [35], [41] are ORPHANS (not in any live node ring; live verts are 0..23). Their
`iVertex` is the editor's "leave the dropped point's stale index untouched" bookkeeping
(`reorder_points_canonical`/orphan rule). ued leaves `10` (one past the 10-entry Points pool);
native leaves `9`. Deterministic in principle (the index the point held before the pre-repartition
Points GC dropped it), but reproducing it needs exact point-GC + vert-pool insertion-history parity
with the editor. Related: `native-point-vert-pool-byte-parity-port`,
`unatco-verts-points-residual-after-the-zone`.

## Why parked, not fixed

Both are genuine (not editor-nondeterministic, so not exclusion candidates) but neither is a surgical
change: A rewrites a shared float path used by every scaled brush; B needs a vert-pool-history port.
Each warrants its own focused CSG-core spike with editor goldens, not a blind edit under the N=2
push. Reproduce: `_scratch/dump_model.py` + `_scratch/dump_soup.py` (harness scratch) vs the cached
`_scratch/actor-parity/06_hongkong_wanchai_market/{native_N2,ref_N2}.dx`.
