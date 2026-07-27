+++
priority = "p3"
kind = "chore"
summary = "Fix `bspspike/umodel_parser.py` `FBspSurf` mislabel:"
+++

# Fix `bspspike/umodel_parser.py` `FBspSurf` mislabel:

field at mem `+0x18` is `iLightMap`
(parser calls it `i_actor`); `+0x24` is the brush `Actor`. Verified via `GetLightMapIndex`
(`Engine 0x1127c0`). Fold in at native-materialize N-4. p3.
