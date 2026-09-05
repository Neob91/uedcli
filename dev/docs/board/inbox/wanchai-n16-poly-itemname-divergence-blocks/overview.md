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
