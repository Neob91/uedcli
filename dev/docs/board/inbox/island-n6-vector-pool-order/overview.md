+++
priority = "p2"
kind = "debug"
summary = "Island is byte-exact N=1..5 and FAILS at N=6: one world Model2 Vector sits at pool index 8 in UED22 and 16 in native. Same 19 vectors, same relative order otherwise; only the surfs' vNormal/vTextureU/vTextureV indices follow."
+++

# Island N=6 world-`Model2` vector-pool order

Found 2026-09-06 extending the ladder after `a762617` closed N=5
(`island-n5-n12-pre-existing-model2-orphan-vert-4`). N=6 adds `Brush1353`, the mirrored east
seawall.

## The divergence

One gate residual, `BODY model model2`. `points` (81), `nodes` (46), `leaves`, `bounds`,
`leafhulls` are all byte-identical; `vectors` (19 both sides), `surfs` and `verts` differ **only**
through one pool index:

    UED22   vectors[8]  = (0.24253599345684052, 0.9701420068740845, 0.0)
    native  vectors[16] = the same value

Every other vector keeps its relative order, so UED22's 9..16 are native's 8..15. The vector is
`Brush1353`'s oblique-face normal and only `surfs[24]` (its own face) references it.

UED22's pool IS native's canonical-surf walk with exactly one entry hoisted to the front of the
"new" block:

| UED22 idx | value | proposed by |
|---|---|---|
| 8 | `( 0.242536,  0.970142, 0)` | `surfs[24].vNormal` — hoisted |
| 9 | `(-0.242536, -0.970143, 0)` | `surfs[13].vNormal` |
| 10 | `( 0.485071, -0.121268, 0)` | `surfs[13].vTextureU` |
| 11 | `( 0, 0, -0.5)` | `surfs[13].vTextureV` |
| 12 | `(-0.246097,  0.969245, 0)` | `surfs[14].vNormal` |
| 13 | `(-0.484579, -0.123221, 0)` | `surfs[14].vTextureU` |
| 14 | `( 0, -0.499999, 0)` | `surfs[15].vTextureU` |
| 15 | `(-0.121268, -0.485071, 0)` | `surfs[23].vTextureU` |
| 16 | `(-0.485071,  0.121268, 0)` | `surfs[23].vTextureV`, `surfs[24].vTextureU` |
| 17 | `( 0.246097, -0.969245, 0)` | `surfs[25].vNormal` |
| 18 | `( 0.484623,  0.123049, 0)` | `surfs[25].vTextureU` |

Only the NORMAL is hoisted — `surfs[24]`'s own texture axes stay at 16/11. `bspAddNode` adds a new
surf's `vNormal`, `vTextureU` and `vTextureV` together, so a ghost surf created early would have put
its `vTextureU` `(-0.485071, 0.121268)` at slot 9 too, and it is at 16. So slot 8 was claimed by a
`bspAddVector` call that adds a normal ALONE. Finding that call site is the crux.

## What is known

- Native builds its final pool in `bspcsg.rs::rebuild_vector_pool`, which walks the surf array in
  `reorder_surfs_canonical` order and appends each surf's `vNormal`, `vTextureU`, `vTextureV`. The
  surf array order itself MATCHES UED22 (surfs 12-16 `Brush1355`, 17-21 `Brush1359`, 22-27
  `Brush1353`), so a surf-order walk cannot put `surfs[24]`'s normal at 8.
- Native's PRE-rebuild (incremental-CSG) pool is a third order again — index 8 there is
  `(-0.121268, -0.485071, 0)`, a texture axis — so neither of native's two orders is UED22's.
- So UED22 proposes `Brush1353`'s oblique normal to `bspAddVector` BEFORE `Brush1355`'s
  (`(-0.242536, -0.970143)`, UED22 index 9), i.e. before the first surf of the brush that precedes
  it in trunk order. Why is the open question: a surf created early and later merged away
  (`bspRefresh`'s vector GC is order-preserving, so the survivor keeps its FIRST-proposal slot), or a
  CSG/`bspAddNode` order native does not reproduce.

Next step: find UED22's normal-only `bspAddVector` call site. `bspAddVector` is
`Editor.dll 0x35530` (`?bspAddVector@UEditorEngine@@UAEHPAVUModel@@PAVFVector@@H@Z`) and is
**virtual**, so a scan of `.text` for `E8`-relative calls to it finds none — resolve its
`UEditorEngine` vtable slot first, then scan for `call dword ptr [reg+slot]`.

## Repro

    ladder_run.py --dx <…>/Maps/01_NYC_UNATCOIsland.dx --from 6 --to 6 --keep-native
    model_dump.py <…>/native_N6.dx <…>/ref_N6.dx Model2
