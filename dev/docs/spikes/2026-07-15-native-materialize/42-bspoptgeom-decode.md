# Section 42 — `bspOptGeom` decoded (T-junction retess + side-links), implemented & validated

**Status:** instruction-level decode of `UEditorEngine::bspOptGeom` (`Editor.dll 0x36870`) and its
subroutines, **ported standalone** to `uedcli-native/src/bspoptgeom.rs`, and **validated byte-exact
against `Test_Castle.dx`**. **Method:** static disassembly of UED22 `Editor.dll` (`capstone`+`pefile`,
host-native; the UT-v469-lineage 2022 MSVC/SSE rebuild — see `41-fp-model-x87-vs-sse.md`) +
empirical inspection of the golden Model. ImageBase `0x10000000`; all RVAs are file RVAs.
**Reproduce the decode checks:** `UED22=…/uned/UED22 python harness/verify_bspoptgeom.py` (27/27
string/RVA checks). **Reproduce the port validation:** `python harness/optgeom_validate.py`
(pass-1 idempotent + pass-2 iSide 16163/16163 byte-exact + NumSharedSides=2739). Confidence legend:
✅ live/golden-verified, 🔬 live-probed, 📖 binary-extracted.

> **⚠️ CORRECTION (2026-07-17):** an earlier version of this doc claimed `bspOptGeom` "does **not**
> add/remove/edit vertices" and is "irrelevant to vertex-set parity." **That was WRONG.**
> `bspOptGeom` **DOES insert vertices** — it eliminates T-junctions by inserting the offending point
> as a new polygon vertex (`AddPointLink`→inserter `0x31920`, in a *subroutine* the earlier
> body-only skim missed). This is a **primary** driver of the editor's fat FVert pool
> (castle **16163** verts vs a raw CSG build's ~4945). The task premise (T-junction re-tessellation)
> was correct. The corrected decode + a validated standalone port are below.

---

## 0. What `bspOptGeom` actually does (the load-bearing result)

`bspOptGeom` runs once at the tail of `bspRepartition` (after CSG + `SplitPolyList` + `bspRefresh`).
It does **two** things, in order, both operating in place on the `UModel`:

1. **Pass 1 — T-junction elimination (INSERTS vertices).** A *T-junction* is a point that lies in
   the **interior of another coplanar polygon's edge** (not at one of its vertices). Left alone it
   produces lighting seams. Pass 1 walks the BSP for the endpoints of every not-yet-shared node
   edge, finds each coplanar node whose polygon edge that endpoint splits, and **inserts the point
   as a new vertex into that node's ring** — growing `Model.Verts` and the node's `NumVertices`.
   This is why the editor's pool fattens to ~14 verts/node.

2. **Pass 2 — shared-side linking + `NumSharedSides` tally.** For every pair of node edges that are
   geometrically the same edge (same two point indices, opposite winding), it assigns a shared side
   id (`FVert.iSide`) and allocates a fresh id from `Model.NumSharedSides` (seeded at 4) the first
   time a pair is seen. **Purely combinatorial** (point indices + ring positions; no floating
   point).

Its own log lines: `"BspOptGeom begin"` → `"Geometry optimization"` (progress) →
`"BspOptGeom building sidelinks"` → `"Processed %i T-points, linked: %i/%i sides"` →
`"BspOptGeom end"`. The **`"Polys: %i -> %i"` / `"Nodes: %i -> %i"`** reduction lines belong to
`bspRefresh` (`0x36cd0`), which `bspOptGeom` calls internally once up front; `bspRefresh` is dead-node
GC (drops tree-**unreachable** nodes/surfs — see §4), not a redundant-split trimmer.

**Empirical golden shape** (`Test_Castle.dx`, `harness/optgeom_validate.py` + scratch inspection):
`NumSharedSides = 2739 = 4 (reserved) + 2735 (allocated)`; `max iSide = 2738`; **34 %** of verts
(5494 / 16163) carry `iSide != -1`; **2711** side ids are carried by exactly 2 verts and **all 2711
are exact shared edges** (same point-index pair, opposite winding), 24 by 3 verts (an edge shared by
3 faces). So pass-2 linking is **vertex-coincidence** based — because pass 1 already turned every
T-junction into a real shared vertex.

---

## 1. `bspOptGeom` body (`0x36870`–`0x36c32`, `ret 4`) — instruction-level (📖)

In-memory `UModel` offsets (self-consistent with `FBspNode`=0x40, `FVert`=8, `FBspSurf`=0x40,
`FVector`=12):

| mem off | meaning |
|---|---|
| `+0x58 / +0x5c` | `Nodes.Data / Nodes.Num` |
| `+0x68 / +0x6c` | `Verts.Data / Verts.Num` (`FVert` = {`iVertex`@+0, `iSide`@+4}) |
| `+0x88 / +0x8c` | `Points.Data / Points.Num` |
| `+0xfc` | `NumSharedSides` |
| node `+0x18` iVertPool · `+0x20` iFront · `+0x24` iBack · `+0x28` iPlane (coplanar chain) · `+0x36` (byte) NumVertices · `+0x37` (byte) NodeFlags |

**Prologue (`0x36870`–`0x3690b`):**
- `debugf("BspOptGeom begin")`; `StatusUpdate("Geometry optimization")`.
- `call 0x33dc0(Model, 0.25f)` — **point-merge prep** (`ShrinkModel`-style): merges near-coincident
  world points within 0.25 uu so side-links/T-tests compare by point index. **No-op on the golden**
  (closest point pair 0.76 uu apart — measured).
- `Editor->bspRefresh(Model, 0)` (vtable `+0x200`) — GC pass (§4).

**Build vertex-occurrence table (`0x3690b` ctor `0x31d70`, init `0x316d0`→`0x31830`):** a per-point
head array (`[ebp-0x6c]`, indexed by point index). `InitNode` (`0x31830`) is called for **every node
0..N**, and for **every ring vertex j** prepends a record `{node@0, ringpos@4, next@8}` (12-byte,
`FMemStack`) to `head[Verts[iVertPool+j].iVertex]`. So `table[p]` = **all** `(node, ringpos)` at which
`p` is a vertex, head→tail in **descending** `(node, ringpos)` (prepend order — load-bearing for pass
2's first-match).

`Model.NumSharedSides = 4`; then `for k in Verts: Verts[k].iSide = -1`.

**Pass 1 — T-junction elimination (`0x36939`–`0x36a0a`):**
```
for iNode in 0..Nodes.Num:
  for B in 0..node.NumVertices:                 # NumVertices re-read each iter (rings can grow)
    A  = (B ? B : NumVertices) - 1
    pB = Verts[iVertPool+B].iVertex ; pA = Verts[iVertPool+A].iVertex
    # dup-guard (0x36985): is there a node OTHER than iNode holding BOTH pA and pB as vertices?
    #   scan table[pB] (outer) x table[pA] (inner) for a common node != iNode.
    if not edge_shared_elsewhere(pA, pB, iNode):
        tpoints++                               # the "%i T-points" count
        AddPointLink(Model, table, root=0, pA)  # 0x325e0
        AddPointLink(Model, table, root=0, pB)  # 0x325e0
```
`AddPointLink` (`0x325e0`, **recursive**) descends the BSP for one point and inserts it wherever it
splits a coplanar edge:
```
dot = FPlane::PlaneDot(node.Plane, Points[point])          # Core!PlaneDot [0x100ce514]
if dot <  +0.25:  if node.iFront(+0x20)!=-1: recurse iFront   # bands from 0x100dcb00=+0.25,
if dot <= -0.25:  return                                       #            0x100dcb40=-0.25
if node.iBack(+0x24)!=-1: recurse iBack
if dot >= +0.25:  return
# -0.25 < dot < 0.25 : point lies ON this node's plane
cur = node
while cur != -1:                                              # coplanar chain via +0x28 (iPlane)
    if point is NOT a vertex of cur.ring AND lies in the interior of one of cur's edges:
        insert_ring_vertex(cur, edge, point)                  # 0x31920  (grows Verts, NumVertices++)
    cur = cur.iPlane
```
**The per-node ring scan** (`0x326fc`–`0x32977`, f32/f64 SSE) — **RE-DECODED 2026-07-18 to the
instruction level**, constants read live from the DLL (`0x100dcb00`=+0.25, `0x100dcb40`=-0.25,
`0x100dcb08`=1e-6 f64, `0x100dcb28`=0.251001 f64, `0x100dcb10`=0.5). **This is a genuine
point-on-edge-INTERIOR test** — the earlier "near-endpoint / along-edge weld" reading was a MIS-DECODE
(§6b) and is the byte-parity bug this section corrects. The load-bearing instruction is the
`??TFVector@@` call at `0x3276a` = **`Core.dll FVector::operator^` (the CROSS product)**: the scan
projects the point not onto the edge `E` but onto **`C = E × N`** (edge crossed with the node PLANE
NORMAL), i.e. it measures the **signed PERPENDICULAR distance of the point from the edge line**, in the
plane:

```
if point is already a ring vertex (exact iVertex index):  skip node
best = -1
for j in 0..NumVertices:                       # esi
    prev = (j ? j-1 : NumVertices-1)
    E    = P[cur=j] - P[prev]                   # ??GFVector (operator-)
    C    = E ^ N                                # ??TFVector (operator^ = CROSS), N = node plane normal
    if |C|² <= 1e-6:  continue                  # degenerate (jbe 0x32965; note: tests |E×N|, not |E|)
    proj = (C · (P[point] - P[cur])) / |C|      # signed PERPENDICULAR distance from the edge LINE
                                                #   (f32 dot, f64 |C| via appSqrt, proj back to f32)
    if proj >= +0.25:  BREAK  → no insert       # jae 0x32977 — point is OUTSIDE this edge (convex)
    if proj <= -0.25:  continue                 # jbe 0x32952 — point well INSIDE rel. to this edge
    # -0.25 < proj < 0.25 : point lies ON this edge's line
    M = 0.5*(P[prev] + P[cur])                  # edge midpoint
    if |E|²·0.251001 < |P[point] - M|²:  continue   # midpoint-capsule fail (jb 0x3293f, all f64;
                                                #   uses the REAL |E|², bounds the on-line point to seg)
    best = j                                    # accept, keep the LAST matching edge ([ebp-0x34]=esi)
# after a FULL scan (no break): if best>=0, insert point at ring position `best`
```

Because `|N|=1` and `E⊥N` in-plane, `|C| = |E|`, so `proj` is a perpendicular distance in world
units. A point in the **deep interior** of an edge (perpendicular distance ~0, inside the segment) **IS
welded** — that is exactly the CSG T-junction. `proj ≥ 0.25` on **any** edge means the point sits
outside that convex boundary → the point is not interior to this polygon → abort the node. Verified
against the editor's inserter oracle (`bspopt_insert_oracle.py`, 975 welds): e.g. node 1 (plane
`(-1,0,0,48)`) welds `(-48,-500,0)`/`(-48,-410,0)` at `edge=1` — both at `proj=0` (they lie ON the
z=0 edge `(-48,-380,0)→(-48,-530,0)`, `120`/`90` uu from the endpoints), which the old along-edge
reading wrongly rejected at `proj=-120/-90 ≤ -0.25`. Ported in `bspoptgeom.rs::tjunction_edge`.

**The inserter** (`0x31920`): asserts `NumVertices+1 < 16`; allocates `NumVertices+1` fresh slots at
the **end** of `Verts` (`0x31680`), copies the ring with the new vertex spliced in at `edge`
(`iVertex=point, iSide=-1`), sets `node.iVertPool` to the new base and `NumVertices++`. The old ring
slots are **orphaned**. **Crucially there is NO `bspRefresh` after `bspOptGeom`** (`bspRefresh` runs
once at the *front*, §0/§4), so the orphaned slots are **never compacted** — they survive into the
on-disk `Verts` pool. This is why the golden's pool is **16163** total while only **5496** slots are
live (referenced by a node ring): **10667 orphans** (measured on `Test_Castle.dx`). A compact
in-place splice can therefore never reach byte-parity — the port MUST reproduce the append-and-orphan
layout (`bspoptgeom.rs::insert_ring_vertex`, corrected 2026-07-18). After pass 1 the code **tears down
and REBUILDS the table** (`0x36a2c`/`0x31d70`/`0x316d0`) over the now-split rings.

**Pass 2 — side-links (`0x36a45`–`0x36b6f`):**
```
for iNode in 0..Nodes.Num:
  for B in 0..node.NumVertices:
    if Verts[iVertPool+B].iSide != -1: continue
    A = (B ? B-1 : NumVertices-1)
    # FIRST match wins: outer over table[pB], inner over table[pA]
    for (nodeB,posB) in table[pB]:
      for (nodeA,posA) in table[pA]:
        if nodeB==nodeA and nodeB!=iNode and (posA - posB) mod nodeB.NumVertices == 1:
           side = Verts[other.iVertPool + posA].iSide
           if side == -1: side = Model.NumSharedSides++     # allocate
           Verts[other.iVertPool + posA].iSide = side       # second endpoint of other's edge
           Verts[iNode.iVertPool  +   B    ].iSide = side    # second endpoint of this edge
           goto next_B
```
`(posA - posB) mod k == 1` means `other` traverses the shared edge as `pB→pA` — **opposite** winding
to `iNode`'s `pA→pB` — the correct adjacency. **Pass 3** (`0x36b7f`) just tallies the log counters
(`Σ NumVertices`, sides linked) and emits `"Processed %i T-points, linked: %i/%i sides"`.

**Helper RVAs:** `0x33dc0` point-merge · `0x325e0` `AddPointLink` (recursive) · `0x31920` ring-vertex
inserter · `0x31680` Verts grow · `0x316d0`/`0x31830` table init · `0x31d70` table ctor · `0x33950`
table teardown · vtable `+0x200` `bspRefresh`.

---

## 2. Standalone port (`uedcli-native/src/bspoptgeom.rs`) & validation ✅

`pub fn bsp_opt_geom(model: &mut Model)` = `merge_near_points` → `eliminate_tjunctions` (pass 1) →
`build_side_links` (pass 2), all pure over `model::Model`. `build_side_links` is exposed separately.
FFI test entry `opt_geom_from_arrays` (in `lib.rs`) reconstructs the golden Model's touched fields
from flat arrays and runs the pass. **`harness/optgeom_validate.py` result (golden `Test_Castle.dx`):**

- **pass 1 idempotent** — 0 vertices inserted (16163 → 16163), node `iVertPool`/`NumVertices`
  unchanged. The golden is a **fixpoint** of the perpendicular interior weld: every on-edge T-point is
  already a ring vertex, so the index-equality guard skips it (validated with the *instruction-exact*
  `0x326fc` transcription re-decoded 2026-07-18, §6b — the CROSS-product `E×N` perpendicular test).
- **pass 2 byte-exact** — all **16163** `FVert.iSide` reproduced, `NumSharedSides = 2739`.

Rust unit tests (`cargo test bspoptgeom`): shared-edge → 1 side / `NumSharedSides=5`;
`tjunction_inserts_near_endpoint` (a point on a long quad's edge line **is** welded, appended +
orphaned); `tjunction_welds_mid_edge_interior` (a **deep-interior** mid-edge point IS welded — the
perpendicular test, guarding against regressing to the old along-edge reading); `merge_near_points`
no-op when far.

---

## 3. Wiring into `bspcsg.rs` — call at csgRebuild STEP 5, not the repartition tail (corrected 2026-07-18)

`csgRebuild` (`Editor 0x4a650`, `80-bspbuild-topology.md §1`) issues, IN ORDER: (1) structural
brushes → incremental `bspBrushCSG`; (2) `bspRepartition` (`bspBuildFPolys`→`bspMergeCoplanars`→
`bspBuild`/`SplitPolyList`→`bspRefresh`); (3) **`TestVisibility`** — the zone/portal fragment-split
(our `zones::assign_leaves_and_zones` "Pass D", nodes 1127→1156); (4) **semisolid/detail brushes** →
incremental `bspBrushCSG` again (NOT repartitioned); (5) **`bspOptGeom`** → `bspBuildBounds`.

So `bspOptGeom` is **step 5** — it runs AFTER the zone split AND the semisolid layer, on the FINAL
1156-node tree in ENGINE convention. An earlier wiring (2026-07-17) called it at the **repartition
tail** (step 2), i.e. at 1127 nodes, in BUILD convention (front/back not yet swapped), before the zone
split created the extra coplanar faces. **Corrected 2026-07-18:** the call now sits in
`build_geometry_bspcsg` **after `finalize(&mut model)`** (which does the zone split + the front/back
swap + bbox) and after the Pass-2 semisolid loop, right before `passes::bsp_build_bounds`. This moved
pass-1 from **0 → 22** insertions (it now sees the zone-split tree in the right convention).

- **Inputs (read):** `model.points`, per node `plane`/`i_vert_pool`/`num_vertices`/`i_front`(+0x20)/
  `i_back`(+0x24)/`i_plane`(+0x28 coplanar chain), `model.verts[].i_vertex`. Post-`finalize` these are
  final and in engine convention; Pass D appends its split fragments onto the `i_plane` chain, so the
  coplanar chain pass 1 walks includes them.
- **Outputs (write, in place):** grows `model.verts` (+ node `i_vert_pool`/`num_vertices`) via the
  append-and-orphan inserter; sets every `model.verts[].i_side`; sets `model.num_shared_sides`.
- **Note:** our `insert_ring_vertex` is byte-faithful to the editor's append-and-orphan `0x31920`
  (old slots orphaned, never compacted) — no post-`bspRefresh` runs after it, matching the editor.

---

## 4. `bspRefresh` (`0x36cd0`) — the GC, unchanged (📖)

`bspRefresh(Model, NoRemapSurfs)`: alloc `NodeRemap`/`SurfRemap` (`-1`), `MarkReachable(0)`
(`0x34aa0`, recursive from root 0 through children `+0x20`/`+0x24` and coplanar `+0x28`), then compact
Surfs (log `"Polys: %i -> %i"`), Nodes (`"Nodes: %i -> %i"`), remap `iSurf`/children/coplanar, then
Verts/Vectors/Points. Removes only **tree-unreachable** elements — every `SplitPolyList` node is
reachable, so it can't collapse an over-split tree. (`NoRemapSurfs==0` keeps all surfs.)

---

## 5. Split distribution (for the `bspcsg.rs` agent, secondary)

The per-surf **partition** vertex sets (which planes cut which walls) still come from the real
`Balance=50 FindBestSplit` + faithful `SplitPolyList` (`FindBestSplit` byte-ported §6.3 of the CSG
docs). `bspOptGeom` is **downstream** of that: it doesn't choose split planes, it (a) welds
T-junctions the splits created between adjacent polygons and (b) side-links. So a split-*distribution*
divergence vs the editor is a `SplitPolyList` issue (coplanar chaining / candidate stride /
structural-splitter skip), confirmed with a differential editor node dump — **not** a `bspOptGeom`
issue. But the **vertex-COUNT** gap (4945 → 16163) is largely `bspOptGeom` pass 1, now ported.

---

## 6. The edge test: perpendicular (cross-product) interior weld, instruction-exact (2026-07-18)

The port's edge test is `proj = (E×N)·(point-v_cur)/|E×N|` — the signed **perpendicular** distance of
the point from the edge line — with the `±0.25` band, the `proj ≥ 0.25` whole-scan break, the
`|E|²·0.251001 ≥ |point-midpoint|²` capsule (real `|E|²`, bounds the on-line point to the segment),
and the "keep LAST accepted edge" tie-break, in the editor's FP model (f32 cross/dot, f64
`appSqrt(|E×N|²)` for the divide, f64 capsule). It reproduces the golden's **zero-insertion fixpoint**
(`optgeom_validate.py`: 16163→16163, iSide byte-exact, `NumSharedSides=2739`) and, on the from-scratch
castle, **959/975 of the editor's exact welds** (see §6b). There is no remaining FP ambiguity in the
test itself — the residual is upstream (§6a).

