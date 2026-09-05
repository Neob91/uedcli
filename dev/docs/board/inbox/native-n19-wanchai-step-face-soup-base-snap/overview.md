+++
priority = "p2"
kind = "debug"
summary = "native N19 WanChai Step face soup-base snap exceeds 5e-4 PB-tie mask (dW=0)"
+++

# native N19 WanChai Step face soup-base snap exceeds 5e-4 PB-tie mask (dW=0)

WanChai `06_HongKong_WanChai_Market` passes the parity gate at N=1..18 and FAILS at N=19. Same
base-dedup class as `done/native-n8-unatco-rotated-brush-base-fp-diverges` (owner-ruled EXCLUDE), but
the deviation exceeds the implemented `NODE_W_DEDUP_TOL = 5e-4` mask, so the gate does not cover it.

## The one residual (all else byte-exact)

`BODY polys polys@model model2` (world CSG soup): 3 coplanar `Step` faces differ in `FPoly.Base` only.
Owner brush `Brush405`, `ilink` 151/153/155 (identical native/ued), `Item=Step`:

- normal `(0, 0, 1)` (a horizontal / Z-facing top face)
- native base `(0.0006103515625, -3072.0, -152/-144/-136)` — snapped; IS a point of Model2.Points
- ued base `(-0.0003662109375, -3072.000244140625, same z)` — raw; NOT in either (byte-identical) table
- `d_euclid = 1.007e-3`; **`dW = base·normal = 0` exactly** (z is identical) — the node plane is
  UNAFFECTED, and there is NO Model/node-W residual. The divergence is purely the in-plane X,Y of the
  soup FPoly.Base.

Mechanism = the known one: native's linear-scan `bsp_add_point` snaps the raw base onto a nearby
own-Model point (here `(0.00061, -3072.0)`), losing ~1e-3 in X,Y; the editor's `FindNearestVertex`
spatial-index keeps the raw base distinct. Points table 76/76 byte-identical both sides.

## Why it is not covered / not self-fixable

- Gate PB-tie mask (`parity_gate.py` `_poly_base_tie`) masks iff `d <= 5e-4 AND native base is a real
  own-Model point`. Here the second condition holds but `d = 1.007e-3 > 5e-4`.
- Faithful native fix = reproduce the editor's incremental-tree wiring + `FindNearestVertex` dedup =
  the multi-week `bspcsg.rs` core rewrite the owner ruled out for N8 (built + reverted twice there).
- No scoped native fix: linear-scan dedup cannot selectively miss without regressing the 76/76 table.

## Note vs the N8 exclusion

N8's excluded case had a REAL `dW = 2.16e-4` (node plane offset), justified inconsequential against the
`±0.001` zero-extent line-trace band. This WanChai case is STRICTLY more inconsequential: `dW = 0` (the
plane is bit-identical), the only diff being the persisted soup-base X,Y — CSG-rebuild scratch, not a
runtime geometry field. But the mask keys on Euclidean base `d`, and `1.007e-3 > 5e-4`, so it fails.

See `questions/widen-pb-tie-mask.md` for the proposed decision.

## Evidence

Native/ref N19 under `_scratch/actor-parity/06_hongkong_wanchai_market/{native,ref}_N19.dx` (worktree
`worktree-agent-aa080191056878d3f`). Reproduce: `parity_gate.py native_N19.dx ref_N19.dx`. Field diff
via the per-FPoly parser in this session's transcript (num/base/normal/actor/ilink/item decode).
