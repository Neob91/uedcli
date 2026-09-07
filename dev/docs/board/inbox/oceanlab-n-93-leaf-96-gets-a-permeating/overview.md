+++
priority = "p2"
kind = "debug"
summary = "OceanLab is byte-exact N=1..92 and bails at N=93: world leaf 96's permeating-light run carries Light111, which UED22 leaves out -- one extra Model.Lights entry, every other array byte-exact."
+++

# OceanLab N=93 — leaf 96 gets a permeating `Light111` UED22 leaves out

Found 2026-09-07 walking the ladder forward after the gather zone-retire fix took OceanLab from
N=47 to N=92 (`oceanlab-n48-world-model2-lightbits-differ-on`).

`parity_gate.py`: one failure, `BODY model model2`.

    bbox sphere vectors points numsharedsides zones bounds leafhulls lightbits tail   SAME
    nodes surfs verts                                                                masked only
    leaves lightmap lights                                                           REAL

- **One leaf, one light.** Leaf 96's run is `[Light106, Light121, Light111, Light109]` in native and
  `[Light106, Light121, Light109]` in UED22. `Model.Lights` is 742 vs 741; the other 76 differing
  leaves are the pure `+1` `iPermeating` shift that follows, and the `LightMap` records differ only
  by the same shift in `iLightActors`/`DataOffset`.
- **The per-surf half is clean**: `lightbits` is byte-identical (101437 bytes both sides) and
  `harness/lightbits_diff.py` reports **0 differing records** — same run lengths, same bit planes.
  (`lightrun_diff.py` reports 13 differing runs here; that is an artefact of the `+1` array shift,
  not a real per-surf difference — trust `lightbits_diff.py` on this one.)

So this is the leaf permeating flood, not the raytrace: the same family as
`island-n-123-world-model2-leaf-permeating-light`, where native likewise gives one leaf a run UED22
leaves empty. Worth attacking together — two independent reproducers of one gap, and this one is a
single extra light rather than a whole extra run.

## Repro

    ladder_run.py --dx dev/games/deusex/Maps/14_OceanLab_Lab.dx --from 93 --to 93 --keep-native
    model_dump.py <native_N93.dx> <ref_N93.dx> Model2