## 6b. The detector HAD a real bug (along-edge vs perpendicular) — RE-DECODED & FIXED (2026-07-18)

An earlier decode (superseding note now retracted) transcribed the ring scan as an *along-edge*
projection `proj = E·(point-v_cur)/|E|` and concluded it was a "near-endpoint weld" that fires on only
~22 castle cracks — and §6a (below, now partly superseded) then concluded the detector was correct and
the whole pool gap was upstream. **Both were wrong about the detector.** The `0x3276a` call is
`??TFVector@@QBE?AV0@ABV0@@Z` = `FVector::operator^` = the **CROSS product** (confirmed by resolving the
Editor.dll import against Core.dll), so the projection vector is `E × N`, not `E`. The old reading
dotted the point offset with the edge DIRECTION (measuring how far *along* the edge the point sits)
instead of with the edge's in-plane NORMAL (measuring how far *off* the edge line it sits). Result: it
rejected every **deep-interior** T-junction (`proj = −|offset-along| ≤ −0.25`) and welded almost
nothing. Fixing `tjunction_edge` to the true perpendicular test moved the castle from **22 → 1012
welds**, matching **959 of the editor's 975** (permutation-invariant match on `(node-plane, welded-P)`
via `bspopt_insert_oracle.py`); the ~16 unmatched-each-way are FP-alias duplicates (e.g. editor
`−111.9583` vs native `−112.0`) plus the +37 over-weld (§6a). This is the primary geometry-body parity
lever the old decode missed.

