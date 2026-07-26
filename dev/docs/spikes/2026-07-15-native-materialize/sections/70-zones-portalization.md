# Section 70 — `TestVisibility` portalization: leaves, zones, connectivity (native port spec)

**Status:** RE COMPLETE — instruction-level decode of every pass of
`UEditorEngine::TestVisibility` and its `FEditorVisibility` helper passes. **Date:** 2026-07-16.
**Method:** static disassembly of UED22 `Editor.dll` (`capstone`+`pefile`, ImageBase
`0x10000000`) via the spike harness (`adis.py`/`leaf_disas.py`/`pe.py`); cross-checked against the
GAME `Engine.dll` (base `0x10300000`) for the shared `IsCsg`/`PointRegion` primitives and against
real-map ground truth (`harness/zone_ground_truth.py` on `DXOnly.dx` + `Test_Castle.dx`).
**Raw instruction-level evidence** (one file per pass, with quoted disasm) is preserved under
[`../re-raw-zones/`](../re-raw-zones/) — this section is the synthesized port spec; cite the raw
files for the byte evidence behind any single claim.

### Confidence legend
- ✅ live-verified / byte-exact against a real `.dx`
- 📖 binary-extracted (read out of the compiled `Editor.dll`/`Engine.dll` this session)

> **IMPORTANT scope note (2026-07-16).** The playability blocker for a native multi-brush `.dx`
> was found to be **collision** (the pawn *falls through the floor* → "fell out of the world"),
> NOT missing zones — see [[native-castle-blocker-is-collision]] / the board. Zones are still
> required for true UnrealEd parity and correct per-room `ZoneInfo`, and this decode is what the
> port is built from; but the *fall-through* fix is tracked separately (section 60 / the LineCheck
> oracle). Do not assume shipping these zones alone makes the map playable.

---

## 0. Ground truth (the two real maps — `harness/zone_ground_truth.py`)

| field | `DXOnly.dx` (menu backdrop) | `Test_Castle.dx` (plays) |
|---|---|---|
| NumZones | 2 | **4** |
| zone[0] | actor None, conn `0x1`, vis `~0` | actor None, conn `0x1` |
| zone[1] | actor None, conn `0x2` | `ZoneInfo_93iu8d` (ZoneInfo), conn `0x6` |
| zone[2] | — | actor None, conn `0x6` |
| zone[3] | — | `SkyZone_1zdw8v` (SkyZoneInfo), conn `0x8` |
| leaves | 1 (iZone 1) | **384** (iZone 1×11, 2×359, 3×14) |
| node iZone pairs | `(0,1)×6` | `(0,1),(0,2),(0,3),(1,2),(2,2)` |
| node_flags | all `0` | `0`×535, `8`×598, `0x0d`×9, `0x10`×7, `0x18`×5, `5`×2 |
| num_shared_sides | 16 | 2739 |
| Visibility | `~0` (all zones) | `~0` (all zones) |

Key facts this pins: **zone 0 is always the solid/outside zone (no leaves, no ZoneActor,
Connectivity `1<<0`)**; interior zones are numbered `1..NumZones-1`; `Visibility` is **never
computed** — it stays the `EmptyModel` default `0xffffffffffffffff` on every real map; a zone's
`ZoneActor` is its `ZoneInfo`/`SkyZoneInfo` (never the `LevelInfo`); `Connectivity` self-bit
`1<<z` OR the bits of zones joined to it across a `PF_Portal` face.

## 0.5 CSG precondition — the portal sheet must SURVIVE CSG (✅ live-verified 2026-07-16)

Portalization can only cut a zone boundary where the BSP actually has a **`PF_Portal` splitting
node**. That node exists only if the authored portal sheet (e.g. a water-surface `bluewater` quad,
flags `0x0400010c` = `PF_Portal|PF_NotSolid|PF_TwoSided|…`) survives CSG as a real node. **Our
native CSG originally dropped it**, which silently defeated the whole pipeline: with no portal node,
Pass C's flood merged the water region into the dry interior and the pawn inherited the water zone's
`bWaterZone` → it **swam instead of walking**.

