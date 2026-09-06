+++
priority = "p2"
kind = "debug"
summary = "Island is byte-exact N=1..122 and bails at N=123: native gives world leaf 26 a permeating-light run UED22 leaves empty, so every later leaf's `iPermeating` shifts by 2 and `Model2.Lights` is 1729 vs 1727."
+++

# Island N=123 — world `Model2` leaf 26 gets a permeating-light run UED22 does not

Found 2026-09-06 pushing the ladder after the zone-actor ancestry fix
(`dev/docs/board/done/island-n-93-zone-actor-missed-resolve-zone/`) took Island from N=92 to N=122.

## The divergence

`parity_gate.py`: one failure, `BODY model model2: canonical bodies differ`.

`model_dump.py <native_N123.dx> <ref_N123.dx> Model2` per array:

    bbox/sphere/vectors/points/numsharedsides/lightbits/bounds/leafhulls/tail   SAME
    nodes / surfs / zones                                                       permutation only
    leaves / lights / lightmap                                                  REAL

- `leaves[26]`: native `(iZone=1, iPermeating=107, iVolumetric=-1)`, UED22
  `(1, -1, -1)`. Every leaf after it carries native's `iPermeating` exactly **+2**
  (27: 109 vs 107, 28: 115 vs 113, …).
- `lights` (the run pool the leaf indexes) is **1729 vs 1727** — the 2 extra entries are leaf 26's
  run: one light index plus its `-1` terminator.

So native decides one light PERMEATES leaf 26 and the editor decides it does not. Nothing upstream
of lighting differs — the tree, points, vectors, hulls and bounds are all byte-identical.

The `nodes`/`surfs`/`zones` diffs are export-index permutation and the gate-excluded
`NF_PolyOccluded`/`NF_BoxOccluded` bits; they are not the cause.

## Next step

Identify which light native runs into leaf 26 and where the editor's per-leaf permeating pass
(`shadowIlluminateBsp`'s leaf walk) rejects it. Same residual FAMILY as the other levels' open
light-run items (`unatco-n-116-world-model2-light-runs-differ-on`,
`wanchai-n45-spotlight22-light-runs-differ-on-4`) but a different array: those differ on the
per-lightmap runs, this one on a LEAF's permeating run.

## Repro

    ladder_run.py --dx dev/games/deusex/Maps/01_NYC_UNATCOIsland.dx --from 123 --to 123 --keep-native
    model_dump.py <native_N123.dx> <ref_N123.dx> Model2
