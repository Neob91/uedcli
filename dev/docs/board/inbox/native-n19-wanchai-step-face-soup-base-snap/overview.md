+++
priority = "p2"
kind = "debug"
summary = "native N19 WanChai Step face soup-base snap (dW=0, d=1.007e-3) — same point-dedup class as N8; faithful FindNearestVertex fix in progress."
+++

# native N19 WanChai Step face soup-base snap (dW=0)

WanChai `06_HongKong_WanChai_Market` passes the parity gate at N=1..18 and FAILS at N=19. Same
point-dedup class as `done/native-n8-unatco-rotated-brush-base-fp-diverges` — native's linear-scan
`bsp_add_point` snaps a raw face base onto a nearby own-Model point; the editor's incremental
`FindNearestVertex` keeps it distinct.

## The one residual (all else byte-exact)

`BODY polys polys@model model2` (world CSG soup): 3 coplanar `Step` faces differ in `FPoly.Base` only.
Owner brush `Brush405`, `ilink` 151/153/155 (identical native/ued), `Item=Step`:

- normal `(0, 0, 1)` (a horizontal / Z-facing top face)
- native base `(0.0006103515625, -3072.0, -152/-144/-136)` — snapped; IS a point of Model2.Points
- ued base `(-0.0003662109375, -3072.000244140625, same z)` — raw; NOT in either (byte-identical) table
- `d_euclid = 1.007e-3`; **`dW = base·normal = 0` exactly** — the node plane is bit-identical, no
  node-W residual. The divergence is purely the in-plane X,Y of the soup FPoly.Base.

Points table 76/76 byte-identical both sides.

## Resolution path: faithful fix (prime directive), not a wider mask

Per `NATIVE-MATERIALIZE.md` "Prime directive", an algorithmic divergence is fixed toward UED22's own
algorithm, not masked. So N19 is NOT covered by widening the gate's PB-tie tolerance; it is fixed by
the faithful `FindNearestVertex` incremental point-dedup — the SAME fix that retires the x=448/N8
stopgap mask. That fix is being spiked (2026-09-05). The earlier "widen the mask?" question is
withdrawn: the directive answers it. N19 resolves when the spike lands; until then WanChai holds at N=18.

## Evidence

Native/ref N19 under `_scratch/actor-parity/06_hongkong_wanchai_market/{native,ref}_N19.dx`.
Reproduce: `parity_gate.py native_N19.dx ref_N19.dx`.
