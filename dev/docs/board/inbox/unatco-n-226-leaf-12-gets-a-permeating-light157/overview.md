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

## Its two siblings are fixed; this one survived that fix (2026-09-07)

`oceanlab-n-93-leaf-96-gets-a-permeating` and `island-n-123-world-model2-leaf-permeating-light` were
the same shape and are both closed: the beam clip took its crossing vertex from
`alpha = dp/(dp-ds)` where `SplitWithPlaneFast` calls `FLinePlaneIntersection`, and a crossing
landing exactly on a grid coordinate collapsed the next hop's clip edge to zero length
(`wanchai-n45-leaf-20-permeating-light-over-included`, spike
`dev/docs/spikes/2026-09-07-gather-box-verdict/`). **Re-measured after that fix, this one is
unchanged** — leaf 12 still carries `Light157` (`Model.Lights` 2953 vs 2952, per-surf runs 0
differing), so it is a second, independent case.

The method that cracked WanChai applies directly: capture the editor's own flood with
`2026-09-07-gather-box-verdict/harness/actor_visibility_probe.py` and diff it with
`perm_flood_diff.py` to find the one crossing native takes that the editor does not — WanChai's
capture had 10 of 11 lights already identical, so the diff is narrow. UNATCO N=226 is bigger
(147 leaves) but the probe cost scales with the flood, not the level.

## Repro

    ladder_run.py --dx dev/games/deusex/Maps/03_NYC_UNATCOHQ.dx --from 226 --to 226 --keep-native
    model_dump.py <native_N226.dx> <ref_N226.dx> Model2
