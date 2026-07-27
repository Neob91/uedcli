# 82 — `bspBrushCSG` incremental CSG: the port-ready decode

**Date:** 2026-07-17. **Status:** DECODE COMPLETE + coplanar-IsCsg seeding PORTED & VERIFIED. The §6
"world-face SPLIT-and-re-add" crux, the Subtract leaf mirror, and the coplanar cascade (child-first
order AND the IsCsg Outside-seeding, §8.3) are all instruction-decoded and the seeding fix is landed in
`bspcsg.rs` (N=2 castle subset now node-count/plane-multiset exact vs the editor). §6/§8.1 fragmentation
+ zones remain the open items for full byte-identity (see §8.3 tail / §8.4). **Soup is FACE-SET-exact
through N=32; the N=33 residual is now traced to full mechanism (§10.6): a merge-blocking clip on a
DEAD merlon-east node — a cumulative incremental-tree-ORDER divergence, NOT any local rule (three
decisive negatives in §10.6, incl. a disasm proof that the engine has no dead-node skip). No safe code
fix; characterized, not forced.**

**Reader with no prior context:** UnrealEd builds the world BSP for a level by feeding brushes
(convex solids the mapper places) into the engine one at a time. Each brush *adds to* or *subtracts
from* a growing binary-space-partition tree of the world. Our native builder (`uedcli-native`)
currently takes a shortcut — it CSG's brushes into a flat surface list and partitions that once — so
its tree is leaner and not byte-identical to UnrealEd's. To get a byte-identical `.dx` we must port
UnrealEd's actual *incremental* algorithm. This doc is the decoded algorithm.

**Confidence:** ✅ uedcli-used/live-verified · 🔬 live-probed (static disassembly) · 📖 binary-extracted.
**Evidence:** `../re-raw-zones/bspbrushcsg-filter-decode.md` (full VA-cited disasm, this session) +
`../re-raw-zones/bspbuild-splitpolylist-decode.md` (the already-decoded `bspBuild`/`SplitPolyList`/
`FindBestSplit`/`bspAddNode`/`csgRebuild` half). Read those for the raw instructions; this section is
the synthesis. Supersedes the "bevel plane" hypothesis in `80-bspbuild-topology.md §0` (see §3 below).

---

## 0. The crux, up front: THERE ARE NO BEVEL PLANES 🔬

The prior working model — "each brush builds a temp BSP whose *bevel planes* bound the fragment and
make solid leaves watertight" — is **wrong**. Instruction-level decode of the entire filter half
shows UE1 has **no bevel-plane generation anywhere** in `bspBrushCSG`. Watertightness comes from two
plain steps:

1. **Add the brush's own faces as nodes.** Each brush polygon is filtered down the *growing world
   tree* (`FilterEdPoly`). Wherever a surviving fragment lands in an OUTSIDE leaf, it is added as a
   new BSP node **whose plane is that brush face's own plane** (`AddBrushToWorldFunc → bspAddNode`).
   The fragment was clipped by every ancestor node plane on the way down, so it tiles exactly the
   part of that face inside the leaf cell → the solid region ends up bounded by real brush faces on
   every side. That is the watertightness.