## 6a. The RESIDUAL after the detector fix is the point-pool / CSG-transient accounting (2026-07-18)

With the perpendicular detector (§6b) the from-scratch castle is native **1797 points / 10418 verts /
26 vectors / `NumSharedSides` 2728 / Σnv 5533** vs editor **2035 / 16163 / 26 / 2739 / 5496**. The
**live ring geometry now matches**: comparing the distinct live-vertex coordinate sets, **1549/1555 are
identical**, the 6 differences per side are sub-0.05 uu FP-noise aliases (native `(-112.0,-160,160)` ↔
editor `(-111.9583,-160,160)`), and by multiplicity native has +37 live verts — the **over-weld**. So
`SplitPolyList` DOES place the editor's split vertices (the earlier §6a claim that it distributed them
differently was an artifact of comparing raw node INDICES across an isomorphic-but-permuted tree). What
remains is entirely **point-pool bookkeeping**:

- **Orphan points.** The editor does NOT clear the Points pool at `bspRepartition`; it keeps ~2091
  pre-opt points (incl. CSG-transient orphans not referenced by any live ring), and its bspOptGeom
  point-merge prologue (`0x33dc0`, radius 0.25) trims 56 → 2035. Native (`bspcsg.rs` @ repartition)
  **clears** Points/Verts and rebuilds only from the live soup, so it holds 1797. Diffing the final
  pools by coordinate: native is **missing 485** editor coords (orphan CSG-transient points, z-clusters
  75/80/88/124/125/176/277/287/292/3000…) and has **247 spurious** coords the editor lacks (z-clusters
  −80/−12/0/64/160). Native's raw *uncleared* CSG pool is ~6627 (3× the editor's) — native's
  incremental `bspBrushCSG` over-produces transient points (rolled-back grazes leak), so neither
  clearing (→1797, over-merged) nor not-clearing (→6627) matches the editor's 2091.
