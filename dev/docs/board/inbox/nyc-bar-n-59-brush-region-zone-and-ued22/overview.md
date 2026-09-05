+++
priority = "p1"
kind = "debug"
summary = "NYC_Bar N=59: Region zone-actor, mover base-pose and pawn Foot/HeadRegion all FIXED; what remains is world-node NF_IsFront/NF_IsBack and unbuilt mover private models."
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

## 2. Mover `BasePos`/`BaseRot` — the ladder loses it on BOTH sides

`LIGHT APPLY` assigns `Location = BasePos`, `Rotation = BaseRot` on every Mover. That is a
NORMALIZATION back to the key-0 rest pose, not a reset: it is a no-op on correctly-authored data.

Read straight out of the retail `02_NYC_Bar.dx` at the property-tag level — all five movers carry
`BasePos`, `BaseRot` (plus `SavedPos`/`SavedRot`/`OldLocation`), and **`BasePos == Location` and
`BaseRot == Rotation` exactly**:

| mover | BasePos | Location | BaseRot.Yaw | Rotation.Yaw |
|-----------------|--------------------------|--------------------------|---------|---------|
| DeusExMover11   | (-3481.999, 656, -8)     | (-3481.999, 656, -8)     | 16384   | 16384   |
| DeusExMover12   | (-3450, 656, 120)        | (-3450, 656, 120)        | 16384   | 16384   |
| DeusExMover9    | (-3088, 416, 0)          | (-3088, 416, 0)          | 32768   | 32768   |
| DeusExMover5    | (-3296, -1728, 160)      | (-3296, -1728, 160)      | -49152  | -49152  |
| DeusExMover4    | (1024, 1040, 128)        | (1024, 1040, 128)        | -81920  | -81920  |