2. **Cut the world with the brush.** The brush's faces are `bspBuild`-partitioned into a *plain
   convex temp BSP* (the brush's face planes, nothing added). Then every existing world face is
   filtered through that temp BSP (`FilterWorldThroughBrush`); world faces now interior to the brush
   are deleted/split.

The "extra nodes and 4× FVerts" in UnrealEd's tree come entirely from this **incremental
fragmentation** (each brush face splits into many nodes as it descends; world faces get re-split by
each new brush) plus the semisolid second pass and zone splits — **not** from any bounding/bevel
pass. The native scaffold `bound_leaked_solid_leaves` (`80 §3`) is a synthetic stand-in for effect
(1); porting the real incremental filter deletes it.

---

## 1. Per-routine decode-completeness table

| # | Routine | VA (Editor) | Status | Notes |
|---|---|---|---|---|
| 1 | `bspBrushCSG` (driver) | `0x355e0` | **DECODED** 🔬 | Full CFG §2; LOOP1 transform, LOOP2 filter, temp-BSP+world-filter. |
| 2a | `bspFilterFPoly` (driver) | `0x31f50` | **DECODED** 🔬 | empty-tree vs `FilterEdPoly`. |
| 2b | `FilterEdPoly` (recursion) | `0x32bf0` | **DECODED** 🔬 | Front/Back/Split; `Outside` propagation; `SplitInHalf@≥14`. |
| 2c | `FilterLeaf` (dispatch) | `0x33130` | **DECODED** 🔬 | 6-value `EPolyNodeFilter`; coplanar front/back passes. |
| 2d | coplanar cascade (in 2b) | `0x32d91` | **DECODED** 🔬 | Child-first order line-proved (§8.2): Dot≥0→iFront first, Dot<0→iBack first. One Outside-seed nuance residual (§8.3). |
| 3a | `AddBrushToWorldFunc` | `0x31770` | **DECODED** 🔬 | adds on filter {0,2,5&!semisolid}; NO Reverse; `bspAddNode(…,NF_IsNew,…)`. |
| 3b | `SubtractBrushFromWorldFunc` | `0x348c0` | **DECODED (line-transcribed)** 🔬 | NOT a mirror: adds on {1,3} ONLY (no F_4, no semisolid gate), Reverse-wrapped. §8.1. |
| 4 | `FilterWorldThroughBrush` | `0x33250` | **DECODED (split-and-re-add)** 🔬 | world face → brush temp BSP; interior→delete, straddler→re-add every outside cut fragment. §8. |
| 4a | world-thru-brush leaf funcs | `0x31b90` (Add) / `0x34980` (Sub) | **DECODED** 🔬 | jump-table on F; RE-ADD outside cut-fragments (bit31 gate), DISCARD interior. §8. |
| 5 | `bspNodeToFPoly` (vtbl+0x1f8) | `0x365b0` | **DECODED** 🔬 | node→FPoly; Normal/tex PRESERVED from surf, verts from pool. |
| 6 | `bspBuildFPolys` | `0x36090` | **DECODED** 🔬 | empties Polys, `MakeEdPolys` walk, iLink reset. |
| 6b | `MakeEdPolys` (node walk) | `0x33bb0` | **DECODED (mechanism)** 🔬 | recursive `bspNodeToFPoly` append. |
| 7 | `bspMergeCoplanars` | `0x36200` | **DECODED** 🔬 | group by iLink+coplanar+normal(+tex); merge groups>1. |
| 7b | `MergeCoplanarPolys` | `0x33cb0` | **DECODED** 🔬 | fixpoint pairwise `TryToMerge`. |
| 7c | `FPoly::TryToMerge` | `0x34b10` (**Editor**) | **DECODED (line-transcribed)** 🔬 | Instruction-exact 2026-07-17. `>16`-vert gate, first-shared-point + fwd/bwd neighbour edge test, `FPointsAreSame` **box** test, exact splice, RemoveColinears. §10. |
| 8 | `FindBestSplit` | `0x335d0` | **DECODED (exact op-order)** 🔬 | §5; matches prior decode. |
| — | `bspBuild`/`SplitPolyList`/`bspAddNode` | `0x35ef0`/`0x34530`/`0x34e80` | **DECODED (prior)** 🔬 | `bspbuild-splitpolylist-decode.md`; §4 verifies surf/pool emission. |
| — | `bspRepartition`/`csgRebuild` | `0x49fc0`/`0x4a650` | **DECODED (prior)** 🔬 | pipeline order §7; re-confirmed. |
| — | `bspOptGeom` | `0x36870` | **out of this task** 📖 | decoded in `42-bspoptgeom-decode.md`; still a from-scratch port. |

**Can the port be written from docs alone?** For the structural/topology core (routines 1–8 + prior
`bspBuild` half): **yes** — including the world-face SPLIT-and-re-add (§8), which is the fix that
closes the FVert-fatness + solidity residual (see §8.4). The remaining live-differential item is the
coplanar Outside-seed nuance (§8.3), low-risk and gated by the existing CSG differential fixtures.
`TryToMerge` (7c) is now instruction-transcribed — see §10. `bspOptGeom` remains its own port
(already tracked).

---

## 2. `bspBrushCSG` — the incremental driver (VA `0x355e0`) 🔬

Signature `bspBrushCSG(this=GEditor, ABrush* Actor, UModel* Model, DWORD PolyFlags, ECsgOper CsgOper,
UBOOL bBuildBounds, UBOOL bMergePolys)`. `ECsgOper`: Active=0, **Add=1, Subtract=2**, Intersect=3,
Deintersect=4. Full CFG (with VAs) in the evidence file §2; the port shape:

```
Brush = Actor->Brush;  if (!Brush) return;
NotPolyFlags = (CsgOper==Add) ? 0 : (PF_NotSolid|PF_Semisolid /*0x28*/);
TempModel = GEditor->TempModel;  TempModel->EmptyModel(1,1);
Orientation = Actor->BuildCoords(&Coords, &Uncoords);

// LOOP 1 — brush polys -> world space, accumulate in TempModel->Polys
for i in 0..Brush->Polys.Num:
    Ed = Brush->Polys[i]                                  // copy
    Ed.PolyFlags = (Ed.PolyFlags | PolyFlags) & ~NotPolyFlags
    Ed.Actor = Actor;  Ed.iBrushPoly = i;  if Ed.iLink==-1: Ed.iLink=i
    Ed.Transform(Coords, Actor->PrePivot, Actor->Location, Orientation)
    d = Ed.Normal · (Ed.Vertex[0] - Ed.Base);  if |d|>1e-4: Ed.Base += Ed.Normal*d   // snap base to plane
    TempModel->Polys.Add(Ed)

if CsgOper in {Add,Subtract}:
    // LOOP 2 — grow the world tree by filtering each brush poly through it
    for i in 0..TempModel->Polys.Num:
        Ed2 = TempModel->Polys[i]
        Ed2.PolyFlags &= 0x7fffffff
        if Ed2.iLink==i: TempModel->Polys[i].iLink = Ed2.iLink = Model->Surfs.Num   // seed a new surf
        else:            Ed2.iLink = TempModel->Polys[Ed2.iLink].iLink                // share surf
        bspFilterFPoly( Add? AddBrushToWorldFunc : SubtractBrushFromWorldFunc, Model, &Ed2 )

    // cut the world with the brush's convex temp BSP
    if Model->Nodes.Num!=0 and !(PolyFlags & 0x28):
        GEditor->bspBuild(TempModel, Opt=0, Balance=0, PortalBias=1, RebuildSimplePolys=0)  // plain convex partition
        TempModel->BuildBound()
        FilterWorldThroughBrush(Model, TempModel, CsgOper, 0, &TempModel->Bound)
// (Intersect/Deintersect and bspCleanup tails not used by MAP REBUILD)
```

> **`bspBuild` is a 5-arg function** `bspBuild(Model, EBspOptimization Opt, INT Balance, INT
> PortalBias, INT RebuildSimplePolys)` (`ret 0x14`) — the prior `bspbuild-splitpolylist-decode.md`
> named only four (omitting `PortalBias`). The temp-brush call pushes reversed-args `(TempModel,
> 0,0,1,0)`, so `RebuildSimplePolys=0` and the `1` is `PortalBias`; do NOT read it as
> `RebuildSimplePolys=1`.

The **surf-share seeding** in LOOP 2 (`iLink==i → Surfs.Num`) is what makes all fragments of one
brush face share one `FBspSurf`; `bspAddNode` allocates the surf the first time it sees
`iLink==Surfs.Num` and shares it thereafter (§4). Reproduce this exactly — surf ORDER (Phase C) and
pool ORDER (Phase B) depend on it.

---

## 3. The filter recursion (`FilterEdPoly` `0x32bf0`) 🔬

Filters one FPoly down the world tree; at each node splits the poly by the node's surf plane and
recurses, propagating an `Outside` flag; at a `-1` child (leaf) or a coplanar node it calls
`FilterLeaf`, which invokes the per-op leaf callback. The `Outside` propagation is **the same rule the
native `collect_leaks` already uses** (`80 §3`):

```
SP_Front (poly in front):  Outside' = Outside || Node.IsCsg();   descend Node.iFront (+0x24)
SP_Back  (poly behind):    Outside' = Outside && !Node.IsCsg();  descend Node.iBack  (+0x20)
SP_Split:                  recurse BOTH children with the two split halves + the two Outside' values
SP_Coplanar:               coplanar cascade (§ evidence 3) -> FilterLeaf with a cospatial filter
if child == -1:            FilterLeaf(...) instead of recursing
if EdPoly.NumVertices >= 14: SplitInHalf first, filter each half (vertex-overflow guard)
```
`FBspNode::IsCsg(node) = NumVertices>0 && !(NodeFlags & (NF_NotCsg|NF_IsNew /*0x21*/))` (`0x33b80`) —
**a node added THIS brush pass (NF_IsNew=0x20) does not yet count as solid**, so the brush's own new
faces don't prematurely flip `Outside` while the rest of the same brush is still filtering in.

**`FilterLeaf` `0x33130`** maps `(iOriginalNode, bProcessingBack, frontOutside, backOutside)` to one of
six `EPolyNodeFilter` values and calls the callback:

| filter | value | meaning |
|---|---|---|
| F_OUTSIDE | 0 | ordinary leaf, region outside |
| F_INSIDE | 1 | ordinary leaf, region inside (solid) |
| F_COPLANAR_OUTSIDE | 2 | coplanar node, both sides outside |
| F_COPLANAR_INSIDE | 3 | coplanar node, both sides inside |
| F_COSPATIAL_FACING_IN | 4 | coplanar, front outside / back inside |
| F_COSPATIAL_FACING_OUT | 5 | coplanar, front inside / back outside |

**Node-adding callbacks** (VA `0x31770` Add / `0x348c0` Subtract):

```
AddBrushToWorldFunc:      add node on filter ∈ {F_OUTSIDE, F_COPLANAR_OUTSIDE, F_COSPATIAL_FACING_OUT&!PF_Semisolid}   (NO Reverse)
SubtractBrushFromWorldFunc: add node on filter ∈ {F_INSIDE, F_COPLANAR_INSIDE} ONLY — NOT a mirror
                            (no F_COSPATIAL_FACING_IN, no semisolid gate); the face is Reverse()d around the add. §8.1
  -> bspAddNode(Model, iNode, ENodePlace, NF_IsNew /*0x20*/, EdPoly)
```

The `ENodePlace` (NODE_Front=1/NODE_Back=0/NODE_Plane=2/NODE_Root=3) is passed straight from the
descent so the new node is spliced into the correct child slot / coplanar chain (`bspAddNode` details
in the prior decode).

---

## 4. Node/surf/pool emission — `bspAddNode` (VA `0x34e80`) 🔬

Re-verified this session against the new-surf path (`0x34eef`–`0x34fc0`):
- **New surf** (when `EdPoly.iLink == Surfs.Num`): `Surf.pBase = bspAddPoint(EdPoly.Base)`,
  `Surf.vNormal = bspAddVector(EdPoly.Normal)`, `Surf.vTextureU/V = bspAddVector(EdPoly.TextureU/V)`,
  `Surf.PolyFlags = EdPoly.PolyFlags & 0x3cffffff`, `Surf.Texture/Actor/iBrushPoly` copied from EdPoly.
  Else the existing surf at `iLink` is **shared** (range-checked, else `appFailAssert`).
- **FVert pool:** `Node.iVertPool = Verts.Add(NumVertices)`; each vertex `bspAddPoint`'d into
  `Model->Points` (dedup via `FindNearestVertex`, threshold 0.002 — `fp-classification-sites.md §7`),
  **collapsing consecutive duplicates**. This is where the 16163-FVert pool is emitted, node by node.
- `NODE_Plane` (coplanar) appends along the `iPlane` chain; `>16`-vert polys split into two nodes
  sharing verts 14/15 (prior decode).

`FBspSurf`/`FBspNode`/`FPoly` field maps: see evidence §1. Load-bearing: **Normal & Textures are
preserved from the authored surf, never recomputed** (`bspNodeToFPoly` and `FPoly::Transform` both
carry the parsed normal; `Finalize` recomputes only a zero normal — Phase-0 finding holds).

---

## 5. `FindBestSplit` — exact score op-order (VA `0x335d0`) 🔬

> **⚠️ PARAM CORRECTION (2026-07-17) — this is the FIRST-DIVERGENCE root cause.** The "MAP REBUILD:
> 50 / 70 / OPTIMAL" annotations below were **WRONG**. Full decode of the actual call chain
> `csgRebuild → bspRepartition(0x49fc0) → bspBuild(0x35ef0) → SplitPolyList(0x34530) → FindBestSplit`
> proves the repartition runs with **Balance=12 (`0xc`), PortalBias=0, Opt=GOOD(1) → stride
> `max(NumPolys/10,1)`** — NOT 50/70/OPTIMAL. Evidence + all VAs:
> `../re-raw-zones/findbestsplit-params-decode.md`. The score op-*order* below is correct; only the
> three constants are fixed. **Subset differential (harness/subset_diff.py) pins the first native↔editor
> tree divergence at N=2 (World Subtract + WallBack Add): a pure tree-ORDER split — all 14 editor
> planes are present in the native 23-node tree, native just has 9 SURPLUS re-fragmentation nodes.**
> The cause: `find_best_split` root choice. On the (near-identical) N=2 soup the floor face and the
> WallBack Add face TIE at Balance=50 (`Score=50·|F−B|+50·Splits` = 500 each); native's earliest-wins
> picks the WallBack side plane, which then shreds the ceiling/floor/walls. At **Balance=12** the
> floor wins strictly (`12·10+88·0=120` vs WallBack `12·6+88·3=336`) → the editor's exact tree.
> Empirically (harness/validate_params.py): Balance=12/PB=0/GOOD reproduces the editor golden
> node-for-node at N=2,4,6; full-castle repartition-soup SplitPolyList drops **1607→1112 nodes**
> (Balance is ~500 of that, stride ~150), matching the editor's ~1156.

Re-verified bit-for-bit; the port must reproduce this exactly (the splitter CHOICE drives all
downstream topology). All arithmetic SSE-scalar `f32`, integer counts converted with `cvtdq2ps`:

```
Balance = packed & 0xff              // REPARTITION: 12  (0xc) — NOT 50
PortalBias = (packed>>8) & 0xff      // REPARTITION: 0        — NOT 70 ; PortalBias/100.0 precomputed (divss)
Inc = OPTIMAL?1 : GOOD?NumPolys/10 : NumPolys/4 ;  Inc = max(Inc,1)     // GOOD for REPARTITION — NOT OPTIMAL
if NumPolys==1: return PolyList[0]

for candidate C (index stride Inc):
    skip C if (C.PolyFlags & 0x28) and !(C.PolyFlags & PF_Portal/*0x4000000*/) and !bAllNonStructural
    Splits = Front = Back = 0
    for other O (index stride Inc, O != C):
        switch C.SplitWithPlaneFast(O):
            SP_Front:   Front++
            SP_Back:    Back++
            SP_Split:   Splits += (O.PolyFlags & PF_Portal) ? 16 : 1
            SP_Coplanar: (ignored in score)
    Score2 = (100 - Balance) * (float)Splits
    Score  = (float)abs(Front - Back) * (float)Balance + Score2       // |F-B|*Balance computed first, +Score2 last
    if C.PolyFlags & PF_Portal:  Score -= Score2 * (PortalBias/100.0)
    if Score < bestScore || best==NULL:  best = C; bestScore = Score   // STRICT less-than; ties keep the EARLIER candidate
return best
```

`bAllNonStructural` = every poly has `PF_NotSolid|PF_Semisolid` (0x28). `find_best_split_exact` uses
the exact score op-order. **Both param sets are now APPLIED in `bspcsg.rs` and threaded separately**
(see board item `bspcsg-findbestsplit-param-fix-bspoptgeom-wire`):
- **Repartition** (`bsp_build` → `split_poly_list(..., Opt::Good)`): `BALANCE=12`, `PORTAL_BIAS=0`,
  GOOD stride `Inc = max(NumPolys/10, 1)` on both the candidate and inner loops.
- **Brush temp BSP** (`build_brush_temp_bsp` → `split_poly_list(..., Opt::Lame)`): `TEMP_BALANCE=0`,
  `TEMP_PORTAL_BIAS=0`, LAME stride `Inc = max(NumPolys/4, 1)` (`Opt=LAME, Balance=0, PortalBias=0,
  RebuildSimplePolys=1` — evidence file §4). This is a *separate* call from the repartition; do not
  conflate them. Applying it is **soup-neutral** (verified 2026-07-17, §10.5) — kept because it is
  the value the binary uses, not because it moves any divergence.

---

## 6. `bspRepartition` inputs — the fat-fragment source (VAs `0x36090`/`0x36200`) 🔬

`bspRepartition` (`0x49fc0`, prior decode) = `bspBuildFPolys(Model,1,Opt)` →
`bspMergeCoplanars(Model,0,0)` → `bspBuild(Model,RebuildSimplePolys=0)` (from-scratch `SplitPolyList`)
→ `bspRefresh(Model,1)`. The two newly-decoded inputs:

**`bspBuildFPolys` (`0x36090`):** empties `Model->Polys`, then `MakeEdPolys` walks every node and
reconstructs it into an FPoly via `bspNodeToFPoly` (Base/Normal/Textures from the surf, `Vertex[k] =
Points[Verts[iVertPool+k].pVertex]`, `RemoveColinears`). **Every CSG-fragmentation vertex is retained**
→ the repartition input is "fat". `bMergePolys=1` here means iLinks are kept (not reset).

**`bspMergeCoplanars` (`0x36200`)** — the REAL algorithm (replaces the `passes.rs` "plausible
reassembly"). Group polys, then fuse each group:
```
group predicate (Pj joins Pi):  Pj.iLink == Pi.iLink
                             AND -0.001 < Pi.Normal·(Pj.Base - Pi.Base) < 0.001    // coplanar offset
                             AND Pi.Normal · Pj.Normal > 0.9999                    // same-facing normal
                             AND (MergeDisparateTextures OR (TextureU~Pj within 4e-4 AND TextureV~ within 4e-4))
for each group of size>1:  MergeCoplanarPolys  =  fixpoint { pairwise FPoly::TryToMerge }
then: compact Polys (drop NumVertices==0); if RemapSurfs: remap iLinks
```
Called as `(Model, RemapSurfs=0, MergeDisparateTextures=0)` from `bspRepartition`, so the **default
requires matching TextureU/V** and does NOT remap surfs. `TryToMerge` (`0x34b10`, **Editor.dll** — a
same-module call from `MergeCoplanarPolys`, NOT the game `Engine.dll`; see §10) fuses two coplanar
edge-sharing polys into one, deleting the shared edge and colinear verts — this fusion, followed by
`SplitPolyList` re-splitting the fused faces at every partition plane, is what yields the ~14
FVerts/node. (A separate `MergeNearPoints`-style point dedup at `0x33dc0` collapses near-identical
points and consecutive-duplicate FVerts.)

**Residual (low risk):**
- Coplanar Outside-seeding nuance — now instruction-decoded in §8.3; the one item that may still want a
  differential trace (matters at shared walls, not truly castle-rare).
  *(`FPoly::TryToMerge`'s vertex splice is no longer a residual — instruction-transcribed in §10.)*

*(The earlier "child-first micro-order" and "Subtract is the exact mirror" residuals are now CLOSED —
see §8.1/§8.2.)*

---

## 8. THE CRUX — world-face SPLIT-and-re-add + Subtract mirror + coplanar order (this session) 🔬

Evidence: `../re-raw-zones/bspbrushcsg-filter-decode.md §5.1/§5.2/§7/§7b`. This closes the §6 gaps and
is the mechanism that fixes both the FVert-fatness (`16163` vs the clip-to-one-fragment `4914`) and the
sub-floor solidity.

### 8.1 `FilterWorldThroughBrush` cuts each world face by RE-ADDING its outside pieces, not clipping

For every existing world node **not** freshly added this pass (`!(NodeFlags & NF_IsNew)`), the engine
reconstructs its face `Ed = bspNodeToFPoly(iNode)` (with **`Ed.iLink = Node.iSurf`** — the face keeps
the original surf) and filters it **down the brush's convex temp BSP** via
`bspFilterFPoly(leafFunc, Brush, &Ed)`. The per-CsgOper leaf func is:

| CsgOper | leaf func | RE-ADD on filter | DISCARD on filter |
|---|---|---|---|
| **Add** | `0x31b90` | {0 OUTSIDE, 2 COPLANAR_OUTSIDE} | {1,3,4,5} |
| **Subtract** | `0x34980` | {0 OUTSIDE, 2 COPLANAR_OUTSIDE, **4 COSPATIAL_FACING_IN**} | {1,3,5} |

> **Correction:** the `cmove` at `0x33472` maps **Add→`0x31b90`, Subtract→`0x34980`** (an earlier
> evidence draft had these swapped). The only filter that differs between the two tables is `F=4`.

**RE-ADD** (`0x349c1`/`0x31bd1`): `if (Ed->PolyFlags & 0x80000000) bspAddNode(Model, GLastCoplanar,
NODE_Plane, NF_IsNew, Ed)`. The gate is **bit 31**, which `FPoly::SplitWithPlane` sets on both output
polys **only on a genuine split** (`Engine!0x1518b0` @`0x151ad9`/`0x151b09`; the Front/Back/Coplanar
returns never set it). So **a fragment is re-added iff a brush plane actually cut it off** the original
face. It is placed `NODE_Plane` on the tail of the original node's coplanar chain (`GLastCoplanar`,
`0x101491c0`) and — because `Ed.iLink` is the original surf — **shares that surf** (no new surf), pooling
its own FVerts. One straddling face therefore becomes *N* re-added outside-fragment nodes.

**DISCARD** (`0x349ee`/`0x31bfe`): `GDiscarded(0x101491b8)++` and mark the original node dead
(`NodeCleanup(iNode); Node.NumVertices = 0`).

**Post-filter reconciliation** (`0x3348b`): if **`GDiscarded != 0`** (some fragment was interior → the
face genuinely enters the brush) keep the re-added outside fragments and **delete the original**
(`NodeCleanup(GNode)` + `NumVertices=0`); if **`GDiscarded == 0`** (nothing interior → the face only
grazes the brush) the re-adds are spurious duplicates and are **rolled back**
(`Nodes.Remove(savedNodeNum, added)`, `0x34050`), keeping the original whole. `NodeCleanup` (`0x34020`)
is only a notify hook — the actual array removal is `Nodes.Remove`.

**What the current `bspcsg.rs` does wrong.** `filter_world_through_brush` (lines ~464–563) hull-classifies
each face and, for a straddler, calls `clip_outside_hull` → keeps **only the single largest outside
fragment** via `replace_node_face`. Replace that whole function with: reconstruct the face (iLink =
node's surf), `bsp_filter_fpoly` it through the brush temp BSP with a world-thru-brush leaf func that
re-adds every bit31 outside fragment as a `NODE_Plane` node sharing the surf, tracks a discard counter,
and then either deletes the original (discard>0) or truncates the re-adds (discard==0). Note this needs
the brush's convex temp BSP built first (`bspBuild(TempModel,…)`) — the world face is filtered through
that tree, **not** tested against raw brush half-spaces.

### 8.2 Subtract LOOP-2 leaf `SubtractBrushFromWorldFunc` (`0x348c0`) — NOT a mirror

Adds on **`{F_INSIDE=1, F_COPLANAR_INSIDE=3}` ONLY** — no `F_COSPATIAL_FACING_IN=4`, no semisolid gate —
and **`Reverse()`s the face around `bspAddNode`** (`0x34904`/`0x34926`, `FPoly::Reverse` `0x100cee44`),
so the carved wall's normal faces into the void but the descent sees the original outward normal.
`ABrush::BuildCoords` returns Orientation `+1` for identity scale regardless of Add/Subtract, so LOOP-1
`Transform` does **not** flip an unscaled subtract brush — the single flip is this leaf-func Reverse.

> **Native discrepancy to fix.** `bspcsg.rs` `bsp_brush_csg` reverses the poly in **LOOP 1**
> (`ed.reverse()` for Subtract) and its `leaf_func` also adds on `F_COSPATIAL_FACING_IN`. The engine
> does neither: it keeps the outward normal through the whole world-tree descent and reverses **only**
> inside `SubtractBrushFromWorldFunc` at store time, and never adds on `F_4`. For a single subtract into
> an empty tree the two coincide (empty-tree path adds F_INSIDE, one net flip); for multi-brush subtract
> (the castle) the LOOP-1 reverse changes every `SplitWithPlane` front/back classification during
> descent → divergent fragments. Port the flip into the leaf func and drop the LOOP-1 reverse + the F_4
> case.

### 8.3 Coplanar cascade `FilterEdPoly` (`0x32d91`) — child-first order + IsCsg seeding PINNED 🔬

`FCoplanarInfo` is the 5-field UE1 struct `{+0x18 iOriginalNode, +0x1c iBackNode, +0x20 FrontLeafOutside,
+0x24 BackNodeOutside, +0x28 ProcessingBack}`. On the first coplanar hit: `Dot = Node.Normal ·
EdPoly.Normal`; **`Dot ≥ 0` descends `iFront` first** (the poly faces the node front), **`Dot < 0`
descends `iBack` first** (faces the node back), recording the *other* child as the back subtree.
`FilterLeaf` then runs the back pass and classifies cospatial from `(frontOutside, backOutside)`:
`(in,in)→3`, `(out,in)→5`, `(in,out)→4`, `(out,out)→2`. The child-first order and cospatial table are
native-correct.

**PINNED (was: "one low-confidence Outside-seeding nuance"; resolved 2026-07-17 by full disasm of
`FilterEdPoly 0x32d91` + `FilterLeaf 0x33130`, cross-checked with a live N=2 castle differential).**
The field NAMES mislead — the real roles are:
- **`+0x20 FrontLeafOutside` = the SEED for the *other* (non-facing) side's descent** — NOT a leaf
  result. Set at coplanar time to the CSG-adjusted outside of the non-facing side.
- **`+0x24 BackNodeOutside` = the classify `frontOutside`** — overwritten with the *facing*-pass leaf
  result in the normal case (`FilterLeaf 0x33184`), but pre-seeded to `facing_out` when the facing
  child is `-1`.

**Each side's descent is seeded with the SAME CSG adjustment the ordinary SP_Front/SP_Back branches
use** — front side `outside||IsCsg`, back side `outside&&!IsCsg`:
```
Dot>=0 (faces front): facing=iFront seed=(outside||csg);  other=iBack  seed=(outside&&!csg)   // 0x32e59
Dot<0  (faces back) : facing=iBack  seed=(outside&&!csg); other=iFront seed=(outside||csg)    // 0x32ece
```
The facing side descends first with `facing_out`; its leaf result becomes `frontOutside`. The other
side then descends with its own `other_out` seed (from the ORIGINAL outside, independent of the facing
leaf); its leaf result is `backOutside`. When the facing child is `-1` the facing "leaf outside" is just
`facing_out` and the code jumps straight to the back pass (`0x32f15`, other!=-1) or classifies inline
(`0x32ec3`, both -1).

**The native bug (2 parts, both fixed in `bspcsg.rs`):** (1) it seeded the facing descent with the raw
incoming `outside` (no `||csg`/`&&!csg` adjust), and (2) it seeded the *other*-side descent with the
FACING leaf result instead of the independent `other_out`. The `Coplanar` struct now carries `back_seed`
(=`+0x20`) and `front_outside` (=`+0x24`) as two distinct fields, mirroring the engine.

**Live-verified (N=2 castle subset, `subset_diff.py diff 2`):** WallBack's floor face `(0,0,-1,0)` is
coplanar with the subtracted room-floor world node (normal `(0,0,1)`, IsCsg). `Dot=-1<0`, facing side =
node back = `iBack=-1`, so `facing_out = outside&&!csg = true&&false = FALSE` → `frontOutside=in`; other
= `iFront` descends `outside||csg = true` → `backOutside=out` ⇒ `(in,out)→F_COSPATIAL_FACING_IN(4)`,
which `AddBrushToWorldFunc` DROPS. Pre-fix the native seeded `frontOutside=out` → `(out,out)→
F_COPLANAR_OUTSIDE(2)`, which Add KEEPS → the surplus node. Result: N=2 native 15→14 nodes, matching the
editor; full-castle shared-plane multiset 867→971, native node count 1028→1158 (editor 1156), solidity
98.96%→98.99% (no regression). This same fix is mirrored into the `wtb_filter_*` world-through-brush
descent (same engine `FilterEdPoly`, different leaf func).

### 8.4 Does §8 fully explain the FVert-fatness + solidity residual?

**Yes, for the dominant term.** The clip-to-largest-fragment approach (a) under-counts FVerts (one
fragment where the engine emits several) and (b) leaves false-solid/false-empty cells because the interior
is only *shrunk*, not deleted, and straddlers aren't fully repartitioned. §8.1 replaces that with the
engine's delete-interior / re-add-every-outside-cut-fragment behaviour, which reproduces both the
~14-FVert/node pool and the watertight solidity. The two caveats that could leave a *small* residual after
the §8.1 fix are the Subtract LOOP-1-reverse discrepancy (§8.2 — a correctness bug affecting the
subtract-heavy castle, must also be fixed) and the coplanar Outside-seed nuance (§8.3, shared walls). Both
are precisely specified above; the next increment can implement §8.1+§8.2 from these docs alone and
differential-check §8.3 only if needed.

**Implementation status (2026-07-17).** §8.1 (split-and-re-add) and §8.2 (Subtract no-LOOP1-reverse +
reverse-at-store, adds only on {F_INSIDE,F_COPLANAR_INSIDE}) are IMPLEMENTED in `bspcsg.rs`
(`filter_world_through_brush`/`wtb_*`/`build_brush_temp_bsp`; `leaf_func`). Verified on the castle: the
CSG soup fattens as predicted — **pre-repartition verts 4914 → 46058** (mechanism fires: 1704 genuine
cuts, 7696 correct grazing rollbacks) — and points came to near-parity (2509 → 1901; editor 2035) once
the repartition was made to rebuild the Points/Vectors pools. BUT the split-and-re-add did NOT by
itself lift the point-in-solid solidity above the floor: it went 99.35% → **98.43%** (step-64 on-grid),
with EVERY disagreement within 8u of a brush boundary and the residual traced to the **MERGE/REPARTITION
stage** — the editor's own golden model scores 99.97%/100% on the same harness, so the finer soup that
§8.1 produces is real but `bspMergeCoplanars`/`TryToMerge` (§7c, not instruction-exact) + `bspBuild`
re-partition don't yet re-tile it watertight, and `bspOptGeom` (out of scope) still gates the vert count
to 16163. **§8.3 was tried and reverted:** implementing the §7b `FCoplanarInfo` field-split + IsCsg
Outside-seed produced NO solidity improvement (98.43 → 98.36), and the §7b coplanar-goto branch (which
`Outside` the back-subtree descent uses) is genuinely ambiguous from the static disasm — it needs a LIVE
differential trace to pin. Do not re-apply §8.3 blind; trace first.

### 8.5 The real leak: STALE AUTHORED NORMALS, not merge/repartition (PINNED 2026-07-17) 🔬 ✅

The "MERGE/REPARTITION" diagnosis of the prior increment was **wrong**. A live differential trace
(harness `bspcsg_diff.py` + descent-tracing our tree vs the golden `Test_Castle.dx` region-by-region)
pinned the dominant leak to the **incremental filter's face normals**, and the leak was present
**pre-repartition** (repartition actually *improved* solidity, 97.5% → 98.6%; it did not cause it).

**Mechanism.** Some Deus Ex T3D brush faces carry a **stale / axis-projected `Normal`** that is NOT
perpendicular to the face the vertices describe. The castle's octagonal **bastion-roof** brushes
(`BRoof*`) are the worst case: a sloped roof panel's vertices span `z ∈ [250,360]` (winding normal
`(0.541,0.541,0.643)`) but its stored `Normal` is the **horizontal** `(0.707,0.707,0)` — the roof's
pre-slope *axis* direction, `normalize(0.541,0.541,0)`. UnrealEd's `FPoly::Finalize` **always
recomputes the normal from the winding**, so the editor builds the true slanted plane. The native
`FPoly::finalize` (`fpoly.rs`) recomputes **only when the stored normal is ≈ zero**, so `bspcsg` kept
the vertical normal, `bspAddNode` stored a **vertical node plane for a slanted face**, and the
incremental descent bounded each roof as a **vertical prism** instead of a pyramid. A grid point just
outside the pyramid but inside that prism (within the roof's max radius, above the shared bastion/roof
cap at `z=250`) was routed into a **solid** leaf → the near-wall false-solids. `bspNodeToFPoly`
reconstructs faces from the (correct) verts + the (wrong) surf normal, so the corruption also poisons
the repartition input — which is why the symptom *looked* like a repartition failure.

**Fix (`bspcsg.rs` `bsp_brush_csg` LOOP 1, after `finalize`):** re-derive each transformed face's
normal from its winding (`calc_normal`) and replace the authored normal **only when it disagrees**
(`dot < 0.9999`), so consistent faces keep their byte-identical authored normal. This mirrors the
default path (`build.rs §7.1`, which does the same before its single partition and is why the default
path never had this leak).

**Result (castle, `bspcsg_diff.py`):** step-64 solidity **98.43% → 99.58%**; step-32 **98.59% →
99.69%** (editor golden 99.97% on the same grid). False-solids **5825 → 472**, and the **genuinely
interior** leaks (>4u from any wall) went **77 → 1** — the tree is now watertight; every remaining
disagreement is boundary-epsilon within ~4u of a wall (the editor is void-biased there, 0 false-solid /
202 false-empty; ours is 472 / 1304). Section counts moved toward the golden: surfs 437→454 (ed 485),
points 1901→2146 (ed 2035), nodes 1263→1543 (ed 1156). Merge was ruled out directly (disabling
`bspMergeCoplanars` changed solidity by <0.05%). The residual boundary-epsilon gap and full vert parity
(6099 vs 16163) wait on `bspOptGeom` + exact-merge/FP — the next task. **§8.3 remains untouched** (still
needs a live coplanar trace; do not re-apply blind).

### 8.6 The FIRST soup divergence is OVER-production over a DEAD node, NOT under-fragmentation (PINNED 2026-07-17) 🔬 ✅

**This overturns the standing "§8.1 world-face split-and-re-add UNDER-fragments" hypothesis.** A
proper **pre-repartition SOUP differential** (new harness `soup_cmp.py` + the `UEDCLI_BSPCSG_SOUP_ONLY`
hook in `bspcsg.rs`) compared native's **post-merge soup** against the editor golden's `Model.Polys`
— which is *exactly* the editor's post-merge, pre-`SplitPolyList` soup (measured: full castle 853
`Model.Polys` vs 1156 final nodes; the SplitPolyList INPUT, not the final faces). The finding:

- **N=1,2 soup MATCHES exactly. The FIRST divergence is N=4** (World Subtract + WallBack/WallLeft/
  WallRight Add). Native has **2 SURPLUS faces** (`onlyN=2, onlyE=0`) — the editor soup is a strict
  SUBSET of native's. Native **OVER-produces**; it does *not* under-fragment. The 2 surplus faces are
  the **bottom faces of the WallLeft/WallRight Add brushes** (`(0,0,-1)` at z=0), which the editor
  never keeps.

- **Traced mechanism.** A wall's bottom face sits coplanar on the world floor (which the earlier
  World Subtract carved). WallBack's `FilterWorldThroughBrush` then **deletes the floor node**
  (`NumVertices=0`, §8.1) where the wall footprint consumed it, leaving it as a plane-only splitter.
  When WallLeft's bottom face (LOOP 2) filters down and lands coplanar with that **dead floor node**,
  `IsCsg` returns **false** (raw engine `IsCsg` gates on `NumVertices>0`, `0x33b80`), so the
  below-floor region mis-propagates as VOID and the coplanar classifier yields `F_COPLANAR_OUTSIDE(2)`
  (both-sides-void) instead of `F_COSPATIAL_FACING_IN(4)` (facing into solid). `AddBrushToWorldFunc`
  KEEPS filter 2 but DROPS 4 → native adds a buried face the editor drops. WallBack's own bottom
  (filtered against the *pre-deletion* live floor, `nv=4`, csg=true) is correctly classified 4 and
  dropped — the divergence appears only once a prior brush has deleted the coplanar anchor.

