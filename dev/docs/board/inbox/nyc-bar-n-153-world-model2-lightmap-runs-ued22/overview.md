+++
priority = "p2"
kind = "debug"
summary = "NYC_Bar is byte-exact N=1..152 and bails at N=153: three world `LightMap` records get an `iLightActors` run UED22 leaves at -1, so `Lights` is 484 vs 478 and `LightBits` 6003 vs 5891."
+++

# NYC_Bar N=153 — three world `LightMap` records get a light run UED22 leaves empty

Found 2026-09-06 pushing the ladder after the permeating-beam-plane fix
(`nyc-bar-n-151-world-model2-leaf-permeating-light`) took NYC_Bar from N=150 to N=152.

## The divergence

`parity_gate.py`: one failure, `BODY model model2: canonical bodies differ`.

    bbox/sphere/vectors/points/bounds/leafhulls/leaves/numsharedsides/tail   SAME
    nodes / surfs / zones                                                    permutation only
    lightmap / lights / lightbits                                            REAL

- The per-leaf permeating region is CLEAN: 0 of 155 leaves differ in run content or order, so this
  is `Model.Lights` region 2 (the per-surf raytraced shadow runs), not the portal flood.
- `lightmap` records **4, 8 and 12** carry `iLightActors` `0x149`/`0x14b`/`0x13f` in native and
  `-1` in UED22, with a real `DataOffset` where UED22 has 0. Everything else in those records
  (`Pan`, `UBits`/`VBits`, `iTexture`) matches.
- `lights` is 484 vs 478 — the six extra entries are those three runs (one light + terminator each).
  `lightbits` is 6003 vs 5891 — 112 extra bytes, the three extra records' bit planes.
- Records 46/49/50/62 differ only in `DataOffset` and `iLightActors` INDEX, which is the same shift.

So native decides one light illuminates three surfaces UED22 leaves dark. Same FAMILY as
`unatco-n-116-world-model2-light-runs-differ-on` and
`wanchai-n45-spotlight22-light-runs-differ-on-4`, but here native is a strict superset rather than
trading decisions.

## NOT the OceanLab N=48 / UNATCO N=163 cause (measured 2026-09-07)

Those two were one bug — the gather never retired a zone whose span buffer had emptied, so it marked
`NF_BoxOccluded` on nodes UED22 never box-tests
(`oceanlab-n48-world-model2-lightbits-differ-on`). Rebuilt and gated here before and after that fix:
**N=153 is unchanged, N=152 still passes.**

Also recorded: N=153 fails on TWO bodies, not one — `model model2` and `model
model_deusexmover9`. The mover body was already failing on master before the box-occlusion work
(checked by rebuilding N=153 against `HEAD`), so it belongs to this item, not to that change.

## Repro

    ladder_run.py --dx dev/games/deusex/Maps/02_NYC_Bar.dx --from 153 --to 153 --keep-native
    model_dump.py <native_N153.dx> <ref_N153.dx> Model2
