+++
priority = "p1"
kind = "implement"
summary = "NATIVE BUILD IS NOW PLAYABLE (2026-07-16) — playability blocker was COLLISION HULLS, NOT zones (handoff assumption corrected)"
+++

# NATIVE BUILD IS NOW PLAYABLE (2026-07-16) — playability blocker was COLLISION HULLS, NOT zones (handoff assumption corrected)

p1. ✅ **`NativeCastle` live: `phys=1`, pawn rests at
`(0,-250,47)`, level STAYS, `uplayctl shot` renders the castle first-person**
(`_scratch/shots/native_castle_playable.png`). Root cause was NOT zone portalization: the pawn fell
through the floor because the native build shipped no collision hulls. `UModel::LineCheck` forks on
Extent — every pawn/actor sweep (`Extent!=0`) is `FBoxLineCheckInfo::BoxLineCheck` (game `0xf42f0`),
whose ONLY hit clips the swept box against `LeafHulls[iCollisionBound]`; `iColl=-1` = non-solid, no
node-plane fallback. Fixed by porting `bspBuildBounds` (`uedcli-native/src/passes.rs::bsp_build_bounds`
→ `LeafHulls` + `iCollisionBound`); `Bounds`/`iRenderBound` stay empty/`-1` (render, separate).
Offline oracle: `harness/line_check.py` (box sweep HITs at `floor+extent`). Full decode
`re-raw-zones/linecheck-oracle.md`. Supersedes
section 60's "bounds optional" (true only for a zero-extent line trace).
**REMAINING for full byte-parity (NOT playability — deferred):** real multi-zone `TestVisibility`
portalization (leaves/zones/`FZoneProperties`/`ZoneInfo` refs — fully RE'd this session, passes A–G in
`sections/70-zones-portalization.md` + `re-raw-zones/`), the side pool (`bspOptGeom`
`NumSharedSides`/`iSide`), render bounds, and editor `NF_` node flags. These fix per-room
gravity/water/sound/`ZoneInfo` + byte parity; the map is walkable without them (single interior zone).
`_multizone_warning` still fires for multi-room maps. `zones.rs` is still a stub. (Revert the scratch
`DeusExLevelInfo` injection if any remains — Test_Castle has none, not the fix.) Handoff doc
`HANDOFF-native-full-parity.md` is now superseded by this entry.
