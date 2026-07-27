# 80 — bspBuild topology: why the native tree leaks, and the leaf-bounding collision repair

**Date:** 2026-07-17. **Status:** collision Z-sink FIXED (live-verified); exact node-for-node
topology parity is an N-2+ residual (measured + tracked below).

This section answers the phase-1 question — *why is the native BSP tree not byte-identical to
UnrealEd's, and how do we at least make its swept-box collision behave identically?* It supersedes
the coordinator's working hypothesis that `bspBuild` contains a "leaf-bounding pass that bounds
every solid leaf, adding nodes" — **instruction-level decode proves no such pass exists** (evidence:
`../re-raw-zones/bspbuild-splitpolylist-decode.md`).

> **CORRECTION (2026-07-17):** Several passages below attribute the editor's watertightness to "the
> brush's own temp-BSP **bevel planes**". Full instruction-level decode of the `bspBrushCSG` filter
> half (`sections/82-bspbrushcsg-port-decode.md` + `re-raw-zones/bspbrushcsg-filter-decode.md`) shows
> **there are NO bevel planes.** The temp brush BSP is a plain convex `bspBuild` of the brush's own
> face planes (used by `FilterWorldThroughBrush` to cut world faces). Watertightness comes from
> filtering each brush face down the growing world tree and adding the surviving OUTSIDE fragments as
> nodes carrying the brush's own face plane, each already clipped to its leaf cell by the ancestor
> planes. Read "bevel planes" below as "the brush's own face-plane fragments added incrementally".

---

## 0. TL;DR

- **Castle counts (native → editor golden `Test_Castle.dx`):** nodes 893→**1156**, FVerts
  3540→**16163**, surfs 438→485, points 1563→2035. After the collision repair here: nodes **909**,
  surfs 438 (unchanged), FVerts 3604. (`harness/bytediff_baseline.py`.)
- **UnrealEd's `bspBuild`/`SplitPolyList` is a PURE PARTITION** — one `bspAddNode` per splitter plus
  one per coplanar poly; an empty child list just ends the recursion. **No leaf-bounding / bevel /
  bounding-face node pass exists.** `bspBuild`'s tail is `bspRefresh` + `bspBuildBounds` (which fill
  the `Bounds`/`LeafHulls` *arrays* — they never add `Nodes`). 🔬
- **The editor tree is watertight because it is built INCREMENTALLY** by `bspBrushCSG`: each brush
  filters through the growing world tree and adds its surviving fragments as nodes, using the
  brush's own temp-BSP **bevel planes**. Our native path (CSG → coplanar-merge → ONE from-scratch
  `SplitPolyList` over lean convex faces) collapses those fragments and produces a **leaner,
  non-watertight** tree. 🔬
- **The live symptom.** In a leaked tree, some solid terminal cells are reached with the game's CSG
  `outside` propagation reading **EMPTY**. The game's swept-box collision
  (`FBoxLineCheckInfo::BoxLineCheck`, `Engine 0xf42f0`) does `if Outside: return` *before* reading
  the leaf hull (`../re-raw-zones/linecheck-oracle.md`), so it never lands on a leaked cell — the
  pawn sinks/falls through. Castle floor drop at (0,-250): pawn rested **z=35 native vs z=47 editor**
  (a 12-uu sink), because the box fell past the leaked stone-floor slab to the water sheet 12 uu
  below.
- **The repair (`build.rs::bound_leaked_solid_leaves`).** After the build, walk the tree; at each
  terminal cell whose propagation reads EMPTY but the point-in-solid oracle says SOLID (a *leak*),
  graft a synthetic **solid-bound node** whose plane is the parent's plane FLIPPED. It coincides
  with the parent (zero-volume front sliver) but is a solid CSG node, so descending into the cell
  now crosses it onto its BACK (solid) side: the live propagation reads SOLID, `assign_leaves` marks
  it solid, and `bspBuildBounds` emits its collision hull bounded by the cell's real ancestor faces
  (the floor plane it should rest on). **Result: native box-drops match the editor exactly; live
  pawn rests at z=47, phys=1.** Not a reproduction of any real editor pass — a synthetic topology
  repair that makes collision behave identically.

---

## 1. The editor pipeline (decoded) vs ours

Decode evidence + all VAs: `../re-raw-zones/bspbuild-splitpolylist-decode.md`.

