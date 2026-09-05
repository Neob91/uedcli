+++
priority = "p1"
kind = "debug"
summary = "FIXED: native concatenated LightBits/Lights in BSP-walk order; UED22 uses surf-index order — decoupled the two passes in light.rs bake"
+++

# native lightmap concat order is BSP-walk, not surf-index — FIXED

`light.rs` `bake` reused the BSP-walk order (`lightmap_emit_order`) for BOTH the `LightMap` record
array AND the `LightBits`/`Lights` data concat, so `DataOffset`/`iLightActors` came out permuted vs
UED22 once two lit/empty surfs appeared in walk order opposite to surf-index order.

Fix: split the concat into two passes — `finalize_offsets` (pass 1) lays the data + assigns offsets
in **surf-index order**; `push_record` (pass 2) pushes the record array in **BSP-walk order** (+ the
defensive surf-order sweep). All three record encodings (populated / empty-run / dark) unchanged.

Disasm confirmed the rule: UED22's raytrace/concat caller loop (`Editor 0x100a6153`) is an ascending
`for i<Model.Surfs.Num()` walk, passing `iSurf=i` to the per-surf raytrace `0x100a5010`.

Verified with `parity_gate.py` on all three ladder levels N=1..16 (cached refs + rebuilt native):
02_NYC_Bar N=1..16 all YES; 03_NYC_UNATCOHQ N=1..16 all YES (N11..16 flipped from FAIL); WanChai
N=1..15 all YES (N10..15 flipped from FAIL). No previously-green cell regressed.

WanChai N=16 still FAILs, but on a separate residual (two `Polys.ItemName` divergences, not
lightmaps) — filed as `wanchai-n16-poly-itemname-divergence-blocks`.
