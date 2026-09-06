+++
priority = "p2"
kind = "debug"
summary = "Island is byte-exact N=1..92 and bails at N=93 on ONE token: `Brush1099`'s Region names the LevelInfo where UED22 names `WaterZone1`. `resolve_zone_actors` picks zone actors by class-NAME suffix (`endswith(\"ZoneInfo\")`), so `DeusEx.WaterZone` — a real ZoneInfo subclass — is skipped."
+++

# Island N=93 — `resolve_zone_actors` matches a name suffix, not `ZoneInfo` ancestry

Found 2026-09-06 pushing the ladder after the `PointRegion` f32 fix took Island from N=9 past N=92
(`dev/docs/spikes/2026-09-06-pointregion-planedot-f32/`).

## The divergence

One gate failure, one token:

```
BODY brush brush1099
  token[5] region: nat=(0, 'PointRegion', ('region', 'levelinfo levelinfo0', 34, 1))
                   ued=(0, 'PointRegion', ('region', 'waterzone waterzone1', 34, 1))
```

Same leaf (34) and same zone number (1) — the descent is right. Only the ZONE ACTOR is wrong.

## Cause

`materialize.resolve_zone_actors` (`uedcli/native/materialize.py`) selects candidates with

```python
if short == "LevelInfo" or not short.endswith("ZoneInfo"):
    continue
```

Island's actor 93 neighbourhood contains `WaterZone1`, `Class=DeusEx.WaterZone` — a subclass of
`Engine.ZoneInfo` whose NAME does not end in `ZoneInfo`. It is skipped, zone 1 gets no zone actor,
and every actor in that zone falls back to the LevelInfo. `UModel::PointRegion`
(`Engine.dll 0x101aee60`) returns `Zones[ZoneNumber].ZoneActor` and only falls back to the passed-in
default when that slot is NULL, so the editor names `WaterZone1`.

## Fix shape

Decide by ancestry, not spelling — the `movers._mover_by_ancestry` pattern: `ClassIndex.ancestry`
(`uedcli/classindex.py`) already resolves the chain, and `apply._materialize_native` has the
`class_index` in hand at the `resolve_zone_actors(level, world_model)` call site. Keep the
`LevelInfo` exclusion explicitly — `Engine.LevelInfo` IS a `ZoneInfo` subclass, and the editor never
spatially zones it.

Not done in the pass that found it: `resolve_zone_actors` feeds every level's `Region` props and
`Model.Zones[].ZoneActor`, so the change needs a full five-level ladder re-verification, which did
not fit that pass.

## Repro

    ladder_run.py --dx dev/games/deusex/Maps/01_NYC_UNATCOIsland.dx --from 93 --to 93 --keep-native
    body_token_diff.py <native_N93.dx> <ref_N93.dx> brush1099
