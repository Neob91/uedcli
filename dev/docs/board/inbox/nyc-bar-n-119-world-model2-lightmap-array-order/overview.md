+++
priority = "p2"
kind = "debug"
summary = "NYC_Bar is byte-exact N=1..118 and bails at N=119 on `BODY model model2`: the world Model's `LightMap` array diverges from index 144 (an insertion/reorder of two entries), which shifts every downstream surf's iLightMap by 2. Points, vectors, bounds, leafhulls, leaves and LightBits are all byte-identical."
+++

# NYC_Bar N=119 — world `Model2` `LightMap` array order

Found 2026-09-06 pushing the ladder after the `PointRegion` f32 fix took NYC_Bar from N=112 to N=118
(`dev/docs/spikes/2026-09-06-pointregion-planedot-f32/`).

## The divergence

`parity_gate.py`: one failure, `BODY model model2: canonical bodies differ`. `model_dump.py` on the
pair:

| array | verdict |
|-----------|---------|
| bbox, sphere, vectors (55), points (885), lightbits, bounds (247), leafhulls (2595), leaves (147), lights | SAME |
| nodes (538) | differ only in `node_flags` bits `0x08`/`0x10` — gate-masked |
| lightmap (276) | **DIFF from index 144** |
| surfs (278), verts, zones | downstream index shifts |

`LightMap[144..]` is shifted: native's `[145]` is UED22's `[144]`, native's `[146]` is UED22's
`[145]`, and UED22's `[146]` is an entry native does not have there (`Pan` `(-1761.125, -397.125)`
vs native's `(-296.125, ...)`). The surf tokens the gate flags all differ in ONE compact index by
exactly 2 — the `iLightMap` shift the reorder causes.

So this is a lightmap ALLOCATION/order divergence, not a lighting-run content one (`LightBits` is
byte-identical and every geometry array matches).

## Repro

    ladder_run.py --dx dev/games/deusex/Maps/02_NYC_Bar.dx --from 119 --to 119 --keep-native
    model_dump.py <native_N119.dx> <ref_N119.dx> Model2
    body_token_diff.py <native_N119.dx> <ref_N119.dx> model2
