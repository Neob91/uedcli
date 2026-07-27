+++
priority = "p1"
kind = "unknown"
summary = "(historical detail for the above) native from-scratch `.dx` did NOT game-load: engine could not instantiate the ULevel (`Failed to find object 'Level None.MyLevel'`)"
+++

# (historical detail for the above) native from-scratch `.dx` did NOT game-load: engine could not instantiate the ULevel (`Failed to find object 'Level None.MyLevel'`)

p1. **First-ever game-load test of a
natively-synthesized map (N-3 gate / M0 gate — never actually run before) FAILS.** Both a full
N-3 multi-brush map (subtract room + add pillar + light + PlayerStart + DeusExLevelInfo, real
CoreTexMetal texture import) AND the **minimal M0 carved-box map** fail *identically*, so the
blocker is in the CORE from-scratch package assembly (M0 skeleton: `native/pkg_write` +
`assemble` + `level_write` + `actor_write` + `umodel`), NOT in the N-3 typed-props / import
synthesis (those are correct + tested) and NOT geometry quality. What we KNOW (headless DeusEx via
`uplayctl session start --map <name>`, map symlinked into the game root from `DX/Maps/`): port
**7777 comes up + the game possesses on the DX.dx boot map**; the travel `open <map>` runs
(`Log: Browse:` + `Log: LoadMap:` + `Log: Loading: Package <map>` — the package DOES load), then
`Warning: Failed to load 'Level None.MyLevel': Failed to find object 'Level None.MyLevel'` and the
engine gracefully reverts to DX.dx (NO crash, NO other error line). So the package parses far
enough to load, but the engine's linker never registers the `MyLevel` ULevel export — most likely
`CreateExport`/`Preload` of the ULevel (or an actor) body silently fails so `FindObject<ULevel>`
returns null. The header + name/import/export TABLES are byte-structurally identical to a real map
(ver 68, licensee 0, pkgflags 0x1; Level export name=MyLevel, outer 0, flags 0x70001, cls→Engine.Level;
LevelInfo0 exp[0] identical), and the file passes the always-on offline self-check + re-parse +
the independent `bspspike` parser — so this is a body-serialization detail the ROUND-TRIP parsers
don't catch but the ENGINE's real deserializer rejects (exactly §5/§7's "from-scratch synthesized
values are the first real test" risk). Next: get a verbose per-object error — load the map in the
**editor** (`dx-lum-uned` MAP LOAD logs the failing object/property) or read UE1 `ULevel::Serialize`
/ `AActor::Serialize` and diff my ULevel-trailing-block / StateFrame / property-tag bytes against a
real map's level export byte-for-byte. Repro: `_scratch/native_e2e.py` (writes a map);
`native.materialize.build_carved_box_package()` (the M0 map). This gates the whole native-materialize
line — nothing ships until a native `.dx` actually loads.