- **Over-weld + orphan-count.** The +37 live over-welds are welds of native's **spurious** z=−12/−80
  pool points (they exist in native's rings, so the correct detector welds them); the editor lacks
  those points so never welds there. And native's 1012 welds orphan only ~4885 verts vs the editor's
  975 welds orphaning ~10667 (editor concentrates many repeat-welds on faces carrying its extra
  orphan-adjacent T-points → big orphaned rings). So verts **16163 vs 10418**, points **2035 vs 1797**
  and `NumSharedSides` **2739 vs 2728** are ALL downstream of this ONE point-pool divergence, not the
  detector.

**Conclusion.** The detector is fixed and byte-faithful; closing the last verts/points/nss gap is a
**`bspcsg.rs` incremental-CSG point-accounting** problem — reproduce the editor's non-clearing
repartition pool (2091 pre-opt) by stopping `bspBrushCSG`'s transient-point leak, NOT by loosening the
detector. This is deeply entangled with the byte-exact node/surf/vector tree (every `surf.pBase` /
`vert.iVertex` is a pool index), so it must be done without perturbing that tree — tracked in
`board/inbox/`. See §8 for the (now-closed) vectors gap.

## 8. The vectors gap (44 vs 26) is missing authored texture axes, not dedup (2026-07-18)

Native emits **44** `Vectors` vs the editor's **26** (18 only-native, 0 only-editor). The oracle shows
the editor already has **26 at `bspOptGeom` entry**, so this is a pure tree-build gap. The 18 extras
are face-LOCAL texture bases (e.g. `0.84072,-0.34873,-0.41421`; `-0.38575,-0.38575,0.83809`) that no
`bspAddVector` threshold could merge into the 26 — they are genuinely different vectors. Root cause:
`bspcsg::alloc_surf` calls `default_texture_axes(normal)` (a `helper×n` face-local basis) whenever the
surf's `FPoly` carries no `TextureU/TextureV`. It never does, because `materialize._build_brush_input`
does **not** parse/thread the trunk brush polys' authored `TextureU`/`TextureV` — which ARE present in
the T3D and are all world/45°-aligned (`(0,0,1)`, `(0.707,-0.707,0)`, …), i.e. they dedup straight into
the editor's 26-normal pool. **Fix = thread authored texture axes** from the trunk (`materialize.py`) →
Rust `BrushInput`/`FPoly` → `alloc_surf`'s `have_u && have_v` branch. That spans the Python brush-input
layer + the Rust `FPoly` plumbing (`build.rs`/`csg.rs`/`lib.rs`), OUTSIDE `bspoptgeom.rs`/`bspcsg.rs`
dedup — tracked in `board/inbox/`. (No `bspAddVector` change helps; the vectors are mis-*generated*,
not under-*merged*.)

**CLOSED 2026-07-18.** Threaded the authored per-poly `TextureU`/`TextureV` end-to-end:
`materialize._build_brush_input` now emits two per-poly axis arrays (`tex_u_flat`/`tex_v_flat`, one
`x,y,z` triple per poly, `(0,0,0)` when a poly omits the axis) → `BrushTuple` (two new trailing
`Vec<f32>` fields, `lib.rs`) → `brush_from_tuple` sets `FPoly::texture_u/texture_v`. The rest of the
Rust plumbing already existed: `FPoly::transform` rotates the axes into world space, `clone`/
`empty_copy` preserve them through CSG splitting/merge, and BOTH cores' `alloc_surf` already took
the `have_u && have_v` authored branch. Result on the castle (`NativeCastle.dx` vs `Test_Castle.dx`):
**Vectors 44 → 26, exactly the editor's pool** (rounded pools equal as sets); tree/soup unchanged
(nodes 1156, surfs 485, shared_sides ~1161); all **485** surfs' `(TextureU,TextureV)` axes match the
editor's per-surf (0 mismatches, the `iU`/`iV` indices resolve to the right vectors). `bin/test` green
(1410 passed). The two non-materialize `build_geometry` callers (`preview_native.py`, the differential
golden) pass empty axis lists → unchanged default basis (they don't pin the Vectors pool). No change to
`bspAddVector`, `bspcsg.rs`, or `bspoptgeom.rs`.

---

## 7. Portal cospatial side-face discard (independent, was §5) (📖)

Unchanged from the prior decode and orthogonal to `bspOptGeom`: a portal brush stays `CsgOper=CSG_Add`
but is forced `PF_NotSolid, ¬PF_Semisolid` (`csgRebuild 0x4a814`: `and eax,~0x20 ; or eax,8` gated on
`test eax,0x4000000`). Its side faces are dropped because `FilterEdPoly`'s coplanar branch (`0x32e54`,
`comiss dot,0 ; jb`) classifies them `F_INSIDE`/`F_COSPATIAL_FACING_OUT` (facing sign, **exact 0.0
inclusive to FACING_OUT**), which `AddFunc` (`0x31770`) discards — a **classification-fidelity** slice
in `FilterEdPoly`, not an `AddFunc` keep-set issue. (`verify_bspoptgeom.py` covers these.)

## 9. The pass-1 dup-guard table is LIVE — the +2 castle over-weld fix (✅ 2026-07-18)

**Symptom (RAW, `ground_truth_bytediff.py`, `NativeCastle.dx` vs `Test_Castle.dx`).** After the Pass-D
vert re-emit (§70 §11) the native pool sat at **Verts 16183 vs editor 16163 (+20)**. The residual
split (measured at the `bspOptGeom` boundary with the pool oracles): **+9 already present at
`bspOptGeom` ENTRY** — native pool **10527** vs editor **10518** (a Pass-D/`bspcsg` orphan over-emit,
out of `bspoptgeom.rs`'s lane) — **plus +11 added by `bspOptGeom` itself**: native welded **977**
T-points vs the editor's **975** (`bspopt-pool.log`: editor 10518→16163 = +5645; native 10527→16172
after fix / 16183 before = +5656/+5645). The two extra native welds (isolated with a tolerant
plane+P matcher, all 975 editor welds otherwise matched) were BOTH into **node 1096** (plane z=−12),
welding the pit points **(48,−500,−12)** and **(48,−410,−12)** at ring edges 1/4 — genuine
edge-interior T-junctions the editor leaves alone.

**Why the editor leaves them.** The dup-guard (`0x36985`, `edge_shared_elsewhere`) skips an edge if
some OTHER node already holds BOTH its endpoints. The triggering edges are the pit's vertical wall
segments **(48,−500,−8)→(48,−500,−12)** on node 1150 and **(48,−410,−8)→(48,−410,−12)** on node 1154.
Pre-pass1 only node 1150 (resp. 1154) holds both endpoints, so with a **static** table the edge is
"unshared" → it fires `AddPointLink`, whose descent reaches node 1096 and welds. BUT node 1148 (resp.
1152) gets the **−8** point WELDED INTO IT earlier in the same pass (a matched weld both sides do) — so
AFTER that weld node 1148 holds BOTH −8 and −12, i.e. it now shares the edge. The editor's inserter
(`0x31920`) **updates the vertex-occurrence table's per-point head list on every weld**, so by the time
node 1150's edge is reached the guard sees the freshly-shared vertex and skips → no weld into 1096. Our
port built the table ONCE and never updated it, so it over-welded.

**Fix (`bspoptgeom.rs`, in lane).** Make the pass-1 table **live**: after `insert_ring_vertex` welds
`point` into node `cur`, prepend `(cur, edge)` to `table[point]` (membership is all the guard reads).
`add_point_link` now threads `&mut table`. Pass 2 still rebuilds a fresh table.

**RAW result** (`ground_truth_bytediff.py`): pass-1 welds **977 → 975** (== editor); **Verts count
16183 → 16172** (editor 16163); **Verts section 53924 → 53887 B** (editor 53866); **NumSharedSides
stays byte-identical 2739**; **Nodes section 54035 → 54034 B** (now == editor's `iVertPool` encoding).
Guards unregressed: nodes 1156/1156 planes, soup 853/853, surfs 485, vectors 26, Points 2035, Bounds
484, LeafHulls 308/3866/1710 (+0/+0), LightMap 484, Leaves 384. `optgeom_validate.py` golden fixpoint
still holds (16163→16163, iSide byte-exact, NSS 2739). `cargo test bspoptgeom` 4/4; offline suite 1705
passed / 1 skipped / 1 xfailed.

**Evidence harness (committed):** `editor-tree-oracle/weld_livetable_diff.py` reconstructs BOTH the
native and editor PRE-pass1 models and shows static→977 (+2 into node 1096) / live→975 (0) on **both**
— i.e. the divergence was purely the missing live update, not a detector or Pass-D difference.

**Residual (honest, out of lane).** Native is still **+9 verts** over the editor (16172 vs 16163), all
of it the **+9 orphan slots present at `bspOptGeom` ENTRY** (Pass-D killed-fragment re-emit in
`zones.rs`, native pool 10527 vs 10518). The Verts section is still not byte-identical because the
editor's **Pass-D orphan verts carry STALE pre-`bspRefresh` point indices** (a `passes.rs` bsp_refresh
point-compaction artifact) that native's "snap to nearest existing point" does not reproduce (§70 §11).
That orphan-`iVertex` parity is NOT reachable from `bspoptgeom.rs`: the `bspOptGeom`-created orphans
(old rings left by `insert_ring_vertex`) already reference the post-compaction live indices and match;
the stale ones are Pass-D orphans emitted upstream. Closing it needs `zones.rs` (emit Pass-D orphans
with the editor's pre-compaction indices) + `passes.rs` (simulate the `bspRefresh` renumber) — tracked
in `board/inbox/`.
