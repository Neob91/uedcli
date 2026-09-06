# NYC_Bar N=59 — what `LIGHT APPLY` does to movers

**Result: fixed faithfully, no mask.** All three N=59 residuals turned out to be one thing — the
moving-brush half of `UEditorEngine::shadowIlluminateBsp`, which native never ran. NYC_Bar gates
byte-exact at N=59 and the ladder moves on. Board item:
`nyc-bar-n-59-brush-region-zone-and-ued22`.

## The divergence

Seven gate failures at N=59 (the level's first world CSG brush), in three clusters:

| body | native | UED22 |
|---|---|---|
| world `Model2` nodes 0/2/3/4/5 `node_flags` | `0` | `0x40 / 0x80 / 0x40 / 0x40 / 0x80` |
| `Model_DeusExMover{9,11,12}` `LightMap` | 0 records | 6 records |
| `Polys@Model_DeusExMover{9,11,12}` `iLink` / `iBrushPoly` | own index / `-1` | `6+`/`0..5` |

At N=58 (no world brush yet) native matched UED22 exactly on all three, and a reference built with
`--no-light` (`MAP IMPORT` + `MAP REBUILD`, no `LIGHT APPLY`) also matches native. So all three are
`LIGHT APPLY` output, and all three appear only once the world has geometry.

## Why nothing happens at N=58

`shadowIlluminateBsp` (`Editor.dll 0x100a5e10`) returns at once when the world `Model`'s
`Nodes.Num()` is 0 (`0x100a5ea9`). A trunk prefix whose brushes are all movers builds a 0-node
world, so the whole moving-brush pass is skipped and the imported values stand.

## What the pass does — three stored effects

**1. Per-mover `LightMap` records** (`0x100a6020`–`0x100a6065`). For every `AMover` (the cast at
`0x10062340` resolves `AMover::StaticClass`), the mover's `Brush->LightMap` is emptied and then
walked poly by poly: a poly with `PolyFlags & 0x400081` (the same `PF_Unlit|PF_Invisible|
PF_FakeBackdrop` mask native already uses for world surfs) gets `iBrushPoly = -1`; every other poly
appends one `FLightMapIndex` and stores its slot in **`iBrushPoly`** (`+0x1c8`). So the mover's
saved `iBrushPoly` is not a brush-poly index at all — it is the lightmap slot.

The record's grid is measured in the brush's OWN LOCAL space (`0x100a51e3`–`0x100a52e5`): with the
poly's stored `Base`/`TextureU`/`TextureV`, `u = (Vertex - Base) · TextureU`, `v = … · TextureV`,
min/max over the poly's own vertices, then the same `axis_grid` the world surfaces use. NYC_Bar's
movers come out `USize = VSize = 2` with `Pan = (Umin-0.125, Vmin-0.125, 0)` and
`iLightActors = -1` — the same values at N=59 and N=62, because they depend on nothing outside the
poly.

**2. Mover polys mirrored into transient world surfs — the `iLink`.**
`GNewBrushTracker(Level)` (`Engine.dll 0x1014cb30`) creates the level's `FMovingBrushTracker`, and
`AMover::SetBrushRaytraceKey` → `Update` (`0x1014d530`) attaches each moving brush through
`0x1014d250`: **one `FBspSurf` appended to the WORLD `Model->Surfs` per mover poly**, carrying the
poly's texture/pan, `iBrushPoly = the poly index`, `Actor = the mover`, `PolyFlags & 0x3cffffff`,
`iLightMap = the poly's own `iBrushPoly`` (the lightmap slot from step 1) — and the new surf's index
written back into the poly's **`iLink`** (`0x1014d442`). No filtering: every poly gets a surf.

The attach walks `Level->Actors` in index order, so the numbering runs
`worldSurfs, worldSurfs+1, …` across movers in actor order. Measured: at N=59 the world has 6 surfs
and the movers take 6-11 / 12-17 / 18-23; at N=62 it has 18 and they take 18-23 / 24-29 / 30-35.
`SurfIsDynamic(iSurf)` is literally `iSurf >= <the static count>` (`0x1014d510`), and the tracker's
destructor truncates the array back — which is why the saved world `Model` still has only its own
surfs while the movers keep their `iLink`s.

**3. `PrecomputeSphereFilter` per mover — the world nodes' `NF_IsFront`/`NF_IsBack`.**
After attaching, the tracker drains its pending-mover list (`0x1014d692`): per mover it transforms
the brush's polys to world space, builds an `FSphere` over ALL their vertices, and calls
`UModel::PrecomputeSphereFilter` (`Engine.dll 0x1014d812`). The list is built by prepending, so it
drains in **reverse actor order** — which is exactly the call order the earlier
`spikes/2026-09-05-lightapply-node-flags` probe measured (mover9, mover12, mover11).

`PrecomputeSphereFilter` (`0x101af030`, helper `0x101aefb0`) per visited node: clear
`NF_IsFront|NF_IsBack` (`flags &= 0x3f`), then with `d = PlaneDot(Plane, centre)` and `r = radius` —
`-r > d` sets `0x80` and continues down the first child; `d > r` sets `0x40` and continues down the
second; otherwise the node keeps neither bit, the first child is walked recursively, and the walk
continues down the second.

The earlier spike concluded no single descent could produce UED22's pattern, and that is right — but
it does not have to. A node the descent never reaches KEEPS what an earlier descent left, so the
stored bits are the accumulation over all three, last write wins. Replaying the three descents in
reverse actor order over the final tree reproduces `0x40 0x00 0x80 0x40 0x40 0x80` exactly, first
try (`harness/sphere_probe.py`).

The sphere is `FSphere(Pts, Count)` — bbox midpoint, `radius = sqrt(max squared distance) * 1.001`,
the same construction a shape model's stored sphere uses — over `Location + L·(v - PrePivot)`.
Getting `PrePivot` wrong still happens to reproduce this level's pattern (the offsets are ~72 uu
against a ~71 uu radius), so the probe pins the centres too: mover9 `(-3087, 384, 64)` r 71.633,
mover12 `(-3419, 655.5, 56)` r 71.185, mover11 `(-3513.001, 655.5, 56)` r 71.185.

