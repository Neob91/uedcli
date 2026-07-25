# Zones & performance  [ENGINE]

UE1 has no fancy occlusion. Rendering performance comes almost entirely from **zones** — sealing the
map into airtight regions the engine can cull whole. Get zoning right and a large level runs; get it
wrong (one merged mega-zone) and everything draws at once.

## What a zone is

A **zone** is a watertight region — any solid brush shape — sealed off from its neighbours by
**zone-portal sheets**. Each zone carries a `ZoneInfo` actor placed inside it, resolved at build time.
The engine culls per zone: if no part of a zone's sealing portal is visible to the camera, the whole
zone (and its contents) is skipped.

## Building a zone

1. **Seal the region with solid geometry.** The zone *boundary* — the walls, floor, ceiling around it —
   must be **solid**. A semisolid on a boundary won't seal, and a semisolid abutting a portal wrecks the
   BSP.
2. **Split it from neighbours with a zone-portal sheet.** A portal is a **nonsolid sheet** brush placed
   across the opening (a doorway), flagged as a zone portal:

```
brush build sheet --width 256 --height 128 --flag portal --flag invisible | actor add -
```

3. **Drop a ZoneInfo inside each zone:**

```
actor build Engine.ZoneInfo --at 512,512,128 | actor add -
```

Verify zoning in the editor's **Zone/Portal view** — one flat colour per zone. Two rooms sharing a
colour means the portal isn't watertight (a **leak**): a gap, or a hole on the portal face, merged them.

### The portal-solidity rule (get this exact)

The precise truth — often mis-stated as "portals must be solid":

- The **portal sheet itself is NONSOLID.** ✅
- It is the **zone-boundary geometry around it that must be SOLID.**
- A **semisolid touching a portal or boundary** is the real BSP-wrecker — keep them apart.

### Size the portal to the opening, not the room

Visibility is tested against the **portal geometry**. Cover the **doorway** (the actual opening between
the zones) fully. You *can* safely oversize a portal into the surrounding wall — excess sheet **buried in
solid** is clipped by BSP and harmless *for sealing*. What breaks culling is portal area left **exposed in
open air**: any fragment hanging in open space stays visible and keeps its zone from ever culling. So
cover the opening; just don't let portal area hang in the open. (For best *culling*, still keep portals
snug to the opening — an oversized portal, even buried, can cull a bit less well than a tight one.)

## No antiportals

UE1's occlusion model is **solid BSP + zones only**. There are **no antiportals** (occluder brushes) —
that's a UE2+ feature. You cannot drop a box to block a sightline; the only way to hide a zone is to
break the line of sight to its portal with actual structure. **Long sightlines are the enemy** — bend
corridors, offset doorways, add pillars and level changes so the camera can't see straight through many
zones at once.

## The budgets

| Budget                | Limit                                      | Why |
| --------------------- | ------------------------------------------ | --- |
| **Polys in view**     | **~150** (rule of thumb, not a hard limit) | originally ~150; modern hardware handles 400+ easily. The busiest camera view is what matters |
| **Zones per map**     | **≤ ~64**                                  | exceed it and zones start merging unpredictably |
| **See-through depth** | **~3** (practical)                         | plan for ~3 zones deep through portals before a far portal shows its own texture — a mapping rule of thumb, **not** a hardcoded cap (and often conflated with the separate mirror/warp recursion limit) |
| **Node:poly ratio**   | ~**2:1**                                   | see [geometry-and-bsp.md](geometry-and-bsp.md); high ratio = over-split BSP |

Check the busy views with `STAT FPS` (frame time / fps) and `STAT ZONE` (visible vs **rejected** zones —
confirms culling is working) in-game.

## Zone properties live on the ZoneInfo

A zone's *behaviour* — water, pain, gravity, fog, sound — is set on its `ZoneInfo`:

```
actor prop set MyZone bWaterZone=True                       # swimmable water (see recipes/water.md)
actor prop set MyZone bPainZone=True DamagePerSec=5         # damages continuously while inside (~1s cadence), not on entry
actor prop set MyZone ZoneGravity=(X=0,Y=0,Z=-320)         # per-zone gravity
actor prop set MyZone bFogZone=True                          # distance fog (see recipes/fire-and-fog.md)
```

- **Distance fog** is `FogDistance` (float) + `FogColor` on the ZoneInfo, gated by `bFogZone=True` (as
  above). Fog is invisible across zone boundaries — build an L-bend so a foggy zone doesn't pop in
  suddenly as you round a corner.
- Give every ZoneInfo an `AmbientSound` (the actor's own ambient-sound field, emitted from the
  ZoneInfo) — silence reads as unfinished.

## Build order matters

The editor rebuilds in the order **Geometry → BSP → Lighting → Paths**. Rebuilding Geometry+BSP
**erases lighting** — so relight after any geometry change (uedctl bakes lighting inside `materialize`,
so this is automatic there). Keep **Build Visibility Zones** on during a rebuild — unchecking it wipes
your zones.

## Related

- [geometry-and-bsp.md](geometry-and-bsp.md) — solid vs semisolid, node count, BSP holes on portals.
- [recipes/water.md](recipes/water.md), [recipes/fire-and-fog.md](recipes/fire-and-fog.md) — zone
  behaviour in practice.
