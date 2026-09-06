# Island N=10 / NYC_Bar N=113 — the `Region` descent's plane dot must be f32

**Result: one root cause, fixed faithfully, no mask.** Native's point-region descent evaluated the
node plane in double precision; the engine evaluates it in SINGLE precision with a fixed summation
order. Both levels' failing token was a brush pivot sitting exactly on a node plane, where the f64
value is ~1e-5 off zero and the descent takes the other child. Board items:
`island-n-10-brush1359-region-ileaf-13-vs-18`, `nyc-bar-n-113-brush69-region-lands-outside-the`.

## The two divergences

Same shape, different level, one gate residual each — the world `Model`/`Model2` byte-identical on
both sides.

| level | actor | Location | native | UED22 |
|---------|-------------|------------------------|----------------|--------------------|
| Island  | `Brush1359` | (-11680, 4528, -384)   | iLeaf 13, zone 1 | iLeaf 18, zone 1 |
| NYC_Bar | `Brush69`   | (-384, -440, 0)        | iLeaf -1, zone 0 | iLeaf 55, zone 1 |

## What the disassembly pinned

`UModel::PointRegion` (`Engine.dll 0x101aee60`) is a plain descent:

```text
iNode = 0
while iNode != -1:
    IsFront = setae(FPlane::PlaneDot(Nodes[iNode].Plane, P), 0.0)   ; 0x101aef00
    iParent, iNode = iNode, Nodes[iNode].iChild[IsFront]            ; 0x101aef08, node+0x20
iLeaf      = Nodes[iParent].iLeaf[IsFront]                          ; node+0x38
ZoneNumber = NumZones ? Nodes[iParent].iZone[IsFront] : 0           ; node+0x34
Zone       = Zones[ZoneNumber].ZoneActor or the passed-in default
```

`node+0x20` is `iChild[0]` = `iBack`, so `IsFront=1` picks the SECOND child index — which is also the
second on-disk index, the one `native/umodel.py` calls `i_back`. Native's child selection was already
right; the `FPlane::PlaneDot` call was not.

`FPlane::PlaneDot` (`Core.dll 0x10024e60`) is an SSE horizontal add over **f32** lanes:

```text
xmm2 = (P.X, P.Y, P.Z, +0.0)
xmm2 |= [0x100a0af0] = (0, 0, 0, -1.0)      ; lane 3 := -1.0
xmm2 *= Plane                                ; (X*Px, Y*Py, Z*Pz, -W)
result = (lane3 + lane2) + (lane1 + lane0)   ; shufps 0xb1 / addps / movhlps / addss
```

so `PlaneDot = f32( f32(-W + f32(P.Z*Z)) + f32( f32(P.Y*Y) + f32(P.X*X) ) )`. Both the precision and
the pairing matter. For Island's node 22 (`plane = (-0.24609742, 0.96924520, 0, 7263.16015625)`) the
f64 dot is `-9.632e-05` and the f32 dot is exactly `0.0`; for NYC_Bar's node 272 it is `-7.629e-06`
vs `0.0`. `setae` takes 0.0 as front, so the editor descends the other way in both cases.

## The fix

`materialize._plane_dot` reproduces that expression exactly (f32 rounding via `struct`), and
`_model_point_region` uses it. That is the whole change — every `Region`/`FootRegion`/`HeadRegion`
stamp and the `resolve_zone_actors` / `paths` / `pathplace` zone lookups route through it.

## Evidence

- `harness/descent_compare.py <pkg.dx> X Y Z` prints both trails; it is what pinned the two nodes.
- `harness/region_corpus_check.py` re-runs the descent for every actor of a UED22 reference and
  scores it against the `Region` the editor stamped. Across the five levels' highest cached refs
  (Island N10, NYC_Bar N113, UNATCO N115, WanChai N44, OceanLab N45) — 324 actors — **0 mismatches**.
- `2026-09-03-incremental-actor-parity/harness/test_pointregion_planedot_f32.py` pins the two DLL
  byte sequences and both near-tie cases.
- `parity_gate.py`: Island N=10 PASS, NYC_Bar N=113 PASS, no new mask.
- `ladder_run.py` after the change: Island N=1..92 PASS (was 9; now bails at 93 on a zone-ACTOR
  selection bug, `dev/docs/board/inbox/island-n-93-zone-actor-missed-resolve-zone/`), NYC_Bar N=1..118
  PASS (was 112, now bails at 119 on the world `Model2` `LightMap` order —
  `dev/docs/board/inbox/nyc-bar-n-119-world-model2-lightmap-array-order/`), UNATCO N=1..115 PASS,
  WanChai N=1..44 PASS, OceanLab N=1..45 PASS — every other level's ceiling unchanged.

## Left open

`region_corpus_check.py` also scores a fully faithful transcription of `PointRegion`, which differs
from ours in two ways the corpus never exercises: it reads `ZoneNumber` from the terminating NODE's
`iZone[IsFront]` (we read the leaf's `i_zone`), and it keeps `iLeaf` even when it is -1, so a point
in solid space can still carry a non-zero zone (we return `(-1, 0)`). `leafzone == nodezone` holds on
every leaf side of every reference measured, and `cur_vs_faithful` is 0 for all 324 actors — but 371
of NYC_Bar N113's node sides are solid with a non-zero `iZone`, so an actor placed there would
diverge. Board: `pointregion-zone-comes-from-the-node-not-the-leaf`.