`csgRebuild` (`Editor 0x4a650`):
1. `EmptyModel`; structural brushes → **incremental `bspBrushCSG`** (adds fragment nodes to the world Model).
2. `bspRepartition` = `bspBuildFPolys` (nodes→Polys) → `bspMergeCoplanars` → **from-scratch `bspBuild`/`SplitPolyList`** over the merged soup → `bspRefresh`.
3. `TestVisibility` (zones/portals).
4. Semisolid/nonsolid brushes → **incremental `bspBrushCSG` again, NOT repartitioned**.
5. `bspOptGeom` → `bspBuildBounds`.

Our native `build_geometry_from_brushes` (`build.rs`): per-brush CSG leaf-filter (`csg.rs`) building
a **surface FPoly list** → `bspMergeCoplanars` (`passes.rs`) → **one** `build_bsp_opt`
(`SplitPolyList` equivalent) → `finalize`/`zones`/`bspBuildBounds`.

**Where the gap is** (`bspbuild-splitpolylist-decode.md` §Verdict):
- **FVerts (3540 vs 16163, ≈4/node vs ≈14/node):** the editor repartitions *CSG-fragmented,
  coplanar-fused* faces that retain every CSG boundary/T-junction vertex; we repartition clean
  convex brush faces. `bspAddNode` stores `NumVertices` FVerts per node, so the fat faces dominate.
- **Nodes (893 vs 1156):** the editor's semisolid/detail brushes (LOOP 3) are filtered in
  incrementally after the repartition (never merged) + `TestVisibility` zone splits.
- **Watertightness:** the editor's incremental `bspBrushCSG` bounds every solid leaf by real
  fragment + bevel-plane nodes; our lean single-partition leaks.

Exact topology parity ⇒ port the incremental `bspBrushCSG` (temp-brush bevel planes + `FilterFPoly`
node adds) + the semisolid second layer. That is out of this section's scope (see §5).

---

## 2. The leak, concretely (castle floor at (0,-250))

Measured with `harness/line_check.py` (BoxLineCheck oracle) + `harness/drop_probe.py`:

| probe | native (pre-repair) | editor |
|---|---|---|
| point-region floor@ (0,-250) | z=-2 | z=-2 (AGREE) |
| swept box (0,-250,148)→(0,-250,-52), extent (20,20,44) | HIT center z=52, node 885 | HIT center z=64, node 1152 |
| the hit node's hull TOP plane | z=**-12** (the water sheet, node 15) | z=**0** (the stone floor, node 991) |

The point-region (zero-extent) agrees because the mis-flood workaround (`build.rs`, the `iLeaf`
patch) already corrects the *stored* `iLeaf` from the oracle. But the **box** trace recomputes
solidity live from the tree propagation, which the workaround cannot touch: the −2>z>−12 stone-floor
slab is a terminal cell whose propagation reads EMPTY (a distant wall's unbounded splitter flips
`outside` back to empty), so (a) `bspBuildBounds` emits no hull for it and (b) the box's
`if Outside: return` skips it → the box falls to the water cell 12 uu lower. Grid sample
(`prop_solid` vs the editor tree): **2434 leaked-solid cells** before repair.

---

## 3. The repair — `bound_leaked_solid_leaves` (`build.rs`)

Runs in BUILD convention (front child = `i_front`), right after `build_bsp_opt`, before `finalize`
swaps to engine order. Two phases (collect-then-insert so insertions never perturb the walk):

1. **`collect_leaks`** — DFS tracking the CSG `outside` propagation (`front = outside||IsCsg`,
   `back = outside && !IsCsg`; `is_csg_build` ignores the transient `NF_IsNew` bit) and the cell's
   half-space list (each ancestor node plane, oriented for the descended side). At every terminal
   child that reads EMPTY, find a strict interior point (`region_interior_point`, projections-onto-
   convex-sets from the parent-face centroid) and test the point-in-solid oracle
   (`csg::point_in_solid_world` — the CSG replay). Oracle-solid ⇒ a leak.
2. **`insert_solid_bound`** — graft node `M` at the leaked child slot: `M.plane = parent.plane`
   **flipped** (negated normal + w), `NumVertices>0` (copy parent verts, so `IsCsg` holds),
   `node_flags = NF_SOLID_BOUND (0x40)`. `M` coincides with the parent plane, so descending into the
   cell crosses `M` onto its BACK (solid) side → `back = outside && !IsCsg(M) = false` → SOLID. The
   FRONT sliver is zero-volume.