- **Fix (`bspcsg.rs is_csg_filter`): drop the `NumVertices>0` clause** — `IsCsg = !(node_flags &
  0x21)`. A face deleted by FWTB is gone, but the **solid it bounded persists** (below the cut floor
  is still solid), so the plane must keep flipping `Outside` for later coplanar filtering. In this
  pipeline every `nv==0` node is an FWTB-deleted formerly-solid divider (NotCsg is still masked by
  0x21; a freshly-added node always has verts), so this re-CSGs *only* those, never a live or
  genuinely-non-CSG node. The engine reaches the same fragment set via its node ordering / tree
  structure; this is the order-independent equivalent (the literal `nv>0` `IsCsg` is preserved in the
  disasm — see §8.6 note below).

- **Result (measured).** Soup **N=4..8 now EXACT (`onlyN=onlyE=0`)**; full-castle soup divergence
  **132/109 → 24/17**. Full-castle **solidity 98.99% → 99.97%** (== the editor golden's own score on
  the same grid) and **surf count 474 → 485 (== editor exactly)**. Node count 1158 → 1060 (editor
  1156); points 1699 → 1618 (editor 2035, awaiting `bspOptGeom`). `cargo test` + `bin/test` green.

- **Open (next divergence — LOCALIZED to N=33, `soup_cmp --subsets` with fresh goldens).** The
  `node_diff` ordered prefix is **still 0**: the repartition ROOT is native `(-1,0,0,-128)` vs editor
  `(-1,0,0,48)`, and it cannot match until the WHOLE soup matches (full-castle soup still **24/17**).
  The soup is now **EXACT through N=32** (rebuilt goldens: N=1..12,20,30,31,32 all `0/0`; golden3 was
  corrupt and was rebuilt). **The first remaining divergence is N=33 = `TowerNW_2eoc3d`** (the second
  octagonal tower): `onlyN=2, onlyE=1` on plane `(0,0,-1,-248)` — the **NE roof underside** (x∈103..112,
  y∈128..180). Native leaves it as **2 fragments** where the editor holds **1** (editor verts
  `{(103,136),(103,171),(111,128),(112,128),(112,180)}`; native splits it at y=160). Adding the NW tower
  does not touch NE geometry — so this is an **under-MERGE**, not a CSG-fragmentation bug: native's
  `bspMergeCoplanars`/`FPoly::TryToMerge` (§7c, the one routine NOT transcribed to instructions) fails to
  fuse two coplanar same-surf fragments the editor fuses, and the recompute at N=33 tips the grouping.
  This is the next `soup_cmp` target — trace `try_to_merge`/`merge_group` on this NE-roof group. The
  other full-castle `onlyE` planes (`(0,0,-1,-280)`, sloped octagonal-bastion `(0,±1,0,-295.7)`, BRoof at
  79/81/83/85, §8.5) are the same tower/bastion/roof family, likely the same merge mechanism.

> **Note — why the fix deviates from the literal `IsCsg` yet is faithful.** `FBspNode::IsCsg`
> (`0x33b80`) genuinely gates on `NumVertices>0` (`cmp byte[ecx+0x36],0; jbe→0`), and `NodeCleanup`
> (`0x34020`) is only a notify hook (no relink), so the engine keeps the dead node in the tree with
> `nv=0`. The engine nonetheless gets the editor result because its node **ordering** routes a later
> coplanar face to a *live* floor fragment rather than the dead original (native's tree order already
> diverges at N=2 — same faces, different order). Matching that order exactly is the byte-identity
> tree-order problem (unsolved); dropping the `nv>0` clause is the **order-independent** shortcut that
> reproduces the exact editor *fragment set* now, without adding any face the editor lacks (it only
> DROPS the buried surplus). Validated by the exact N=4..8 soup match + 99.97% solidity + 485 surfs.

---

## 9. Port order (unchanged from spec §2.1, now fully grounded)

```
EmptyModel
for STRUCTURAL brush in trunk order:  bspBrushCSG(Model, brush, flags, brush.CsgOper)   // §2-4
bspRepartition:  bspBuildFPolys -> bspMergeCoplanars -> bspBuild(SplitPolyList/FindBestSplit) -> bspRefresh   // §5-6
TestVisibility (zones.rs, already ported)
for SEMISOLID/NONSOLID brush in trunk order:  bspBrushCSG(...)   // NOT repartitioned (2nd incremental layer)
bspOptGeom  (separate port; 42-bspoptgeom-decode.md)
bspBuildBounds  (bounds-and-zonelayout.md)
```
Delete the synthetic `bound_leaked_solid_leaves` scaffold once the structural loop lands (its role is
subsumed by real bounded fragments — §0). The semisolid second pass runs `bspBrushCSG` again on
detail brushes *after* the repartition and is never re-merged — this is the source of the remaining
node-count delta beyond the repartitioned structural tree.

---

## 10. `FPoly::TryToMerge` + `MergeCoplanarPolys` — instruction-level decode (§7c closed) 🔬

*(Traced 2026-07-17 from `Editor.dll`. **Location correction:** `TryToMerge` is **`Editor.dll`
RVA `0x34b10`**, not `Engine.dll` — `MergeCoplanarPolys` (`0x33cb0`) reaches it by a plain
same-module `call 0x10034b10`. The earlier "`0x34b10` (Engine)" note disassembled the game
`Engine.dll` at that RVA and hit unrelated bytes. `RemoveColinears`, the FPoly copy-ctor and
`operator=` ARE cross-module imports from `Engine.dll` (IAT `0x100cee2c / 0x100cee94 / 0x100cee28`).)*

### 10.1 `FPointsAreSame` (`0x32b90`) — a **box** test, not Euclidean
For each axis independently: return 0 unless `-0.002 < (P-Q).axis < 0.002` (strict), for X **and**
Y **and** Z. So it is a Chebyshev/box test at `THRESH_POINTS_ARE_SAME = 0.002`, **not** a
`.Size() < 0.002` sphere. A pair `0.002 < d < 0.0034` apart along a diagonal is "same" by the box
test but "different" by Euclidean distance. The native port previously used `.size() < 0.002`
(Euclidean) — corrected to the box test in `bspcsg.rs::points_are_same`.

### 10.2 `MergeCoplanarPolys` (`0x33cb0`) — the fixpoint over one group
Signature `MergeCoplanarPolys(Model, INT* PolyIndexList, INT Count)`; `FPoly` stride `0x1d8` (472),
`NumVertices` at `+0x1c0`, `Vertex[k]` at `+0x30 + k*12`.
```
Try = 1
while Try:
    Try = 0
    for i in 0..Count:
        Pi = &Polys[List[i]];  if Pi.NumVertices <= 0: continue
        for j in i+1..Count:                       # UPPER TRIANGLE ONLY (j>i)
            Pj = &Polys[List[j]];  if Pj.NumVertices <= 0: continue
            if TryToMerge(Pi, Pj):  Try = 1        # NO break — Pi keeps growing
```
Key points the native port now matches (`bspcsg.rs::merge_group`): **only `j>i` is scanned** (the
old port tried all ordered pairs `a!=b`); after `Pi` absorbs `Pj` (`Pj.NumVertices=0`) the SAME,
now-larger `Pi` continues against `j+1, j+2, …`; any successful pass re-runs the whole outer loop.

### 10.3 `FPoly::TryToMerge` (`0x34b10`) — `TryToMerge(Poly1 /*ebp+8, "this"*/, Poly2 /*ebp+0xc*/)`
Merges `Poly2` INTO `Poly1`; on success `Poly2.NumVertices = 0` and it returns 1.
```
NV1 = Poly1.NumVertices;  NV2 = Poly2.NumVertices
if NV1 + NV2 > 16:  return 0                       # FPoly::VERTEX_THRESHOLD == 16  (0x10034b6e)

# Find ONE overlapping point — FIRST hit in (i over Poly1, j over Poly2) row order:
Start1 = Start2 = -1
for i in 0..NV1:  for j in 0..NV2:
    if FPointsAreSame(Poly1.V[i], Poly2.V[j]):  Start1=i; Start2=j; goto found
return 0                                            # no shared point
found:
End1 = Start1;  End2 = Start2
# FORWARD neighbour test:
T1 = (Start1+1) % NV1;  T2 = (Start2-1) mod NV2
if FPointsAreSame(Poly1.V[T1], Poly2.V[T2]):
    End1 = T1;  Start2 = T2                         # shared edge is fwd on P1 / bwd on P2
else:
    # BACKWARD neighbour test:
    T1 = (Start1-1) mod NV1;  T2 = (Start2+1) % NV2
    if FPointsAreSame(Poly1.V[T1], Poly2.V[T2]):
        Start1 = T1;  End2 = T2
    else:  return 0                                 # only one point overlaps -> not an edge

# BUILD merged ring into NewPoly = *Poly1 (copy-ctor), NumVertices=0:
v = End1;  for _ in 0..NV1:      NewPoly.push(Poly1.V[v]);  v=(v+1)%NV1     # ALL of Poly1, rotated to End1
v = End2;  for _ in 0..NV2-2:    v=(v+1)%NV2;  NewPoly.push(Poly2.V[v])    # Poly2 minus its 2 shared verts, pre-incr

if NewPoly.RemoveColinears() == 0:  return 0        # collapsed < 3 verts (Engine.dll import)
if NewPoly.NumVertices > 16:        return 0        # post-thin cap (0x10034df0)
*Poly1 = NewPoly;  Poly2.NumVertices = 0;  return 1
```
The splice keeps **all** of `Poly1` (rotated so `End1` is first) and appends `Poly2`'s vertices
**except its two shared ones** (walk starts one past `End2`, `NV2-2` verts). Both shared corners
survive as duplicates at the seam and are dropped by `RemoveColinears`. Order-independent face-set
identity is therefore unchanged by splice order, but the exact ring matters once `SplitPolyList`
re-splits it, so the port reproduces this order. See `bspcsg.rs::try_to_merge`.

### 10.4 Result — fidelity up, and why §7c is NOT the N=33 divergence
Porting 10.1–10.3 faithfully (box test, `>16` gate, upper-triangle accumulation, exact splice) is
byte-neutral on the **exact** prefix (soup stays identical through N=32) and moves the **full**
castle strictly toward the editor: full-soup `only-native 24→21, only-editor 17→15`; nodes
`1060→1171` (editor 1156), points `1618→1745`, num_shared_sides `1069→1214` — all closer; surfs
stay `485` (== editor) and solidity stays `99.98%`.

**But the pinned N=33 (`RoofNE`, plane `(0,0,-1,-248)`) under-merge is NOT a merge bug.** Traced
2026-07-17: native leaves two roof-underside fragments — `iSurf 196` with the TowerNE octagon corner
`x=111.958` and `iSurf 199` with a spurious `x=112.0` — whose shared `y=160` edge endpoints differ
by `0.042 (> 0.002 box)`, so **no correct `TryToMerge` can fuse them**. The editor has a single
5-vert face there using `111.958` throughout and **no `112.0` anywhere on the plane**. TowerNE's
west face plane is `x=111.958` (verts `(111.958,140.1)`–`(111.958,179.9)`); its diagonal face runs
`(111.958,140.1)→(140.1,111.958)` i.e. `x+y≈252.06`, and native's stray `(112.0,140.059)` lies on
that **diagonal**. So native clips the `RoofNE` bottom fragment against the tower's **diagonal**
face where the editor clips against the **west** face — an upstream **CSG split/classification**
divergence in `FilterWorldThroughBrush`/`bspFilterFPoly`/`SplitWithPlane`, not in coplanar merge.
The whole remaining `only-editor` family (`-280`, sloped bastion `-295.7`, `BRoof` planes) is the
same tower/roof clip-selection shape. **Next divergence to chase = that split selection, decoded to
instruction level before any change** (do NOT force the merge — it would over-fuse non-adjacent
fragments and regress). Tracked in `board/inbox/`.

### 10.5 N=33 clip-selection PINNED to instruction level — it is a LOOP-2 world-tree ORDERING divergence, NOT the temp brush (2026-07-17) 🔬 ✅

