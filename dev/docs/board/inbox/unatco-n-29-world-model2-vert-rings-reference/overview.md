+++
priority = "p2"
kind = "debug"
summary = "UNATCO's ladder now bails at N=29: the world Model2's node set, planes and Points array are identical to UED22's, but 391 of 860 FVerts point at different Points -- the polygons wound into the same nodes differ."
+++

# UNATCO N=29 — same nodes, same points, different vertex rings

`ladder_run.py --dx 03_NYC_UNATCOHQ.dx --from 1` passes N=1..28 and bails at N=29 with
`BODY model model2: canonical bodies differ`. This is a NEW divergence, uncovered by closing the old
N=26 blocker (`dev/docs/board/done/port-urender-boundvisible-box-occlusion-test/`); it is a geometry
divergence, not a lighting one, so it predates that work.

## What is and isn't equal

Measured with `dev/docs/spikes/2026-09-03-incremental-actor-parity/harness/model_dump.py` on
`native_N29.dx` vs `ref_N29.dx`:

| array | result |
|---|---|
| `Vectors` (35), `Points` (171) | byte-identical |
| `Nodes` (91) | identical except `NodeFlags` — only the gate-excluded `NF_PolyOccluded`/`NF_BoxOccluded` bits. Planes, children, `iVertPool`, `NumVertices`, `iZone`, `iLeaf` all match |
| `Verts` (860) | **391 differ**, indices 364..783, in `iVertex` (the `Points` index); `iSide` matches throughout |
| `Zones` (11), `LightMap` (89), `LightBits` (5638), `Bounds` (67), `LeafHulls` (794), `Leaves` (15) | identical |
| `Surfs` (89) | differ only in `iActor` (an export index the gate remaps) |
| `Model.Lights` (83) | differ in light indices |

## Why it is not a point-dedup tie

The N=8 class of divergence (fixed faithfully, `faithful-incremental-bsp-dedup-rewrite`) was two
coincident points and a near-tie over which index a vert took. That is not this: the differing
indices name genuinely different coordinates — e.g. native vert 364 → `Points[90]` =
`(928, -16, -64)` where UED22 has `Points[97]` = `(928, 736, 96)`. The deltas are not a constant
shift either (2, 3, 7, 8, 10..15, 17, 18). The two builds wind different polygons into structurally
identical nodes.

## Where to start

Every node's `iVertPool`/`NumVertices` matches, so the ring LAYOUT is agreed and only the contents
differ, from vert 364 onward — find the first node whose ring diverges and which CSG operation filled
it. Actor 29 in trunk order is the one that introduces it (N=28 is byte-exact).

Reproduce:

```
.venv/bin/python dev/docs/spikes/2026-09-03-incremental-actor-parity/harness/actor_parity.py \
  --dx dev/games/deusex/Maps/03_NYC_UNATCOHQ.dx diff 29
```
