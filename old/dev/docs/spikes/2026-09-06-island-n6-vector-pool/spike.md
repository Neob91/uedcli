# Island N=6 — the world `Model2` Vectors pool order

**Result: fixed faithfully, no mask.** Native now KEEPS the incremental-CSG Vectors pool across the
repartition (as UED22 does) instead of rebuilding it from the surviving Surfs. Island N=6 gates
byte-exact. Board item: `island-n6-vector-pool-order` (now in `done/`).

## The divergence

One gate residual, `BODY model model2`. `points`, `nodes`, `leaves`, `bounds`, `leafhulls` all
byte-identical; `vectors` (19 both sides), `surfs` and `verts` differed only through one pool index:
`(0.242536, 0.970142, 0)` sat at index 8 in UED22 and 16 in native, with UED22's 9..16 = native's
8..15.

The board item had traced it to a `bspAddVector` call the editor makes that native's
canonical-surf-order pool walk cannot account for, and — because only `surfs[24]`'s NORMAL follows
the hoisted slot while its texture axes do not — concluded that slot 8 was claimed by a normal-only
`bspAddVector`. That conclusion was wrong; the live trace shows a TEXTURE AXIS claimed it.

## What the live probe pinned

`bspAddVector` (`Editor.dll 0x10035530`) is virtual, so no `E8` call to it exists in `.text`. Its
`UEditorEngine` vtable slot is `+0x1f0` (`bspAddPoint` `+0x1f4`, `bspRefresh` `+0x200`, `bspAddNode`
`+0x224`, vtable base `0x100cf5d4`), and every call to it goes through `mov reg,[vt+0x1f0]; call reg`
— which a `call dword ptr [reg+disp32]` scan misses. Outside the interactive texture tools
(`polyTexAlign`/`polyTexScale`, not reached by `MAP REBUILD`) the ONLY call sites are the three in
`bspAddNode`'s surf-allocation block: `0x10034f39` `vNormal` (`Exact=1`), `0x10034f55` `vTextureU`
(`Exact=0`), `0x10034f71` `vTextureV` (`Exact=0`).

`harness/addvector_call_trace.py` breaks at the function entry (reading the caller off `[esp]`) and
at its single `ret 0xc` (`0x100355a7`), with phase markers on `csgRebuild`/`bspBrushCSG`/`bspBuild`/
`bspRefresh`/`TestVisibility`/`bspAddNode`. One `MAP IMPORT` + `MAP REBUILD` of the N=6 subset
(`logs/addvector-call-trace.log`, 177 calls; `harness/parse_addvector_trace.py` summarises it):

All 177 calls came from those three sites (59 each) — no other caller exists at rebuild time.

| fact | value |
|---|---|
| world `UModel` | `0x587ce8c` (87 hits); `0x2610ec` is `bspBrushCSG`'s per-brush `TempModel` |
| world pool before the GC | 20 vectors, all proposed from `bspAddNode` |
| slot 8's first claim | call `n=77`, `Brush1355` bottom face (`N=(0,0,-1)`), **`vTextureU`** `(0.242535993, 0.970142007, 0)` |
| slot 9's first claim | call `n=78`, the same face's `vTextureV` `(0.970142007, -0.242535993, 0)` |
| slot 8's second referrer | call `n=148`, `Brush1353`'s oblique-face **`vNormal`** `(0.242535651, 0.970142603, 0)` → `idx=8` |
| final pool | the 20 minus slot 9 — the bottom-face surf is merged away, so only its `vTextureV` is unreferenced |

`bspAddVector` → `AddThing` (`0x10031ae0`, `Check=1`) takes the FIRST pool entry within a
per-COMPONENT box of the threshold — `2e-5` when `Exact` (`0x100dcaf0`), `4e-4` otherwise
(`0x100dcaf4`). The axis and the normal agree to 3.4e-7 / 6.0e-7, so the normal lands on the axis's
slot even at the tighter `Exact` threshold.

So the pool's on-disk order is the order `bspAddVector` first proposed each SURVIVING vector during
incremental CSG, and a surf CSG later merges away still leaves its proposals in it. A rebuild from
the surviving surfs cannot reproduce that.

## The fix

Native's incremental pool was already byte-identical to the editor's pre-GC pool (measured with
`UEDCLI_BSPCSG_POOLDUMP=1`: same 20 vectors, same order, same 29 incremental surfs). It was being
thrown away: the repartition checkpoint cleared `model.vectors`, and a post-build
`rebuild_vector_pool` re-derived the pool by walking the canonical Surfs.

`bspcsg.rs` now keeps `model.vectors` across the repartition — exactly as it already keeps
`model.points` for the same reason (`EmptyModel(0,0)` clears Nodes/Verts only) — and
`rebuild_vector_pool` is deleted. `bsp_build`'s re-allocated surfs resolve their axes against the
preserved pool via the normal `bsp_add_vector` find-or-add, and the existing
`bsp_refresh_points_vectors` GC drops the entries no surviving surf references, order-preserving.

## Evidence

- `parity_gate.py` on Island N=6: PASS, byte-exact, no new mask. The ladder now reaches N=9 and bails
  at N=10 on an unrelated `Brush1359.Region` iLeaf token.
- `ladder_run.py` re-verification after the change: UNATCO N=1..28 PASS (bails at 29, unchanged),
  WanChai 1..44 (bails at 45, unchanged), NYC_Bar 1..58 (bails at 59, unchanged), OceanLab 1..43
  (bails at 44, unchanged).
- Regression `2026-09-03-incremental-actor-parity/harness/test_island_n6_vector_pool.py`: builds
  native from the 6-actor subset trunk committed in `golden/subset/` and gates it against
  `golden/ref_N6.dx` (the UED22 build). Verified to go RED when the fix is reverted.
- Rust `a_texture_axis_absorbs_a_later_near_equal_normal`: the 6e-7 dedup that makes slot 8 survive.

## Loose ends found on the way

- `bsp_add_vector` compares EUCLIDEAN distance; `AddThing` compares each component against the
  threshold independently (a box, which is strictly looser). Not the cause here and not changed in
  this pass — board `bsp-add-vector-uses-a-sphere-where-addthing`. It matters more now: the pool this
  dedup builds is the one that ships.
- The trace also shows the editor makes **zero** `bspAddVector` calls after `bspRepartition` and
  leaves `Surfs.Num` at 29 throughout it — it never re-allocates a surf. Native still clears and
  re-allocates Surfs at that checkpoint and re-resolves each axis against the preserved pool, so a
  re-derived axis that drifted by less than the threshold is now absorbed into the old slot instead
  of surfacing. Keeping `model.surfs` too is the faithful end state — board
  `native-re-allocates-surfs-at-repartition-where-ued22`.
