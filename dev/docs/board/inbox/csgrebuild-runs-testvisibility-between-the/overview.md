+++
priority = "p2"
kind = "debug"
summary = "csgRebuild calls TestVisibility BETWEEN the world repartition and the detail-brush loop, not after it — reordering native's zone pass closes the UNATCO node gap to 0 (6314/6314) and fixes leaves 2739→762 and zones 10→7"
+++

# `csgRebuild` runs `TestVisibility` between the repartition and the detail-brush loop

Native ran its zone/visibility pass (`finalize` → `zones::assign_leaves_and_zones`, i.e. UnrealEd's
Pass A–D) LAST, after the semisolid/detail-brush CSG layer. The real editor runs it in the MIDDLE.

## Evidence

**[DISASM `Editor.dll 0x4a650` (`UEditorEngine::csgRebuild`)]** — the call sequence, by address:

| address | call | what |
|---|---|---|
| `0x1004a870` | `[edx+0x214]` | `bspBrushCSG` — the STRUCTURAL brush loop |
| `0x1004a89a` | `[eax+0x1ec]` (Model, 0, 0) | `bspRepartition` — the world repartition |
| `0x1004a8af` | `[eax+0x264]` (Level, Model, 0, 0) | **`TestVisibility`** — leaves/portals/zones/Pass D |
| `0x1004a9e8` | `[edx+0x214]` | `bspBrushCSG` — the DETAIL brush loop |
| `0x1004aa3f`, `0x1004aa90` | `[eax+0x1ec]` (Model, iChild, 2) | per-node SUB-BSP repartitions (not ported) |
| `0x1004aab0` | `[eax+0x218]` | `bspOptGeom` |
| `0x1004aac0` | `[eax+0x208]` | bounds |

The vtable slots are the ones spec §1.1 already names (`+0x264` = `TestVisibility` → `AssignLeaves`,
`+0x218` = `bspOptGeom`).

**[LIVE, 734-brush UNATCO]** two new oracles, both committed under
`dev/docs/spikes/2026-07-15-native-materialize/harness/editor-tree-oracle/`:

- `repart_stage_unatco.py` — the five `bspRepartition` sub-stage counts. The editor's world
  repartition returns **2953 nodes**, byte-for-byte native's own number.
- `repart_tree_unatco.py` — the whole `Model->Nodes` array at `0x1004a05f` (right after
  `bspRefresh(Model, 1)` inside `bspRepartition`). Diffed node-for-node against native's own
  post-repartition dump: **2953 vs 2953, zero mismatches** on `NumVertices`/`iBack`/`iFront`/
  `iPlane`/`NodeFlags`/plane, and `iSurf` is a clean bijection (1633 surfs used on both sides). The
  repartition — soup, `bspMergeCoplanars`, `FindBestSplit`, `SplitPolyList`, `bspAddNode`,
  `bspRefresh` — is exact at real production scale.
- `brushcsg_calls_unatco.py` — one line per `bspBrushCSG` call with `Model->Nodes.Num` and the
  length of a watched node's coplanar chain. The editor's FIRST detail-loop brush already sees
  **2984 nodes** (+31 over the repartition's 2953) and the watched `(0,-1,0,32)` chain already at 26
  (from 10). Nothing but `TestVisibility` runs in between.
- `repart_tree_diff.py` and `surf_node_diff.py` — the offline halves: the first diffs the two
  post-repartition dumps node-for-node, the second reduces a whole-tree node-count gap to the
  individual source faces it hangs off (which is what localized this one to `Brush507`).

## Why the old order was wrong twice over

Pass D splits a coplanar face into one fragment per `(frontLeaf, backLeaf)` landing. Running it after
the detail layer meant (a) the detail brushes filtered through an unfragmented tree, and (b) Pass D
then re-fragmented faces the detail layer had already cut. Measured on UNATCO: Pass D emitted **+81**
nodes where the editor emits **+31**, and the leaf enumeration ran over the 6283-node tree instead of
the 2953-node one.

Since the editor never re-runs `TestVisibility` inside `csgRebuild`, the leaves it writes go STALE
against the finished tree. That is the real editor's own bare-`MAP REBUILD` output, not something to
paper over: spec §14 records 9.45 node `iLeaf` refs per leaf for exactly this reason, and native now
reproduces it (762 leaves, 7204 refs).

## Result on the full 734-brush UNATCO map

Against the real editor golden `/tmp/UEDGolden_unatco_full.dx` (bare `MAP REBUILD`):

| dimension | native before | native after | editor golden |
|---|---:|---:|---:|
| nodes | 6364 | **6314** | 6314 |
| surfs | 3616 | 3616 | 3616 |
| vectors | 599 | 599 | 599 |
| leaves | 2739 | **762** | 762 |
| zones | 10 | **7** | 7 |
| bounds | 3641 | 3641 | 3641 |
| leaf hulls | 25084 | 25084 | 25084 |
| NumSharedSides | 13064 | 13064 | 13064 |
| points | 10810 | 10758 | 10752 |
| verts | 95049 | 66037 | 76488 |

Per-surf node counts now match on **all 3616 surfs** (was 3 surfs / +50), and the synchronized
tree-structural walk matches **6314 of 6314 nodes with zero divergence points** at the 0.05 plane
tolerance that looks past the separately-filed rotated-brush normal drift.

## Change

`uedcli-native/src/bspcsg.rs`: `finalize`'s zone half is split out as `zone_pass` and called between
the repartition and the detail loop, bracketed by `swap_node_children` (the pass reads the engine
child convention; the detail loop needs native's back). `finalize` keeps only the convention swap,
the `NF_IsNew`/`iRenderBound` reset and the world bbox.

`passes::bsp_build_bounds` now re-runs Pass E (`zones::build_zone_masks`, made public), which is
step 1 of the editor's own `bspBuildBounds` (spec §8) and had no port. It is load-bearing once the
zone pass moves: a node the detail layer appends afterwards is born with `ZoneMask` all-ones and is
stamped only here. Before this, 3330 of UNATCO's 6314 nodes shipped the `0xFFFFFFFFFFFFFFFF`
sentinel; now none do.

Also added `UEDCLI_BSPCSG_STAGE_COUNTS` (node/vert/point counts per pipeline stage) and
`UEDCLI_BSPCSG_REPART_NODES` (the post-repartition node array, in the new editor oracle's own line
format). `cargo test --release` 57/57.

## Still open

- `Verts` 66037 vs 76488 — the whole gap is `csgRebuild`'s ~209 per-node sub-BSP repartitions
  (`0x1004aa3f`/`0x1004aa90`), which native does not port. `bspOptGeom`'s weld itself is already
  exact (+21712 on both sides). Filed as `unatco-verts-points-residual-after-the-zone`; read that
  before touching `bspoptgeom.rs`.
- 23 nodes whose `iPlane` and 3 whose `iBack` differ from the golden's — same chain contents, so the
  tree-structural walk sees no divergence. Filed as `pass-d-chain-link-order-native-splices-zone`.
- Detail-layer nodes carry `iZone = (0,0)` because `bsp_add_node` does not inherit zones from the
  parent the way the editor's does. Filed as `bspaddnode-does-not-seed-a-new-node-izone-ileaf`, with
  the fresh decode.
