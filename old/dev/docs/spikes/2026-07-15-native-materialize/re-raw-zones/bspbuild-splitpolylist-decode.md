# RE: `bspBuild` / `SplitPolyList` / `FindBestSplit` / `bspBrushCSG` / `csgRebuild` — 2026-07-17

**Binary:** `uned/UED22/Editor.dll` (ImageBase `0x10000000`). All addresses are VAs. Decoded with
`dev/docs/spikes/2026-07-15-native-materialize/harness/adis.py Editor 0x<rva> 0x<len>` (annotates
CALL targets from the export table and memory operands with float/wide-string literals). Struct
offsets per the shared UModel/FBspNode/FPoly brief. 🔬 = disassembled this session.

This is the evidence backing `sections/80-bspbuild-topology.md`. The load-bearing verdict: **there
is NO leaf-bounding / bevel node-expansion pass in `bspBuild`** — `SplitPolyList` is a *pure
partition*; the editor tree's watertightness comes from **incremental `bspBrushCSG` filtering
against each brush's own bevel/bounding planes**, not from any post-hoc bounding stage.

## Vtable (UEditorEngine, base `0x100cf5d4`) 🔬
Resolved by locating the `bsp*` export pointers in `.rdata` (cluster `0x100cf7c0`) and anchoring on
the independently-confirmed `bspAddNode` slot.

| slot | fn | RVA | slot | fn | RVA |
|---|---|---|---|---|---|
| +0x1ec | bspRepartition | 0x49fc0 | +0x210 | bspMergeCoplanars | 0x36200 |
| +0x1fc | bspBuild | 0x35ef0 | +0x214 | bspBrushCSG | 0x355e0 |
| +0x200 | bspRefresh | 0x36cd0 | +0x218 | bspOptGeom | 0x36870 |
| +0x208 | bspBuildBounds | 0xaace0 | +0x224 | bspAddNode | 0x34e80 |
| +0x20c | bspBuildFPolys | 0x36090 | +0x264 | TestVisibility | 0xaa940 |

## `bspBuild` @0x35ef0 🔬
`bspBuild(UModel* Model[+8], EBspOptimization Opt[+0xc], INT Balance[+0x10], INT RebuildSimplePolys[+0x14])`
(`ret 0x14`). `esi=Model`; `[esi+0x54]=Polys(UPolys*)`, `[eax+0x2c]=Polys.Num`.
- `RebuildSimplePolys==1` (0x35f33): `EmptyModel(1,0)`.
- `RebuildSimplePolys==0` (0x35f3f): clear every `Node.NumVertices=0` (byte +0x36); `bspRefresh(Model,1)` [vtbl+0x200]; `EmptyModel(0,0)`.
- Build (0x35f74): `PolyList = PushBytes(Polys.Num*4)`, fill with `&Polys[i]` where `NumVertices!=0`, then **`SplitPolyList(Model, -1, NODE_Root=3, n, PolyList, Opt, Balance, RebuildSimplePolys)`** (call 0x35fe1 → 0x34530).
- Post (0x35fe9): if `RebuildSimplePolys==0`, `bspRefresh(Model,1)` [+0x200] then **`bspBuildBounds(Model)`** [+0x208].

**Tail is `bspRefresh` + `bspBuildBounds` only — no node-adding leaf-bounding.** `bspBuildBounds`
(decoded in `bounds-and-zonelayout.md`) fills the `Bounds`/`LeafHulls` *arrays*; it never touches
`Nodes`. So the final node COUNT is exactly whatever `SplitPolyList` produced.

