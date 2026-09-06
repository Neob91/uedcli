+++
priority = "p2"
kind = "debug"
summary = "Island is byte-exact N=1..9 and FAILS at N=10 on ONE token: `Brush1359`'s cached `Region` names leaf 13 in native and 18 in UED22 (same Zone actor, same bZoneNormal). The world `Model` matches."
+++

# Island N=10 — `Brush1359`'s `Region` iLeaf

Found 2026-09-06 extending the ladder after `island-n6-vector-pool-order` closed N=6. N=10 adds the
tenth trunk actor; N=9 is byte-exact.

## The divergence

The only gate residual (`parity_gate.py`, full run):

    BODY brush brush1359: actor body differs
      token[5] region: nat=(0, 'PointRegion', ('region', 'levelinfo levelinfo0', 13, 1))
                       ued=(0, 'PointRegion', ('region', 'levelinfo levelinfo0', 18, 1))

`FPointRegion` = (Zone actor, iLeaf, ZoneNumber/bZoneNormal). The zone actor (`LevelInfo0`) and the
trailing byte agree; only **iLeaf** differs, 13 vs 18. Every world `Model`/`Model2` array is
byte-identical at N=10, so this is the point-location descent (or the leaf NUMBERING it lands in),
not the geometry.

Related, already fixed once for another level: `nyc-bar-n-59-brush-region-zone-and-ued22` fixed the
Region ZONE ACTOR and the mover base pose; the leaf index was not in play there.

## Repro

    ladder_run.py --dx <…>/Maps/01_NYC_UNATCOIsland.dx --from 10 --to 10 --keep-native
    body_token_diff.py <…>/native_N10.dx <…>/ref_N10.dx brush1359