**Hypothesis tested and DISPROVEN.** §5 (lines 247–248) records that the brush **temp** BSP (the
convex tree `FilterWorldThroughBrush` filters each world face through) is built with `Opt=LAME,
Balance=0, PortalBias=0` (evidence `re-raw-zones/findbestsplit-params-decode.md` §4), whereas
`bspcsg.rs` had left it on `OPTIMAL/50/70`. The standing hypothesis was that this wrong temp-brush
splitter choice picked the wrong first-clipping brush face and produced the stray `x=112.0`. **It
does not.** Switching the temp brush to the byte-verified `LAME/0/0` (`Opt::Lame`, `TEMP_BALANCE=0`,
`TEMP_PORTAL_BIAS=0` in `bspcsg.rs`, threaded separately from the repartition's `12/0/GOOD`) is
**exactly soup-neutral**: N=30–33 unchanged, and the full-castle soup stays `onlyN=21, onlyE=15`,
nodes `1171`, surfs `485` — byte-identical to the `OPTIMAL/50/70` build (verified by flipping the
config and re-running `soup_cmp.py`). The "convex temp brush classifies inside/outside invariantly to
splitter choice" assumption is therefore **empirically true**; the change is kept only because
`LAME/0/0` is the value the binary actually uses, not because it moves the divergence.

**Where the stray `x=112.0` is actually born (traced this session, `bspcsg.rs` instrumented then
reverted).** For brush N=33 = `RoofNE_0oh4ff`, the roof-underside poly (plane `(0,0,-1,-248)`) is
cut in **LOOP-2 — `bsp_filter_fpoly` filtering the BRUSH poly DOWN the growing WORLD tree** (the
`bspFilterFPoly`/`FilterEdPoly` descent), **before** `FilterWorldThroughBrush` runs. It is the
world-tree descent, not the temp brush, that selects the clip. Phase-tagged node-add trace: the
`x=112.0` vertical edge appears with `TRACE_PHASE==1` (LOOP-2), never phase 2 (FWTB).

The roof poly hits THREE near-coincident vertical `x`-planes as world nodes during that descent:

| world node | `iSurf` | plane base `x` | normal | source |
|---|---|---|---|---|
| 254 | 146 | **111.9583** | `(-1,0,0)` | `TowerNE` octagon west face (the editor's choice) |
| 80  | 48  | **112.0000** | `(+1,0,0)` | a **grid-aligned box/wall** face (`i_brush_poly 0`) |
| 112 | 69  | **112.0000** | `(-1,0,0)` | same box/wall, opposite face (`i_brush_poly 1`) |

Both `x=112.0` planes are **axis-aligned** (`normal=(±1,0,0)`), i.e. a straight grid-snapped
wall/box face at `x=112` — NOT `TowerNE`'s diagonal `x+y≈252.06` as §10.4 supposed (there is *also*
a genuine diagonal clip on the same fragment, but the spurious vertical `x=112` edge that blocks the
merge comes from this box plane). The box's `x=112` node clips the roof to a `(112,128)–(112,160)`
edge in native's `nv=5` fragment, while the neighbouring fragment is clipped by `TowerNE`'s
`x=111.958` node — so the shared `y=160` corner disagrees by `0.042` and the two faces cannot fuse.
The editor's world tree routes the whole region to `x=111.958`; native's routes part of it to the
box's `x=112` plane.

**Root cause = the incremental world BSP tree ORDER, not any single param.** Native's pre-repartition
world tree has +15 nodes vs the editor (`1171` vs `1156`) and a different node insertion order, so
`FilterEdPoly` reaches the box's `x=112` node before it is bounded away by `TowerNE`'s `x=111.958`
node — the opposite of the editor's descent. This is exactly the "exact node-for-node topology parity
requires the editor's incremental `bspBrushCSG` node ordering" residual flagged in
`bspbuild-splitpolylist-decode.md` (verdict §117–129). Consequently the ordered `node_diff` prefix
stays **0 / 1156** (it is gated on an exact full-castle soup, which this does not yet deliver) and the
whole `only-editor` plane family (`-248`, `-280`, sloped bastion `-295.7`, `BRoof`) is the same
world-tree-order clip-selection shape. **Next: reconcile native's incremental LOOP-2 node insertion
order with the editor's — a structural `bspBrushCSG` ordering task, not a scalar-param fix.** Do NOT
force the merge or the clip. Tracked in `board/inbox/`.

### 10.6 N=33 divergence traced to instruction level — it is a MERGE-BLOCKING clip born on a DEAD merlon-east node; NOT any local rule (2026-07-17) 🔬 ✅

This closes the §10.5 trace to full mechanism, names every actor/node, disasm-proves the negative
results, and pins the one architectural fact that reframes the whole residual. Evidence + throwaway
harness reverted; instrumentation added to `bspcsg.rs` then removed (soup back to baseline 24→**N32
`0/0`, N33 `onlyN=2/onlyE=1`**, full `21/15`). Actors identified with `find_box.py`; descent traced
with a `UEDCLI_BSPCSG_TRACE` gate on the roof-underside poly (`normal≈(0,0,-1)`, `base.z≈248`).

**The three actors (measured, world-space bboxes):**
| brush idx / N | actor | oper | role |
|---|---|---|---|
| 10 / N=11 | **`Merlon_y4jykf`** | Add | battlement tooth `x[80,112] y[128,160] z[160,192]`; **east face `x=112`** (normal `+1,0,0`), north `y=160` |
| 31 / N=32 | **`TowerNE_1f5drh`** | Add | octagon tower `x[111.96,208] y[111.96,208] z[0,248]`; **west face `x=111.958`** (normal `-1,0,0`) |
| 32 / N=33 | **`RoofNE_0oh4ff`** | Add | roof `z[248,336]`; the **underside** poly `(0,0,-1,-248)` is the divergent face |

The `x=112` "grid box" of §10.5 is therefore the **`Merlon_y4jykf` east face** (one of a 4-merlon row
`x=-80,-16,48,112`), NOT a wall — and the whole family of grid-aligned brushes sits `0.042` off the
octagon's `111.958`.

**Full descent of the roof-underside poly (traced):** the octagon poly is first split at `node[8]`
(WallBack north `y=160`) into an **upper band (`y>160`)** and a **lower band (`y∈[128,160]`)**.
- Upper band → `node[254]` (`iSurf 146` = `TowerNE` west, `x=111.958`) → clips at **111.958** ✓ (soup
  `iSurf 196`).
- Lower band → `node[10]` (WallBack **top** `z=160`) FRONT → the merlon east-face **`iFront` staircase**
  `node[57→64→72→80]` (`x=-80,-16,48,112`) → SPLITs at **`node[80]` (`x=112`)** → back fragment bounded
  at **112** (soup `iSurf 199`, split at `y=160`).

**The load-bearing fact — `node[80]` is a DEAD node.** Dumped at N=33: `node[80] iSurf=48
plane=(1,0,0,112) nv=0 iPlane=255`. `TowerNE`'s `FilterWorldThroughBrush` (N=32) deleted the merlon
east face (`x=112` is `0.042` **inside** the octagon `x≥111.958`) → `NumVertices=0`. Native keeps it a
live CSG splitter (the §8.6 `nv>0`-clause drop). Its **live coplanar sibling** `node[255] iSurf=146
plane=(-1,0,0,-111.958) nv=4` (the `TowerNE` west fragment for `y∈[140.1,160] z∈[192,248]`) sits on
`node[80]`'s `iPlane` chain — put there at N=32 LOOP-2, when the tower west face descended, hit the
then-LIVE `node[80]`, and `SplitWithPlane` classified it **COPLANAR** (`|111.958−112|=0.042 <
THRESH_SPLIT_POLY_WITH_PLANE=0.25`, the engine's own non-precise threshold) → added `F_COPLANAR_OUTSIDE`
at `NODE_Plane`. **This is faithful — the engine does exactly this.**

**Why the roof clips at 112, not 111.958.** When the lower band SPLITs at `node[80]` (`x=112`),
`FilterEdPoly` recurses `iFront`/`iBack` only; the `iPlane` chain (`node[255]`, `x=111.958`) is **not**
consulted on `SP_Split` (decode §3, re-verified). So the back fragment keeps the `x=112` split
boundary. Result: two roof soup faces — `A`(`iSurf196`, `y160–179.9`, `x=111.958`) and `B`(`iSurf199`,
`y128–160`, `x=112`). They FAIL `TryToMerge`: their shared `y=160` corner is `111.958` (A) vs `112` (B),
`0.042 > 0.002` box test. **The editor produces BOTH bands at `x=111.958` and MERGES them into one
5-vert face** (golden's single `link=160` face `{(102.72,170.66),(111.958,179.9),(111.958,128),
(110.99,128),(102.72,136.27)}`). So the editor's single face is a **merge of two same-plane bands**, and
native's divergence is a merge-BLOCKING clip on the lower band.

**Three decisive negatives (why NO local rule fixes it):**
1. **No dead-node skip in the engine.** Disassembled `FilterEdPoly` top (`Editor 0x32bf0`): it reads
   each node's plane from its **surf** (`Node.iSurf → Surf.pBase/vNormal`) and `SplitWithPlane`s — there
   is **no `NumVertices==0` (dead) check** before the split (`0x32c56` is the `≥14` vertex-overflow
   guard, not an `nv` gate). So the engine ALSO splits at `node[80]`'s `x=112` plane *if* `node[80]` is
   on its path. The editor clips at `111.958` **only because `node[80]` is NOT on its roof-B descent
   path** — a tree-STRUCTURE difference, not a dead-node rule. (This also refutes any "restore the
   `nv>0` IsCsg clause" fix: `IsCsg` only gates the `Outside` flag, never the split, so the clip is
   unaffected.)
2. **The `0.25` threshold is non-separable.** Probe: forcing the LOOP-2 descent `SplitWithPlane` to
   `very_precise` (`0.01`) DOES yield the editor's merged roof face (N=33 `onlyE 1→0`, confirming the
   coplanar-absorption is the mechanism) — but it symmetrically **un-merges the mirror-image sliver** at
   N=32 (a `0.042`-gap face on the tower SW diagonal `(-0.707,-0.707,0,-178.2)`), introducing a fresh
   `onlyN=1` there. Both cases hinge on the SAME `0.042` grid-snap gap; the editor handles BOTH with the
   SAME `0.25`. So no split/coplanar threshold separates them.
3. **Only the SOUP matters — and its lone divergence is this clip.** `bspRepartition` rebuilds the final
   tree from scratch (`bspBuildFPolys → bspMergeCoplanars → bspBuild/SplitPolyList`), so the incremental
   tree ORDER is irrelevant EXCEPT through the soup face-set it produces. Measured: editor `golden32`
   and `golden33` FINAL trees carry the **same** `x=112` / `x=111.958` node-plane multiset (`2 / 2`) as
   native's final — the only difference anywhere is the one roof soup face, whose clip is
   tree-order-determined. (This is why the soup is exact through N=32 despite the `+15`-node order
   divergence: that order is soup-neutral until N=33 changes a clip.)

**Verdict.** The N=33 divergence (and the whole `only-editor` `-248/-280/-295.7/BRoof` family) is a
genuine **cumulative incremental-tree-ORDER** divergence, rooted in the `0.042` grid-snap gap between
grid-aligned brushes (merlons/walls at integer coords) and the octagonal tower/bastion faces
(`111.958`, `-295.7`, …): native's tree routes the roof's lower band through the **dead** `Merlon`
east node (`x=112`) whose live `TowerNE`-west coplanar sibling (`x=111.958`) is unreachable on
`SP_Split`, so the two same-plane bands can't merge. It is **NOT** fixable by any single add rule,
threshold, dead-node rule, or `IsCsg` change (all three refuted above); a byte-identical soup requires
reproducing the editor's exact incremental `bspBrushCSG` node order so `node[80]` is off the roof-B
path — the standing structural residual. **The editor's incremental tree is not dumpable** (only its
final, soup-rebuilt tree is), so pinning the specific earlier order rule that diverges is blocked on
that; the productive next lever is an editor-tree oracle (e.g. an `MAP REBUILD` build with node-add
logging, if the editor can be made to emit it), not another blind local tweak. Do NOT force the merge
or the clip — forcing regressed twice. Tracked in `board/inbox/`.

### 10.7 The editor-tree ORACLE built + the first incremental divergence PINNED to leaf-add #184 (2026-07-18) 🔬 ✅

§10.6 closed on "the editor's incremental tree is not dumpable … the productive next lever is an
editor-tree oracle." **That oracle now exists and works**, and it moves the pin from §10.6's *symptom*
(the roof-underside routing through the dead merlon node) UPSTREAM to the *origin* add.

**The oracle** (`harness/editor-tree-oracle/`). `Editor.dll`'s single node emitter `bspAddNode`
(RVA `0x34e80`, loaded un-relocated at `0x10034e80` in 32-bit wine) is breakpointed under **gdb**
inside a ptrace-capable debug container (`dx-lum-uned-dbg` = `dx-lum-uned` + gdb; `compose.override.yml`
adds `SYS_PTRACE` + `seccomp:unconfined`). `editor_tree_oracle.py run N` MAP-LOADs the cached
`golden{N}.dx` subset, attaches gdb (a `commands`/`silent`/`continue` breakpoint that printf's each
call's args + FPoly plane), then `MAP REBUILD`s — logging every incremental add to `logs/oracle-N.log`.
The editor's call-SITE (`ret`) separates the phases: `ret=0x100317df` = `AddBrushToWorldFunc` LOOP-2
Add, `ret=0x10034924` = the Subtract leaf, `ret=0x10031bfc` = `FilterWorldThroughBrush` re-add, and
`ret=0x100345f8`/`0x100346bb`/`0x100aa284` = the final `bspRepartition`/`SplitPolyList` rebuild. The
native counterpart is `native_tree_dump.py N` — the same brushes through `build_geometry_bspcsg` with
the env-gated `UEDCLI_BSPCSG_TREE_DUMP` hook (`bspcsg.rs trace_node_add`), phase-tagged
`ADD`/`SUB`/`FWTB`. `compare_trees.py N` aligns the two LOOP-2 streams under a **plane-normalised** key
`(place, ilink, nv, N, d=N·B)` — so a different base POINT on the same plane (e.g. roof `z=248` at
`(160,160)` vs `(217.28,136.27)`) is treated equal (bspAddNode stores the plane, not the base).

**Result — the LOOP-2 leaf-add streams agree exactly through N=32, and N=33 first diverges at
leaf-add #184.** Editor-vs-native LOOP-2 Add counts match to the line (N=32: 171/171 — **identical**
under the plane key; N=33: 221/221), as do the Subtract counts (6/6) — native reproduces the editor's
incremental leaf-add multiset. At N=33 the two streams are identical for adds `0..183`, then differ:

| leaf-add | actor face | editor emits | native emits |
|---|---|---|---|
| … 0–183 | (incl. RoofNE `ilink=154` sloped, `ilink=155` frags 1–3) | identical | identical |
| **#184–185** | RoofNE `ilink=155` sloped `N=(-0.838,0,+0.546)` frags 4–5 | `parent=84 (nv=4)` **then** `parent=267 (nv=3)` | `parent=267 (nv=3)` **then** `parent=84 (nv=4)` — **SWAPPED** |

Both builds carry the SAME node set here (parents `84, 267, 254, 297, 298` all present) — this is **not**
a missing/extra node, it is a **fragment-emission ORDER swap**: the ilink=155 sloped roof face straddles
and its two straddle fragments descend to two different leaves — `node[84]` = the **merlon top** plane
`z=192` (`ilink=52`, added back at the merlon brush ~N=11) and `node[267]` = the **roof** plane `z=248`
(`ilink=151`, RoofNE) — and the editor visits the merlon-top-subtree leaf first while native visits the
roof-subtree leaf first. The swap cascades: the roof-**underside** `ilink=160` adds (§10.6's non-merging
face) then agree for their first 12 fragments and diverge on the last two — editor `parent=309 (nv=5),
parent=310 (nv=3)`; native `parent=309 (nv=3), parent=311 (nv=5)` — i.e. the exact `5/3`-vs-`3/5` roof
split §10.6 pinned from the final soup, here shown to be the DOWNSTREAM consequence of the #184 swap.

**What this localises the fix to.** The divergence is entirely inside the LOOP-2 world-tree descent
`filter_ed_poly` (`bspcsg.rs:427`, the port of `FilterEdPoly`) — specifically its `split_with_plane`
call (`bspcsg.rs:453`) and the front/back piece routing on `SP_Split`. Through 184 identical adds the
front-then-back recursion order is provably correct GLOBALLY, so this is **not** a global recursion-order
bug — it is a *single* near-coincident-plane classification that native resolves to the opposite
side/order than the editor, at exactly the `0.042` grid-snap gap (merlon `x=112` vs octagon
`x=111.958`) §10.6 identified. The fix task is therefore concrete and bounded: make native's
`FPoly::split_with_plane` (vertex-side classification + `THRESH_SPLIT_POLY_WITH_PLANE`/`…_PRECISELY`
handling of a near-zero distance, and which piece becomes `front` vs `back`) reproduce UnrealEd's
`FPoly::SplitWithPlane` bit-exactly for the RoofNE `ilink=155` face against that plane, so the two
straddle fragments emit in the editor's order (`node[84]` before `node[267]`). This is a **targeted**
split-classification parity fix on ONE straddle — distinct from §10.6 negative #2's *global*
`very_precise` flip (which regressed N=32); note the oracle now shows N=32's LOOP-2 stream is already
byte-identical, so the N=32 mirror-sliver that negative #2 feared was an artifact of forcing the
threshold globally, not present in the faithful incremental stream. Still **do NOT force the merge or
the clip** — the parity must come from matching `SplitWithPlane`, verified by re-running
`compare_trees.py 33` to `leaf-add #184: identical`. Harness + the four evidence logs (`oracle-{32,33}`,
`native-{32,33}`) live in `harness/editor-tree-oracle/`. Tracked in `board/inbox/`.

### 10.8 The #184 swap is NOT an `ilink=155` split — it is a SYSTEMIC coplanar-chain-head divergence from BRUSH 0 (2026-07-18) 🔬 ✅

§10.7 hypothesised the #184 swap is a *targeted* `FPoly::SplitWithPlane` classification bug on the
RoofNE `ilink=155` face ("make the two straddle fragments emit in the editor's order"). **Direct
editor-tree evidence REFUTES that hypothesis.** The fix is neither in `split_with_plane` nor anywhere
on the `ilink=155` path; the two builds split that poly *identically*. The real divergence is a
**tree-STRUCTURE** difference — native and the editor build **structurally different incremental world
trees from the very first brush** — that `compare_trees.py` cannot see because it compares only the
leaf-ADD multiset and **deliberately ignores each add's parent/linkage**.

**Three new oracle probes settled this** (all in `harness/editor-tree-oracle/`, run under
`.venv/bin/python`):
- `editor_descent.py N ILINK` — breakpoints `FilterEdPoly`'s **loop head** `0x10032cb6` (every
  `FilterLoop` iteration — `goto SP_Front/SP_Back` included — falls through here; `iNode=[ebp-0x5a4]`,
  `EdPoly=[ebp-0x5ac]`, `Model=[ebp-0x5b4]`), conditional on `EdPoly->iLink==ILINK`, logging the exact
  tree path the poly + its fragments descend. The native counterpart is the env-gated `DESC` trace in
  `filter_ed_poly` (`bspcsg.rs`, `UEDCLI_BSPCSG_DESCENT=<ilink>`).
- `editor_struct.py N` — gdb dumps the editor's **whole** `Model->Nodes` (plane, `iFront`, `iBack`,
  `iPlane`, `iSurf`, `NumVertices`) at the entry to `bspBuildFPolys` (`0x10036090`) — the complete
  incremental tree the instant before `bspRepartition` rebuilds it. Native counterpart: the env-gated
  `STRUCT` dump in `build_geometry_bspcsg` (`UEDCLI_BSPCSG_TREE_STRUCT=1`). `tree_struct_diff.py N`
  diffs the two node tables.
- `oracle_pp.py N` — the `bspAddNode` oracle AUGMENTED with the **parent node's plane**
  (`PP=X,Y,Z,W`); native's `trace_node_add` now also emits `PP`/`pnv`. This confirms the leaf-ADD
  parent-PLANES match through add #183 and first differ exactly at #184 — the tree is identical *as
  far as the leaf attach-points reveal*, and the swap is a same-plane-set order flip.

