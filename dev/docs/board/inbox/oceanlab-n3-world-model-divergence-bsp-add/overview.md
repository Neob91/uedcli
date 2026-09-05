+++
priority = "p2"
kind = "bug"
summary = "OceanLab N3 fails parity on world Model2 + its Polys: bsp_add_vector pools 2 texture-U axes the editor keeps distinct because its exact=false tol is 0.001, not the disasm-confirmed THRESH_VECTORS_ARE_NEAR=0.0004. One-const fix, but a global dedup change needing a corpus A/B + owner sign-off."
+++

# OceanLab N3 world-Model divergence: `bsp_add_vector` texture-axis threshold 0.001 vs editor 0.0004

`14_oceanlab_lab` N=3 is the sole remaining gate residual (its LevelInfo issue is fixed). Diagnosis
only — no production code changed.

## Actor #3 = the trigger

Trunk order N=3: `LevelInfo0`, `Brush1453`, `Brush779`. N=2 (LevelInfo + `Brush1453`, a plain 6-face
box subtract) passes. `Brush779` is actor #3: a **258-triangle tessellated (curved) `CSG_Subtract`**
with `Rotation=(Yaw=16384)` (90 deg) and fractional `PrePivot=(-1727.999,2624,-2160)`, ~10000x10000x4320
bbox — a rotated dome/bowl. Its many near-parallel facets are what expose the bug.

## Symptom (parity_gate.py, cached `_scratch/actor-parity/14_oceanlab_lab/{native,ref}_N3.dx`)

Gate FAILS with exactly 2 body residuals: world `Model2` body and `Polys@Model Model2` (the CSG soup).
Decoded (`uedcli.native.umodel.parse_model_body`):

- `Nodes`=271, `Surfs`=135, `Leaves`=97, `Points`=386 all MATCH, count AND content.
- **Live** node vertex rings are identical: sum `NumVertices`=1040 both sides, identical per-node
  histogram. The `Verts`-pool delta (native 3074 vs ued 2989, +85) is entirely **orphan** FVerts and
  is absorbed by the gate's orphan-iVertex liveness exclusion — NOT flagged, NOT the blocker (known
  class: `verts-residual-on-structure-exact-levels`).
- `Vectors`: native 364 vs ued 366 (native 2 FEWER). Vectors are byte-identical 0..246; ued inserts
  one extra at idx247 and one at idx355; native = ued's table with exactly those two deleted.

## Root cause — a wrong `bsp_add_vector` texture-axis dedup threshold (classification (c))

Every vector is surf-referenced (no orphan vectors). The two "missing" vectors are **TextureU axes**,
not normals. The editor rotates each source poly's OWN authored TextureU by the brush's 90-deg yaw and
keeps near-parallel ones distinct; native pools two of them:

| surf | src `Brush779` poly | authored TU (local) | world TU = Rot90(local) | ued vec | native vec |
|------|--------------------|--------------------|------------------------|---------|-----------|
| 36 | poly 30  | (0.505185, 0.863011, 0) | (-0.863011, 0.505185, 0) | vec[101] | vec[101] |
| 94 | poly 161 | (0.504697, 0.863297, 0) | (-0.863297, 0.504697, 0) | vec[247] | **vec[101]** |
| 91 | poly 157 | (0.938427,-0.345478, 0) | (0.345478, 0.938427, 0) | vec[238] | vec[238] |
| 131| poly 228 | (0.938096,-0.346374, 0) | (0.346374, 0.938096, 0) | vec[355] | **vec[238]** |

native's TU VALUES are bit-correct (kept indices are byte-identical to ued). The only error is the
dedup: surf 94's TU vs surf 36's TU differ by (dx=2.86e-4, dy=4.88e-4), Euclidean 5.66e-4; surf 131 vs
91 by (dx=8.96e-4, dy=3.31e-4), Euclidean 9.55e-4.

`bsp_add_vector` (`uedcli-native/src/bspcsg.rs:142-147`) uses `tol = 0.001` for `exact=false` (texture
axes) with a Euclidean `v.sub(p).size()` test. Both pairs' Euclidean distance (5.66e-4, 9.55e-4) is
`< 0.001`, so native pools them. The disassembled editor value is
**`THRESH_VECTORS_ARE_NEAR = 0.0004`** (spec `unrealed-geometry-build-map-rebuild-bsp-rebuild/spec.md`
§3.10, DISASM `Editor.dll 0x35530`; also `dev/docs/unrealed/leveldesign/kb/csg-bsp.md`). At 0.0004 both
pairs exceed threshold (5.66e-4, 9.55e-4 > 4e-4) → kept distinct, matching the editor. The metric is
right (spec: `bspAddVector` is "same shape" as `bspAddPoint` → real sqrt distance); only the constant
is wrong. `bspcsg.rs:2098` already uses `4.0e-4` for a texture_u compare in `try_to_merge`,
corroborating 0.001 as an oversight (line 92 comment: "copied from build.rs ... to keep it untouched").

Both residuals are one bug: `bsp_node_to_fpoly` (`bspcsg.rs:1027-28`) rebuilds each soup FPoly's
TextureU from `model.vectors[surf.v_texture_u]`, so the wrong pooling corrupts BOTH the `Vectors`
array (Model body) and the reconstructed `Model2.Polys` TU (Polys body). Fixing the threshold makes
surf 94/131 keep vec[247]/vec[355], so the soup polys reconstruct their own TU → both bodies match.

## Known class?

Same FAMILY as the rotated-brush FP work (`native-n8-unatco-rotated-brush-base-fp-diverges` done, and
the `points-residual` value-drift thread), but a DISTINCT axis: N8 was the poly BASE/position
re-derived from a deduped point; this is a texture-AXIS dedup threshold. The 0.0004 constant is already
documented; the specific `bsp_add_vector` 0.001 error is newly pinned to a failing level here.

## Fix plan + size

Change: `bspcsg.rs` `bsp_add_vector` `exact=false` tol `0.001` -> named const `THRESH_VECTORS_ARE_NEAR
= 4.0e-4`. Code change is ~1 line + a const. Verified sufficient for OceanLab N3 by the arithmetic
above (no rebuild done — diagnosis only).

This is a GLOBAL dedup-threshold change (every level's `Vectors` pool), so per the `ring_point_tol`
precedent it is NOT self-authorizable: it needs a corpus A/B (does 0.0004 hold/improve every
currently-exact ladder + OG level, regress any?) and the owner's yes before shipping as default; gate
it behind an env flag for the A/B first, like `UEDCLI_BSPCSG_POINT_NEAREST`. Matching the disasm value
should only improve fidelity; residual risk is interaction with native's default FIRST-not-NEAREST scan
(`point_nearest_enabled` off) and proposal order flipping a borderline pool elsewhere.

Size: code trivial; work is the corpus A/B sweep + one subagent review + owner decision, plus a
regression test (a minimal 2-face rotated-brush unit test pinning the 4e-4 keep/merge boundary, and/or
OceanLab N3 in the ladder). Estimate S-M (~half a day incl. the sweep). Ladder needs N=3 byte-exact
before advancing.

## Evidence

Decode via `uedcli.native.umodel.parse_model_body` on the cached
`_scratch/actor-parity/14_oceanlab_lab/{native,ref}_N3.dx`; source TU from the trunk brush (Yaw=16384
=> world TU = (-local.y, local.x, 0)). Gate: `parity_gate.py` reports the two body residuals.
