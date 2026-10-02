+++
priority = "p3"
kind = "debug"
summary = "`_model_point_region` reads ZoneNumber off the LEAF and returns (-1, 0) for a point in solid; `UModel::PointRegion` reads it off the terminating NODE's iZone[IsFront] and keeps iLeaf=-1 with that zone. No corpus case separates them yet."
+++

# `PointRegion`'s zone comes from the node, not the leaf

Found 2026-09-06 while fixing the f32 plane dot (`dev/docs/spikes/2026-09-06-pointregion-planedot-f32/`).
Native's descent is now byte-faithful in the part that was failing; two decoded differences remain.

`UModel::PointRegion` (`Engine.dll 0x101aee60`) ends:

```text
iLeaf      = Nodes[iParent].iLeaf[IsFront]                  ; node+0x38 -- stored as-is, -1 included
ZoneNumber = NumZones ? Nodes[iParent].iZone[IsFront] : 0   ; node+0x34
```

`materialize._model_point_region` instead reads `model.leaves[iLeaf].i_zone`, and collapses an
out-of-range `iLeaf` to `(-1, 0)`.

## Why it does not show yet

`harness/region_corpus_check.py` in that spike scores both variants against the `Region` UED22
stamped. Over the five levels' highest cached references (Island N10, NYC_Bar N113, UNATCO N115,
WanChai N44, OceanLab N45 — 324 actors) the two agree everywhere and both match the editor.
`leaves[iLeaf].i_zone == nodes[i].i_zone[side]` holds on every leaf-bearing node side measured.

But 371 of NYC_Bar N113's node sides are solid (`iLeaf = -1`) with a NON-zero `iZone`. An actor whose
`Location` lands on one of those gets `(-1, 0)` from us and `(-1, <zone>)` — hence a real ZoneActor
rather than the LevelInfo — from the editor. The ladder will surface it eventually.

Fix: transcribe the tail as decoded, then re-verify the five ladders. Left out of the f32 change to
keep that change to the divergence it was measured against.
