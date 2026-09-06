+++
priority = "p2"
kind = "debug"
summary = "NYC_Bar is byte-exact N=1..150 and bails at N=151: native gives world leaf 74 a permeating-light run UED22 leaves empty, so every later leaf's `iPermeating` shifts by 2 and `Model2.Lights` is 247 vs 245. Same shape as Island N=123."
depends-on = ["island-n-123-world-model2-leaf-permeating-light"]
+++

# NYC_Bar N=151 — world `Model2` leaf 74 gets a permeating-light run UED22 does not

Found 2026-09-06 pushing the ladder after the lightmap zero-vertex gate
(`dev/docs/board/done/nyc-bar-n-119-world-model2-lightmap-array-order/`) took NYC_Bar from N=118 to
N=150.

## The divergence

`parity_gate.py`: one failure, `BODY model model2: canonical bodies differ`.

`model_dump.py <native_N151.dx> <ref_N151.dx> Model2` per array:

    bbox/sphere/vectors/points/numsharedsides/lightbits/bounds/leafhulls/tail   SAME
    nodes / surfs                                                               permutation only
    leaves / lights / lightmap                                                  REAL

- `leaves[74]`: native `(iZone=2, iPermeating=63, iVolumetric=-1)`, UED22 `(2, -1, -1)`. All 33
  later differing leaves carry native's `iPermeating` exactly **+2** (76: 65 vs 63, 77: 67 vs 65, …).
- `lights` is **247 vs 245** — the 2 extra entries are leaf 74's run: one light index plus its `-1`
  terminator.
- `lightmap` diverges from record 78 in `iLightActors` only, which is the same +2: the permeating
  region is written into `Model.Lights` ahead of the per-surf runs.

Ignoring the permutation-only fields, **0 of 558 nodes and 0 of 298 surfs differ** — nothing upstream
of lighting moved.

## Same root cause as Island N=123

`island-n-123-world-model2-leaf-permeating-light` is the identical shape on another level (leaf 26,
`Lights` 1729 vs 1727). Fix that one and re-check this N; do not diagnose them separately.

## Repro

    ladder_run.py --dx dev/games/deusex/Maps/02_NYC_Bar.dx --from 151 --to 151 --keep-native
    model_dump.py <native_N151.dx> <ref_N151.dx> Model2
