+++
priority = "p1"
kind = "bug"
summary = "NYC_Bar N=59: the Region zone-actor half is FIXED; what remains is UED22's LIGHT APPLY resetting every Mover to BasePos/BaseRot (which would put the trunk's movers at the origin), pawn Foot/HeadRegion, and mover-model Bounds."
+++

# NYC_Bar N=59 — the first world CSG brush

`02_NYC_Bar` gates byte-exact N=1..58 and fails at N=59. Actor 59 is `Brush1` (`Engine.Brush`,
`CSG_Subtract`, Location `(-1024, 0, 128)`) — the level's FIRST world brush: the N=58 world `Model`
has **0 nodes**, the N=59 one has **6**. That turns on everything the editor only does to a zoned
world. Reproduced against a freshly forced editor reference.

## 1. Actor `Region` zone actor — FIXED

Native bound every actor's `Region.Zone` to the LevelInfo; UED22 binds it to the ZoneInfo.
`UModel::PointRegion` (`Engine 0x101aee60`) returns `Zones[iZone].ZoneActor` and falls back to the
LevelInfo only when that slot is NULL (`0x101aef3e`-`0x101aef4a`). Native already had the
`{zone: actor}` map (it fills `Model.Zones[].ZoneActor` with it); it just was not used for `Region`.
Fixed — brushes, patrol points, Pinball and the ZoneInfo itself all match now, and UNATCO N=20..25 +
NYC_Bar N=1..25 re-verify clean against freshly built references.

## 2. `LIGHT APPLY` resets every Mover to `BasePos`/`BaseRot` — needs a ruling

Isolated by verb (same trunk, three builds):

| build | mover `Location`/`Rotation` | pawn `FootRegion` |
|-------------------------------------|-----------------|-------------------|
| `MAP IMPORT` only                   | kept            | unset (`None`)    |
| `MAP IMPORT` + `MAP REBUILD`        | kept            | stamped           |
| + `LIGHT APPLY` (the golden recipe) | **dropped**     | stamped           |

Then measured directly: authoring `BasePos=(100,200,300)` / `BaseRot=(Yaw=8192)` on `DeusExMover11`
makes the built package store exactly `Location=(100,200,300)`, `Rotation=(Yaw=8192)`. So
**`LIGHT APPLY` assigns `Location = BasePos` and `Rotation = BaseRot` on every Mover** — the editor
closing movers to their base before baking. The trunk's movers carry an authored `Location`
(`DeusExMover11` `(-3482, 656, -8)`) and NO `BasePos`, so the reset drops them at the origin.

**Why this needs the owner, not a fix:** the trunk was extracted from the shipped retail
`02_NYC_Bar.dx`, whose movers also have no `BasePos` while carrying a real `Location`. So the shipped
map was never saved after a `LIGHT APPLY` that ran this reset. Reproducing UED22 here is faithful to
the reference recipe and produces a level whose every mover sits at the origin.

## 3. Pawn `FootRegion`/`HeadRegion` — decoded, not yet implemented

`ULevel::SetActorZone` (`Engine 0x10161e10`, live `0x1781e10`) runs during `MAP REBUILD` and, for an
actor that IsA `APawn`:

    Region     = Model->PointRegion(LevelInfo, Location)
    FootRegion = Model->PointRegion(LevelInfo, Location - (0, 0, *(float*)(pawn+0x194)))
    HeadRegion = Model->PointRegion(LevelInfo, Location + (0, 0, *(float*)(pawn+0x2ec)))

and returns early for the LevelInfo itself after stamping it `(LevelInfo, -1, 0)` — which is the rule
native already encodes. Live capture at `0x1782008` over 20+ pawns: `+0x194` reads 39 / 43 / 47.5,
matching each class's decoded `CollisionHeight` default (Jock 47.5, SandraRenton and Female1 43), so
`+0x194` is `CollisionHeight`. `+0x2ec` reads **0.0 for every pawn**; those classes have
`EyeHeight` default 0 and `BaseEyeHeight` 36/38/40, so it is the runtime eye height, not
`BaseEyeHeight`. Native stamps neither field today.

## 4. Mover private `Model` `Bounds` — not investigated

Each `Model_DeusExMover*` gains a 6-entry `Bounds` array in UED22's N=59 build (`bspBuildBounds` on
the mover models) where native emits none; their `Polys` differ too.