Root cause + fix (`uedcli-native/src/csg.rs` `leaf_apply`): a portal sheet is `PF_NotSolid` and
floats in empty space, so the point-in-solid classifier sees **void on both sides** and returns
`Filter::CospatialFacingOut` — the "shared wall between two empty voids → annihilate" rule, which is
correct **only for solid faces**. The fix keeps a face when `filter == CospatialFacingOut &&
(poly_flags & PF_NOTSOLID) != 0` (in both the `Add` pass-1 and `Outside` pass-2 arms), so the
non-solid sheet survives as a splitting node. It is deliberately gated on `CospatialFacingOut`
alone: a non-solid fragment **buried in solid** classifies `CospatialFacingIn` and is kept by the
pre-existing non-semisolid `CospatialFacingIn` arm (the engine's own `csgFunc` behavior — keep it,
editor-faithful), while a fragment buried by a *later* solid brush hits the `Outside` pass with no
`CospatialFacingIn` keep and is correctly discarded (no entombed portal). **Byte-proof:** with the
fix, the native castle's four water portal surfs match `Test_Castle.dx` exactly (`surf X[-500,500]
Y[410,500] Z[-12,-12]`, …) and the native zone layout matches the editor (4 zones; PlayerStart in
the dry zone, water pool in the `bWaterZone` zone). Regression:
`test_water_portal_keeps_playerstart_out_of_water_zone`.

## 1. The pass pipeline (📖 `TestVisibility` 0xaa940 → portalize `sub_aa370`)

`FEditorVisibility` is a `sizeof=0x10058` stack object (ctor `0xa6970`, dtor `0xa6c70` = one
`FMemMark::Pop`). Fields (ctor decode, `re-raw-zones/ctor-fieldmap-6970.md`): `+0xc` `ULevel*`,
`+0x10` `UModel*`, `+0x14..+0x10013` a `0x4000`-entry INT node-path stack (bit `0x40000000` =
"descended back child", depth at `+0x1001c`), `+0x10014` NumPortals, `+0x10034` NumZonePortals,
`+0x10038` NumFragments, `+0x10044` global `FPortal*` list head, `+0x1004c[]` per-node heads,
`+0x10050[]` per-leaf heads, `+0x10054[]` per-leaf light/volumetric INT lists. An **`FPortal` is
`0x200` bytes** = an `FPoly` + tail: `iFrontLeaf +0x1d8`, `iBackLeaf +0x1dc`, `iNode +0x1e0`,
list-nexts `+0x1e4/+0x1e8/+0x1ec/+0x1f0` (global / leafA / leafB / node), `iZonePortalSurf +0x1fc`
(ctor-init `-1`).

Portalize order (📖 `0xaa370`), with the durable evidence file per pass:

| # | RVA | name | produces | evidence |
|---|---|---|---|---|
| pre | — | reset | every node `iLeaf[0..1]=-1`, `iZone[0..1]=0`; every surf `+0x18=-1`; empty `Leaves` + `Lights` | `passesEFG-…` |
| A | `0xa7760` | `AssignLeaves(iNode, Outside)` | one `FBspLeaf` per empty terminal child; `node.iLeaf[side]` | `passA-leafenum-7760.md` |
| B | `0xa9750` | `MakePortals` | the leaf-adjacency **portal graph** (lists at `+0x10044/4c/50`); marks zone portals | `passB-makeportals-9750.md` |
| C | `0xa93c0` | `FormZonesFromLeaves` | flood-merge leaves → `leaf.iZone`; `NumZones` (`Model+0x100`) | `passC-zoneflood-93c0.md` |
| D | `0xa7400` | `AssignAllZones` | per-node `iZone[0..1]` (byte) by re-filtering each node poly to leaves | `passD-assignzones-7400.md` |
| — | — | `bspCleanup`+`bspRefresh(1)`+`bspBuildBounds` | GC + node bounds (§60/§7.4) | — |
| E | `0xa8850` | `BuildZoneMasks` | per-node `ZoneMask` (u64, `Model` node `+0x10`) | `passesEFG-…` |
| F | `0xa7960` | `BuildConnectivity` | `Zones[i].Connectivity` (u64) | `passesEFG-…` |
| G | `0xa7e60` | `BuildZoneInfo` | `Zones[i].ZoneActor`; every actor's `Region`; reverb/warp | `passesEFG-…` |

(Then two per-actor light/volumetric floods, `0xa6d00`/`0xa9290` → `Model.Lights` + `leaf.iPermeating`/
`iVolumetric` — orthogonal to zones; `re-raw-zones/lightflood-6d00.md`.)

## 2. Pass A — `AssignLeaves` (📖, the leaf enumerator)

DFS over `iChild[0]`(back) then `iChild[1]`(front) — **the coplanar `iPlane` chain is NOT
followed**. Seeded `AssignLeaves(0, Model.RootOutside)` (`Model+0xf0`, confirmed by the game
`UModel::UModel` ctor storing arg2 there). Per side:
```
NewOutside = IsCsg(node, ExtraFlags=4) ? (side==1) : Outside
IsCsg = NumVertices>0 && (NodeFlags & (ExtraFlags | 0x21)) == 0     // 0x21 = NF_NotCsg|NF_IsNew
```
`ExtraFlags=4` means the **PF_Portal-derived NodeFlags bit `0x04` makes a node transparent to
solidity** — a portal splits space without flipping empty/solid. At a terminal child (`==-1`) with
`NewOutside != 0` (empty), append a leaf `{iZone = Leaves.Num (its own index), iPermeating=-1,
iVolumetric=-1, iExclusive=~0}` and set `node.iLeaf[side]` to its index; solid terminals keep
`iLeaf=-1`. **Every empty terminal cell is its own leaf, in DFS-preorder (back subtree before
front).** The `iZone = own index` seed is the union-find label pass C flips.

## 3. Pass B — `MakePortals` (📖, the portal graph)

For each node, build a ±65536 infinite quad on its plane (`BuildInfiniteFPoly` from
`Surf.pBase`(+0x8)/`vNormal`(+0xc)), clip it to the node's convex cell by `FPoly::SplitWithNode`
against every ancestor on the path stack (SplitInHalf above 14 verts), then `FilterThroughSubtree`:
filter the survivor down the node's BACK subtree; each back-leaf fragment re-filters down the FRONT
subtree; each (frontLeaf, backLeaf) pair with **both leaves empty** allocates an `FPortal`
(`AddPortal 0xa72a0`) linked into the global list, the per-node list, and BOTH per-leaf lists;
`+0x10014++`. Fragments touching solid (leaf `-1`) are dropped. Then for each coplanar-chain node
whose surf has **`PF_Portal` (0x04000000, at `FBspSurf+0x4`)**: take its real polygon
(`bspNodeToFPoly`), `+0x10034++`, re-filter, and `BlockPortal 0xa7870` stamps every existing portal
joining the same unordered leaf pair with `iZonePortalSurf = that surf index` (`+0x10038++`). **A
stamped portal is a ZONE boundary; an unstamped portal is an interior adjacency.**

## 4. Pass C — `FormZonesFromLeaves` (📖, the flood = union-find)

Not a spatial flood — a union-by-relabel over the global portal list:
```
for each FPortal p with p.iZonePortalSurf == -1:              # NON-zone-portal = interior adjacency
    a = Leaves[p.iFrontLeaf].iZone ; b = Leaves[p.iBackLeaf].iZone
    for every leaf L with L.iZone == a: L.iZone = b           # merge the two classes
