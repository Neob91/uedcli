+++
priority = "p2"
kind = "debug"
summary = "DONE — `resolve_zone_actors` picked zone actors by class-NAME suffix, skipping `DeusEx.WaterZone`. Now decided by `Engine.ZoneInfo` ancestry (`ULevel::SetActorZone`'s own `IsA(AZoneInfo) && !IsA(ALevelInfo)`). Island byte-exact N=1..122, no mask."
+++

# Island N=93 — `resolve_zone_actors` matched a name suffix, not `ZoneInfo` ancestry

Fixed 2026-09-06. `Brush1099`'s `Region` named the LevelInfo where UED22 names `WaterZone1` (same
leaf 34, same zone 1 — the descent was right, only the zone-actor lookup was wrong).

`materialize.resolve_zone_actors` selected candidates with `short.endswith("ZoneInfo")`, so
`DeusEx.WaterZone` — a real `Engine.ZoneInfo` subclass whose name does not end in "ZoneInfo" — was
skipped, zone 1 got no zone actor, and every actor in it fell back to the LevelInfo.
`UModel::PointRegion` (`Engine.dll 0x101aee60`) returns `Zones[ZoneNumber].ZoneActor` and falls back
to the passed-in default only when that slot is NULL.

`materialize._is_zone_actor_class` now decides by resolved ancestry — `ULevel::SetActorZone`'s own
`IsA(AZoneInfo) && !IsA(ALevelInfo)` — through the `ClassIndex` that `apply._materialize_native`
already holds; `resolve_zone_actors` takes it as a required `index=`. Like `movers.is_mover` it
answers or raises: a chain truncating before `Core.Object` is a `ClassRefError`, never a silent
`False`.

Regression: `test_zone_actor_is_decided_by_ancestry_not_by_the_class_name_suffix`
(`uedcli/tests/test_native_roundtrip.py`).

Verified: Island N=93 byte-exact, then N=1..122 with the ladder; no regression on UNATCO N=1..115,
WanChai N=1..44, NYC_Bar N=1..118, OceanLab N=1..47. Island now bails at N=123 —
`dev/docs/board/inbox/island-n-123-world-model2-leaf-permeating-light/`.
