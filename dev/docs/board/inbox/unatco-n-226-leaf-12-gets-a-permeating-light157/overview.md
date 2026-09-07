+++
priority = "p2"
kind = "debug"
summary = "UNATCO is byte-exact N=1..225 and bails at N=226: world leaf 12's permeating-light run carries Light157, which UED22 leaves out -- one extra Model.Lights entry, the per-surf half byte-identical."
+++

# UNATCO N=226 — leaf 12 gets a permeating `Light157` UED22 leaves out

Found 2026-09-07 walking the ladder forward after the gather zone-retire fix took UNATCO from N=162
to N=225 (`oceanlab-n48-world-model2-lightbits-differ-on`).

`parity_gate.py`: one failure, `BODY model model2`.

    bbox sphere vectors points numsharedsides zones bounds leafhulls lightbits tail   SAME
    nodes surfs verts                                                                masked only
    leaves lightmap lights                                                           REAL

- Leaf 12's run is `[Light318, Light157, Light156]` in native and `[Light318, Light156]` in UED22.
  `Model.Lights` is 2953 vs 2952; every later leaf differs only by the resulting `+1` `iPermeating`
  shift, and the `LightMap` records only by the same shift.
- The per-surf half is clean: `lightbits` is byte-identical (211650 bytes) and
  `harness/lightbits_diff.py` reports **0 differing records**.

Same shape as `oceanlab-n-93-leaf-96-gets-a-permeating` (found in the same pass) and
`island-n-123-world-model2-leaf-permeating-light`: native's permeating flood reaches a leaf UED22's
does not. Three independent reproducers of one gap — attack them together.

## Repro

    ladder_run.py --dx dev/games/deusex/Maps/03_NYC_UNATCOHQ.dx --from 226 --to 226 --keep-native
    model_dump.py <native_N226.dx> <ref_N226.dx> Model2