So the trunk loses nothing by stripping them (`normalize.py` drops `BasePos`/`SavedPos`/`BaseRot`/
`SavedRot` as engine-managed; `architecture.md`: "uedcli never emits `BasePos`/`BaseRot` — the editor
derives them from `Location`/`Rotation`"), and `movers.set_base_pose` re-derives exactly
`BasePos = Location`, `BaseRot = Rotation`. The product path is already right:
`apply._materialize_native` -> `_assembly_level` -> `set_base_pose`.

The N=59 "movers at the origin" outcome is the LADDER's plumbing, on both sides:

- **Native side**: `parity_compare.build_native_lit_dx` (the harness the ladder builds native with)
  calls `assemble_unbuilt` directly and never calls `set_base_pose`, so it emits movers with no
  `BasePos` — NOT what `level materialize` produces.
- **Reference side**: measured on the same N=59 trunk, `MAP IMPORTADD` derives
  `BasePos`/`BaseRot` from `Location`/`Rotation` on import (built ref carries
  `BasePos = Location = (-3482, 656, -8)`, `BaseRot = Rotation = Yaw 16384`, and `LIGHT APPLY` is
  then a no-op), while the golden recipe's `MAP IMPORT` does NOT — leaving `BasePos = 0`, so the
  normalization drops the mover at the origin. This matches `architecture.md`'s existing note that
  the derivation happens on `MAP IMPORTADD`/`EDIT PASTE`.

Fix shape (needs the owner's call on which side): make both sides carry the base pose the way the
product does — apply `set_base_pose` in the ladder's native build, and have the reference builder's
T3D carry it too (mirroring what `level materialize` hands the editor) rather than switching the
ruled `MAP IMPORT` ingest verb. Not an exclusion; nothing is lost or masked.

## 3. Pawn `FootRegion`/`HeadRegion` — FIXED

`ULevel::SetActorZone` (`Engine 0x10161e10`, live `0x1781e10`) runs during `MAP REBUILD` and, for an
actor that IsA `APawn`:

    Region     = Model->PointRegion(LevelInfo, Location)
    FootRegion = Model->PointRegion(LevelInfo, Location - (0, 0, *(float*)(pawn+0x194)))
    HeadRegion = Model->PointRegion(LevelInfo, Location + (0, 0, *(float*)(pawn+0x2ec)))

Live capture at `0x1782008` over 20+ pawns: `+0x194` reads 39 / 43 / 47.5, matching each class's
decoded `CollisionHeight` default (Jock 47.5, SandraRenton and Female1 43). `+0x2ec` reads 0.0 on
every pawn; those classes declare `EyeHeight` 0 and `BaseEyeHeight` 36/38/40, so it is the runtime
eye height an editor-placed (never-ticked) pawn still holds at its class default.

Native now stamps both from the same descent, dropping the trunk's authored pair (whose Zone refs a
subset cannot resolve, and which the editor overwrites anyway), and only when the world Model has
nodes — with none, the rebuild's zoning pass does not run and the imported values stand, which is
what UED22 does at N=58. All eight pawns match.

## 4. World-node `NF_IsFront` / `NF_IsBack` — decoded, NOT reproducible from one descent

The only remaining divergence in the world `Model`. Native leaves every node's `node_flags` 0; UED22
sets `0x40`/`0x80` on 5 of the 6 (the gate compares them — its mask is only `~0x18`):

| node | 0 | 1 | 2 | 3 | 4 | 5 |
|--------|------|------|------|------|------|------|
| UED22  | 0x40 | 0x00 | 0x80 | 0x40 | 0x40 | 0x80 |
| native | 0x00 | 0x00 | 0x00 | 0x00 | 0x00 | 0x00 |

The writer is `UModel::PrecomputeSphereFilter` (`Engine 0x101af030`) via its recursive helper
`0x101aefb0`, decoded in full:

    node.flags &= 0x3f                       // clear NF_IsFront|NF_IsBack       (0x101aefcc)
    d = PlaneDot(node.Plane, sphere.center);  r = sphere.radius
    if (-r > d)   { node.flags |= 0x80; inode = node.iBack;  }        // 0x101aeff2, wholly behind
    elif (d > r)  { node.flags |= 0x40; inode = node.iFront; }        // 0x101af000, wholly in front
    else          { if (node.iBack != -1) recurse(node.iBack); inode = node.iFront; }

Live capture at `0x17cf030` over the whole golden batch: it is called **exactly 3 times** on the
world model, once per mover, each with that mover's shape-model sphere centred at **-PrePivot**
(mover9 `(-1, 32, 64)` r 71.63; mover12 `(-0.5, -31, -64)` r 71.19; mover11 `(-0.5, 31.001, 64)`
r 71.19 — the last call).

Replaying any of the three against the FINAL tree yields `0x40 0x00 0x40 0x40 0x00 0x40`, not
UED22's pattern — and no single descent can produce UED22's: this tree is a linear chain whose every
`iBack` is -1, so a `0x80` mark at node 2 sets `inode = -1` and the walk STOPS, yet nodes 3-5 are
also marked. So the stored bits accumulate across several descents and/or against INTERMEDIATE tree
states during the incremental CSG. Reproducing them means modelling when the editor runs the
precompute during the build, not replaying one call — do not guess it.

Probe: `spikes/2026-09-05-lightapply-node-flags/harness/spherefilter_calls.py`.

## 5. Mover private `Model`s — OPEN

Each `Model_DeusExMover*` differs in two ways, both "the mover's brush model was never built":

- **`Bounds`**: UED22 stores 6 entries, native 0 (`bspBuildBounds` on the mover model).
- **`Polys` `iLink`/`iBrushPoly`**: native writes `iLink` = the poly's own index and
  `iBrushPoly = -1`; UED22 writes linked values (`iLink` 6.., `iBrushPoly` 0..).

The older `native-geometry-path-leaves-mover-models-unbuilt` item was closed as superseded and "not
re-confirmed against the current tree" — this re-confirms it, with bytes.