## `SplitPolyList` @0x34530 🔬
`SplitPolyList(Model[+8], iParent[+0xc], ENodePlace[+0x10], NumPolys[+0x14], PolyList[+0x18], Opt[+0x1c], BalancePacked[+0x20], RebuildSimplePolys[+0x24])`.
```c
FrontList = PushBytes(4*(NumPolys*1.25)+0x20);  BackList = same;      // 0x3457b/0x345a3 (GMem)
FPoly* Split = FindBestSplit(NumPolys, PolyList, Opt, BalancePacked); // 0x345bf -> 0x335d0
if (RebuildSimplePolys) Split->iLink = Model->Surfs.Num;              // 0x345cf
INT iNode = bspAddNode(Model, iParent, ENodePlace, 0, Split);        // 0x345f2 [vtbl+0x224]
INT iPlane = iNode;
for (i=0; i<NumPolys; i++) {                                          // 0x34654
    FPoly* P = PolyList[i];  if (P==Split) continue;                  // 0x3466b
    switch (P->SplitWithPlane(Split->Base, Split->Normal, &Front, &Back, 0)) { // IAT 0x100cee34
      case 0 /*Coplanar*/: if (RebuildSimplePolys) P->iLink = Surfs.Num-1;
                           iPlane = bspAddNode(Model, iPlane, NODE_Plane=2, 0, P); break; // 0x346af
      case 1 /*Front*/:    FrontList[nF++] = P; break;               // 0x346c4
      case 2 /*Back*/:     BackList[nB++]  = P; break;               // 0x346e0
      case 3 /*Split*/:    FrontList[nF++]=Front; BackList[nB++]=Back;// 0x346f9
                           if (Front->NumVertices>=0xe) SplitInHalf(Front); // 0x34716
                           if (Back->NumVertices >=0xe) SplitInHalf(Back);  // 0x3475f
    }
}
if (nF) SplitPolyList(Model, iNode, NODE_Front=1, ...FrontList, nF...); // 0x34824
if (nB) SplitPolyList(Model, iNode, NODE_Back =0, ...BackList,  nB...); // 0x34841
```
jump-table @0x3489c = `{coplanar,front,back,split}`. **The ONLY `bspAddNode` calls are the splitter
(1×) and one per coplanar poly (`NODE_Plane` chain via `iPlane`).** An empty Front/Back list simply
stops the recursion — **no leaf node is emitted, no bounding pass.** So
`#nodes = #input FPolys + #SP_Split fragments`; nothing expands it.

## `FindBestSplit` @0x335d0 🔬 — scoring EXACT
`FindBestSplit(NumPolys[+8], PolyList[+0xc], Opt[+0x10], BalancePacked[+0x14])`.
- **`Balance = BalancePacked & 0xff`** (0x33629); **`PortalBias = (BalancePacked>>8)&0xff`** (0x33648), stored as `PortalBias/100.0`.
- Candidate stride `Inc`: `Opt==2`(OPTIMAL)→1 (0x3366f); `Opt==1`(GOOD)→NumPolys/10 (0x3369e); else(LAME)→NumPolys/4 (0x336b1); `max(Inc,1)`.
- Structural skip (0x336cb/0x3374b): `AllStructural` iff EVERY poly has `PolyFlags & 0x28` (`PF_NotSolid|PF_Semisolid`). A candidate with `& 0x28` and NOT `PF_Portal(0x4000000)` is skipped unless `AllStructural`.
- Inner loop `SplitWithPlaneFast` (IAT 0x100cee30), jmptbl @0x33934. Split case (0x3380e): `Splits += (Other->PolyFlags & PF_Portal) ? 0x10 : 1`.
- **Score:** `Score2 = (100-Balance)*Splits` (0x3385e); `Score = Score2 + Balance*abs(Front-Back)` (0x33874); if candidate `PF_Portal`: `Score -= Score2*(PortalBias/100)` (0x3588d). **Min** wins; first candidate always taken.

> **⚠️ PARAM CORRECTION (2026-07-17):** this line's "`Balance=50, PortalBias=70`" is **WRONG** for the
> REPARTITION `bspBuild`. Decoding the call chain proves the repartition uses **Balance=12 (`0xc`),
> PortalBias=0, Opt=GOOD(1)** (stride `NumPolys/10`), not 50/70/OPTIMAL. So `Score = 88*Splits +
> 12*|F-B|`, no portal discount. See `findbestsplit-params-decode.md` (VA-cited) — this is the
> first-divergence root cause. (The `csg.rs::find_best_split SPLIT_WEIGHT` note is stale; the
> `bspcsg.rs` path uses `find_best_split_exact`, whose only bug is the three wrong constants.)

## `bspAddNode` @0x34e80 🔬
- NODE_Plane coplanar-chain walk (0x34eb9): follow `Node.iPlane`(+0x28) from iParent to `-1`, append there.
- `>16`-vert storage split (0x35058): split into `EdPoly1.NumVertices=16` + `EdPoly2.NumVertices=N-14` sharing verts 14/15 (copy `Verts[14..]` at 0x350ff), recurse `bspAddNode` for both (0x35130/0x35145).
- Surf sharing (0x34ede): if `Poly->iLink == Surfs.Num` allocate a new `FBspSurf` (`Base=bspAddPoint`, `Normal/U/V=bspAddVector`, `PolyFlags = Poly->PolyFlags & 0x3cffffff`, `iBrushPoly`); else share the existing surf at `iLink`.
- FVert pool (0x35224): **`Node.iVertPool = Verts.Add(Poly->NumVertices)`** (FVert stride 8 = `{INT pVertex; INT iSide}`); the vert loop (0x352f0) `bspAddPoint`s each vertex, **collapsing consecutive duplicates** (0x3532a). ⇒ `#FVerts ≈ Σ_nodes NumVertices` (minus dup collapse).