**What actually diverges at leaf-add #184.** The `ilink=155` roof face straddles a near-coincident
vertical plane at x≈112 (the §10.6 "0.042 grid-snap gap": merlon face x=112 vs octagon TowerNE face
x=111.958). Both builds split it into the SAME two fragments — nv=4 → the x<112 leaf (node `84`, merlon
top z=192) and nv=3 → the x>112 leaf (node `267`, roof z=248). The ONLY difference is the **splitter
node's orientation**, which flips which fragment is `front` and therefore which emits first under the
(correct, front-first — §3 `SP_Split`) recursion:

| | primary splitter at x≈112 | its normal | children (`iFront`,`iBack`) | front-first emits |
|---|---|---|---|---|
| **native** | node `80` (merlon x=112), **FWTB-DEAD** `nv=0` | `(+1,0,0)` | `(258→267, 81→84)` | `267`(nv3) then `84`(nv4) |
| **editor** | node `255` (octagon x=111.958), **ALIVE** `nv=4` | `(−1,0,0)` | `(81→84, 258→267)` | `84`(nv4) then `267`(nv3) |

Same geometric plane, opposite orientation ⇒ `iFront`/`iBack` swapped ⇒ opposite emit order. (Native
even carries the editor's octagon node as `node80.iPlane = 255` on the merlon's coplanar chain — both
faces exist in both trees; only *which one is the descent splitter* differs.)

