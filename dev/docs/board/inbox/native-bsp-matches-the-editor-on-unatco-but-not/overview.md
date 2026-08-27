+++
priority = "p1"
kind = "debug"
summary = "Native BSP is node-exact against the editor's paste-built golden on 01_NYC_UNATCOHQ (734 brushes) but not on 09_HONGKONG_WANCHAI_MARKET (1304 brushes): nodes 11381 vs 11648, leaves 3240 vs 3371, points 16522 vs 16791, vectors 481 vs 487, surfs 5283 vs 5284. Same pipeline both sides."
+++

# Native BSP matches the editor on UNATCO but not on `WANCHAI_MARKET`

The BSP parity work reached exact node/surf/leaf/zone/vector agreement with the editor's
`MAP NEW` + `EDIT PASTE` + `MAP REBUILD` golden on `01_NYC_UNATCOHQ`. Running the SAME comparison on a
larger original level shows it does not generalise.

`09_HONGKONG_WANCHAI_MARKET`, world-only (1304 `Engine.Brush` actors of 2288 trunk actors), native
`build_geometry_bspcsg` vs `build_ued_lit_golden.py` (bare `MAP REBUILD`, paste-added):

| | native | editor | delta |
|---|---:|---:|---:|
| surfs | 5283 | 5284 | +1 |
| nodes | 11381 | 11648 | +267 |
| leaves | 3240 | 3371 | +131 |
| points | 16522 | 16791 | +269 |
| vectors | 481 | 487 | +6 |
| lit records | 4531 | 4530 | −1 |
| surfs `iLightMap = -1` | 752 | 754 | +2 |

For contrast, on UNATCO every one of those columns is equal (3616 / 6314 / 762 / 10758-vs-10752 /
599).

The `vectors` delta is the interesting one: 6 texture/normal vectors the editor's build has and
native's does not, on a level whose surf count is otherwise within 1. `nodes` and `leaves` are ~2.3%
and ~4% low, which is the shape of a missing fragmentation or repartition step rather than a wholly
different partition.

Reproduce (each side ~4 min for the editor, ~40 s native):

    dev/docs/spikes/2026-08-27-native-light-apply-parity/harness/build_ued_lit_golden.py \
        --trunk <trunk> --out golden.dx --overwrite
    UEDCLI_NATIVE_MATERIALIZE=1 bin/uedcli --project <proj> level materialize \
        --tree level/<lvl> --out native.dx --overwrite --no-verify
    dev/docs/spikes/2026-08-27-native-light-apply-parity/harness/lightparity.py native.dx golden.dx

The trunk used is `dev/games/trunks/tmp-wanchai-market` (2288 actors, every class fully qualified).

## Why it is filed from the lighting work

The lighting bake's `LightMap` array is one record per lit surface in BSP tree-walk order, so a
per-record byte comparison is only meaningful when the two trees agree. It does on UNATCO (2522 of
3345 records byte-identical) and cannot on this level. The bake was validated here by matching
surfaces by GEOMETRY instead (`harness/light_geomatch.py`: plane + nearest centroid), which shows the
bake RULES generalise — 95.5% of the bit-comparable planes are byte-identical and 98.96% of the
shadow bits agree — but byte identity of the lighting sections on this level is gated on the BSP gap
above, not on anything in `light.rs`.
