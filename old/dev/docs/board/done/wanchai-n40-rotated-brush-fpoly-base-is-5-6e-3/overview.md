+++
priority = "p1"
kind = "debug"
summary = "WanChai N40 rotated-brush FPoly.Base is 5.6e-3 off UED22"
+++

# WanChai N40 rotated-brush FPoly.Base is 5.6e-3 off UED22

FIXED 2026-09-05 (`Remap FBspSurf.pBase in MergeNearPoints, as the editor does`). The base value
itself is NOT wrong — `bspOptGeom`'s `MergeNearPoints(Model, 0.25)` welds the two points, and its
SECOND remap loop (`Editor.dll 0x33eee`-`0x33f27`, `Model->Surfs` stride 0x40, field `Surf+8`) puts
every `FBspSurf.pBase` through the same table it puts `FVert.iVertex` through. Native ran only the
vert half, so the merged-away point stayed alive under a `pBase` and survived the next `bspRefresh`.
With the surf half in place native lands 628 points and `Surf[206].pBase = 134`, exactly UED22's.
Pinned by `test_wanchai_ladder_facts.py::test_mergenearpoints_remaps_surf_pbase_too`.

The analysis below is the diagnosis as it stood before the cause was found; it is kept because the
ruled-out list is what pointed at `bspOptGeom`.

## What diverges

Actor 40 is `Brush3674`: `CSG_Add`, `Rotation=(Pitch=16384,Yaw=16384)` (90 deg / 90 deg),
`PostScale=(X=0.25,Y=4.000014,Z=0.125)`, `Location=(1312,-1656,-304)`. Its poly 4 is authored with a
FAR-AWAY origin — `Origin +128,+5248,+354` against verts at local `x=128, y=+-128, z=+-2` — so the
transform's rounding is amplified by a ~5000-unit lever.

Native's world-space `FPoly.Base` for that face comes out `(0.0, -3072.0068359375, -288.0)`. UED22's
is within `THRESH_POINTS_ARE_SAME` (0.002) of the already-present `Model.Points[134]`
`(0.0001220703125, -3072.001220703125, -288.0000305175781)` — which is `Brush282`'s poly 5 base,
added at N=20 — so the editor's `bspAddPoint` SNAPS to it. Native's value is `5.6e-3` away, above the
threshold, so it appends a new point.

Result: native 629 points vs UED22 628, every point index from 177 up shifts by one, and
`Surf[206].pBase` differs. Everything else is byte-exact: 388/388 nodes with identical planes,
225/225 surfs, 5892/5892 verts, and `Surf[206]` is the ONLY surf whose `pBase` differs once the
one-slot shift is accounted for.

## What it is NOT

- Not the point-dedup class fixed on 2026-09-05: the two values are `5.6e-3` apart, above 0.002, so
  no `FindNearestVertex` reachability question arises — the editor could not snap native's value
  either. The raw base VALUE differs.
- Not the base-snap onto the plane. That moves `Base` along the face normal, and this face's world
  normal is `(0,0,1)`; the offset is `(-1.2e-4, -5.6e-3, +3.1e-5)`, essentially all in `-Y`.
- Not a vertex-transform bug: this brush's own four poly-4 vertices land bit-identically in both
  tables (see below), so its `PointXform` is right.

## Ruled out: the transform matrix, the composition, and the trig table

Chased and DISPROVEN, so the next session does not repeat it:

- `ABrush::BuildCoords` (`Engine.dll 0x111390`) builds `PointXform` as
  `((UnitCoords * PostScale) * Rotation) * MainScale` — the order `rotation.editor_point_xform`
  already uses. `FCoords::operator*=(FRotator)` (`core.dll 0x17fe0`) applies Yaw, then Pitch, then
  Roll, with axes `X=(cos,sin,0) Y=(-sin,cos,0) Z=(0,0,1)`, `X=(cos,0,sin) Y=(0,1,0)
  Z=(-sin,0,cos)`, `X=(1,0,0) Y=(0,cos,-sin) Z=(0,sin,cos)` — `_fcoords_mul_rotator` matches all
  three, sign for sign.
- The GMath trig table is built at runtime, not stored in the DLL; native's
  `gmath_cos(16384) = -8.742278e-08` is `sinf` of the f32-narrowed angle, the value UE1's
  `FGlobalMath` constructor produces.
- Decisively: all four of poly 4's VERTICES transform bit-identically and are present in BOTH point
  tables, and they are 1-ULP sensitive to the row's near-zero entries (local `(128,128,-2)` lands on
  `-1648.0001220703125`, one ULP off `-1648`, only because of the `-8.95e-5` those entries
  contribute). A different near-zero entry would move them. So UED22's `PointXform` IS native's, and
  UED22's stored base for this face is NOT `PointXform * Origin + Location`.
- The `pBase` threshold is right: `bspAddNode`'s surf-alloc calls `bspAddPoint(Model, &Base, 1)`
  (`Editor.dll 0x10034f0b push 1`) = `THRESH_POINTS_ARE_SAME`, not the ring's 0.015.

## Where it was

The first of those candidates: `bspOptGeom` (`Editor.dll 0x36870`) -> `MergeNearPoints` — not a
recompute but a REMAP, at a radius (0.25) two orders above `bspAddPoint`'s 0.002, which is why a gap
this size survives the add and dies at optgeom.

## Reproduce

    .venv/bin/python dev/docs/spikes/2026-09-03-incremental-actor-parity/harness/actor_parity.py \
      --dx <maps>/06_HongKong_WanChai_Market.dx native 40
    .venv/bin/python dev/docs/spikes/2026-09-03-incremental-actor-parity/harness/body_token_diff.py \
      _scratch/actor-parity/06_hongkong_wanchai_market/native_N40.dx .../ref_N40.dx

`UEDCLI_BSPCSG_POINT_TRACE=0,-3072.004,-288,0.02` on the native build shows both raw values being
added, with the second `ADD` reporting `gnear` at `d=5.617e-3`.