**Root cause — a coplanar-chain-HEAD / dead-node-relink difference at BRUSH 0.** `tree_struct_diff.py
33` walks both 339-node tables and pins the **first** structural (non-`nv`) divergence at **node 4**
(the room's ceiling `z=−1`, added by the first structural brush): native `node4.iFront = 5`, editor
`node4.iFront = 12`. Nodes `5` and `12` are BOTH `z=0` floor faces on the same surf (5) coplanar chain
`5→11→12→13→14` (linked by `iPlane`); the difference is which one is the **BSP child / chain head** that
descent splits at — and native's pick (node 5) is **FWTB-DEAD** (`nv=0`) while the editor's (node 12) is
**ALIVE** (`nv=4`). The same pattern cascades: native routes `4→5(dead)→6(dead x=160)`, editor routes
`4→12(alive)→40(alive x=160)`. So across the whole build native systematically makes an **earlier,
FWTB-killed** coplanar face the primary splitter where the editor keeps an **alive** one — the general
form of the x≈112 merlon(dead)-vs-octagon(alive) flip. The leaf-ADD multiset stays byte-identical
through N=32 only because a flipped-orientation internal splitter routes the *same* fragments to the
*same* leaves — it just changes their front/back **order**, which first becomes observable when two
fragments of one poly land in two non-empty sibling subtrees (N=33, leaf-add #184).

**Consequences for the fix.** (1) Do NOT touch `FPoly::split_with_plane` for this — it is correct;
the prior `very_precise` global-flip instinct (§10.6 negative #2) was doubly wrong (it regressed the
now-proven-identical N=32 AND it targets the wrong function). (2) The real target is the incremental
tree's **coplanar-chain construction + `FilterWorldThroughBrush` dead-node handling** so native selects
the same primary splitter (same node, same orientation) as the editor when coplanar faces stack — i.e.
`bspAddNode`'s `NODE_Plane` chaining (`bspcsg.rs:202`) and/or how a face that later goes `nv=0` is kept
vs. relinked as the chain head. This needs the editor's `bspAddNode` `NODE_Plane` path + the
`FilterWorldThroughBrush` `NodeCleanup`/relink (`0x34020`/`0x34050`, §5.1) decoded at instruction level
to see the exact head-selection rule; `tree_struct_diff.py` (node-4 divergence) is the tight fixture to
iterate against — it reproduces the root divergence in the FIRST brush, no need to build to N=33.
(3) This is why the final repartitioned tree's node[0] prefix is still 0/1156: the pre-repartition soup
routes through different splitters, so a from-scratch `bspRepartition` sees a different `Polys` order.

**Status:** hypothesis corrected, root cause pinned to node 4, fix NOT yet implemented (it is a
coplanar-chain-head parity problem, materially larger than §10.7's framing — flagged for Andrzej in
`board/inbox/`). Evidence logs `editor-descent-33`, `editor-struct-33`, `oracle-pp-33`,
`native-{32,33}` (now PP-augmented) live beside the harness. The `bspcsg.rs` probes
(`UEDCLI_BSPCSG_DESCENT`, `UEDCLI_BSPCSG_TREE_STRUCT`, and `PP`/`pnv` in `UEDCLI_BSPCSG_TREE_DUMP`) are
env-gated — the default build path is byte-unchanged (N=32 still `compare_trees.py`-identical; full
offline suite green).

### 10.9 The node-4 root cause DECODED + FIXED — `bspCleanup` is a per-brush dead-node splice, `MakeEdPolys` a tree-walk (2026-07-18) 🔬 ✅

§10.8 pinned the root cause to node 4 (a coplanar-chain-head / dead-node relink) but left the
*mechanism* open: "which coplanar face becomes the node's iFront/iBack child vs stays on the iPlane
chain, and how NodeCleanup relinks a dead node's chain." **All three questions are now decoded from
`Editor.dll` at instruction level, ported to `bspcsg.rs`, and verified against the oracle — the
pre-repartition SOUP is now byte-exact against the editor golden (`soup_cmp.py` 0/0, was 24/17).**
Decode harness committed beside the oracle: `dll_disasm.py` (capstone/pefile `Editor.dll`
disassembler), `dll_exports.py`, `dll_vtable.py` (maps the UEditorEngine vtable slots), and
`cleanup_proto.py` (the Python reference of the splice, validated to reproduce the editor struct).

**Finding 1 — `NodeCleanup` (`0x34020`) does NOT relink; the splice is `bspCleanup`, run PER-BRUSH.**
§8.1 correctly noted `NodeCleanup` is a notify-only hook (disasm confirms: it thunks the object-notify
callback `0x344c0` and does no array/link edit). The relink that orphans dead node 5 and makes
`node4.iFront` skip to the ALIVE fragment lives in a *separate* routine, **`bspCleanup`
(`0x36160`)**, whose recursive worker is **`CleanupNodes` (`0x32100`)**. Crucially it is called at the
**TAIL of `bspBrushCSG` after EVERY Add/Subtract brush** (`bspBrushCSG` `0x35de1`: `call [eax+0x204]`,
unconditional on `CsgOper∈{Add,Subtract}`), NOT once before the final repartition. So each brush
filters through a tree the *previous* brush already cleaned. (`bspBrushCSG`'s tail also runs
`bspMergeCoplanars` when `bMergePolys`, and `bspBuildBounds` when `bBuildBounds`; `csgRebuild`'s
per-brush call `0x4a870` passes **`bBuildBounds=0, bMergePolys=1`** — the per-brush merge operates on
`Model->Polys`, which native rebuilds from the nodes at repartition, so it is node-tree-neutral.)

**Finding 2 — the `CleanupNodes` splice rule (`0x32100`, fully transcribed).** Recurse children
(`iFront`, `iBack`, `iPlane`) first, clearing `NodeFlags &= 0x1f` on each; then on the way back up, if
the node is DEAD (`NumVertices == 0`):
- **Case A — has an `iPlane` successor `P`:** promote `P`. `P` inherits the dead node's `iFront`/
  `iBack` children, **SWAPPED iff `P` faces the opposite way** — `d = Node.Normal · P.Normal` via
  `FPlane::operator|` (`Core.dll ??|UFPlane`), threshold `0.0` (`comiss` vs `[0x100dcaec]=0.0`):
  `d ≥ 0` keeps `(P.iFront=Node.iFront, P.iBack=Node.iBack)`, `d < 0` swaps. Then the PARENT's link
  that pointed at the dead node (`iFront`/`iBack`/`iPlane`) is repointed to `P`. Root special-case
  (`iParent == -1`): copy `P`'s whole node into the root slot and mark `P` dead.
- **Case B — no `iPlane` successor:** if it has BOTH children, keep it as a pure splitter; else the
  parent is repointed straight to its single child (or `-1`).
Dead nodes are never removed from the array — indices stay stable (matching the editor); they just
become unreachable garbage. **This orientation-swap is the exact §10.8 flip** (native's dead merlon
`(+1,0,0)` splitter vs the editor's alive octagon `(−1,0,0)`): once the dead `(+1,0,0)` node is
spliced and its opposite-facing `(−1,0,0)` successor promoted, the swap makes the promoted node's
front/back match the editor's — so descent front-first emits fragments in the editor's order.

**Finding 3 — `MakeEdPolys` (`0x33bb0`, via `bspBuildFPolys` `0x36090`) is a TREE-WALK, not an index
scan.** The repartition input FPoly soup is built by a recursive pre-order walk **(emit self, then
recurse `iFront`, `iBack`, `iPlane`)** from the root — so the soup ORDER is tree-structural. Native's
old `bsp_build_fpolys` iterated nodes by array index; it produced the right face SET but the wrong
ORDER. This is why the incremental tree structure matters at all *after* a from-scratch repartition:
the tree structure (post-`bspCleanup`) determines the order in which faces enter `bspMergeCoplanars`
and `SplitPolyList`/`FindBestSplit`.

**The fix (`bspcsg.rs`, committed).** (1) `bsp_cleanup`/`cleanup_nodes` port `CleanupNodes` exactly;
it runs at the tail of `bsp_brush_csg` (per-brush), REPLACING the old flat `NF_IsNew` clear. (2)
`bsp_build_fpolys` now walks the tree (`make_ed_polys`, self/front/back/plane) instead of scanning by
index.

**Results (all oracle-verified).**
- **`tree_struct_diff.py 33`:** the first STRUCTURAL divergence moves off node 4 (now identical) onto
  dead orphaned nodes only; the merlon/octagon splitter region (nodes 72→255→{81,258}, dead 80/267)
  is node-for-node identical to the editor.
- **`soup_cmp.py` FULL:** `onlyN=0 onlyE=0` — the post-merge soup is **byte-exact** vs the editor
  golden `Model.Polys` (853/853; was 24/17 at §8.6, then 10/4 with tree-walk alone).
- **`compare_trees.py 32`:** LOOP-2 add streams still identical (no regression). Full offline suite
  green (`bin/test` 1363 passed; `cargo test` 35 passed).

**The next divergence (localised — repartition, NOT the incremental soup).** `node_diff.py` still
reports matching-prefix **0/1156**; native's final tree is **1251 nodes vs editor 1156** (plane
multiset 1058 shared / 193 only-native / 98 only-editor — native OVER-splits). Since the repartition
INPUT (soup multiset) is now exact, the divergence is entirely in **`bspBuild`/`SplitPolyList`/
`FindBestSplit`**: it consumes the exact soup in an ORDER that still differs from the editor's, so it
picks different partition planes. The residual order gap traces to ~37 incremental fragment-emit-order
swaps (the `119`/`120`-type: two coplanar surf-28 fragments get opposite creation indices; and the
`#184` `compare_trees` swap, which is now a raw-leaf-add-stream artifact that the per-brush cleanup
reconciles in the *final* structure but not in creation order). This is §10.8's distinct "byte-identity
tree-order" residue — the front/back CREATION order during LOOP-2 filtering, upstream of the tree
structure. **Note the `node_diff` ORDERED comparison against the golden `Model.Polys` is not a valid
oracle for the `SplitPolyList` INPUT order:** the golden's `Model.Polys` is the POST-`SplitPolyList`
array (the recursive partition reorders it in place), not the pre-`bspBuild` merged soup. The correct
next probe is an editor oracle that dumps `Model->Polys` at the `bspBuild` entry (right after
`bspMergeCoplanars`, RVA between `0x49fc0`'s merge and build calls) to compare the true
`SplitPolyList` input order — then decide whether the remaining delta is soup ORDER (fix the last
incremental emit-order swaps) or a `FindBestSplit` stride/tie residue. Tracked in `board/inbox/`.

### 10.10 The repartition INPUT ORDER + FindBestSplit stride DECODED + FIXED — node[0] now exact, subset trees plane-identical (2026-07-18) 🔬 ✅

§10.9 left the final tree at `node_diff` prefix **0/1156** with native OVER-splitting (1251 vs 1156)
even though the pre-repartition SOUP was byte-exact as a MULTISET. §10.9 pinned the next probe as an
editor oracle that dumps `Model->Polys` at the `bspBuild` ENTRY (the true `SplitPolyList` input
order, which the saved golden `.dx` does not expose). That oracle is now built, and it cracked TWO
distinct bugs — the tree is now **plane-identical node-for-node on every cached subset** (N≤33) and
the full-castle root `node[0]` is exact.

**The oracle — `editor_polys_oracle.py` (bspBuild-entry `Model->Polys` dump).** Decoded from
`Editor.dll`: `bspRepartition` (`0x49fc0`) issues four vtable calls in order — `bspBuildFPolys`
(`[edx+0x20c]`), `bspMergeCoplanars` (`[edx+0x210]`), **`bspBuild` (`[edx+0x1fc]`, VA `0x1004a041`)**,
`bspRefresh` (`[edx+0x200]`). At the `bspBuild` CALL site the args are already pushed: `[esp]=Model`.
`bspBuild` (`0x35ef0`) reads the poly list as `Model->Polys` (`UModel+0x54`, a `UPolys*`) whose
`Element` TArray is `Data=UPolys+0x28`, `Num=UPolys+0x2c`, `sizeof(FPoly)=0x1d8`; it builds a
temporary pointer array filtering out `NumVertices==0` and hands THAT (in element order) to
`SplitPolyList`. So the SplitPolyList input order == `Element[0..Num)` (nv>0) in array order. The
oracle breakpoints `0x1004a041`, walks `Element`, and dumps each FPoly's normal/base and every vertex
(`FPoly` fields: Base=+0x00, Normal=+0x0c, Vertex[k]=+0x30+12k, NumVertices=+0x1c0, iLink=+0x1c4).
`polys_order_diff.py` diffs it against native's post-merge soup (`UEDCLI_BSPCSG_SOUP_ORDER` env hook),
keying each face by `(normal, w=N·V0, sorted-vertex-set)` — base/first-vertex alone are NOT stable
identities (base is the texture-mapping point; the vertex ring can be rotated).

**Bug 1 — `bspMergeCoplanars` PRESERVES tree-walk order; the old port CLUSTERED it.** With the soup
now a byte-exact multiset, `polys_order_diff` (N=33) pinned the first ORDER break at index 6: native
emitted all 15 coplanar `z=0` floor fragments consecutively (indices 5–19), while the editor kept the
first at index 5 and the other 14 at indices **185–198**. Decoding `bspMergeCoplanars` (`0x36200`)
end-to-end: its grouping/merge phase only MARKS group members and EMPTIES (`NumVertices=0`) the faces
fused away by `TryToMerge`; then a separate **compaction pass (`0x36480`)** walks `Polys[0..Num)` in
ORIGINAL index order and keeps every survivor — it does NOT cluster a group at its head. The prior
native port pushed each whole group consecutively at the head index, producing the right face SET but
the wrong ORDER (a leader-clustering that `MakeEdPolys`'s tree-walk order then fed to `SplitPolyList`
scrambled). **Fix:** `bsp_merge_coplanars` compacts survivors in original tree-walk order. → soup
ORDER now matches the editor 199/199 at N=33 (`polys_order_diff` 100% prefix), soup multiset stays
0/0.

**Bug 2 — `FindBestSplit` GOOD stride is `NumPolys/20`, not `/10`.** Even with 100%-matching soup
order the N=33 tree still diverged at `node[0]`: native picked soup idx 114 (plane `(0,0,1,160)`),
the editor idx 90 (plane `(1,0,0,-48)`) — and idx 90 is NOT a multiple of the assumed stride 19
(`199/10`), so under the old stride native could never pick it. Live-verified with `fbs_stride_oracle.py`
(breakpoint the running editor's root `FindBestSplit` return `0x338ee`, condition `NumPolys>100` to
skip the temp-brush builds): **`NumPolys=199, Opt=1 (GOOD), Balance=12, stride=9`**. Re-reading the
stride idiom (`0x3369e`: `imul 0x66666667; sar edx,3`) = `(NumPolys * 0x66666667) >> 35` =
**`NumPolys/20`** (the `/10` idiom shifts by 34, not 35). `199/20 = 9`, and soup idx 90 = 9×10 IS a
stride-9 candidate — with stride 9 the decoded scorer picks idx 90 exactly (the editor's `Nodes[0]`).
The scoring formula, tie-break (strict-less / keep-earliest), and LAME=`/4` were all re-confirmed
identical (LAME verified by the oracle's temp-brush hit: `Opt=0, stride=1` at `NumPolys=6`). **Fix:**
`Opt::Good` stride → `(n * 0x66666667) >> 35`.

**Results (oracle-verified).**
- **Subsets N≤33:** `node_diff` **plane-identical node-for-node** — N=12 80/80, N=20 135/135, N=33
  255/255 nodes, plane matches at EVERY index (plane-prefix = 100%). (The residual `iFront`/`iBack`
  gap is only the post-`bspRefresh` child-index NUMBERING, not tree shape.)
- **Full castle:** `node[0]` now exact (plane `(-1,0,0,48)`, `iBack=5`, `iPlane=1`, `nv=4` all match;
  only `iFront`/`iSurf`/`iZone`/`node_flags` — all model-local indices/flags — differ). Plane-prefix
  **0 → 51**. Plane multiset **1116 shared / 11 only-native / 40 only-editor** (was 1058/193/98);
  ~11 of each are fp-noise (`-381.065` vs `-381.066`, the octagon-roof slope straddling the 3-dp key
  boundary). Node count **1251 → 1127** (editor 1156). Soup stays 0/0; `bin/test` 1369 passed /
  1 skipped / 2 xfailed, `cargo test` 35 passed; collision unaffected.

**The residual (localised — OUT OF SCOPE of the repartition-order fix).** The ~29 genuinely
editor-only planes are all axis-aligned **outer-boundary walls** (`w = ±500 / ±410`), and the editor's
extra nodes cluster in the **tail (index ≥ 1100)** — 34 outer-wall nodes vs native's 16, first at
1100/1156. These are the **second incremental layer (semisolid/detail brushes) + `TestVisibility`
zone portalization** that `csgRebuild` appends AFTER the from-scratch repartition (§80 steps 3–4),
which native does not yet replicate; those extra tail nodes perturb `bspRefresh`'s numbering and cap
the plane-prefix at 51. Separately, the editor sets `node_flags=8` on 598 nodes (spread across the
whole tree) that native never sets — a node-flag derivation gap, orthogonal to tree shape. Both are
tracked in `board/inbox/`; the repartition-order + `FindBestSplit` splitter-choice half (this
task) is complete. Harness committed: `editor_polys_oracle.py`, `fbs_stride_oracle.py`,
`polys_order_diff.py` beside the oracle; `UEDCLI_BSPCSG_SOUP_ORDER` env hook in `bspcsg.rs` (env-gated,
default path byte-unchanged, mirrors the committed `SOUP_ONLY`/`TREE_STRUCT` hooks).

### 10.11 The structural remainder is NOT a `bspcsg.rs` second-layer gap — it is `zones.rs` Pass D node-fragmentation; and `node_flags=8/0x10` are render-only occlusion bits (2026-07-18) 🔬 ✅

§10.10 handed off with the residual attributed to "the **second incremental layer
(semisolid/detail brushes)** + `TestVisibility` zone portalization that `csgRebuild` appends AFTER
repartition, **which native does not yet replicate**," and pointed the fix at `bspcsg.rs`. **Oracle
investigation refutes both halves of that framing.** No change belongs in `bspcsg.rs`; the entire
genuine remainder is a **`zones.rs`** concern that was *deliberately* left out, plus a *render-only*
flag that is correctly excluded. Nothing was implemented this pass — the finding is the deliverable
(the task's premise did not survive oracle contact; per the spike rule, the exact diff is reported,
not forced).

**Fact 1 — the second incremental layer is ALREADY ported and works; it is not the gap.** The
castle has **exactly 4 detail brushes** — the `Water{N,S,E,W}` sheets (`is_detail = pf & 0x28`;
`CsgOper=Add`, one `PF_NotSolid|PF_Portal|…` poly each). They are **flat single-poly quads at
`z=−12`** (`bz=(−12,−12)`, zero thickness) — the water *surface*, NOT walls. `build_geometry_bspcsg`
Pass 2 (`bspcsg.rs`, "SEMISOLID / NONSOLID detail brushes") already runs `bsp_brush_csg` on them
after repartition, and native's final tree **carries all four water portal nodes** (`(0,0,1,−12)`,
`nf=0x5` = `NF_NotCsg|NF_NotVisBlocking`, matching the editor's four water surfs exactly — the §70
§0.5 result). So the "semisolid second layer" is done; it contributes the portal *surface*, not the
missing nodes.

**Fact 2 — the 29 missing nodes are `TestVisibility` Pass D per-zone fragment-SPLITS of the moat/water
boundary walls (a `zones.rs` gap, deliberately skipped in §70 §9).** Decomposing `node_diff`'s
"1116 shared / 11 only-native / 40 only-editor" with an fp-tolerant key:
- **11 only-native ≡ 11 only-editor are pure rounding-key noise, not a divergence.** They are the
  *same* octagon-roof-slope / bastion planes at a `0.001` `w` difference straddling the 3-dp multiset
  key — native `(…,−381.066)` / `(0.707,0.707,0,−436.486)` vs editor `(…,−381.065)` /
  `(…,−436.487)`. `node_diff`'s ordered pass (tol `1e-3`) already treats them equal; only the
  round-to-3dp multiset key splits them. Real only-native planes = **0**.
- **All 40 genuine only-editor planes decompose as 29 boundary-wall + 11 fp-noise.** The 29 are the
  axis-aligned outer walls `w=±500/±410` (moat/water region), clustered at index ≥1100.
- **Mechanism (oracle-confirmed).** The moat `Subtract` brushes' boundary walls span `z∈[−80,8]`; the
  water portal at `z=−12` puts a **zone boundary** across them (water zone below, outer/dry zone
  above). UnrealEd's Pass D (`AssignAllZones` `0xa7400`, §70 §5) re-filters each node's own polygon
  through the tree; when a face's landings **disagree** on the per-side zone, it **kills the original
  node and keeps one `NF_IsNew` fragment node per zone**. So one authored wall surf fans out to many
  nodes: editor **surf 354 (y=410 wall) → 10 nodes, surf 355 (y=−500) → 10, surf 349/350 → 8** each;
  native's boundary total is **27**, the editor's **56** — the delta is exactly the **29** missing
  nodes. Native's `zones.rs` Pass D (`assign_leaves_and_zones`, the centroid-`PointRegion` sampler,
  §70 §9) assigns **one** `(back,front)` zone pair per node and **never splits** — a *deliberate*
  simplification ("single-zone-per-node is enough for the `ZoneMask` bit `URender` gates on", made +
  live-verified 2026-07-18 to fix in-game black frames). **Reproducing the 29 nodes = porting the
  real Pass D fragment-split into `zones.rs`, which reverses that same-day decision** — out of this
  task's stated `bspcsg.rs`-only scope, and a live-render risk that wants a decision + review gate,
  not a unilateral subagent change. Flagged in `board/inbox/`.

**Fact 3 — `node_flags=8` (and `0x10`) are per-frame RENDERER occlusion bits, never set by the
build; correctly excluded (not a derivation gap).** `0x08 = NF_PolyOccluded`, `0x10 = NF_BoxOccluded`
— the two occlusion bits of `EBspNodeFlags`. DLL scan for a `NodeFlags` (`FBspNode+0x37`, §50) setter
of these bits (`or byte[reg+0x37], imm` and the register form `08 /r`):
- **`render.dll` sets them** in its software-rasterizer occlusion walk — `NF_PolyOccluded` at
  `0x10019c26` (`or byte[eax+0x37], 8`, gated on the current view's span state), `NF_BoxOccluded` at
  `0x100193db`/`0x10019526`.
- **`Editor.dll` sets NEITHER, in either form** — and `Editor.dll` contains the *entire* deterministic
  build (`csgRebuild`/`bspBrushCSG`/`bspRepartition`/`bspRefresh`/`TestVisibility`). So the build never
  derives `0x08`; the value saved in `Test_Castle.dx` (598 nodes, ≈52%, scattered, uncorrelated with
  zone) is whatever the **editor's last viewport render** left — camera-dependent, non-deterministic
  across saves. Native leaving `node_flags ∈ {0, 0x5}` is **byte-correct for a headless build**;
  reproducing `0x08` would require faking a specific camera occlusion pass. **Verdict:
  confirmed-non-deterministic-and-excluded** (this is the evidence §70 §9's note asserted). The rarer
  `0x0d=0x08|0x05` and `0x18=0x08|0x10` are the same occlusion bits ORed onto the real build flags.

**Net multiset (fp-tolerant):** `1127 shared / 0 only-native / 29 only-editor`, the 29 being one
homogeneous family (Pass D boundary-wall zone-splits). Node count **1127** vs **1156** = the same 29.
Plane-prefix caps at 51 because those 29 tail nodes perturb `bspRefresh` numbering. **The next lever
is `zones.rs` Pass D fragment-split (needs an authorize-scope + review-gate decision), NOT anything in
`bspcsg.rs`.** No code changed; `node_diff`/`soup_cmp`/`compare_trees` outputs are unchanged from
§10.10 (soup 0/0, subsets N≤33 plane-identical, `node[0]` exact).

### 10.12 The 29-node Pass D fragment-split is now PORTED — node count + plane multiset byte-exact (2026-07-18) 🔬 ✅

The §10.11 lever was pulled: `zones.rs` Pass D now faithfully ports `AssignAllZones` (`0xa7400`)
including the per-zone node SPLIT (full mechanism + payoff in `sections/70-zones-portalization.md`
§9's 2026-07-18 UPDATE). Each node's polygon is re-filtered through its chain head's back-then-front
subtrees; a face whose landings disagree per side is split into one fragment node per surviving zone,
the original KEPT as the first fragment and the rest appended onto its `i_plane` chain (same plane,
clipped-fragment verts). **`node_diff.py` (full castle):** native node count **1127 → 1156 = editor**;
plane multiset (fp-tolerant) **1156 shared / 0 only-native / 0 only-editor** (node_diff's round-3dp
key still reports 11/11 — the same octagon-roof/bastion planes at `±0.001` `w`, which an fp-tolerant
`2e-3` pairing collapses to 0/0). Boundary walls fan out to match the editor node-for-node (surf
354→10, 355→10, 349/350→8, …). Invariants intact: `soup_cmp` 853/853, `compare_trees 32` incremental
stream identical, `node[0]` plane exact. Bonus — the filter-based Pass D drops the §10.11/§70-§9
`(0,0)×2` solid-solid nodes to `×0` (exact editor match) and the whole iZone distribution now matches
the editor under the zone-number permutation. Offline suite green; the portal corpus case
(`test_case_f_portal_full_compare`) un-xfailed to full parity. **This closes the last STRUCTURAL
byte-parity gap in the node tree; the remaining byte items are the vert pool and the package-wrapper
session-state, both out of `zones.rs` scope.**

### 10.13 The vert/point-pool gap is a `bspOptGeom` DETECTOR bug, NOT a partitioner ring-distribution gap — the pre-weld tree is byte-ISOMORPHIC (2026-07-18) 🔬 ✅

§10.12 handed off "the remaining byte items are the vert pool …", and commit `fbb0c9f8`
("oracle-prove pool gap is `SplitPolyList` ring-distribution, not the detector") framed the vert-pool
gap as a PARTITIONER problem: native produces `~3.8 verts/node` vs the editor's `~9.1`, so `bspBuild`
must be under-splitting. **A new oracle refutes that framing end to end. The partitioner is correct;
the gap is a `bspOptGeom` T-junction-DETECTOR bug.**

**The oracle — `editor_preopt_nodes.py` (Model->Nodes at `bspOptGeom` ENTRY `0x10036870`).** Dumps
every node's plane + iF/iB/iP + `NumVertices` at the exact instant `bspOptGeom` begins — i.e. the
PRE-weld tree, post-`bspRefresh`/post-Pass-D, engine child convention. Diffed against native's
`UEDCLI_BSPCSG_PREOPT_NODES` dump (added to `bspcsg.rs`, env-gated, default path byte-unchanged).

**Finding 1 — the "9.1 vs 3.8 verts/node" comparison mixed a DEAD-ORPHAN array size with a live
count.** The editor's pre-opt `Verts.Num = 10518` (the "9.1/node" figure) is NOT the live tree — only
`Σ node.NumVertices = 4521` verts are referenced; the other ~6000 are **abandoned CSG-phase FVert
rings** the engine never compacts (`bspRefresh` GCs Surfs but leaves Verts/Points fat; §7.3). Native
clears+re-packs the pool at repartition → `4521` live, same count. **Per-node `NumVertices` histogram
is BYTE-IDENTICAL** (native ≡ editor: `{3:171, 4:923, 5:57, 6:4, 7:1}`), and a link-following
isomorphism walk of the two FINAL trees finds **0 plane/link divergences across all 1156 nodes** —
native's BSP is node-for-node isomorphic to the editor's. `node_diff.py`'s index-by-index "984
divergent nodes / prefix 51" is an ARTIFACT: a small early array-layout shift (native's back-subtree
of node 0 is 12 nodes larger) reindexes the tail, so an isomorphic tree reads as "diverged" by index.
The partitioner needs **no** change.

**Finding 2 — the real gap: `bspOptGeom::eliminate_tjunctions` welds only NEAR-VERTEX T-cracks; the
editor welds edge-INTERIOR T-junctions.** With the pre-weld tree identical, the only difference is the
weld: editor `bspOptGeom` grows the pool to `verts 16163 / points 2035 / nss 2739` (live `Σnv=5496`),
native's grows to `verts 4630 / points 1797 / nss 1161` (live `Σnv=4543`) — native welds ~950 fewer
vertices. `bspoptgeom.rs::tjunction_edge`'s committed decode skips any point projecting more than
`0.25 uu` from an edge ENDPOINT (`proj <= -THRESH → skip`), i.e. a *near-vertex* weld. But the editor
welds points in the edge INTERIOR. Concrete (index-aligned node 1, plane `(-1,0,0,48)`): native ring
is the quad `(-48,-380,0)(-48,-530,0)(-48,-530,12)(-48,-380,12)` `nv=4`; the golden ring has two EXTRA
verts `(-48,-410,0)`,`(-48,-500,0)` `nv=6`. Both lie EXACTLY on native's z=0 edge at `proj = -120/-90`
(deep interior) and BOTH already exist in native's point pool (owned by nodes 4/44/52) — so it is not
a missing-corner problem, the detector rejects them. Editor pre-opt node 1 is also `nv=4`
(`editor-preopt-nodes.log`), so the editor introduces them via `bspOptGeom`, not `SplitPolyList`.

**Proof (prototype, `harness/editor-tree-oracle/tjunction_interior_prototype.md`).** Replacing the
`proj`/capsule scan with a clean point-on-segment-INTERIOR test (weld where `0<t<1` and perpendicular
`< THRESH`) — nothing else changed — collapses the isomorphic per-node `NumVertices` mismatch from
**555 → 25** nodes, lifts live `Σnv` 4543 → **5533** (editor 5496) and `NumSharedSides` 1161 → **2728**
(editor **2739**, within 11). `NumSharedSides` is a purely combinatorial shared-edge count, so landing
within 11 of the golden is strong evidence the welds are largely correct. The prototype is an
approximation (25 residual, over-welds +37, does not close the point-pool sub-gap); byte-exactness
needs a faithful re-decode of `AddPointLink`'s inner scan (`Editor.dll 0x326fc`–`0x32977`) — the
committed `proj vs ±0.25` band is the mis-read.

**Verdict + scope.** The last geometry-body byte gap is `bspoptgeom.rs::tjunction_edge` (an
edge-interior weld it currently rejects), plus a secondary `bspcsg.rs` point-pool sub-gap (native's
repartition pool is 1797 pts; the editor keeps ~2091 — native's incremental CSG over-produces
transient points, 6627 uncleared, and the clear+rebuild over-merges the ~294 T-corner deltas). This
**reverses `fbb0c9f8`'s conclusion** ("not the detector"): it IS the detector. Committed this pass:
the `editor_preopt_nodes.py` oracle, the `UEDCLI_BSPCSG_PREOPT_NODES` hook in `bspcsg.rs`, the
prototype/evidence doc. NO change to `bspcsg.rs` logic or `bspoptgeom.rs` (the detector fix is a
byte-exact re-decode that wants its own scoped task + review gate). Flagged for re-scope.

### 10.14 The point-pool residual DECODED to two over-production sources; FWTB flat-loop leak FIXED, a second straddle-graze source REMAINS (2026-07-18) 🔬 ✅ / ⚠️

This section closes the *decode* half of the point-pool item (the last body sub-gap after the
detector was fixed in `a5c072d3`) and lands the first of its two fixes. **The detector is now correct
and frozen (do not touch `bspoptgeom.rs`).** With it correct, native measures **verts 10418 vs editor
16163, points 1797 vs 2035, NumSharedSides 2728 vs 2739**, and a **+37 over-weld** (native inserts
1012 T-junction welds, the editor 975). All of that residual is one thing: the `Points` pool that
feeds `bspOptGeom` differs from the editor's.

**The +37 over-weld is pool-driven — proven by coordinate.** `weld_pool_diff.py`'s `only-native` weld
set is `{z=-12: 36, z=250: 13, z=160: 1, z=0: 3}`; the editor's `only-editor` set is `{z=250: 13,
z=160: 1, z=0: 2}`. The z=250/160/0 rows appear in BOTH lists — same welds, ±0.02uu FP aliases that
miss the permutation-invariant key. **The real over-weld is the 36 welds at `z=-12`, which have NO
editor counterpart.** They are driven by the 247 *spurious* `z=-12` coordinates the pool diff reports
(`native-missing=485 spurious=247`): the detector welds only RING vertices, but `bspoptgeom.rs`'s
`merge_near_points` (the editor's `ShrinkModel` `0x33dc0`, radius 0.25) remaps **139** ring-vertex refs
to lower pool indices — vs the editor's **56** (2091→2035) — and native's extra remaps snap ring edges
onto the spurious `z=-12` orphans, creating false T-junction alignments. So the pool's CONTENT and
ORDER, via `merge_near_points`, changes the welds. Confirmed the pool is the sole lever.

**The editor's point-pool lifecycle — DECODED (answers step-1 of the task).** The editor **add-and-keeps**:
- **Rollback on a graze does NOT truncate the pool.** `FilterWorldThroughBrush`'s `GDiscarded==0`
  rollback is `Nodes.Remove(GSavedNodeNum, N)` — `FArray::Remove` stride **0x40 = sizeof(FBspNode)**,
  nodes ONLY (`re-raw-zones/bspbrushcsg-filter-decode.md:302/370`). The `bspAddPoint`/`Verts.Add` the
  rolled-back re-adds performed are **left in the pool** — the editor leaks graze transients, same as
  native.
- **Repartition does NOT clear the pool.** `bspBuild(RebuildSimplePolys=0)` calls `EmptyModel(0,0)` =
  empties **Nodes + Verts only**; **Points, Vectors, Surfs are KEPT** (`EmptySurfInfo=0`). So the
  repartitioned tree's `bspAddPoint` dedups ring verts against the *existing* CSG-phase pool (including
  its orphans) — which is why the editor's ring verts resolve to orphan representatives, not fresh
  `z=-12` coords.
- **`bspRefresh` does NOT compact Points/Verts** (§7.3; §10.13 Finding 1): it GCs Nodes/Surfs but
  leaves the pools "fat". The editor's pre-opt `Verts=10518` (only ~4500 live) and `Points=2091` (only
  ~1555 live) are *uncompacted* — the ~6000 orphan FVert rings + ~536 orphan points are the kept CSG
  transients. **This fat retention is exactly the `16163` vert count** (welds then grow 10518→16163);
  native re-packs at repartition (→ live ~4500) so its welds only reach 10418.

So the editor's target is: **do not clear the pool at repartition, do not re-pack Verts** — keep the
fat CSG pool of ~2091 points / ~10518 verts. The blocker is that **native's CSG phase over-produces
that pool** (measured uncleared: **6302 points / 44911 verts / 2221 live pts**, ~3× the editor).

**Over-production source #1 — the FWTB flat loop (FIXED, tree-safe).** `filter_world_through_brush`
iterated **every** world node (`for ni in 0..nn`) and filtered each face through the brush temp BSP.
The editor's `FilterWorldThroughBrush` (`0x33250`, decode §8-evidence `0x332d4`–`0x3351f`) is instead
a **recursive tree-walk pruned by the brush bound** `&TempModel->Bound`: at each node
`DoFront=(d>=-Nz)`, `DoBack=(d<=Nz)` (`d = PlaneDot(node.plane, boundCenter)`); a node's face is
filtered **only when it straddles the bound** (`DoFront&&DoBack`), and each child subtree is descended
**only on its flag** — a subtree entirely on one side of the brush is PRUNED. Native's flat loop
therefore grazed thousands of far-away faces against the brush temp BSP's *infinite* plane extensions;
each spurious graze re-adds fragments, is rolled back (`GDiscarded==0`), and **leaks** the re-adds'
points/verts. **Fix landed** (`filter_world_recurse` + `filter_one_world_node`, box push-out
`Nz = |Nx|·hx+|Ny|·hy+|Nz|·hz` from the brush AABB): uncleared pool **6302→3447 points / 44911→15963
verts**. **Provably tree-safe:** a pruned node's plane cannot be genuinely cut by the brush (whole
brush ⊂ bound, one side), so only rolled-back grazes vanish — pre-repartition `nodes=2316 surfs=524
live_pts=2221` and final `nodes=1156 surfs=485 verts=10418 nss=2728 points=1797` are **UNCHANGED**,
`soup_cmp` **853/853**, offline suite **1430 green**, `cargo test` **36 green**. The `Nz` form is the
standard AABB-vs-plane push-out inferred from the fuzzy `d>=-Nz / Nz>=d` decode line; sphere-radius was
tried first (3606, looser) — box is tighter and closer, but neither is *binary-verified* as the exact
`UModel::Bound` type (`BuildBound` `0x100cee8c`, an Engine import — not yet disassembled).

**Over-production source #2 — straddle-graze fragment fatness (UNRESOLVED — the tension).** Box
pruning removed the far-node leak but the uncleared pool is **still 3447**, ~1350 orphans over the
editor's ~536, and **native's pre-repartition live count 2221 already exceeds the editor's entire
post-repartition pool of 2091.** So even a perfect no-clear cannot reach 2091: native's *committed*
CSG tree references more distinct points than the editor's whole pool. The excess is straddle-node
grazes whose re-adds produce more split points than the editor's — likely native's brush-temp-BSP
fragment set or `bspAddPoint` (native uses FIRST-within-0.002; the editor `FindNearestVertex` returns
NEAREST-within-0.002 — `re-raw-zones/fp-classification-sites.md §7`) diverging on the transient
fragments. This needs a per-straddle-graze differential trace (native re-add fragments vs the editor's,
on a single brush) — a separate scoped task.

**Verdict + tension (per the task's "report don't force" gate).** Byte-exact `points=2035` /
`verts=16163` / `nss=2739` is **NOT reachable this pass without a second CSG fix**: the pool over-
production has two sources; #1 (flat-loop FWTB) is fixed and tree-safe, #2 (straddle-graze fatness)
remains and blocks the no-clear + no-vert-repack switch that would keep the editor's fat pool. Forcing
it (the `clear`+`reclaim`+`keeppool` toggles all tried live) does NOT reproduce the editor's specific
2091 pool — it produces *differently-wrong* pools (reclaim→2513 with the wrong orphan set; keeppool→
2884 with 1313 spurious) and does **not** move the +37 over-weld. **Committed this pass:** the
tree-safe FWTB bound-pruning fix (`bspcsg.rs`), the `UEDCLI_BSPCSG_POOLDUMP` uncleared-pool
instrumentation hook, and this decode. **NOT committed:** no `bspoptgeom.rs` change (detector frozen),
no no-clear/reclaim (would regress or mis-produce the pool). Follow-on flagged in `board/inbox/`.

### 10.15 The `z=−12/−80` spurious pool cluster RE'd to a THIRD source — the zone-split Pass-D raw point append (FIXED); CSG over-production narrowed to z=0 graze transients (2026-07-18) 🔬 ✅ / ⚠️

§10.14 attributed **all** 247 spurious pool coords to CSG straddle grazes (source #2). A
differential-by-coordinate re-trace this pass shows the largest, sharpest cluster — the **56 `z=−12`
+ 56 `z=−80`** spurious points that drive the `+37` over-weld — is a **separate third source** in the
zone pass, not the CSG phase:

**Root cause (`zones.rs`, Pass D `AssignAllZones` fragment append).** When the `z=−12` water portal
splits a moat floor/wall face into per-zone fragments, native appended each fragment's vertices with a
**raw `model.points.push()`** — no dedup. The editor's `AssignAllZones` fills fragment vertices via
**`bspAddPoint`** (`passD-assignzones-7400.md` §5 "Vertex fill", vtbl+0x1f4 — dedup into the existing
pool at 0.002). So every fragment re-emitted the moat's floor/wall CORNER points fresh; the pool held
each `z=−12/−80` corner **≈3×** (original + two fragment re-adds — verified by `_scratch/pool`
`analyze3.py`: 28 exact-duplicate coords at each of `z=−12`/`−80`, `dist=0.0`). These duplicate
orphans are exactly what `merge_near_points` (0.25) snapped ring edges onto → the 36 spurious `z=−12`
welds.

**Fix (committed, tree-safe).** `zones.rs` Pass-D fragment fill now dedups via a 0.002 pool scan
(mirrors `bsp_add_point` / the editor's `bspAddPoint`). Effect on the shipped (clear-path) build:
final pool `1797→1684`, pool-diff **spurious 246→133** (the whole `z=−12/−80` cluster gone),
`merge_near_points` remaps `139→26`. **No structural regression:** nodes 1156, surfs 485, vectors 26,
leaves 384, zones 4, `soup_cmp` 853/853, `compare_trees.py 32` IDENTICAL, T-junction weld match 958,
offline suite green. (The count moves *further* from 2035 only because the clear-path is itself wrong —
it must switch to no-clear; in the editor-faithful no-clear path this dedup is REQUIRED, as the editor
dedups here.)

**Candidate (b) is a red herring for the pool COUNT.** `bspAddPoint` FIRST-within-0.002 (native) vs
NEAREST-within-0.002 (editor `FindNearestVertex`) changes only WHICH representative index a vertex
resolves to, never whether a new point is added (`∃ point within 0.002?` is identical for first/nearest).
It perturbs `merge_near_points` remapping and weld *selection*, but cannot explain the 3447-vs-2091 pool
**size** gap. The size gap is candidate (a): a genuinely fatter fragment set.

**CSG over-production (source #2) narrowed — z=0 graze transients dominate.** With the zone-dup source
removed, the residual over-production is the CSG phase's uncleared pool (`POOLDUMP` **3447 points /
15963 verts / 2221 live**, editor ~2091). The `keeppool` experiment (keep Points/Vectors/Surfs at
repartition, per `EmptyModel(0,0)`) gives **3684 points / 2116 spurious**, and every one of those 2116
is a **novel off-grid FP coord** (not in the editor pool at all) — **z=0 alone = 1072**, then z=160
(150), z=120 (109), z=192 (72). So native's straddle-graze re-adds emit ~2116 spurious FP split points
(mostly at the z=0 floor plane) that the editor's `FilterWorldThroughBrush` does not — rolled-back
graze transients left in the pool (both leak, but native leaks a fatter set). This is the true remaining
blocker for byte-exact `points=2035 / verts=16163 / nss=2739`.

**Verdict (report-don't-force gate).** Byte-exact geometry-body remains **NOT reachable** without the
CSG straddle-graze fragment fix. Confirmed unreachable by the toggles again this pass (`keeppool→3684`).
The next mechanism is a **per-straddle-graze differential trace of `FilterWorldThroughBrush` vs the
editor oracle on a single floor brush at z=0** — comparing the native `wtb_filter_ed_poly` re-add
fragment set to the editor's `0x33250` emission, and binary-verifying the `UModel::Bound` prune type
(`BuildBound 0x100cee8c`, still not disassembled — the box push-out may over-graze). **Committed this
pass:** the `zones.rs` Pass-D dedup fix + this decode. **NOT committed:** no `bspoptgeom.rs` change
(detector frozen), no no-clear switch (native's CSG pool is still over-produced, so it mis-produces the
pool — `keeppool→3684`). Follow-on remains `board/inbox/` [spike] p2, updated.

### 10.16 The "CSG over-production" premise is WRONG — bound RE'd to an FSphere; the pool gap is the repartition CLEAR + Pass-D ring re-emit, NOT graze transients (2026-07-18) 🔬 ✅

§10.14/§10.15 concluded the byte-parity blocker is native's `FilterWorldThroughBrush` **over-producing**
z=0 straddle-graze transients, and framed the fix as a box→(tighter) prune + a no-clear switch. **A live
oracle sweep this pass proves that premise is FACTUALLY WRONG.** Native does not over-produce — it
*under*-produces — and the gap is two unrelated bookkeeping mechanisms, one of which lives in `zones.rs`
(outside the CSG core). Every number below is live-measured (`editor-tree-oracle/repart_pool_oracle.py`,
`repart_stage_oracle.py`, gdb-attached to `MAP REBUILD` on `Test_Castle.dx`).

**Bound type BINARY-VERIFIED — it is an `FSphere`, not a box (resolves the §10.14 open item).**
`UModel::BuildBound` is **`Engine.dll 0x16fcf0`** (not the `0x100cee8c` guess). It sets `Model.Bound`
= { `FBox`@UModel+0x28 = the AABB over the brush's `Polys` vertices, `FSphere`@+0x44 }, where
`FSphere(Pts,Count)` (`core.dll 0x50100`) = { center = AABB midpoint, radius = √(max‖pt−center‖²) **·
1.001** (a small pad-fudge, the tail `fmul [0x100a5b40]` = the f32 literal `1.001`) }.
`FilterWorldThroughBrush` (`Editor.dll 0x33250`) takes the bound as **arg5** and computes
`d = FPlane::PlaneDot(node.plane, *arg5)` then reads `R = *(arg5+0xc)`, forming `DoFront = d >= −R`,
`DoBack = d <= R` (disasm `0x33316`–`0x33355`, the `xorps [0x100dcb60]` sign-flip = `−R`). `arg5+0xc`
is the `FSphere.Radius` slot ⇒ **`arg5 = &TempModel->Bound.Sphere`, a SPHERE prune**, not the box
push-out §10.14 inferred. **The box and sphere are DIFFERENT, INCOMPARABLE prunes** — neither
straddle-set contains the other (for a diagonal node normal on a near-cubic brush the box support
`Σ|Nᵢ|hᵢ` exceeds `R`; for a thin wall the sphere is looser). Both are nonetheless CONSERVATIVE (the
brush's true support along any normal is `≤ R` AND `≤ box-push`), so neither prunes a genuine cut — the
committed tree is identical either way, and the box↔sphere symmetric difference is ALL grazes. **Fixed**
in `bspcsg.rs` (`filter_world_through_brush` + `filter_world_recurse`, constant `radius` with the 1.001
fudge, f64 sqrt·1.001→f32): uncleared CSG pool **3447→3606 points, 15963→17120 verts** — and **17120 now
EXACTLY equals the editor's CSG-phase verts** (measured below), confirming the sphere is faithful.
**Tree-safe / output-invariant:** the prune only changes rolled-back GRAZE transients, and the current
clear-path compacts them away — final `nodes 1156 / surfs 485 / verts 10418 / points 1684 / vectors 26 /
nss 2728` **byte-UNCHANGED**, `cargo test` 36 green, offline suite 1568 green.

**`EmptyModel(0,0)` + `bspRefresh` keep-set — decoded.** `EmptyModel` (`Engine.dll 0x16ff10`, args
`EmptySurfInfo, EmptyGeometry`) unconditionally empties **Nodes(+0x58)** and **Verts(+0x68)**; the
Points(+0x88)/Vectors(+0x78)/Surfs(+0x98) frees are BOTH gated on the args, so `EmptyModel(0,0)` **KEEPS
Points, Vectors, Surfs** (§10.14 was right on this). `bspRefresh` (`0x36cd0`) marks a point USED iff it
is referenced by **`surf.pBase` (surf+0x8) OR a node ring `vert.iVertex`**, then compacts; it is called
from `bspRepartition` with **`NoRemapSurfs=1`** (`0x1004a049 push 1`) so all **524** CSG surfs (and their
base points) survive to `bspOptGeom`, whose own front `bspRefresh(…,0)` finally compacts surfs 524→485.

**The gap LOCALIZED by a stage sweep — it is NOT the CSG phase.** Pool sizes through `bspRepartition`
(`repart_stage_oracle.py`) and at `bspOptGeom` entry (`repart_pool_oracle.py`), editor vs native:

| checkpoint | nodes | verts | points | surfs |
|---|---|---|---|---|
| CSG-phase / repart ENTRY (editor) | 2316 | **17120** | **4939** | 524 |
| CSG-phase / repart ENTRY (native, post-sphere) | 2316 | **17120** | 3606 | 524 |
| after `bspBuild` (EmptyModel+SplitPolyList) — editor | 1127 | **4405** | **2088** | 524 |
| `bspOptGeom` ENTRY — editor | 1156 | **10518** | 2091 | 524 |
| `bspOptGeom` ENTRY — native | 1156 | **4521** | 1684 | 485 |

Two facts kill the over-production premise: (1) the editor's CSG pool (**4939** pts / 17120 verts) is
*bigger* than native's, and nodes/surfs match exactly (2316/524) — native never over-produces. (2) The
editor's `bspBuild` **COMPACTS** the fat CSG pool to **4405 verts / 2088 points** (EmptyModel keeps
Points, SplitPolyList appends+dedups, `bspRefresh` keeps only referenced). Live ring sums are IDENTICAL
(Σnv = **4521** both sides). So the two remaining gaps are pure orphan bookkeeping, and NEITHER is CSG
graze fatness:

- **Verts (native 4521 vs editor 10518 — the dominant gap) = `TestVisibility`/Pass-D ring RE-EMISSION.**
  Between `bspRepartition` exit (4405) and `bspOptGeom` entry (10518) the editor gains **+6113 verts** but
  only **+29 nodes / +3 points** — i.e. `TestVisibility` (our zones Pass D) re-emits ~every node's ring
  with fresh `FVert`s (referencing existing points), **orphaning the originals**. Native's Pass D keeps
  the original ring as its first fragment and only adds verts for the 29 new fragment nodes (+~116),
  so native carries ~0 orphan verts. **This gap is in `zones.rs`, not `bspcsg.rs`.** (The editor's
  on-disk 16163 = 10518 + `bspOptGeom` inserts; native's 10418 = 4521 + inserts. Fix the 6113 Pass-D
  orphans and the vert pool falls into place.)
- **Points (native 1684 vs editor ~2088–2091) = the repartition CLEAR.** Native clears Points AND
  compacts Surfs (524→485) at repartition; the editor keeps the CSG Points pool and all 524 surf bases
  (`EmptyModel(0,0)` + `bspRefresh NoRemapSurfs=1`). The ~404-point delta is surf-base + retained CSG
  points native drops early. **This gap is in `bspcsg.rs`** (a no-clear repartition + deferred surf
  compaction) but is entangled with `surf.pBase`/`vert.iVertex` pool indices — high tree-regression risk.

**Verdict (report-don't-force gate).** Byte-exact `points=2035 / verts=16163 / nss=2739` is **not
reachable by a `bspcsg.rs`-only change**, and the prior "z=0 graze over-production" lever does not exist.
The dominant lever (verts) is a **`zones.rs` Pass-D ring-re-emit** port — explicitly out of this task's
scope ("do not touch `zones.rs`") — and the points lever is a no-clear repartition that risks the
byte-exact tree. **Committed this pass:** the binary-verified FWTB **sphere** prune (`bspcsg.rs`, safe /
output-invariant), the oracle harness (`repart_pool_oracle.py`, `repart_stage_oracle.py`, `disx.py`
cross-DLL disassembler), and this decode. **NOT committed:** no no-clear switch, no `zones.rs` change
(frozen), no `bspoptgeom.rs` change (detector frozen). Follow-on re-scoped in `board/inbox/`: the
remaining body gap is a **Pass-D orphan-ring port in `zones.rs` + a no-clear repartition in `bspcsg.rs`**,
NOT CSG graze over-production.

> **DONE 2026-07-18 (the Verts half — see [§70 §11](70-zones-portalization.md)).** The Pass-D orphan-ring
> re-emit is ported in `zones.rs`: every landing's ring is appended in the editor's walk+landing order
> (orphans snap to existing points and never grow the pool; the retained disagreement original is
> repointed onto its first clipped zone fragment). **Verts 10407→16183** (editor 16163, +20 residual),
> **NumSharedSides 2707→2739 byte-identical**, **Points unchanged at 2061**, all node/soup/bounds/leafhull
> guards held (1156/1156 planes). The Points half here (native 2061 vs editor 2035) is NOT the repartition
> clear — §10.18 superseded that: it is the surf-emit-ORDER +26 residual, a separate follow-on lever.

### 10.17 The node-emit-ORDER lever RESOLVED — the tree was already ISOMORPHIC; the gap was Pass-D fragment array-layout, fixed by a tail-relabel (2026-07-18) 🔬 ✅

§10.10 left the final tree at RAW positional plane match **172/1156, first divergence node 51**, and
attributed the cap to "the 29 tail nodes perturb `bspRefresh` numbering." §10.13 Finding 1 hinted the
partitioner needs no change ("native's BSP is node-for-node isomorphic … `node_diff`'s index-by-index
divergence is an ARTIFACT of an early array-layout shift"). **This section proves that hint exactly,
identifies the layout mechanism, and lands the fix — RAW positional plane match is now 1156/1156.**

**The decisive measurement (`harness/node_order_iso.py`, new).** A link-following lock-step walk of
the two FINAL on-disk trees — follow `(iFront, iBack, iPlane)` from the root on both, compare planes
(abs tol) — matches **1156/1156 nodes with 0 divergences**: the native and editor BSP trees are
**node-for-node ISOMORPHIC** (identical split at every tree position). But only **53/1156** nodes sat
at the same ARRAY index; the first mismatch was native `[51] -> editor [1102]`. So the entire residual
was **linearization** (the order nodes are stored in `Model->Nodes`), NOT the partition — exactly the
"node emit ORDER" lever.

**The layout mechanism (permutation-run analysis).** The array order is CREATION order (both sides;
neither is a from-root DFS re-traversal — a preorder walk reproduces neither). Native's BASE nodes
(the from-scratch repartition, indices 0..~1099) were **already in the editor's exact creation order**
— the permutation `native_idx -> editor_idx` was a sequence of constant-delta runs whose deltas
(-2, -4, … -23) counted only the nodes native had inserted early. Those inserted-early nodes were the
**56 Pass-D boundary-wall zone-split fragments** (planes `w = ±500 / ±410`, the moat/water outer walls
the `z=−12` water portal cuts into two zones). UnrealEd's `TestVisibility`/`AssignAllZones`
(`passD-assignzones-7400.md`) on a zone-spanning face **kills the original node and appends ALL its
zone fragments at the TAIL of `Model->Nodes`** (then `bspCleanup` removes the dead original), so every
split node — original included — lands in the tail cluster (editor indices ~1100–1155) in walk order,
as interleaved `(0,1)`/`(0,2)` fragment pairs. Native's `zones.rs` Pass D instead **kept the split
original in place** (its early repartition index) and appended only the EXTRA fragments — scattering
each split group and shifting every downstream index.

**The fix (a pure, tree-preserving relabel — `bspcsg.rs` + one `zones.rs` seam).** Because the tree is
already isomorphic, matching the editor's array needs only a **permutation of `Model->Nodes`** with a
child/chain-link remap — no partition, tree, collision, zone, or render change (nothing outside the
node array references a node by index at this stage: leaves/surfs carry no node ref, and
`Bounds`/`LeafHulls` are built AFTER). Two parts:
1. `zones::assign_leaves_and_zones` now **returns the split-group node indices in the editor's
   emission order** (`[original, frag1, …]` per split, in `passd_walk` order — `frags` is grouped by
   owner contiguously, so this is free to record). The legacy `build.rs` path ignores it.
2. `bspcsg::reorder_nodes_to_tail` (called at the end of `finalize`, before `bspOptGeom`/
   `bspBuildBounds`) moves exactly those nodes to the array tail in that order, keeping all other
   nodes' relative order, and remaps every `iFront`/`iBack`/`iPlane` through the old→new map (root
   node 0 is pinned). A total, safe relabel.

**Results (all measured on the final on-disk `NativeCastle.dx` vs `Test_Castle.dx`).**
- **RAW positional plane match `172/1156` → `1156/1156` (abs tol 1e-3), first divergence NONE**
  (`harness/bounds_leafhulls_decode.py`, now abs-tolerance not a round-3dp key; `node_order_iso.py`).
  The `node_diff.py` `plane` field DROPS OUT of the divergence histogram entirely (was 984/1156).
- The round-3dp multiset key still shows `1144 / 12 / 12` — the **same** `−381.0655` octagon-roof/
  bastion planes straddling the round boundary (`−381.065` vs `−381.066`); the fp-noise §10.10-§10.12
  tracked, provably one plane, collapses to 0 under any absolute tolerance.
- Isomorphism preserved (1156/1156, 0 divergences); **identity-position 53 → 1146/1156** (the residual
  ~10 are duplicate `±500/±410` boundary-wall planes the link-walk maps to an equal-plane sibling
  index — positional PLANE match is unaffected, 1156/1156).
- Invariants intact: `soup_cmp` **853/853 (0/0)**, surfs **485**, vectors **26**, leaves 384, zones 4;
  `compare_trees 32` incremental stream unchanged; collision test green. `cargo test` 36 passed,
  offline suite **1644 passed / 1 skipped / 1 xfailed**.
- Side effect (benign, in-scope-noise): `bspOptGeom` runs after the reorder, so its order-sensitive
  T-junction weld shifted `verts 10418→10407` and `NumSharedSides 2728→2707` — a ≪1% move inside the
  already-out-of-scope vert-pool gap (native ~10.4k vs editor 16163; §10.16). Planes are untouched
  (welds add ring verts, never move a plane).

**What remains (all OUT OF SCOPE of the node-ORDER lever, unchanged by this fix).** `node_diff`'s
full-TUPLE prefix is still 0 because the per-node INT fields differ on their own separately-tracked
axes, none of which is node order: `i_zone` (a zone-number permutation — semantically matched, §10.12),
`i_surf` (Surfs-pool order), `i_vert_pool`/`num_vertices` (the vert-pool ring gap, §10.13-§10.16),
`node_flags` (`0x08/0x10` camera-occlusion render bits, non-deterministic, correctly excluded §10.11
Fact 3). **The node-emit-ORDER blocker that §82c/§82b framed as gating `Bounds`/`LeafHulls` byte-parity
is now removed** — those aux arrays are built against the relabelled (editor-order) tree, so their
node-order dependence is satisfied; their remaining gaps (§82c: post-order-DFS `iRenderBound` numbering
+ tight-cell bbox; plane-cull count) are the independent recipes that section already documents, no
longer node-order-blocked. Harness committed: `node_order_iso.py`; `bounds_leafhulls_decode.py` metric
corrected to an absolute float tolerance.

### 10.18 The point-pool gap was NOT the repartition clear — it was the DROPPED authored `FPoly::Base` (surf `pBase`); plumbing T3D `Origin` closes it (2026-07-18) 🔬 ✅

§10.16 (line ~1420) diagnosed the **Points** gap (native 1684 vs editor 2035) as "the repartition
CLEAR" and proposed a risky no-clear repartition. **That diagnosis is WRONG on mechanism.** Two
cheap RAW measurements disprove it and pin the real cause:

- **The clear is not the cause.** Gating out the `model.points.clear()` at repartition
  (`UEDCLI_BSPCSG_NOCOMPACT`, throwaway) leaves the total pool fat (3838) but the **referenced**-point
  count IDENTICAL: `refd_points = 1681` with OR without the clear. The rebuilt tree genuinely
  *references* only 1681 distinct points either way — so no clear/no-clear knob moves the on-disk pool
  (the editor drops unreferenced points at `bspRefresh` regardless). Keeping the pool would only add
  unreferenced ORPHANS at the wrong coordinates, not the editor's points.
- **The real gap is `pBase`.** A nearest-neighbour scan (`harness` scratch `pt_nn.py`) of the editor's
  2035 points vs native's 1684 found: 1544 exact, 11 sub-0.002 FP aliases, and **480 editor points that
  are >2 uu from ANY native point** — genuinely-absent geometry, not FP welds. Grouping those 480 by
  who references them: **0 appear in any node ring; all 480 are surf `pBase` origins** (the editor's
  Points array LEADS with 484 distinct pBase points, in surf-emit order — e.g. `Points[0]=(1150,0,210)`
  is surf 0's base). The editor stores each surf's **texture-origin `FPoly::Base`** as a distinct
  orphan point; native stored a ring CORNER (only 103 orphan bases, 448 distinct).
- **Root cause: the authored `Origin` was dropped in marshalling.** `FPoly::new(verts)` defaults
  `base = verts[0]`, and `_build_brush_input` passed verts/normals/texture-axes but **never the T3D
  `Origin=`** (`poly.origin`, which `uedcli/model.py` already parses). So every surf `pBase` welded onto
  a corner. The editor keeps `EdPoly->Base` = the stored texture origin (usually not a vertex): e.g.
  the World shell's x=1150 face has authored `Origin (0,0,210)` → LOOP-1 base-snap onto the plane →
  `(1150,0,210)`, matching the editor byte-for-byte.

**Fix (committed): plumb per-poly `Origin` through to `FPoly.base`.** `_build_brush_input` emits
`origins_flat` (one local-space FVector per poly, gated on every poly having an origin — mirrors the
`normals` gate); the PyO3 `BrushTuple` carries it bundled with `tex_v_flat` in a nested
`(tex_v_flat, origins_flat)` pair (PyO3 tuple `FromPyObject` caps at 12 fields); `brush_from_tuple`
sets `p.base` from it (empty → keeps the `verts[0]` default). `FPoly::transform` rotates it into
world; the existing LOOP-1 base-snap lands it on the plane. Files: `lib.rs`, `materialize.py`, and the
two other tuple constructors (`preview_native.py`, `test_csg_native_differential.py`, both passing
empty origins → unchanged).

**RAW result (fresh `build_native_castle.py` → `ground_truth_bytediff.py`):**

| metric | before | after | editor |
|---|---|---|---|
| Points (count) | 1684 | **2061** | 2035 |
| Points only-editor / only-native (tol-multiset) | 482 / 131 | **3 / 29** | — |
| per-node pBase **coord**-equal | **0/1156** | **1156/1156** | — |
| per-node pBase byte(index)-equal | 0/1156 | **241/1156** | — |
| surf-base coord multiset (only-nat / only-ed) | — | **0 / 0** | — |
| whole-body positional byte match | 20.21% | **23.66%** | — |
| Bounds first-diff (in-section) | @2 | **@27** | — |
| LeafHulls first-diff (in-section) | @86 | **@842** | — |

pBase **value** parity is now COMPLETE (1156/1156 coord-equal, all 485 surf bases match). The residual
is pure point-pool **ORDER**: native overshoots by 26 points and the emit order diverges from surf 6
onward, so only 241/1156 pBases are byte(index)-exact and `Bounds`/`LeafHulls` still carry a
point-index residual. Guards intact: nodes 1156/1156 planes, soup 853/853, surfs 485, vectors 26,
leaves 384, Bounds/LeafHulls length 484/3866; verts/nss unchanged (that gap is the `zones.rs` Pass-D
ring re-emit of §10.16, still out of scope). Offline suite 1665 passed; `cargo test` 37 passed.

**Next point-pool lever (deferred):** byte-exact point ORDER — reconcile native's surf/point emit
sequence with the editor's (the Points array is laid out in surf-emit order; native's diverges at
surf 6, and 26 spurious points remain). This is a surf-emit-order reconciliation, coupled to the
node-emit reorder of §10.17, not another base-value fix.

### 10.19 The Surfs/Vectors pool ORDER RE'd to the repartition surf-CLEAR — the editor KEEPS the incremental-CSG surf pool; a canonical re-sort lands surf order + node.iSurf + vector order (2026-07-18) 🔬 ✅

§10.18 left the residual as "pure point-pool ORDER: native overshoots by 26 points and the emit order
diverges from surf 6 onward." This section RE's the **surf/vector** half of that ORDER gap to a single
mechanism and fixes it (the point half — §10.20, next — rides on the same finding).

**Decode — the editor does NOT rebuild the Surfs pool at repartition.** The vector pool is a pure
function of surf order: walking `Surfs` in array order and `find-or-add`-ing each surf's
`(vNormal, vTextureU, vTextureV)` reproduces the on-disk `Vectors` array **byte-for-byte on BOTH
files** (`harness` scratch `vecrule.py`: editor 26/26, native 26/26). So "vectors" is not an
independent lever — it is downstream of surf order. And the surf order itself was a pure PERMUTATION:
native and editor carry the **same 485-surf set** (`(iActor,iBrushPoly)` multiset only-native = 0,
only-editor = 0; `surforder.py`), diverging at surf 6. The tell (`surf_grouping.py`): the editor's
surf array has **95 contiguous `iActor` runs for 95 brushes** — every brush's surviving faces are
contiguous, brushes in CSG-processing order, polys ascending — i.e. the **incremental-`bspBrushCSG`
allocation order**. Native's was **322 runs** — brushes shattered across the pool, the
repartition split-recursion order. Root cause: native's `bspRepartition` does
`model.surfs.clear()` and re-allocates surfs fresh during `bspBuild`; **the editor keeps the
incremental surf pool** (`EmptyModel(0,0)` + `bspRefresh NoRemapSurfs`, §10.16) and only *compacts*
it (524→485, relative order preserved). The canonical order is exactly
`sort by (actor-first-appearance-order, iBrushPoly ascending)`, and the `(iActor,iBrushPoly)` key is
**unique per surf** (485/485; `surf_key.py` reproduces the editor order from this rule exactly).

**Fix (committed) — a post-build canonical re-sort, tree-safe by construction.** Rather than rework
the repartition (high node-tree-regression risk), `build_geometry_bspcsg` snapshots the
incremental-CSG surf key order **just before the repartition clear** (`canon_surf_keys`), then AFTER
the whole build (post-`bspBuildBounds`):
1. `reorder_surfs_canonical` stable-sorts the final surfs by their rank in that snapshot (detail/
   semisolid surfs added post-snapshot keep their order, after all ranked surfs) and remaps every
   `node.iSurf` through the old→new permutation.
2. `rebuild_vector_pool` walks the re-sorted surfs, `find-or-add`s each `(vNormal,vTextureU,
   vTextureV)` into a fresh pool (exact-equality dedup, values pulled from the existing pool) and
   rewrites the surf refs — the proven rule that reproduces the editor `Vectors` order.

Both are pure array relabels referenced by nothing but surfs/nodes' `iSurf`, so **no node plane,
tree link, vert, bound, or hull is touched** — node isomorphism is preserved by construction.

**RAW result (`build_native_castle.py` → `ground_truth_bytediff.py`):**

| metric | before | after |
|---|---|---|
| surf `(iActor,iBrushPoly)` contiguous-actor runs | 322 | **95** (= editor) |
| Vectors pool order (value, 2dp) positional | 8/26 | **26/26** |
| node `iSurf` per-field mismatch (triage) | 932/1156 | **0** (dropped off) |
| surf `iBrushPoly` / `polyFlags` / `vNormal` / `vTextureU/V` mismatch | 410/8/438/309/412 | **all dropped off** |
| whole-body positional byte match | 29.21% | **29.64%** |
| node isomorphism (link-walk) | 1156/1156 | **1156/1156, 0 div** |

The `Vectors` section is now byte-EQUAL in ORDER; its remaining on-disk diff (`@73` = vector 6 =
`(0.7071,0.7071,0)`) is a **1–3 ULP normal-VALUE difference** (native `0x3f3504f7` vs editor
`0x3f3504f4`) — a normal-computation FP-precision lever (`fpoly` normalize / x87-vs-SSE, §41), NOT
pool order. The `Surfs` section residual is now only `iActor` (a package export-index numbering diff,
not order), `pBase` INDEX (the point pool is not yet re-sorted — §10.20), and `iLightMap` (LightMap
array order, `light.rs` lane). Guards intact: nodes 1156/1156 planes (first-div None), soup 853/853,
surfs 485, vectors 26, leaves 384, Verts 16183, NumSharedSides byte-identical, Bounds/LeafHulls
484/3866. `cargo test` 37 passed; offline suite 1678 passed.

**Next (§10.20):** the point pool. With surf order canonical, re-sort the Points pool so the leading
surf `pBase` block follows the new surf order (and reconcile the `+26` overshoot) — the same
"keep-incremental-order" finding, applied to Points.

### 10.20 The Point pool: +26 orphans DROPPED + bases-then-rings LAYOUT restored — whole-body positional match 29.6%→43.6% (2026-07-18) 🔬 ✅ / ⚠️

With surf/vector order canonical (§10.19), this closes the reachable half of the Points ORDER gap.

**Decode — two separate defects.** (1) **+26 overshoot = unreferenced orphans.** Native carried 2061
points vs the editor's 2035; **exactly 26 are UNREFERENCED** (named by no `surf.pBase` and no
`vert.iVertex`; `pointstruct.py`) — native's `bsp_refresh` (`passes.rs`) deliberately skips point
compaction, so the CSG-phase orphans survive; the editor's `bspRefresh` GCs them. The *referenced*
set is otherwise identical (base-only/ring-only/both = 480/1551/4 on BOTH sides; a pure 2dp
permutation, only-nat/only-ed = 0/0, with an ~84-point sub-0.002 FP-value floor). (2) **Layout =
bases-first.** The editor's Points array LEADS with a **contiguous 484-entry surf-`pBase` block**
(`Points[0]` = surf 0's base) THEN the ring vertices (`ptrule.py`: the first 484 are all base points).
Native's repartition rebuild interleaved base+ring per node in split-recursion order.

**Why the editor's exact order is NOT cleanly reproducible.** Neither native's own INCREMENTAL point
pool (captured pre-repartition-clear; reorder to it scored **1/2035** — it is base-then-ring
interleaved, not bases-first) nor the clean rule "bases-in-surf-order ++ rings-in-node-order" is the
editor's true order: that rule matches the editor's OWN file only **384/2035** (diverges at base #132
and at ring #5). The editor's intra-block sub-order is a `bspRefresh` reachability-DFS-compaction
artifact of the **pre-compaction pool indices** (`fp-classification-sites.md` §7.3: "compacts by a
reachability DFS from node 0"), which the final on-disk model does not expose. Pinned as a deeper
follow-on lever, not forced.

**Fix (committed) — `reorder_points_canonical` (`bspcsg.rs`), a final post-pass.** Drop every
unreferenced point, then re-emit the survivors **bases-first** (walk canonical surfs, first-appearance
`pBase`) THEN **rings** (walk nodes, first-appearance ring `iVertex`), renumbering `surf.pBase` +
`vert.iVertex` (the only two point-ref classes; Bounds/LeafHulls store plane-refs + float bboxes, not
point indices). The pool is already 0.002-deduped, so exact-index first-appearance re-emits the same
distinct set with no re-weld. Runs last (after `bspBuildBounds`) so those two refs are the only ones
live. Touches no node plane/link, vector, or bound → node isomorphism preserved by construction.

**RAW result (`build_native_castle.py` → `ground_truth_bytediff.py`):**

| metric | before (§10.19) | after |
|---|---|---|
| Points count / section length | 2061 / 24734 | **2035 / 24422** (both byte-exact vs editor) |
| Points section first-diff (in-section byte) | @0 | **@1586** (leading 132-base block byte-EXACT) |
| whole-body positional byte match | 29.64% | **43.60%** |
| node isomorphism (link-walk) | 1156/1156 | **1156/1156, 0 div** |

Guards intact: nodes 1156/1156 planes (first-div None), surfs 485, vectors 26, Verts 16183,
NumSharedSides byte-identical, Bounds/LeafHulls 484/3866, leaves 384. `cargo test` 37 passed; offline
suite 1701 passed. **Residual (⚠️, deeper follow-on):** the Points intra-block sub-order (base #132+,
ring order) — the pre-compaction reachability-DFS artifact above — plus the ~84-point sub-0.002 FP
value floor; and downstream `Bounds`/`LeafHulls` still carry the resulting point-INDEX residual.