## The fix

`unbuilt.light_apply_movers` runs all three steps when the world `Model` has nodes, and the
per-brush loop now builds each mover's shape model EAGERLY (before any body is serialized) because
both it and this pass write the saved `Polys`. The grid math is not duplicated: a new Rust
`light::brush_lightmap_indices` reuses `axis_grid`/`lumel_scale`, exposed as
`uedcli_native.brush_lightmap_indices`.

## Evidence

- `parity_gate.py` on NYC_Bar N=59: PASS, byte-exact, no new mask (was 7 failing bodies).
- Regression `2026-09-03-incremental-actor-parity/harness/test_nycbar_n59_light_apply_movers.py`:
  builds native from the 59-actor subset committed in `golden/subset/` and gates it against
  `golden/ref_N59.dx`, plus a direct replay of the three descents.

## Loose ends

- The grid's PolyFlags get an extra `PF_LowShadowDetail` when `Actor+0x280 & 0x10` is set
  (`0x100a52cc`) — some mover bool. NYC_Bar's movers do not set it, so the port leaves it out;
  a level whose movers do would need it identified.
- The port uses the key-0 rest pose (`Location`/`Rotation`), which is what these movers are at, and
  a mover parked elsewhere gets a FOURTH descent the port does not make. `shadowIlluminateBsp`'s
  second loop calls `AMover::SetBrushRaytraceKey` per mover in ACTOR order (`0x100a620d`), which
  moves it to `KeyPos[BrushRaytraceKey] + BasePos` and calls `Update(actor)`; `Update`'s non-null
  path (`Engine.dll 0x1014d5cd`-`0x1014d634`) compares `Location`/`Rotation` against what the attach
  recorded in `+0x3a0`/`+0x3c4` and, if they moved, re-attaches — running
  `PrecomputeSphereFilter` again, later and in actor order, at the moved pose.
- Mover lightmaps here are all DARK (`iLightActors = -1`, no `LightBits`). A mover a light actually
  reaches would need the raytrace half of `0x100a5010` too, which is not ported.
