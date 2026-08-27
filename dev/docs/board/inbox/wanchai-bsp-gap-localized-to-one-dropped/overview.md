+++
priority = "p1"
kind = "debug"
summary = "Wanchai BSP gap localized to one dropped Subtract face on Brush250"
+++

# Wanchai BSP gap localized to one dropped Subtract face on Brush250

Follows `native-bsp-matches-the-editor-on-unatco-but-not`, which reported the gap from the lighting
work. That item's numbers reproduce exactly here; this one bisects them. No fix landed, and the
causal chain from the divergence found in §4 to the final node gap is NOT established — see §5.

Level: `06_HongKong_WanChai_Market.dx`, ingested trunk = 2288 actors / 1304 world CSG brushes (both
larger than UNATCO's 1437 / 734). The sibling item names the same level as
`09_HONGKONG_WANCHAI_MARKET` from a differently-named trunk copy; the two trunks are the same content
— an editor golden built here from an independent copy matched the lighting session's golden
byte-for-byte on every geometry section.

## 1. The gap is real, and it is not a golden-construction artifact

Two independently built editor goldens — one by the native-lighting session, one built fresh here
from the same trunk with `harness/build_ued_golden.py --world-only --no-light` (`MAP NEW` →
`EDIT PASTE` → `MAP REBUILD` → `MAP SAVE`) — agree on every geometry section, exactly. So the gap
below is native's, not the golden's.

| section          | native | editor golden | Δ |
|------------------|-------:|--------------:|---
| vectors          |    481 |           487 | −6 |
| points           |  16522 |         16791 | −269 |
| nodes            |  11381 |         11648 | −267 |
| surfs            |   5283 |          5284 | −1 |
| verts            | 165125 |        169313 | −4188 |
| num_shared_sides |  26217 |         26712 | −495 |
| zones            |      8 |             5 | +3 |
| bounds           |   4659 |          4758 | −99 |
| leaf_hulls       |  40700 |         41141 | −441 |
| leaves           |   3240 |          3371 | −131 |

UNATCO control, re-measured with the same pipeline both before and after merging the native lighting
bake (`033408b`): nodes 6314, surfs 3616, vectors 599, zones 7, leaves 762, bounds 3641, leaf_hulls
25084, num_shared_sides 13064 — all exact. Residual there is unchanged and still open: points +6,
verts −10451.

## 2. Where in the pipeline it starts

`csgRebuild` stage counts, native (`UEDCLI_BSPCSG_STAGE_COUNTS`) vs editor (live gdb,
`harness/editor-tree-oracle/repart_stage_unatco.py` run against the Wanchai golden — the script
takes the golden path as `argv[1]`, so it is not UNATCO-specific despite the name):

| stage                                                    | native nodes | editor nodes |
|----------------------------------------------------------|-------------:|---
| committed incremental CSG tree (`bspRepartition` entry)   |        21148 | 21147 |
| repartition soup handed to `bspBuild` (polys, not nodes)  |         8190 | 8187 |
| after repartition + `bspRefresh`                          |        10785 | 11011 |
| after `TestVisibility`                                    |        10835 | — |
| after the detail-brush loop                               |        11381 | 11648 |

So −226 of the final −267 is created inside `bspRepartition`, and the remaining −41 in the
`TestVisibility`+detail-brush layer downstream of it. Native's `SplitPolyList` turns a soup of 8190
into 2595 splits where the editor turns 8187 into 2824.

## 3. The repartition's root splitter differs

Nothing below the root is comparable index-for-index:

- editor root node plane `(-0.0, 0.40082, -0.91616, -157.57904)` — a slanted face
- native root node plane `(-0.0, -1.0, -0.0, 512.0)` — an axis-aligned one

`FindBestSplit` runs `GOOD` at the repartition (`Balance=12`, `PortalBias=0`, hardcoded immediates
at `Editor.dll 0x1004a02f/0x1004a031`), so the candidate stride is `Inc = NumPolys/20` = 409 at
this soup size — see board item `unrealed-geometry-build-map-rebuild-bsp-rebuild`'s `spec.md` §5.2
/ §5.3 item 2 [DISASM]. Slot `k`'s candidate is the first eligible poly at or after index `k·409`,
so a soup offset by even one entry picks a different candidate from the first slot onward. At
UNATCO's soup (~2500, stride ~125) the same offset perturbs less. That is why a 3-poly soup delta
is a plausible explanation for a 226-node partition delta — plausible, not shown; see §5.

## 4. One divergence in the committed CSG tree: an extra Subtract face on `Brush250`

Index-for-index diff of the two committed pre-repartition trees (`committed_tree_diff.py` +
`committed_tree_side.py` over `UEDCLI_BSPCSG_TREE_STRUCT` vs the new `ed_committed_tree.py`, §6):

- native 21148 nodes / editor 21147; dead-node (`nv==0`) counts identical at 5114 each, so native
  has exactly one extra live node;
- the two trees are identical index-for-index through node 20445 (only sub-grid plane-`w` twins
  differ);
- at index 20446 native inserts one node — plane `(0, 0, 1, 112)`, `nv=4`, no children, its own
  fresh surf — and from 20447 on native node `i+1` == editor node `i`, and native surf `j+1` ==
  editor surf `j`, to the end. One clean insertion, nothing else.

That node is the bottom face of `Brush250`, a `CSG_Subtract` cube: `Location=(-16,-912,144)`,
`PrePivot=(8,8,8.000002 on Y)`, `PostScale=(14,6.999995,2)` → world box x ∈ [−240,−16],
y ∈ [−1023.99993,−912], z ∈ [112,144]. (The authored Y prepivot/scale noise is what reproduces the
editor's stored `-1023.99994`, not a clean −1024.)

**What identifies the brush is contiguity plus consecutive surf numbering, not plane equality** —
these planes recur level-wide (`(0,0,1,112)` appears at 14 other editor nodes; `(0,-1,0,912)` 118
times). Editor nodes 20445–20457 + 20484–20486 are `Brush250`'s contiguous block, holding
consecutive fresh surfs 5195–5199:

| surf | stored plane (Subtract reverses the winding) | brush face (world) |
|------|---------------------------------------------|---
| 5195 | `(0,0,-1,-144)`                             | z = 144, outward `(0,0,1)` |
| —    | `(0,0,1,112)`                               | z = 112, outward `(0,0,-1)` — native only |
| 5196 | `(0,-1,0,912)`                              | y = −912, outward `(0,1,0)` |
| 5197 | `(0,1,0,-1023.99994)`                       | y = −1024, outward `(0,-1,0)` |
| 5198 | `(-1,0,0,16)`                               | x = −16, outward `(1,0,0)` |
| 5199 | `(1,0,0,-240)`                              | x = −240, outward `(-1,0,0)` |

Five of six faces, no z=112, and editor node 20458 starts a different brush. Native's block holds
all six and shifts every later surf by one. `Brush250` was first located from the plane set with
`actor find --within-bbox -250,-1034,102,-6,-902,154` (one hit).

## 5. What is ruled out, and what is still open

**Ruled out**

- Golden construction / pipeline choice — two independent goldens agree exactly (§1), and both used
  the paste route that is proven exact on UNATCO.
- Actor-set contamination — the golden is `--world-only`, 1305 kept actors (1304 brush +
  LevelInfo), no mover pasted as a world brush; native builds the same 1304 through
  `brush_marshal._in_world_csg`.
- A diffuse, level-character-wide CSG failure — the committed trees match to node 20445 of 21147.

**Open — the soup delta may be a SECOND, independent defect.** The tempting reading is that the +3
soup polys are just downstream of §4's +1 committed node. That does not follow, and the board holds
a counterexample: `editor-unatco-repartition-soup-size-unknown` measured UNATCO with these same
instruments and found the committed trees *identical* (0 structural nodes, 6368 = 6368) yet the
soups 10 apart (native 2504 vs editor 2514). A soup delta arose there with a zero committed-node
delta. Nor does the arithmetic close here: one extra 4-vertex childless node contributes +1 fpoly
through `bspBuildFPolys`; where the other +2 come from is unmeasured. `ed_soup.py` (§6) exists to
settle this and has not been run.

**Open — whether §4 causes the node gap at all.** Nothing here shows that suppressing native's
extra face makes native's tree match. The same UNATCO item concluded the opposite for that level —
that its residual "cannot be explained by soup composition" and "sits entirely in
`SplitPolyList`/`FindBestSplit`'s own split choices". Unreconciled. One fact points the other way
too: native starts the repartition with one *more* node and one *more* surf and ends with fewer of
everything (§1 surfs 5283 vs 5284). That is not explained.

**The cheapest decisive test, and it needs no live editor:** force-drop `Brush250`'s z=112 face in
native, rebuild, and see whether nodes go 11381 → 11648. That settles causality offline in a minute.
Run it before any further disassembly.

**Then, why the editor drops that face.** `SubtractBrushFromWorldFunc` adds a node only on
`F_INSIDE(1)` / `F_COPLANAR_INSIDE(3)` — no cospatial case
(`unrealed-geometry-build-map-rebuild-bsp-rebuild`'s `spec.md` §3.4 [DISASM]). So the editor must
classify the z=112 face as something else. Two candidate mechanisms:

1. the face is cospatial with an existing world floor face at z=112, the editor enters the coplanar
   cascade (`EPolyNodeFilter`, same `spec.md` §3.3) and gets `F_COSPATIAL_FACING_IN/OUT` (4/5) →
   drops it, while native's cascade yields `(in,in)` → `F_COPLANAR_INSIDE(3)` → adds it. Note that
   `spec.md` §3.3 carries its own `[OPEN]` citation conflict over which pair maps to 4 vs 5;
   native's `bspcsg.rs` `filter_leaf` implements the higher-confidence table, which has never been
   independently re-resolved against the binary.
2. native never enters a cascade (`coplanar.i_original_node == -1`) and takes the plain
   `leaf_outside==false → F_INSIDE` arm, because its descent misses the coplanar node the editor
   hits — a descent/tree-shape or `±0.25`-band question, not a classification-table one.

`UEDCLI_BSPCSG_DESCENT=<iLink of that face>` against the editor's `editor_descent.py` distinguishes
them: if the editor's descent reaches a coplanar node native's does not, it is (2); if both reach it
and only the returned filter value differs, it is (1) — and (1) then demands fresh disassembly of
`FilterLeaf` (`Editor.dll 0x33130`) to settle the 4-vs-5 conflict the drop hangs on.

## 6. Tooling and evidence added by this item

Three new tools under `dev/docs/spikes/2026-07-15-native-materialize/harness/editor-tree-oracle/`.
The two oracles take the golden `.dx` as an argument; the pre-existing `editor_struct_unatco.py` and
`editor_polys_oracle.py` are hardcoded to a developer path and to the castle / N-brush subsets, so
neither runs on a whole real level.

- `ed_committed_tree.py <golden.dx> <out.log>` — the editor's committed pre-repartition
  `Model->Nodes`, dumped once at `bspRepartition` entry (`Editor.dll 0x49fc0`) and detached. Emits
  `committed_tree_diff.py`'s `ND …` format, so it pairs with native's `UEDCLI_BSPCSG_TREE_STRUCT`.
- `committed_tree_side.py <native.log> <editor.log> <lo> <hi>` — side-by-side of the two dumps over
  an index range. `committed_tree_diff.py` reports only counts and the first structural index; this
  is what showed the +1 shift and the surf renumbering in §4.
- `ed_soup.py <golden.dx> <out.log>` — the editor's repartition soup (`Model->Polys->Element`,
  planes + full vertex rings) at the `bspBuild` call site inside `bspRepartition` (`0x1004a041`).
  Emits native's `UEDCLI_BSPCSG_SOUP_ORDER` format for `polys_order_diff.py`. NOT YET RUN.

The four editor-side captures behind §2–§4 are committed beside them, so the next session need not
re-run the live editor for any of them: `logs/wanchai-ed-committed-tree.log`,
`logs/wanchai-ed-repart-tree.log`, `logs/wanchai-ed-repart-stage.log`,
`logs/wanchai-ed-repart-numpolys.log`. The native-side dumps are not committed — `native_dumps.py`
(§7) regenerates them offline in under a minute.

`tests/test_wanchai_committed_tree.py` pins §4's editor-side facts against those committed logs
(21147 nodes, 5114 dead, `Brush250`'s five-face block at 20445, no z=112 in it). It does not pin the
native side, which needs the Rust extension and is covered by the reproduce path instead.

## 7. Reproduce

```
# trunk: _scratch/proj/maps/wanchai (harness/ingest_dx_trunk.py from 06_HongKong_WanChai_Market.dx;
# needs --search DX/Sounds --search DX/Music as well as the two texture dirs)
H=dev/docs/spikes/2026-07-15-native-materialize/harness
.venv/bin/python -u $H/build_ued_golden.py --trunk _scratch/proj/maps/wanchai \
  --out _scratch/golden_wanchai_world.dx --world-only --no-light --overwrite
UEDCLI_NATIVE_MATERIALIZE=1 bin/uedcli --project _scratch/proj level materialize \
  --tree level/wanchai --out _scratch/native_wanchai.dx --overwrite --no-verify

# native-side stage counts and dumps (offline, no editor)
.venv/bin/python $H/editor-tree-oracle/native_dumps.py _scratch/proj _scratch/proj/maps/wanchai \
  --stage-counts --tree-struct _scratch/native_struct.log --soup-order _scratch/native_soup.log

# editor-side (live, bounded; the four logs are already committed)
.venv/bin/python $H/editor-tree-oracle/repart_stage_unatco.py _scratch/golden_wanchai_world.dx
.venv/bin/python $H/editor-tree-oracle/repart_numpolys_unatco.py _scratch/golden_wanchai_world.dx
.venv/bin/python $H/editor-tree-oracle/ed_committed_tree.py _scratch/golden_wanchai_world.dx \
  _scratch/ed_committed.log

# the §4 diff
.venv/bin/python $H/editor-tree-oracle/committed_tree_diff.py \
  _scratch/native_struct.log $H/editor-tree-oracle/logs/wanchai-ed-committed-tree.log
.venv/bin/python $H/editor-tree-oracle/committed_tree_side.py \
  _scratch/native_struct.log $H/editor-tree-oracle/logs/wanchai-ed-committed-tree.log 20440 20500
```

This item changed no `uedcli-native` code; `cargo test --release` is 58/58 green.

## 8. Stale spike numbers this supersedes (needs the owner's yes to edit)

`sections/85-hkmarket-parity.md` (2026-07-19) reports native at 5428 nodes / 2664 surfs on this
level and concludes native "under-builds by roughly half" with "64 native zones vs 5 editor". Native
now builds 11381 / 5283 / 8 zones. So §85's headline is stale because NATIVE CHANGED, not because
its reference was unfair — its shipped-map reference (11849 / 5224) is within ~2 % / ~1 % of this
golden. The proposed correction is in `questions/85-hkmarket-parity-numbers-are-stale.md`; §85 is
left untouched until answered.
