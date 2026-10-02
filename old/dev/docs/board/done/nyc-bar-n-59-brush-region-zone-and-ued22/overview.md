+++
priority = "p1"
kind = "debug"
summary = "DONE — NYC_Bar N=59's four clusters are all fixed; the last three were one thing, the moving-brush half of shadowIlluminateBsp that native never ran. Byte-exact, no mask."
spikes = ["dev/docs/spikes/2026-09-06-nycbar-n59-light-apply-movers/"]
+++

# NYC_Bar N=59 — the first world CSG brush

`02_NYC_Bar` gated byte-exact N=1..58 and failed at N=59. Actor 59 is `Brush1` (`Engine.Brush`,
`CSG_Subtract`) — the level's FIRST world brush: the N=58 world `Model` has 0 nodes, the N=59 one
has 6. That turns on everything the editor only does to a zoned world. Fixed 2026-09-06; the ladder
now runs past N=59.

## 1. Actor `Region` zone actor — FIXED

Native bound every actor's `Region.Zone` to the LevelInfo; UED22 binds it to the ZoneInfo.
`UModel::PointRegion` (`Engine 0x101aee60`) returns `Zones[iZone].ZoneActor` and falls back to the
LevelInfo only when that slot is NULL. Native already had the `{zone: actor}` map; it just was not
used for `Region`.

## 2. Mover `BasePos`/`BaseRot` — FIXED (ladder plumbing, both sides)

`LIGHT APPLY` assigns `Location = BasePos` on every Mover — a normalization back to the key-0 rest
pose, a no-op on correctly-authored data. The N=59 "movers at the origin" outcome was the harness:
its native build called `assemble_unbuilt` without `movers.set_base_pose` (unlike the product path),
and the golden's `MAP IMPORT` T3D did not author the base pose either. Both sides now carry it.

## 3. Pawn `FootRegion`/`HeadRegion` — FIXED

`ULevel::SetActorZone` (`Engine 0x10161e10`) runs during `MAP REBUILD` and, for an `APawn`, stamps
`Region`/`FootRegion`/`HeadRegion` from three `PointRegion` descents at `Location`,
`Location - (0,0,CollisionHeight)` and `Location + (0,0,EyeHeight)`. Native now does the same, and
only when the world Model has nodes.

## 4 + 5. World-node `NF_IsFront`/`NF_IsBack`, and the mover `Model`s — FIXED, one cause

Both, plus the mover `Polys`' `iLink`/`iBrushPoly`, are `LIGHT APPLY` output — a `--no-light`
reference (`MAP IMPORT` + `MAP REBUILD`) matches native on all three. They are the moving-brush half
of `shadowIlluminateBsp` (`Editor.dll 0x100a5e10`), which bails when the world `Model` has no nodes
— which is why N=58 was clean:

- each mover model gets one `FLightMapIndex` per lightmappable poly, and the poly's `iBrushPoly` is
  that slot (not a brush-poly index);
- `FMovingBrushTracker` (`Engine.dll 0x1014d250`) mirrors every mover poly into a TRANSIENT world
  surf and writes the surf index into the poly's `iLink` — hence the `6..23` numbering after the
  world's own 6 surfs;
- the tracker then walks its pending movers in REVERSE actor order, building an `FSphere` over each
  brush's world-space vertices and running `UModel::PrecomputeSphereFilter`, whose node bits
  ACCUMULATE across the descents (the earlier "no single descent can produce this" reading was
  right, and beside the point).

Ported as `unbuilt.light_apply_movers` + Rust `light::brush_lightmap_indices`. Full decode, evidence
and loose ends: `dev/docs/spikes/2026-09-06-nycbar-n59-light-apply-movers/spike.md`. Regression:
`dev/docs/spikes/2026-09-03-incremental-actor-parity/harness/test_nycbar_n59_light_apply_movers.py`.
