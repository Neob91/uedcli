+++
priority = "p1"
kind = "debug"
summary = "WanChai N16 world Model + brush1643 Polys carry wrong ItemName (native 'outside' vs UED 'rise'/'step') — sole residual after the lightmap concat-order fix"
+++

# WanChai N16 poly ItemName divergence blocks parity

After the lightmap data-concat-order fix (board `native-lightmap-concat-order-is-bsp-walk-not`),
`06_HongKong_WanChai_Market` is byte-exact at N=8..15 but N=16 still fails the gate with 2 diffs,
both `Polys` bodies — **not lightmaps**:

- `polys@model model2` (world Model): the poly `ItemName` FName differs. Native stamps `'outside'`
  where UED22 has `'rise'` / `'step'` (first at flattened token `[2][431]`, repeating on many polys).
- `polys@model model_brush1643` (a brush): the poly's name/flags word differs — native FName-index
  bytes `81 81 ...` vs UED `22 81 ...`, i.e. a different `ItemName` referenced.

Everything else at N=16 matches; the lightmap arrays (`LightMap`/`LightBits`/`Lights`,
DataOffset/iLightActors) are byte-identical native==UED after the concat fix.

## Independent of the lightmap fix

The residual is `Polys.ItemName`, set by CSG/brush poly propagation, not by `light.rs`. It is
pre-existing: before the concat fix N=16 failed on both lightmaps AND these polys; the fix cleared
the lightmap half. The 16th actor (introducing `brush1643`) is where a poly ItemName first diverges.

Native assigns the group/item name `outside` to world/brush polys that UED22 names `rise`/`step` —
a CSG ItemName inheritance/assignment difference. Not yet diagnosed to a mechanism.

## Repro

    _scratch/actor-parity/06_hongkong_wanchai_market/{native,ref}_N16.dx
    parity_gate.gate(native_N16, ref_N16)  # -> (False, [2 polys BODY diffs])

## Resolved

Two independent Brush1643 causes, both fixed in `uedcli/native/unbuilt.py` (Python-only):

- `Model2` (world soup): native hardcoded every world-soup poly `Item=OUTSIDE`. The editor
  propagates each surviving world fragment's `ItemName` from its SOURCE brush poly. `_world_soup_fpolys`
  now reads `csg_brushes[i_actor].polys[i_brush_poly].item` (same provenance as the texture ref) and
  defaults to `OUTSIDE` only when the source is unresolvable/None. Brush faces are usually authored
  `Item=OUTSIDE`, so cube brushes are unchanged; Brush1643's `Rise`/`Step`/`Side`/`Base` now carry.
- `model_brush1643` (private model): the diff was `iLink`, not ItemName. The editor DOES run
  bspValidateBrush's LINK phase on an imported content brush's own model — the prior "no link phase"
  claim was an under-determined inference (every N<16 content brush is a 6-face cube = all singletons
  = all -1, which can't distinguish it from "link phase, no groups"). `_fpolys` now calls new
  `_assign_content_ilinks`: coplanar same-facing/-texture/-flags faces fuse to the group master's
  index, singletons keep -1. Brush1643's two coplanar `Side` walls are the first real groups.

Both verified: all 3 ladder levels (UNATCO / WanChai_Market / NYC_Bar) PASS the gate at N=1..16;
cargo goldens 111/0; regression tests in `test_native_roundtrip.py`
(`test_content_brush_shape_polys_link_coplanar_faces`,
`test_content_brush_ilink_link_phase_stores_editor_convention`).