# (zone-portal-stamped records are SKIPPED -> their two leaves stay in different zones)
compact the surviving iZone labels to dense 0..K-1 (first-seen order)
debugf("Found %i zones", K)
for each leaf: leaf.iZone = (denseId % 63) + 1                # zones 1..63; 0 reserved for solid
Model.NumZones (Model+0x100) = min(K + 1, 64)
```
So: **leaves connected by any non-portal boundary collapse to one zone; a `PF_Portal` face keeps
them apart.** Zone numbers depend on portal-record creation order (documented; membership is
order-independent).

## 5. Pass D — `AssignAllZones` (📖, per-node iZone bytes)

For each non-`NF_IsNew` node, re-filter its own polygon through the tree; each landing produces a
(backLeaf, frontLeaf) pair, and a coplanar `NF_IsNew` fragment node is `bspAddNode`ed carrying
`iZone[k]=Leaves[backLeaf].iZone`, `iZone[k^1]=Leaves[frontLeaf].iZone` with
`k = (dot(Head.Plane.N, Poly.N) < 0)`; `iLeaf==-1 → zone 0`. If all fragments agree per side, the
fragments are killed and the ORIGINAL node gets `iZone[0..1]` = the agreed pair; on disagreement the
original node is killed and only the per-zone fragment nodes survive (this is where the extra
`Test_Castle` nodes vs ours come from). **Node `iZone` is a BYTE (`+0x34/+0x35`); leaf `iZone`
(i32) is truncated to a byte on store.**

## 6. Passes E/F/G — masks, connectivity, actors (📖)

- **E `BuildZoneMasks` (`0xa8850`)**: recursive `node.ZoneMask (+0x10, u64)` = OR of
  `1<<iZone[0]` | `1<<iZone[1]` over self + both children + the `iPlane` chain; **zone 0 sets no
  bit** (so a solid-only node contributes nothing). Also runs standalone inside `bspBuildBounds`.
- **F `BuildConnectivity` (`0xa7960`)**: `Zones[i].Connectivity = 1<<i`, then for every node whose
  surf is `PF_Portal`, OR each of the node's two `iZone` bits into the other's Connectivity (an
  undirected edge). Matches `Test_Castle` (zone1↔zone2 both `0x6`; sky zone3 isolated `0x8`).
- **G `BuildZoneInfo` (`0xa7e60`)**: clears each `Zones[i].ZoneActor`; for every `AZoneInfo` actor
  **except `ALevelInfo`**, `Model->PointRegion(LevelInfo, actor.Location)` → its zone → set that
  zone's `ZoneActor` (first wins; logs `%i ZoneInfo actors, %i duplicates, %i zoneless`). Then
  `SetActorZone` for every actor. Reverb (256-ray) + WarpZone coords are filled here too (out of
  scope for a minimal port).

## 7. UModel zone layout (📖, pinned from `UModel::Serialize` 0x1705a0 + `EmptyModel` 0x16ff10)

`NumSharedSides` at `+0xfc`, **`NumZones` at `+0x100`**, **`Zones[64]` at `+0x104`, stride
`0x18`**: `ZoneActor` (+0), pad (+4), `Connectivity` u64 (+8), `Visibility` u64 (+0x10). Serial
order = `i32 NumSharedSides, i32 NumZones, NumZones×{ci(ZoneActor), u64 Connectivity, u64
Visibility}` — **exactly what `uedcli.native.umodel.write_model_body` already emits; no serializer
change is needed.** `Visibility` is never computed → emit `0xffffffffffffffff`.

## 8. Native-port contract (what `zones.rs` must produce, replacing the single-zone finalize)

1. **Leaves** — run Pass A verbatim on the finished tree AFTER the front/back convention is in
   engine order (front child in `iChild[1]`): DFS, `IsCsg` with `ExtraFlags=4`, one leaf per empty
   terminal, `node.iLeaf[side]` set, `leaf.iZone = own index` seed.
2. **Portal graph** — Pass B: per-node infinite-quad clipped to the cell, filtered to leaf pairs;
   this needs faithful `SplitWithNode`/cell clipping (the heaviest new geometry). Mark
   `PF_Portal`-surf portals.
3. **Zone flood** — Pass C union-find; `leaf.iZone = (dense%63)+1`; `NumZones = min(K+1,64)`.
4. **Node iZone/ZoneMask** — Pass D per-node `iZone` bytes (fragment split on disagreement),
   Pass E `ZoneMask`.
5. **Connectivity** — Pass F; `Visibility = ~0`.
6. **ZoneActor** — Pass G is an **assembly-time** patch (mirror `_patch_light_refs`): Rust tags each
   zone with the *name/index* of the `ZoneInfo` whose `Location` PointRegion-resolves into it (the
   default interior zone with none → NULL, NOT the LevelInfo), and `assemble.py` rewrites to the
   export ref. Validate zone/leaf **MEMBERSHIP** (never counts — D2) against `DXOnly` then
   `Test_Castle` with `harness/zone_ground_truth.py` + a PointRegion equivalence check.

**Simplification available:** for zone *membership* correctness in the common no-explicit-`PF_Portal`
castle, Pass B's full portal geometry can be replaced by a cheaper leaf-adjacency test (two empty
terminal cells sharing a node face are adjacent ⇒ same zone unless the face is `PF_Portal`), because
Pass C only consumes the (leafA, leafB, isZonePortal) triples — the portal *polygon* is used only by
the light flood and warp coords. This is the recommended first cut; keep the full portal poly only if
a later slice needs lighting/warp parity.

## 9. Pass D as SHIPPED (`zones.rs`) — faithful node-polygon re-filter + fragment SPLIT, and the FBspSurf.iZone trap (✅ 2026-07-18)

> **UPDATE 2026-07-18 (fragment-split ported — supersedes the "never-split centroid sampler" first
> cut described in the rest of this section).** `zones.rs` Pass D now ports UnrealEd's
> `AssignAllZones` (`0xa7400`, §5 / `re-raw-zones/passD-assignzones-7400.md`) FAITHFULLY, including
> the per-zone node SPLIT. For every node in each coplanar (`i_plane`) chain, its stored polygon is
> rebuilt (`node_poly`) and re-filtered through the chain HEAD's back-then-front subtrees
> (`node_landings`, the same two-pass filter Pass B uses), collecting every `(backLeaf, frontLeaf)`
> landing. If the landings AGREE per side the node keeps one `iZone` pair (the `AllSame` branch); if
> they DISAGREE — a face spanning two zones, e.g. a moat/water outer wall the `z=−12` water portal
> cuts — the editor kills the node and keeps one `NF_IsNew` fragment per surviving (nonzero-zone)
> landing. Native reproduces the resulting node fan-out by KEEPING the original as the first
> fragment and APPENDING the rest onto its `i_plane` chain (all share the node's plane, with the
> clipped fragment polygon as verts). **Byte payoff (full castle, `node_diff.py`/fp-tolerant
> multiset):** native node count **1127 → 1156 = editor**; plane multiset **1156 shared / 0
> only-native / 0 only-editor** (was 1127/0/29). The boundary walls fan out to match the editor
> exactly (surf 354→10 nodes, 355→10, 349/350→8, …). **The whole iZone distribution now matches the
> editor** under the zone-number permutation (native zone 1 ↔ editor zone 2; §4 flood-order
> relabel): native `(0,1)×1058,(0,2)×39,(0,3)×40,(1,1)×8,(2,1)×11` ≡ editor
> `(0,2)×1058,(0,1)×39,(0,3)×40,(2,2)×8,(1,2)×11`, and the old `(0,0)×2` solid-solid nodes drop to
> `×0` (exact editor match — the filter is strictly more accurate than the centroid nudge below, so
> the render-critical `ZoneMask` bits are if anything MORE complete). `soup_cmp` (853/853),
> `compare_trees 32` (incremental stream identical), and `node[0]` (plane) are unchanged — the split
> is purely a finalize/post-repartition addition. Offline suite green;
> `test_case_f_portal_full_compare` un-xfailed (the portal corpus case now reaches full surf-set +
> node/surf/zone/leaf-count parity). The rest of this section documents the earlier centroid first
> cut for history; the FBspSurf.iZone trap (Bug 2) still holds verbatim.


The last in-game render-parity gap (§20 of `20-lighting-bake.md`: ~15–32 % of an in-game frame
rendered BLACK) was **node-level portalization**, and it came down to TWO concrete bugs in
`zones.rs`, both now fixed. Verified by re-rendering all four preview poses in-game (`NativeCastle.dx`
vs the editor's `Test_Castle.dx`): the three interior poses dropped to editor parity — **s76 32.1 %→3.8 %**
(editor 4.0 %), **s34 14.4 %→0.0 %**, **s07 16.3 %→0.0 %** black.

**Bug 1 — Pass D was a subtree-descent guess, not a face-adjacency read.** The old code took a
node's per-side zone by "descend into that child subtree and grab the first leaf you reach". That
grabs a **far, unrelated** leaf, so ~450 interior wall nodes came out zoned `(0,0)` (solid on both
sides) and another ~384 came out `(1,1)`. A node zoned `(0,0)` contributes **no bit** to any
`ZoneMask` (zone 0 sets no bit — §6 Pass E), so the game's `URender` front-to-back walk dropped
those walls' surfaces from the frame → black.

The editor's real Pass D (`re-raw-zones/passD-assignzones-7400.md`) re-filters each node's OWN
polygon through the tree and reads the `(backLeaf, frontLeaf)` zones the poly actually lands
*between*. The shipped port gets the identical answer far more cheaply: **sample the node's
face-polygon centroid, nudged `±0.5uu` off the plane along its (unit) normal, and run the engine's
own PointRegion descent** (`PlaneDot = n·p − w ≥ 0` → FRONT `i_back`/`iLeaf[1]`, `< 0` → BACK
`i_front`/`iLeaf[0]`) to the adjacent leaf. `iZone[0] = back leaf's zone`, `iZone[1] = front leaf's
zone` (0 for a solid/`-1` terminal). A convex BSP face's centroid is strictly interior, so it is
clear of edges; the nudge lands inside the real neighbour cell. This produces the editor's
distribution: node iZone `(0,0)×450 → ×2`, and `(0,interior)` becomes dominant (native `(0,1)×1090`
≈ editor `(0,2)×1058`; native's interior is zone 1, the editor's is zone 2 — zone *numbers* differ
by portal-record creation order, membership is identical). It does not reproduce the editor's rare
fragment-SPLIT of a node whose face spans two front zones (§5) — unnecessary here, because the water
portal sheet already splits such faces at the BSP level, and single-zone-per-node is enough for the
`ZoneMask` bit `URender` gates on.

**Bug 2 — native was WRITING FBspSurf.iZone; the editor leaves it (0,0).** `FBspSurf` has a real
on-disk `iZone[2]` (two `u16`, §50 field order), but the editor's `TestVisibility` **writes nothing
into any FBspSurf** (`passD-assignzones-7400.md` §3): a real editor map (`Test_Castle.dx`) ships **all
485 surfs at iZone (0,0)**. The game **recomputes** a surface's zone at load from the node tree — and
a **non-zero** stored value is taken as "already resolved" and trusted stale. Native's inherited
surf-zone loop stamped varied values (`(1,0)`, `(3,0)`, …), which mis-zoned surfaces at load and
rendered the water-pit/backdrop region black (this made the water-pool pose s69 *worse*, 18.2 %→37.3 %,
until fixed). Fix: emit the editor's bytes — leave every `surf.iZone = (0,0)`. This alone recovered
s69 to ~baseline (37.3 %→20.7 %) and improved s76 (5.9 %→3.8 %).

**Residual / out of scope.** Pose **s69 (looking down into the water pool) stays ~20 % black** —
that is the pre-existing **water-portal / pool-pit** render gap, NOT this fix's regression and NOT the
fake-backdrop (the `ClenCloudBank_A` fake-backdrop is a ceiling plane at `Z=420`, *behind* the
downward s69 camera). The pit walls are correctly zoned `(0,3)` (water) with the water bit in their
`ZoneMask`, and zone1↔zone3 connectivity matches the editor (`0xa`), yet `URender` doesn't draw the
pit through the translucent water surface — a deeper portal-traversal/translucency concern tracked as
the separate water/sky-portalization item. **node_flags stay `{0, 5}`** (native sets no `NF_*` render
bits): the editor's dominant `0x08` is `NF_PolyOccluded`, a per-frame **renderer-set** occlusion hint
(editor viewport leftover at save), which `URender` re-derives each frame — it is neither load-bearing
for the black nor deterministically reproducible offline, so native correctly omits it. **DLL-confirmed
2026-07-18** (`sections/82 §10.11`): scanning both `NodeFlags` (`FBspNode+0x37`) setter forms across the
binaries, **`render.dll` sets the two occlusion bits** — `0x08 NF_PolyOccluded` at `0x10019c26`
(`or byte[eax+0x37],8`, gated on the current view's span state) and `0x10 NF_BoxOccluded` at
`0x100193db`/`0x10019526` — while **`Editor.dll` (the entire deterministic build:
`csgRebuild`/`bspBrushCSG`/`bspRepartition`/`bspRefresh`/`TestVisibility`) sets NEITHER**. So `0x08` is
genuinely camera-dependent render state (non-deterministic across saves), not a build derivation —
confirmed-excluded, not faked.

**Collision unaffected.** Node `iZone`/`ZoneMask`/surf `iZone` are read only by the renderer; the
box-sweep collision path (`linecheck.rs`, `LeafHulls`, `iCollisionBound`) reads none of them. Verified
live: the pawn walks NativeCastle at `phys=1` after the fix.

## 11. Pass D VERT-POOL re-emit ported — Verts 10407→16183, NumSharedSides 2707→2739 exact (✅ 2026-07-18)

> This closes the dominant remaining geometry-body byte gap that §82 §10.16 localized to `zones.rs`:
> the post-`bspBuild` vert pool jumps **4405→10518** in the editor but only **4405→4521** in native,
> a **+6113-vert** deficit that dwarfed everything else (~50 kB of the ~160 kB body gap). It is
> UnrealEd's Pass-D per-landing vert append, and it lives entirely in `zones.rs`.

**The mechanism (`passD-assignzones-7400.md` §1/§4/§5).** UnrealEd's `AssignAllZones`, for EVERY node
in each coplanar chain, re-filters the node's polygon through the chain head's back- then
front-subtree and, **for EVERY landing**, calls `bspAddNode` — which does `iVertPool =
Verts.Add(NumVertices)`, appending that landing's ring verts to the pool (each vertex resolved through
`bspAddPoint`'s Euclidean `dist < 0.002` dedup into the existing Points pool). The keep/split decision
then **kills** most of those fragment nodes (`NumVertices = 0`): the AllSame branch kills ALL of them
(original keeps its own ring), the disagreement branch kills the original + zoneless fragments. But
**killing a node does NOT reclaim the verts it appended** — the post-D `bspCleanup`/`bspRefresh` only
compacts POINTS by live reference (and does not remap orphan verts), so every killed fragment's ring
stays in the pool as an **orphan** (uncompacted, referencing whatever point indices it grabbed —
indices that go stale when `bspRefresh` later renumbers Points, but are never read because no live
node ring points at them). That orphan re-emit IS the +6113.

**What native now does (`zones.rs` `passd_process` + the `Emit` consume loop).** Pass D records one
`Emit` per landing, in walk+landing order (the editor's `bspAddNode` order):
- **`Orphan`** — a killed-fragment landing (every AllSame landing; the disagreement zoneless
  landings). Its verts are appended (`append_ring_verts(create_points=false)`) but **no node** is
  created, and the append **NEVER grows the Points pool**: a vertex with no existing point within
  `0.002` snaps to the NEAREST existing point instead of adding one. This is faithful — the editor's
  orphan verts carry stale indices and its final Points count is bounded by ring/`pBase` references,
  not by orphans — and it is what keeps native's Points at its prior **2061** (a raw create-if-absent
  append instead added **+447** spurious orphan-only points, blowing Points to 2508).
- **`OriginalRing`** — the FIRST surviving landing of a disagreement split, retargeted onto the
  RETAINED original node: the original's `i_vert_pool`/`num_vertices` are repointed to this clipped
  landing (a **live** ring, `create_points=true`), and its full base ring is thereby orphaned — exactly
  as the editor kills the original and keeps S clipped zone fragments. This aligns native's live-ring
  layout with the editor (ring-sum **5498** vs editor **5496**; ring-distinct-points **1555 = 1555**),
  which is what makes **`NumSharedSides` come out byte-identical at 2739** (it was 2707 while the
  original kept its full base ring).
- **`Frag`** — the remaining surviving landings, as before: real coplanar nodes spliced onto the
  owner's `i_plane` chain. Unchanged set/order, so the node count (1156), planes, and the
  split-group `tail_order` handed to `bspcsg::reorder_nodes_to_tail` are **identical** to §10.17.

**RAW byte result (`ground_truth_bytediff.py`, `NativeCastle.dx` vs `Test_Castle.dx`).**

| section | before | after | editor |
|---|---|---|---|
| Verts (count) | 10407 | **16183** | 16163 |
| Verts (section bytes) | 36569 | **53930** | 53866 |
| NumSharedSides | 2707 | **2739 (byte-identical)** | 2739 |
| Points (count) | 2061 | **2061 (unchanged)** | 2035 |
| whole-body positional match | 23.66% | **29.21%** | — |
| whole-body byte delta | −22656 | **−4926** | — |

**Guards all held** (`bounds_leafhulls_decode.py`, `soup_cmp.py`, `build_native_castle.py`): nodes
**1156/1156 positional planes** (first divergence NONE), soup **853/853 (0/0)**, surfs **485**, vectors
**26**, leaves **384**, Bounds **484**, LeafHulls **308 hulls / 3866 ints / 1710 refs (+0/+0)**, node
`iZone` distribution + zones unchanged. Offline suite **1665 passed / 1 skipped / 1 xfailed**; `cargo
test` **37 passed**.

**Residual (honest, UPDATED 2026-07-18).** This +20 was later split and half-closed: the **ring-sum
+2** was NOT a Pass-D `clip_poly` fragment gap but a `bspOptGeom` pass-1 **over-weld** (a missing
live-table dup-guard update) — fixed in `bspoptgeom.rs`, dropping welds 977→975 and Verts **16183 →
16172**, ring-sum now matches the editor exactly (see `42-bspoptgeom-decode.md §9`). What remains is
**+9 orphan slots** present already at `bspOptGeom` ENTRY (native pool 10527 vs editor 10518) — this
IS Pass-D: killed-fragment rings native re-emits that the editor doesn't. **The +9 is now CLOSED
(§12): three spurious `[A, B, B]` orphan triangles that native's `clip_poly` produced and the
editor's `FPoly::Fix` dropped.** The Verts section is still not byte-identical because the SURVIVING
**Pass-D orphan verts' `iVertex` values are not editor-faithful** — the editor's are stale
pre-`bspRefresh` indices we do not reproduce (we snap to nearest existing point); matching them was
shown in §12 to be **architecturally infeasible in-lane** (the editor's stale orphan indices run up
to 2642, a transient CSG point numbering native never constructs). (Points is now **2035 = editor**,
closed by the point-pool-order work; the old +26 surf-emit-order note is superseded.) Follow-on
levers, not regressions.

## 12. The +9 Pass-D orphan overshoot CLOSED — 3 spurious `[A,B,B]` triangles native emitted that the editor's `FPoly::Fix` drops; Verts 16172→16163 (✅ 2026-07-18)

§11 left native entering `bspOptGeom` with **+9 vert-pool slots** (native 10527 vs editor 10518),
carried straight through to the on-disk Verts section (native 16172 vs editor 16163). This section
pins that +9 to **exactly three spurious orphan triangles** and closes it with a faithful port of the
editor's `FPoly::Fix`.

**Localization (native-side, `preopt_runs2.py`).** Decompose both PRE-`bspOptGeom` vert pools into
live-ring slots (per-node `[iVertPool, +NumVertices)`) and ORPHAN runs (the gaps). The editor's PRE
layout comes from `editor-preopt-nodes.log` (`editor_preopt_nodes.py`, the gdb `bspOptGeom`-entry
Nodes dump); native's from a `UEDCLI_PASSD_DUMP` dump added to `zones.rs`. Both sides have **28
orphan runs**; **26 are byte-length-identical**. The whole +9 is two runs: native run @5596 is **843**
long vs editor **840** (+3), and native @7591 is **632** vs editor **626** (+6).

**Ground truth (the editor's exact orphan-ring segmentation).** The final `.dx` cannot expose the
editor's orphan rings (their `iVertex` are stale, unresolvable to coords), so a new oracle
`bspaddnode_ring_oracle.py` breakpoints `bspAddNode` (`Editor.dll` RVA `0x34e80`) during `MAP
REBUILD` and logs `(Verts.Num, NumVertices)` per call — i.e. every ring's `[ivp, +nv)` slot range in
emission order. The **final append pass** (after the last `Verts.Num` reset) climbs 0→10518 = exactly
the pre-`bspOptGeom` state, giving the editor's ring segmentation of both divergent runs. A
`SequenceMatcher` align of the editor's nv-sequence against native's orphan len-sequence shows native
has **3 EXTRA rings, all `nv=3`** (one in run @5596, two in run @7591) — the +9.

**Root cause — a `clip_poly` grazing-corner duplicate the editor's `bspAddNode` collapses away.** All
three extra rings are `[A, B, B]` — a triangle whose 2nd/3rd vertices are `0.000183` uu apart (a
near-exact duplicate), collapsing it to a zero-area line. **The editor's collapse is NOT a
`FPoly::Fix` pre-pass** (an earlier framing of this that the disasm refutes): `AssignAllZones`'s
`FilterFunc` (`re-raw-zones/passD-assignzones-7400.md §4`) calls `bspAddNode` UNCONDITIONALLY, and the
drop happens INSIDE `bspAddNode`'s vertex-fill loop (`Editor.dll 0x100352c8`, §5): `bspAddPoint` per
poly vertex with **consecutive-duplicate dropping (by resolved point INDEX) + a first==last dedupe**,
then `if final NumVertices < 3 → NumVertices = 0` — the fragment is emitted with **0 pool slots**.
Native's `clip_poly` (Sutherland–Hodgman with a `1e-4` on-plane band) instead pushes the coincident
vertex and emits the `[A, B, B]` orphan.

**Fix (`zones.rs` `fix_ring`, Orphan arm only).** Collapse consecutive corners within
`THRESH_POINTS_ARE_SAME = 0.002` (cyclic) on each Pass-D orphan ring; a ring left with < 3 verts is
dropped, reproducing the editor's `NumVertices < 3 → 0` (0 pool slots). **Why a COORDINATE test rather
than the editor's index-equality collapse:** native's orphan path does not resolve verts the editor's
way — the editor's `bspAddPoint` ADDS a point when none is near, but native SNAPS an orphan vert to
the nearest existing point (`append_ring_verts(create_points=false)`, to not inflate the Points pool,
§82 §10.16). So the editor's index-equality collapse cannot be replayed on native's snap-indices; the
faithful signal is the coordinate degeneracy the editor's fill loop actually detects (two corners
within the point-merge radius). The `0.002` threshold IS the engine's own `THRESH_POINTS_ARE_SAME`
(the same radius native's `bspAddPoint` dedup uses), so an edge shorter than it is a genuine
zero-length edge — the choice is principled, not fitted; the `0.0417`-uu sliver quads and `0.017`-uu
small triangle the editor KEEPS are all above it, and anything the editor's own `0.002` collapse would
drop native drops too (it cannot drop a ring the editor keeps). Restricted to `Orphan` emissions — the
live `OriginalRing`/`Frag` path resolves ADD-style like the editor and carries no within-threshold
corner on this map, so restricting to orphans is byte-equivalent AND cannot perturb the live ring-sum
/ `NumSharedSides` guards; a universal, index-based collapse in `append_ring_verts` is the faithful
generalization, flagged in `board/inbox.md`. Orphan emission creates NO node, so this touches neither
the node set/order nor the `tail_order` handed to `bspcsg::reorder_nodes_to_tail`.

**RAW result (`ground_truth_bytediff.py`, `NativeCastle.dx` vs `Test_Castle.dx`):**

| metric | before (§11) | after |
|---|---|---|
| PRE-`bspOptGeom` verts | 10527 | **10518 = editor** |
| Verts (count) | 16172 | **16163 = editor** |
| Verts (section bytes) | 53887 | **53860** (editor 53866; −6 residual = stale-index compact-int width) |
| Verts positional byte match | 24.8% | **27.3%** |
| Nodes positional byte match | 91.6% | **92.6%** (live-node `iVertPool` shift into place) |
| whole-body positional match | 42.4% | **43.0%** |

**Guards intact:** nodes **1156/1156** (0..1136 positional, tail perm = the pre-existing `−381.065`
fp-noise, §10.17), soup **853/853 (0/0)**, surfs **485**, vectors **26**, leaves **384**, Points
**2035 / 24422 byte-length** (first-diff @1586 unchanged), `NumSharedSides` **2739 byte-identical**,
Bounds **484**, LeafHulls **308 hulls / 3866 ints / 1710 refs (+0/+0)**, LightMap **484**. `cargo test`
**38 passed**; offline suite **1744 passed / 1 skipped / 1 xfailed**.

**Part 2 (byte-faithful surviving-orphan `iVertex`) — RE'd and deferred as architecturally
infeasible in-lane.** The surviving Pass-D orphan verts still carry native's snapped point indices,
not the editor's stale pre-compaction ones, so the Verts section is length-close but not
byte-identical (`−6` residual + interior byte shifts). The editor's stale orphan `iVertex` run up to
**2642** (measured on `Test_Castle.dx` — orphan slots referencing indices past the final 2035 AND
past the `bspOptGeom`-entry 2091), i.e. they reference a **transient CSG point numbering that peaked
above 2643 during Pass-D and was later compacted away**. Reproducing them would require native to
reconstruct the editor's entire point-pool construction history byte-for-byte (every transient point
added and later dropped), which directly conflicts with native's architecture — `bspcsg.rs` CLEARS
and rebuilds the point pool at repartition (§10.16) and `reorder_points_canonical` renumbers it at
the very end (§10.20), both in files outside this lane and both load-bearing for the Points-section
byte-parity guard. So a `passes.rs bspRefresh` point-renumber simulation cannot be made byte-faithful
without perturbing the Points guard. Deferred; the +9 count/length fix is the closable half.

## 13. Zone-flood OVER-FRAGMENTATION on real levels — TWO causes split (BlockPortal fix + a separate CSG-tree cause) (✅ 2026-07-19)

Native's zone flood emits far MORE zones than UnrealEd on real shipped levels — measured
native-vs-editor: **03_NYC_UNATCOHQ 45 vs 7**, **06_HongKong_WanChai_Market 64 vs 5**,
**10_Paris_Catacombs 43 vs 17** — while `Test_Castle` is correct (4 vs 4). Zone counts are
gameplay-affecting (render/sound/water/skybox) and a leading suspect for the native-UNATCO load-hang.
This section pins the root cause with golden evidence, splits it into **two independent mechanisms**,
and closes the one that lives in `zones.rs`.

### 13.1 The isolation oracle (`harness/zone_flood_oracle.py`)

A shipped `.dx` already carries the editor's FINALIZED BSP tree + its `Leaves` array + per-node
`iLeaf`. So native's Pass B (portal graph) + Pass C (union-find) can be run DIRECTLY on the editor's
OWN tree (a faithful Python re-port of `zones.rs`), decoupling the flood ALGORITHM from the CSG tree
native builds. The oracle reports the flood's zone count plus diagnostics: `[D1]` pure-adjacency
components (union ALL portals — the geometric connectivity), `[D2]` native portals cross-checked
against the editor's true `leaf.iZone`, `[D3]` components if barriers were editor-true, and the
BlockPortal variants `[D5]`/`[D6]`/`[D7]`.

**Result (flood run on the EDITOR's own tree):**

| level | native flood on editor tree | `[D1]` pure-adjacency | editor NumZones |
|---|---|---|---|
| Test_Castle | 4 | 2 | 4 |
| 03_NYC_UNATCOHQ | **7 (correct!)** | 4 | 7 |
| 06_HK_WanChai_Market | **5 (correct!)** | 2 | 5 |
| 10_Paris_Catacombs | **56 (WRONG)** | 3 | 17 |

So on a CORRECT tree the flood is right for UNATCO/HK/Castle but wrong for Catacombs — meaning there
are **two separate bugs**, and the real-build over-fragmentation of UNATCO/HK is NOT the flood.

### 13.2 Cause 1 (IN-LANE, FIXED): zone-portal OVER-MARKING — the infinite quad vs the real polygon

On the Catacombs editor tree, `[D2]` shows native falsely zone-marks **1084** portals that are WITHIN
a single editor zone (of 15268 same-zone portals), and `[D3]` proves that with editor-true barriers
the geometry yields exactly **16** interior components = the editor. So native marks far too many
faces as zone boundaries.

**Mechanism.** The old `zones.rs` marked a portal `zone_portal` iff **the node that generated it**
(via the WORLD-sized `±32768` infinite-quad clipped to the node's whole convex cell) had a
`PF_Portal` surf. But a `PF_Portal` surface (a small water pane) is usually MUCH smaller than its BSP
cell's cross-section. The editor's `MakePortals`/`BlockPortal` (§3) instead takes the `PF_Portal`
node's **REAL stored polygon** (`bspNodeToFPoly`), re-filters it, and stamps only the leaf-PAIRS the
real polygon actually lands between. The infinite quad flags a SUPERSET of those pairs — every extra
pair is a within-zone open face wrongly turned into a barrier, so union-find can't merge across it and
the zone shatters. Catacombs (narrow tunnels, 1146 `PF_Portal` surfaces, little redundant
connectivity) is acutely sensitive; UNATCO/HK have enough redundant open faces that the 117/…-odd
false barriers don't disconnect anything (which is why the flood still came out right there).

**Fix (`collect_zone_barriers`).** Replace the per-generating-node `zone_portal` flag with a barrier
leaf-pair set built the editor's way: walk the tree (the `passd_walk` order — every tree node a
coplanar-chain HEAD, its `i_plane` chain the members); for each node whose surf is `PF_Portal`,
re-filter its REAL polygon (`node_poly`) through the chain HEAD's back-then-front subtrees
(`node_landings`) and record every `(backLeaf, frontLeaf)` landing as an unordered barrier pair.
Pass C skips union for a portal iff its leaf-pair is a barrier; Pass F ORs connectivity across
barrier portals. **Filtering through the chain HEAD (not the node itself) is load-bearing** — a
`PF_Portal` surf on a coplanar-chain MEMBER has `i_front/i_back = -1` and yields no landing on its
own; its space is partitioned by the head's subtrees. The oracle's `[D7]` (this exact algorithm)
matches the editor **leaf-pair-exact on ALL FOUR editor trees**: interior zones **3 / 6 / 4 / 16 =
editor 3 / 6 / 4 / 16** (Castle/UNATCO/HK/Catacombs), i.e. NumZones 4 / 7 / 5 / 17. (A centroid ±eps
PointRegion variant `[D6]` under-separates — it finds only one pair per portal node where the real
polygon spans several; the real-poly re-filter is required.)

**Non-regression.** `Test_Castle` is byte-identical after the fix: NativeCastle.dx unchanged at
283624 B, nodes 1156/1156 positional, Points 2035, Verts 16163, NumZones 4, leaf `iZone`
{1:359,2:11,3:14}, node `iZone` pairs unchanged, whole-body positional 43.04% (= the §12 baseline).
The castle's portal surfaces seal their whole cross-section (real polygon == cell face), so both
rules agree there — which is exactly why the castle masked the bug. Committed regression:
`uedcli/tests/test_zone_flood.py` (BlockPortal flood == editor NumZones on each shipped golden
present) + `cargo test` 40 passed + offline suite 1789 passed.

### 13.3 Cause 2 (OUT-OF-LANE — `bspcsg.rs`/`passes.rs`): native's CSG tree is geometrically SHATTERED

The BlockPortal fix does NOT bring the real native BUILDS to editor counts, because native's CSG tree
is independently fragmented. Running the oracle on native's OWN built trees:

| native build | leaves (native / editor) | `[D1]` pure-adjacency components | zones (native / editor) |
|---|---|---|---|
| NativeUnatco.dx | 2575 / 2266 | **44** | 45 / 7 |
| NativeCatacombs.dx | 5233 / 4485 | **25** | 43 / 17 |

`[D1]` unions **every** portal (ignoring the zone flag entirely) and STILL finds 44 / 25 disconnected
leaf-blobs — where the editor's own tree is 4 / 3. So on native's tree whole regions of empty space
are portal-DISCONNECTED: adjacent rooms that the editor leaves open are walled off, and there are
14–18 leaves with ZERO portals. This is insensitive to Pass B's `MIN_AREA` (lowering it 1.0→0.001
moves 44→41 only), so it is not a sliver/threshold artifact in the flood — it is a genuine difference
in how native's incremental CSG partitions empty space (extra/entombed leaves, boundary faces
classified solid where the editor keeps them open). It lives in the CSG pipeline
(`bspcsg.rs`/`csg.rs`/`passes.rs`), NOT in `zones.rs`, and no flood change can merge leaves that share
no detectable face. The BlockPortal fix is correct and necessary (it removes the false barriers and is
editor-exact on any correct tree), but the dominant real-level over-fragmentation — and therefore the
UNATCO load-hang suspicion — awaits the CSG-tree cause. Filed to `board/inbox.md`.

**Honest status:** flood-on-editor-tree now editor-exact for all four levels (deterministic gate met);
real native builds still over-fragment because their trees are shattered upstream. UNATCO native stays
45 zones (barrier pairs there = 10; the fix is byte-active but the tree is the bottleneck), so this
fix alone does **not** clear the native-UNATCO load-hang.