Supporting wiring:
- **`NF_SOLID_BOUND` (0x40)** is a transient marker, NOT a real on-disk NodeFlag: not in the IsCsg
  masks (0x21/0x25), and cleared in `finalize_leaves_and_bbox` after `zones` reads it.
- **`zones::assign_leaves`** reads the marker to **suppress the zero-volume EMPTY sliver leaf** on a
  bound node's front side — else each sliver becomes an isolated zone (observed: zones 4→20). With
  suppression, zones stay **4** (identical to the editor's zone structure).
- `bspBuildBounds`/`collect_solid_terminals` then emit the leaked cell's hull from its real ancestor
  planes (the floor), so the box clip stops at the true floor.

### Why not graft the real world faces instead?
Tried and rejected: clipping the world surface faces to the leaked cell and grafting them via
`split_poly_list` only fixes cells a real face passes *through*; INTERIOR-solid leaked cells (the
floor slab, bounded by an *ancestor* plane, with no face inside) are not caught — propagation stayed
leaked (2434→2434 in the box column). The flipped-parent bound flips ANY leaked cell.

---

## 4. Results (verification)

- **Offline (`line_check.py`, extent 20,20,44):** native box-drops now match the editor **exactly**
  (identical time, location, normal) at every probed column — (0,-250) center z 52→**64** (= editor),
  (300,-100), (0,0), (100,100). Regression test: `uedcli/tests/test_native_collision.py` (skips
  without the castle assets) + Rust `build::tests::leaf_bounding_flips_a_leaked_solid_cell_to_solid`
  / `leaf_bounding_is_noop_on_a_convex_room`.
- **Live** (session `e3752809`, `TravelToLevel DXONLY` → `NativeCastle`): pawn
  `Position 0 -250 47`, `phys=1` (PHYS_Walking), speed 0 — **z=47, up from z=35**, matching the
  editor. The 12-uu sink is gone.
- **Propagation leaks:** 2434 → **95** (grid sample; a 96% reduction). The main floor and every
  tested walkable column are watertight.
- **No parity regression:** `bin/test` = **1241 passed, 1 skipped, 2 xfailed** (unchanged baseline);
  `cargo test` = 28 passed. The CSG differential, zone-membership, and lightmap goldens are
  untouched — the repair is a no-op on convex geometry (the goldens have no leaks).

---

## 5. Residual to exact topology parity (tracked)

Landing the collision repair does NOT reach byte-identical topology. Remaining gap vs the editor
golden, with the reason (all from `bspbuild-splitpolylist-decode.md`):

| quantity | native (repaired) | editor | reason |
|---|---|---|---|
| nodes | 909 | 1156 | editor's un-repartitioned semisolid/detail fragments + `TestVisibility` zone splits + our lean single partition |
| FVerts | 3604 | 16163 | editor repartitions fat CSG-fragmented coplanar-merged faces (retained boundary/T-junction verts); ours are clean convex quads |
| surfs | 438 | 485 | downstream of the fragment/zone differences |
| propagation leaks | 95 | 0 | residual thin/edge cells the repair's interior-point seed misses |

**What exact parity needs:** port UnrealEd's **incremental `bspBrushCSG`** (per-brush temp BSP +
its bevel/bounding planes, `FilterFPoly` adding fragment nodes to the world Model) plus the
**semisolid second incremental layer**, in place of our CSG-surface-list + single from-scratch
partition. That reproduces both the fragment retention (FVerts) and the extra nodes natively, and
makes the tree watertight by construction (no synthetic bound nodes). N-2+; see `board/inbox/`.

The 95 residual propagation leaks are thin/edge cells whose interior-point seed fails; they are not
on tested walkable floor. A follow-up could seed the interior point more robustly (Chebyshev center)
or fall back to the world-face graft for cells the flip misses — tracked in `board/inbox/`.

**Note (2026-07-19):** the leak-repair does **not** contribute to the on-disk `Vectors` array. Its
bound node carries a flipped parent plane stored **inline** in `FBspNode` (never in `Vectors`) and
**reuses the parent's `iSurf`** (`insert_solid_bound` allocates no surf and calls no `bsp_add_vector`).
The UNATCO `Vectors +24 %` residual is therefore **not** the leak-repair's flipped planes — it is extra
**texture axes** on native's extra/differently-partitioned surfaces (this same less-merged partition),
decode-proven in §91 §10. Closing it couples to the incremental-`bspBrushCSG` port above.
