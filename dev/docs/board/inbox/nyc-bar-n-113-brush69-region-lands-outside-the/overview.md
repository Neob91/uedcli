+++
priority = "p1"
kind = "debug"
summary = "NYC_Bar bails at N=113 on ONE token: Brush69's Region descends out of the BSP in native (iLeaf -1, zone 0) where UED22 lands in leaf 55, zone 1. The world Model itself is byte-identical."
+++

# NYC_Bar N=113 — `Brush69`'s `Region` descends out of the world

`02_NYC_Bar` gates byte-exact N=1..112 and fails at N=113 with a single gate failure and a single
differing token:

```
BODY brush brush69
  [5] native = ('region', 0, 'PointRegion', ('region', 'levelinfo levelinfo0', -1, 0))
      ued    = ('region', 0, 'PointRegion', ('region', 'zoneinfo zoneinfo5', 55, 1))
```

Everything else matches — the world `Model2`, every other actor's `Region`, the lighting. So the
BSP and the zoning are right; only this one point descent disagrees. Native's
`materialize._model_point_zone` walk falls off the tree (`iLeaf = -1`, zone 0, so the `Region.Zone`
falls back to the LevelInfo per `UModel::PointRegion`), where the editor reaches leaf 55.

Actor 113 is `Brush69`, `Engine.Brush` `CSG_Add`, `Location = (-384, -440, 0)`,
`PrePivot = (256, 40, -8)`. The `Region` is taken at the actor's `Location`, which for a brush is
its pivot — not necessarily inside its own solid — so the likely candidates are a point exactly on a
node plane (a tie the two descents break differently) or a descent that stops at an empty child the
editor treats as a leaf.

Next step: dump native's descent for that point against the built tree and compare it node by node
with `UModel::PointRegion` (`Engine.dll 0x101aee60`) — the same shape as the N=59 zone-actor work.

Reproduce: `ladder_run.py --dx dev/games/deusex/Maps/02_NYC_Bar.dx --from 113 --to 113`, then
`token_diff.py <native> <ref> "brush brush69"`.
