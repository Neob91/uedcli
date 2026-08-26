+++
priority = "p1"
kind = "debug"
summary = "Native BSP: node iLeaf marks 2x the solid slots the editor does, so most point actors read as inside solid; meshes render black in-game."
+++

# Native BSP leaf assignment marks 2× the solid slots — point actors read in-solid

Found while rendering a natively built UNATCO in the real game
(`editor-free-native-world-bsp-map-assembly`). The BSP **topology** is editor-exact; the
**node → leaf** assignment is not, and the gap is visible in a game render.

Still open, unchanged — nothing here has been fixed. Reproduce the map with
`UEDCLI_NATIVE_MATERIALIZE=1 bin/uedcli --project <p> level materialize --tree level/unatco --out
<out>.dx`, then `level preview --game --map <out>.dx` (harness:
`dev/docs/spikes/2026-08-26-editor-free-native-materialize/`).

## Measurement

`build_geometry_bspcsg` on the `unatco` trunk vs the editor's own `MAP REBUILD` golden
(`/tmp/UEDGolden_unatco_full.dx`), over the 5646 of 6314 nodes that carry an identical plane at the
same index:

| field | differing |
|-----------------|-----------|
| `iFront` | 0 |
| `iBack` | 3 |
| `iSurf` | 0 |
| `NumVertices` | 0 |
| **`iLeaf`** | **3346** |
| `iVertPool` | 4043 (expected — the known Verts/Points residual) |

Whole-model `iLeaf == -1` (solid) slots: **native 11866, editor 5424**. Same 762 leaves, same 7
zones (the zone numbering is a permutation).

It is not a front/back convention swap in the serialized model: 0 of 6314 nodes have native's
`(iFront, iBack)` equal to the golden's `(iBack, iFront)`, and 0 have a reversed `iLeaf` pair.

## Consequence — measured, not inferred

A `PointRegion` descent (`native/materialize._model_point_zone`) over each actor's `Location`:

| class | n | reads zone 0 (solid), native | same, editor golden |
|--------------|-----|------|----|
| PathNode | 228 | 140 | 2 |
| Light | 193 | 114 | 2 |
| OfficeChair | 20 | 17 | 0 |
| Plant2 | 20 | 13 | 0 |
| Plant1 | 13 | 8 | 0 |
| UNATCOTroop | 10 | 10 | 0 |

So ~60 % of the level's point actors sit in what the native tree calls solid space. In the real
game (`DeusEx.exe` via `level preview --game --map`) the BSP surfaces of that map render correctly
but **no mesh actor draws at all** — plants, chairs and the UNATCO troops are simply absent, and
`DeusEx.log` fills with a repeating per-frame critical stack:

```
Critical: FLightManager::SetupForActor
Critical: URender::DrawLodMesh
Critical: (LodMesh DeusExDeco.Toilet)
Log: Anomalous singularity in URender::DrawWorld
```

Actor lighting goes through the actor's region/zone; an actor whose region resolves into solid
gets nothing to light with. Untested but implied by the same reads: player spawn and collision.

Confounded by one thing worth separating before chasing this: the same map has **no lighting at
all** (nothing bakes lightmaps offline), so `Model.LightMap` is empty and every surf has
`iLightMap = -1`. Whether `SetupForActor` faults on the empty lightmap arrays or on the
solid-region read is not established — establish that first.

## Where to look

`bspcsg.rs`'s leaf pass — the equivalent of the editor's `bspSetLeaf`/zone-flood step that assigns
`iLeaf[2]` per node. It is downstream of the topology (which already matches) and likely related to
the already-filed `iZone=(0,0)` on detail-layer nodes (`bspAddNode`'s parent-zone inheritance is
decoded but not ported): node `iZone` histograms show 3330 native nodes at `(0,0)` where the
editor has none, and 3264 nodes carry `zone_mask == 0`.

Harnesses used are throwaway; the two checks worth keeping are the `iLeaf == -1` count ratio and
the point-actor zone-0 census against the committed UNATCO golden.