## `csgRebuild` @0x4a650 🔬 — the real pipeline
`csgRebuild(Level[+8], INT[+0xc])`. Brush cursor helper `0x49210` = actor-iterator advance (skips
non-`IsStaticBrush`); adds no nodes.
```c
GWarn->BeginSlowTask("Rebuilding geometry");        // 0x4a691
this->vtbl[0xb4](Level);                            // 0x4a6b3 setup
Level->Model->EmptyModel(1,1);                      // 0x4a6bd
// LOOP 1: count real brushes (progress bar).
// LOOP 2 (0x4a7b0): STRUCTURAL brushes -> bspBrushCSG(Brush, Model, ...) [vtbl+0x214]  // 0x4a870 INCREMENTAL adds
bspRepartition(Model, 0, 0);                        // 0x4a89a [vtbl+0x1ec]  *** from-scratch repartition ***
TestVisibility(Level, Model, 0, 0);                 // 0x4a8af [vtbl+0x264]
if (Nodes.Num) sub_49380(Model,&A,&B,0);            // 0x4a8e4 collect zone/bound nodes
// LOOP 3 (0x4a940): SEMISOLID/NONSOLID brushes -> bspBrushCSG(...) [vtbl+0x214]  // 0x4a9e8 INCREMENTAL, NOT repartitioned
// two passes over A,B -> vtbl[0x1ec](Model, child, 2)   // 0x4aa17/0x4aa68
bspOptGeom(Model);                                  // 0x4aab0 [vtbl+0x218]
bspBuildBounds(Model);                              // 0x4aac0 [vtbl+0x208]
GWarn->EndSlowTask();
```
`bspRepartition` @0x49fc0 = `bspBuildFPolys(Model,1,Opt)` [nodes→Polys] + `bspMergeCoplanars(Model,0,0)`
+ `bspBuild(Model,1,0xc,0)` [from-scratch SplitPolyList over the merged Polys] + `bspRefresh(Model,1)`.

## `bspBrushCSG` @0x355e0 🔬 — where watertightness comes from
`bspBrushCSG(Actor[+8], Model[+0xc], PolyFlags[+0x10], CsgOper[+0x14], ...)`. Early-out if `Actor->Brush==NULL` (0x3564a).
- `Actor->BuildCoords` (0x356f4).
- **Temp brush BSP** in the editor scratch model `[editor+0xac]`: `EmptyModel(1,1)` (0x35ab3), per-poly `bspAddNode` (loop 0x35ac1), **`bspBuild([editor+0xac],1,0,0)`** (0x35b93) + `bspRefresh` (0x35bcf). This temp tree carries the brush's **bounding/bevel planes**.
- **Filter brush polys through the WORLD `Model`** via recursive `FilterFPoly` @0x33250 (call 0x35bf8): walks `Model->Nodes`, classifies each brush poly with `SplitWithPlane`, and **at leaves adds the surviving fragment as a node in the world Model via `bspAddNode`**.

So the world tree GROWS incrementally, each solid leaf bounded by CSG fragment faces + the brush's
bevel planes — that is why the editor tree never leaks. There is no separate leaf-bounding stage to
reproduce.

## Verdict on 909↔1156 nodes / 3604↔16163 FVerts
1. `SplitPolyList` adds nodes only for splitter + coplanars (proven above) → no hidden expansion.
2. Editor extra FVerts (≈14/node vs our ≈4/node): the repartition input is the CSG-fragmented +
   `bspMergeCoplanars`-fused poly soup, whose merged faces retain every CSG boundary/T-junction
   vertex; `bspAddNode` stores `NumVertices` FVerts each → the 4.5× blowup.
3. Editor extra NODES: LOOP-3 semisolid/detail brushes filtered in incrementally AFTER the
   repartition (never re-merged) + `TestVisibility` zone/portal splits.
4. Our native = CSG(surface list) → merge → ONE lean from-scratch partition of clean convex faces →
   fewer nodes, far fewer FVerts, AND a non-watertight `outside` propagation (the leak §80 repairs).

Exact node-for-node topology parity therefore requires porting the editor's **incremental
`bspBrushCSG`** (temp-brush bevel planes + `FilterFPoly` node adds) + the semisolid second layer —
an N-2+ effort, tracked in `board/inbox/`.
