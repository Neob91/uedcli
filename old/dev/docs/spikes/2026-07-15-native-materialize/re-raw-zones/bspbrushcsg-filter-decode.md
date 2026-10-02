# RE: `bspBrushCSG` incremental CSG — the filter/leaf/temp-BSP core — 2026-07-17

**Binary:** `uned/UED22/Editor.dll` (ImageBase `0x10000000`), cross-checked against `Engine.dll`
(`0x10300000`) / `core.dll` via the IAT. All addresses are VAs. Decoded with
`harness/adis.py Editor 0x<rva> 0x<len> nostop` (annotates CALL/JMP targets from the export table and
memory operands with float/wide-string literals) + `pefile` for the IAT import descriptor and the
`.rdata` float/double constants. 🔬 = disassembled this session.

This is the evidence file for `sections/82-bspbrushcsg-port-decode.md`. It closes the Phase-0
residual "`FilterFPoly` leaf funcs + bevel-plane generation + `bspBuildFPolys` + `bspMergeCoplanars`
not yet instruction-exact" (board item `native-bsp-exact-topology-parity-byte-identical`, §2.4). It builds on
`bspbuild-splitpolylist-decode.md` (which already nailed `bspBuild`/`SplitPolyList`/`FindBestSplit`/
`bspAddNode`/`csgRebuild`); those are NOT re-derived here, only the previously-undecoded filter half.

**Load-bearing verdict: there are NO bevel planes.** The coordinator's working model ("the brush's
temp-BSP bevel planes bound the fragment") is a **misconception**. UE1 `bspBrushCSG` makes the world
watertight by (1) filtering each brush poly down the growing world tree and adding the surviving
OUTSIDE fragments as nodes whose planes are the **brush's own face planes** (`FilterEdPoly` →
`AddBrushToWorldFunc` → `bspAddNode`), and (2) filtering the existing world faces through the brush's
plain convex temp BSP to cull/split the parts now interior to the brush (`FilterWorldThroughBrush`).
No bevel/expansion planes are ever generated. The temp BSP is a straight `bspBuild` of the brush's
face polys (`FindBestSplit` picks brush faces as splitters) — a convex-cell partition, nothing more.

---

## 0. IAT / symbol resolution (settled this session) 🔬

Resolved from `Editor.dll`'s import descriptor (`pefile`):

| IAT slot | symbol |
|---|---|
| `0x100cee1c` | `UModel::FindNearestVertex(FVector const&, FVector&, float, int&)` |
| `0x100cee24` | `UModel::EmptyModel(int,int)` |
| `0x100cee28` | `FPoly::operator=(FPoly const&)` |
| `0x100cee2c` | `FPoly::RemoveColinears()` |
| `0x100cee30` | `FPoly::SplitWithPlaneFast(FPlane, FPoly*, FPoly*) const` |
| `0x100cee34` | `FPoly::SplitWithPlane(FVector const&, FVector const&, FPoly*, FPoly*, int) const` |
| `0x100cee40` | `FPoly::SplitInHalf(FPoly*)` |
| `0x100cee88` | `ABrush::BuildCoords(FModelCoords*, FModelCoords*)` |
| `0x100cee8c` | `UModel::BuildBound()` |
| `0x100cee90` | `UModel::Modify(int)` |
| `0x100cee94` | `FPoly::FPoly(FPoly const&)` (copy ctor) |
| `0x100ceea4` | `FPoly::FPoly()` (default ctor) |
| `0x100cee3c` | `FPoly::Transform(FModelCoords const&, FVector const&, FVector const&, float)` |
| `0x100ce50c` | `FPlane::operator|(FVector const&) const`  (= `X·vX+Y·vY+Z·vZ`, no −W) |
| `0x100ce514` | `FPlane::PlaneDot(FVector const&) const`  (= `X·vX+Y·vY+Z·vZ − W`) |
| `0x100ce518` | `FPlane::FPlane(FVector, FVector const&)`  (plane from base + normal) |
| `0x100ce530` | `FMemStack::PushBytes` · `0x100ce52c` `FMemMark::Pop` · `0x100ce508` `GMem` |
| `0x100ce5ec` | `FArray::Add(int,int)` |
| `0x100ce788` | `appFailAssert` (all the `check()` sites) |

Editor-local funcs (this session): `0x31770` AddBrushToWorldFunc · `0x348c0` SubtractBrushFromWorldFunc
· `0x31f50` bspFilterFPoly · `0x32bf0` FilterEdPoly · `0x33130` FilterLeaf · `0x33b80` FBspNode::IsCsg
· `0x33250` FilterWorldThroughBrush · `0x34980`/`0x31b90` the world-through-brush leaf funcs (Add/Sub)
· `0x36090` bspBuildFPolys · `0x33bb0` MakeEdPolys (node→FPoly walker) · `0x365b0` bspNodeToFPoly
(vtbl+0x1f8) · `0x36200` bspMergeCoplanars · `0x33cb0` MergeCoplanarPolys · `0x34b10` FPoly::TryToMerge
· `0x33dc0` a point-dedup/remap (MergeNearPoints-style).

**GEditor vtable (UEditorEngine, base `0x100cf5d4`):** +0x1f0 `bspAddVector`, +0x1f4 `bspAddPoint`,
+0x1f8 `bspNodeToFPoly`, +0x1fc `bspBuild`, +0x224 `bspAddNode`, +0xf4 (per-node brush-poly lookup,
sets `iBrushPoly`). (The +0x1ec…+0x264 cluster was resolved in `bspbuild-splitpolylist-decode.md`.)

---

## 1. Struct field maps recovered this session 🔬

**`FPoly` — stride `0x1d8` (472 bytes)** (from the `imul …,0x1d8` element strides and the field
accesses in `bspBrushCSG` LOOP1 + `bspAddNode` + `bspNodeToFPoly`):

| off | field | off | field |
|---|---|---|---|
| +0x00 | `Base` (FVector) | +0x1b0 | `PolyFlags` (DWORD) |
| +0x0c | `Normal` (FVector) | +0x1b4 | `Actor`/brush ptr (→ Surf+0x24) |
| +0x18 | `TextureU` (FVector) | +0x1b8 | `Texture`/ItemName (→ Surf+0) |
| +0x24 | `TextureV` (FVector) | +0x1c0 | `NumVertices` (INT) |
| +0x30 | `Vertex[]` (FVector each) | +0x1c4 | `iLink` (INT) |
| | | +0x1c8 | `iBrushPoly` (INT) |
| | | +0x1cc,+0x1ce | two surf WORDs (→ Surf+0x20/+0x22) |

**`FBspNode` — stride `0x40` (64 bytes):** +0x00 `Plane` (FPlane, 16B); +0x18 `iVertPool`; +0x1c
`iSurf`; **+0x20 `iBack` (child), +0x24 `iFront` (child)**; +0x28 `iPlane` (coplanar chain); +0x36
`NumVertices` (BYTE); **+0x37 `NodeFlags` (BYTE)**. Front/back proven independently by `FilterEdPoly`
(SP_Front descends +0x24, SP_Back +0x20) and `FilterWorldThroughBrush` (front-flag recurses +0x24,
back-flag +0x20).

**`FBspSurf` — stride `0x40`:** +0x00 `Texture`; +0x04 `PolyFlags` (masked `& 0x3cffffff`); +0x08
`pBase` (point idx); +0x0c `vNormal` (vector idx); +0x10 `vTextureU`; +0x14 `vTextureV`; +0x18
`iLightMap` (init −1); +0x1c `iBrushPoly`; +0x20/+0x22 two WORDs; +0x24 `Actor`/brush. (From
`bspAddNode` new-surf emission `0x10034eef`–`0x10034fc0` and `bspNodeToFPoly` `0x100365f0`+.)

**`UModel` fields used:** +0x44 `Bound`(FBoxSphereBounds/param to FilterWorldThroughBrush); +0x54
`Polys` (UPolys*); +0x58 `Nodes` data; +0x5c `Nodes.Num`; +0x68 `Verts` data; +0x6c `Verts.Num`;
+0x78 `Vectors` data; +0x88 `Points` data; +0x8c `Points.Num`; +0x98 `Surfs` data; +0x9c `Surfs.Num`;
+0xf0 `RootOutside`. `UPolys`: +0x28 `Element` data, +0x2c `Element.Num`. `UEditorEngine`: +0xac
`TempModel` (the scratch brush model); +0xb0 a default Texture; +0xb4 a setup vtbl slot.

**`FBspNode::IsCsg` (`0x33b80`, `ret 4`):** 🔬
```
IsCsg(node, extraMask) = node.NumVertices(+0x36) > 0  &&  !(node.NodeFlags(+0x37) & (extraMask | 0x21))
```
`0x21 = NF_NotCsg(0x01) | NF_IsNew(0x20)`. Called with `extraMask=0` from `FilterEdPoly`, so a node
counts as CSG-solid iff it has verts and is neither NotCsg nor freshly-added-this-brush.

---

## 2. `bspBrushCSG` @0x355e0 — full control flow 🔬

`bspBrushCSG(this=GEditor, Actor[+8], Model[+0xc], DWORD PolyFlags[+0x10], ECsgOper CsgOper[+0x14],
UBOOL bBuildBounds[+0x18], UBOOL bMergePolys[+0x1c])` (`ret 0x18`).

```c
Brush = Actor->Brush;   // ABrush+0x138
if (Brush == NULL) return;                                   // 0x3564a early-out
NotPolyFlags = (CsgOper == CSG_Add/*1*/) ? 0 : 0x28;         // PF_NotSolid|PF_Semisolid; 0x3567e
Model->Modify(0);                                            // 0x3569a
if (CsgOper == CSG_Subtract/*2*/) Model->[+0x100] = 0;       // reset a zone/count field
Actor->vtbl[+0x1c](...);                                     // Actor->Modify-ish
Brush->Modify(0);                                            // 0x356c6
GEditor->TempModel->EmptyModel(1,1);                         // 0x356d0
Orientation = Actor->BuildCoords(&Coords[ebp-0x480], &Uncoords[ebp-0x4e0]);   // 0x356ee
NumBrushPolys = Brush->Polys->Element.Num;                  // 0x35700  (>200 -> BeginSlowTask)

// ---- LOOP 1 (0x35791): transform brush polys into TempModel->Polys ----
for (i=0; i < Brush->Polys->Element.Num; i++) {
    // clamp source iLink to [0,Num) else -1  (0x357d7..0x35817)
    FPoly Ed = Brush->Polys->Element[i];                    // copy ctor 0x35817
    Ed.PolyFlags = (Ed.PolyFlags | PolyFlags) & ~NotPolyFlags;   // 0x3583e
    Ed.Actor     = Actor;                                   // Ed+0x1b4 = Actor
    Ed.iBrushPoly = i;                                      // Ed+0x1c8 = i
    if (Ed.iLink == -1) Ed.iLink = i;                       // 0x35857
    Ed.Transform(Coords, Actor->PrePivot/*+0x140*/, Actor->Location/*+0xd0*/, Orientation); // 0x35892
    // base-snap onto plane:  Base += Normal * (Normal · (Vertex[0] - Base))   if |dot|>1e-4
    T = Ed.Vertex[0] - Ed.Base;  d = Ed.Normal · T;                            // 0x35898..0x35911
    if (fabs(d) > 0.0001/*[0x100dcb18] dbl*/) Ed.Base += Ed.Normal * d;         // 0x35950 FVector::+=
    TempModel->Polys.Add(Ed);                              // 0x3596a (PushBytes 0x1d8 + copy)
}

if (CsgOper==3 || CsgOper==4) goto INTERSECT;              // 0x359cd  (Intersect/Deintersect)

// ---- LOOP 2 (0x359e5): filter each TempModel poly through the WORLD, growing nodes ----
for (i=0; i < TempModel->Polys.Num; i++) {
    FPoly Ed2 = TempModel->Polys[i];                       // 0x35a17 copy
    Ed2.PolyFlags &= 0x7fffffff;                           // clear bit31  (0x35a23)
    if (Ed2.iLink == i) TempModel->Polys[i].iLink = Ed2.iLink = Model->Surfs.Num;  // surf-share seed
    else                Ed2.iLink = TempModel->Polys[Ed2.iLink].iLink;             // share
    FILTER_FUNC f = (CsgOper==CSG_Add) ? AddBrushToWorldFunc/*0x31770*/
                                       : SubtractBrushFromWorldFunc/*0x348c0*/;
    bspFilterFPoly(f, Model, &Ed2);                        // 0x35a99 -> 0x31f50
}

// ---- (0x35b3d) build brush temp BSP + filter WORLD through it ----
if (Model->Nodes.Num != 0 && !(PolyFlags & 0x28)) {
    GEditor->bspBuild(TempModel, 0, 0, 1, 0);              // 0x35b93 vtbl+0x1fc; args (Opt=0,Balance=0,PortalBias=1,RebuildSimplePolys=0)
    TempModel->BuildBound();  TempModel->BuildBound();     // 0x35bd5, 0x35bdd (bounds for the filter)
    FilterWorldThroughBrush(Model, TempModel, CsgOper, /*iNode*/0, &TempModel->Bound); // 0x35bf8 -> 0x33250
}
INTERSECT: /* CsgOper 3/4 dedup back into brush — not used by MAP REBUILD */
// (tail, not shown: bspCleanup / node-flag reset; bBuildBounds path)
```

Key: the temp brush BSP is a plain `SplitPolyList` partition of the brush's own faces — **no
bevel/expansion**. The exact call pushes (0x35b83–0x35b8b) are `push 0; push 1; push 0; push 0;
push TempModel`, i.e. reversed args `(TempModel, 0, 0, 1, 0)`. **`bspBuild` is a FIVE-arg function**
`bspBuild(Model, EBspOptimization Opt, INT Balance, INT PortalBias, INT RebuildSimplePolys)` (`ret
0x14`) — the prior `bspbuild-splitpolylist-decode.md` listed only four params (it omitted
`PortalBias`). So the temp-brush build is `Opt=0(LAME), Balance=0, PortalBias=1, RebuildSimplePolys=0`
(NOT `RebuildSimplePolys=1` — the `1` sits in the PortalBias slot). `bspBuild`/`SplitPolyList`
internals are otherwise as decoded in `bspbuild-splitpolylist-decode.md`.

---

## 3. `bspFilterFPoly` @0x31f50 + `FilterEdPoly` @0x32bf0 (the recursion) 🔬

**`bspFilterFPoly(FILTER_FUNC Func[+8], UModel* Model[+0xc], FPoly* EdPoly[+0x10])`:**
```c
if (Model->Nodes.Num == 0)                                             // 0x31f92
    Func(Model, INDEX_NONE/*0? -> passes 0*/, EdPoly, (Model->RootOutside==0), F_ROOT/*3*/); // empty tree
else {
    FCoplanarInfo start = { iOriginalNode=-1, ... };                   // [ebp-0x2c]=-1
    FilterEdPoly(Func, Model, 0, EdPoly, start, Model->RootOutside);   // 0x31fcc -> 0x32bf0
}
```

**`FilterEdPoly(Func[+8], Model[+0xc], INT iNode[+0x10], FPoly* EdPoly[+0x14], FCoplanarInfo
Coplanar[+0x18..0x28], INT Outside[+0x2c])`** — `FilterLoop:`
```c
if (EdPoly->NumVertices >= 14/*0xe*/) {                    // 0x32c56
    FPoly Temp; EdPoly->SplitInHalf(&Temp);                // 0x32c78
    FilterEdPoly(Func, Model, iNode, &Temp, Coplanar, Outside);   // recurse the half
}
Node  = &Model->Nodes[iNode];
Plane = { Model->Points[Surf.pBase], Model->Vectors[Surf.vNormal] };  // 0x32cd9..0x32d09
switch (EdPoly->SplitWithPlane(Plane.Base, Plane.Normal, &Front[ebp-0x1ec], &Back[ebp-0x3c4], 0)) {
  case SP_Front/*1*/:
     Outside = Outside || Node.IsCsg(0);                   // 0x32db7 block
     if (Node.iFront/*+0x24*/ == -1) FilterLeaf(Func,Model,iNode,EdPoly,Coplanar,Outside,NODE_Front);
     else { iNode = Node.iFront; goto FilterLoop; }
  case SP_Back/*2*/:
     Outside = Outside && !Node.IsCsg(0);                  // 0x32d38 block
     if (Node.iBack/*+0x20*/ == -1) FilterLeaf(...,Outside,NODE_Back);
     else { iNode = Node.iBack; goto FilterLoop; }
  case SP_Coplanar/*0*/:  goto COPLANAR;                   // 0x32d91
  case SP_Split/*3*/:                                      // 0x32f56
     // recurse BOTH children with the split halves:
     if (Node.iFront==-1) FilterLeaf(Func,Model,iNode,&Front,Coplanar, Outside||IsCsg, NODE_Front);
     else FilterEdPoly(Func,Model,Node.iFront,&Front,Coplanar, Outside||IsCsg);
     if (Node.iBack ==-1) FilterLeaf(Func,Model,iNode,&Back ,Coplanar, Outside&&!IsCsg, NODE_Back);
     else FilterEdPoly(Func,Model,Node.iBack ,&Back ,Coplanar, Outside&&!IsCsg);
}
```
Reconstructed from the child-slot reads (`+0x20`/`+0x24`), the `call 0x33b80`(IsCsg) sites, the two
`FilterLeaf`(0x33130) tail calls and the two self-recursions (0x33009/0x33063). `Front`/`Back` local
FPolys live at `ebp-0x1ec` / `ebp-0x3c4`.

**COPLANAR (0x32d91) — the coplanar cascade.** On the FIRST coplanar hit (`Coplanar.iOriginalNode ==
-1`): record `iOriginalNode=iNode`, `iBackNode=-1`, `bProcessingBack=0`, `bFrontOutside=Outside`;
then `Dot = FPlane(EdPoly.Base,EdPoly.Normal) | Node.Normal` (`FPlane::operator|`, `0x32e32`) — if
`Dot >= 0` the poly faces the node's front, else back, choosing which child pair to descend and
recording `iBackNode` for the later back pass. A SECOND coplanar hit while already in a coplanar
cascade triggers a `check()` (`0x32d97`, appFailAssert) and is treated as front. (Full detail is the
one **partial** spot — see §7; the front-pass/back-pass completion is driven by `FilterLeaf`.)

**`FilterLeaf` @0x33130** — the leaf/coplanar dispatcher:
```c
if (Coplanar.iOriginalNode == -1)                     // ordinary leaf
    Func(Model, iNode, EdPoly, /*EPolyNodeFilter*/(Outside==0)?F_INSIDE:F_OUTSIDE, ENodePlace);
else if (!Coplanar.bProcessingBack) {                 // finished FRONT of a coplanar node
    if (Coplanar.iBackNode == -1)                     // no back subtree -> emit now
        Func(Model, ..., filter, NODE_Plane);
    else { Coplanar.bProcessingBack=1;                // descend the recorded back subtree
           FilterEdPoly(Func, Model, Coplanar.iBackNode, EdPoly, Coplanar, Coplanar.bFrontOutside); }
} else {                                              // finished BACK -> classify cospatial
    filter = (frontOutside, backOutside) -> { (0,0):F_COPLANAR_INSIDE/*3*/, (0,1):F_COSPATIAL_FACING_IN/*4*/,
              (1,0):F_COSPATIAL_FACING_OUT/*5*/, (1,1):F_COPLANAR_OUTSIDE/*2*/ }   // 0x331cb..0x331ed
    Func(Model, iNode, EdPoly, filter, NODE_Plane);
}
```
So `EPolyNodeFilter` = { F_OUTSIDE=0, F_INSIDE=1, F_COPLANAR_OUTSIDE=2, F_COPLANAR_INSIDE=3,
F_COSPATIAL_FACING_IN=4, F_COSPATIAL_FACING_OUT=5 }.

---

## 4. Leaf callbacks — where nodes are ADDED 🔬

**`AddBrushToWorldFunc` @0x31770** (CSG_Add): 🔬
```c
void AddBrushToWorldFunc(UModel* Model, INT iNode, FPoly* EdPoly, EPolyNodeFilter F, ENodePlace P) {
  switch (F) {
    case F_OUTSIDE/*0*/:
    case F_COPLANAR_OUTSIDE/*2*/:
        GEditor->bspAddNode(Model, iNode, P, NF_IsNew/*0x20*/, EdPoly);   break;   // vtbl+0x224
    case F_COSPATIAL_FACING_OUT/*5*/:
        if (!(EdPoly->PolyFlags & PF_Semisolid/*0x20*/))
            GEditor->bspAddNode(Model, iNode, P, NF_IsNew, EdPoly);      break;
    default: /* F_INSIDE, F_COPLANAR_INSIDE, F_COSPATIAL_FACING_IN: drop */ break;
  }
}
```
(Instruction: `0x317a2` filter switch on `{0,2,5}`, `0x317b7` the `&0x20` semisolid guard, `0x317d9`
`call [eax+0x224]` = bspAddNode with the literal `0x20` NodeFlags pushed.)

**`SubtractBrushFromWorldFunc` @0x348c0** — the mirror. Its switch is `sub eax,1; je / sub eax,2; jne`
⇒ **adds on filter values {1 (F_INSIDE), 3 (F_COPLANAR_INSIDE)}** (reviewer-confirmed this session);
the `F_COSPATIAL_FACING_IN=4` analogue (the semisolid-gated counterpart of Add's `5`) is inferred from
symmetry but not line-proved — confirm on a subtract fixture (the castle is subtract-heavy, so the
differential WILL exercise it). Same `bspAddNode(…, NF_IsNew, …)` shape as `0x31770`.

Thus **each surviving brush-poly fragment is added as a node carrying the BRUSH's own face plane**
(`bspAddNode` builds/shares the surf from `EdPoly.Base/Normal` via `bspAddPoint`/`bspAddVector`). The
fragment was clipped to the leaf cell by every ancestor plane on the way down (the `SplitWithPlane`
Front/Back locals), so it exactly tiles that cell face — this is the watertightness, with **no bevel
planes**.

`bspAddNode` @0x34e80 new-surf emission (confirms provenance): `Surf.pBase = bspAddPoint(EdPoly.Base)`
(vtbl+0x1f4), `Surf.vNormal = bspAddVector(EdPoly.Normal)` (vtbl+0x1f0), `vTextureU/V =
bspAddVector(EdPoly.TextureU/V)`, `Surf.PolyFlags = EdPoly.PolyFlags & 0x3cffffff`, `Surf.Texture =
EdPoly+0x1b8`, `Surf.iBrushPoly = EdPoly.iBrushPoly`, `Surf.Actor = EdPoly.Actor`. Allocated only when
`EdPoly.iLink == Surfs.Num`; else the existing surf at `iLink` is shared. (`0x34eef`–`0x34fc0`.)

---

## 5. `FilterWorldThroughBrush` @0x33250 — cut the world with the brush 🔬

`FilterWorldThroughBrush(UModel* Model[+8], UModel* Brush=TempModel[+0xc], ECsgOper CsgOper[+0x10],
INT iNode[+0x14], FPlane* CoplanarRef[+0x18])`. Recurses the **world** tree:
```c
if (iNode == -1) return;
Node = &Model->Nodes[iNode];
if (Node.NodeFlags & NF_IsNew/*0x20*/) return;             // 0x332d4 skip the brush's own new nodes
// decide which children to descend, by the node plane vs the CoplanarRef plane (0x33311..0x33355)
DoFront = DoBack = 1;
if (CoplanarRef) { d = CoplanarRef->PlaneDot? ; DoFront = (d >= -Nz); DoBack = (Nz >= d); }
if (DoFront && DoBack) {                                    // node straddles -> filter its face
    FPoly Ed; INT n = GEditor->bspNodeToFPoly(Model, iNode, &Ed);   // vtbl+0x1f8, 0x33398
    if (n > 0) switch (CsgOper) {
      case CSG_Add/*1*/: case CSG_Subtract/*2*/:
          // filter the WORLD face Ed through the BRUSH temp BSP; leaf marks/splits the world node
          GNode/*0x101491bc*/=iNode; GModel/*0x101491c8*/=Model; GDiscarded/*0x101491b8*/=0;  // 0x33433
          GSavedNodeNum/*0x101491c4*/=Model->Nodes.Num;                                       // 0x33449
          GLastCoplanar/*0x101491c0*/= last node on Node's iPlane chain (walk +0x28 until -1); // 0x33451
          bspFilterFPoly( (CsgOper==CSG_Add) ? 0x31b90 : 0x34980, Brush, &Ed );  // 0x33483  (SEE NOTE)
          if (GDiscarded == 0)   Nodes.Remove(GSavedNodeNum, Nodes.Num-GSavedNodeNum);  // 0x334b7 -> 0x34050
          else if (Node[GNode].NumVertices != 0) { NodeCleanup(GNode); Node[GNode].NumVertices=0; } // 0x334be
          break;
      case CSG_Intersect/*3*/:    bspFilterFPoly(0x33ab0, Model, &Ed); break;
      case CSG_Deintersect/*4*/:  bspFilterFPoly(0x32460, Model, &Ed); break;
    }
}
if (DoFront) FilterWorldThroughBrush(Model, Brush, CsgOper, Node.iFront/*+0x24*/, CoplanarRef);
if (DoBack ) FilterWorldThroughBrush(Model, Brush, CsgOper, Node.iBack /*+0x20*/, CoplanarRef);
iNode = Node.iPlane; goto top;   // also walk the coplanar chain
```
`bspNodeToFPoly` (`0x365b0`, vtbl+0x1f8) reconstructs the world node's polygon: `Base =
Points[Surf.pBase]`, `Normal = Vectors[Surf.vNormal]`, `TextureU/V = Vectors[Surf.vTextureU/V]`,
`PolyFlags = Surf.PolyFlags & 0x3cffffff`, `Vertex[k] = Points[Verts[iVertPool+k].pVertex]`, then
`FPoly::RemoveColinears` (`0x100cee2c`). It also sets `Ed.iLink = Node.iSurf` — the reconstructed
world face carries the ORIGINAL node's surf index. **Normal/textures preserved from the surf, verts
from the FVert pool** — confirms the Phase-0 "PRESERVE authored normal" finding holds on the
reconstruction path too.

> **CORRECTION (leaf-func selection).** The `cmove` at `0x33472`–`0x3347f` is
> `eax=0x34980; cmp CsgOper,1; ecx=0x31b90; cmove eax,ecx` → for **Add (CsgOper==1)** the func is
> **`0x31b90`**, for **Subtract** it is **`0x34980`**. An earlier draft of this file had them
> swapped; the mapping above is the corrected one. (It only matters for a world face landing
> `F_COSPATIAL_FACING_IN=4` — see the two jump tables below.)

### 5.1 — the world-through-brush leaf funcs = SPLIT-AND-RE-ADD (THE CRUX) 🔬

Both leaf funcs are a jump-table `switch(EPolyNodeFilter F)` on `[ebp+0x14]` (`cmp eax,5; ja default;
jmp [eax*4+table]`). They have exactly two live branches — **RE-ADD** and **DISCARD** — plus a
no-op default. The jump tables (read from `.rdata`):

| F (filter) | 0x31b90 (**Add**) | 0x34980 (**Subtract**) |
|---|---|---|
| 0 F_OUTSIDE            | RE-ADD  | RE-ADD  |
| 1 F_INSIDE            | DISCARD | DISCARD |
| 2 F_COPLANAR_OUTSIDE  | RE-ADD  | RE-ADD  |
| 3 F_COPLANAR_INSIDE   | DISCARD | DISCARD |
| 4 F_COSPATIAL_FACING_IN  | DISCARD | **RE-ADD** |
| 5 F_COSPATIAL_FACING_OUT | DISCARD | DISCARD |

**RE-ADD branch** (`0x31bd1` Add / `0x349c1` Sub) — re-emit the outside-of-brush fragment as a world node:
```c
if (EdPoly->PolyFlags >= 0) break;   // 0x349c4  jge: bit31 CLEAR -> not a cut fragment -> do nothing
GEditor->bspAddNode(GModel, GLastCoplanar/*0x101491c0*/, NODE_Plane/*2*/, NF_IsNew/*0x20*/, EdPoly); // 0x349e6
```
The gate `PolyFlags < 0` tests **bit 31 (`0x80000000`)**, which `FPoly::SplitWithPlane` sets on **both
output polys, and only on a genuine split** (`Engine!0x1518b0`: the SP_Split epilogue `0x10151ad9` and
`0x10151b09` do `PolyFlags |= 0x80000000`; the SP_Front/SP_Back/SP_Coplanar early returns do not).
So a fragment is re-added **iff it was actually cut off the original face** by a brush plane during the
descent. The new node is placed `NODE_Plane` on `GLastCoplanar` (the tail of the original node's iPlane
chain) and — because `EdPoly.iLink == Node.iSurf` from `bspNodeToFPoly` — `bspAddNode` **shares the
original world surf** (no new surf), pooling fresh FVerts for the fragment. This is the mechanism that
turns one straddling world face into *N* re-added outside-fragment nodes.

**DISCARD branch** (`0x31bfe` Add / `0x349ee` Sub) — a fragment landed inside the brush:
```c
GDiscarded/*0x101491b8*/ += 1;                                 // record that a real cut happened
if (Node[GNode].NumVertices != 0) { NodeCleanup(GNode); Node[GNode].NumVertices = 0; } // 0x349ee..0x34a2b
```

**Post-filter reconciliation** (`FilterWorldThroughBrush`, `0x3348b`):
- **`GDiscarded != 0`** (≥1 fragment was interior → the face genuinely enters the brush): keep the
  re-added outside fragments; `NodeCleanup(GNode)` (`0x34020` = a debug/notify hook, no array edit) and
  set `Node[GNode].NumVertices = 0` → **the original whole face is deleted** (a zero-vert node is a
  dead pass-through, dropped by the later repartition). Net: one straddling face → its outside pieces
  as new nodes; the original removed.
- **`GDiscarded == 0`** (no fragment was interior → the face only grazes the brush, entirely outside):
  the fragments that were re-added are spurious duplicates of the intact original → **remove them**:
  `Nodes.Remove(GSavedNodeNum, Nodes.Num - GSavedNodeNum)` (`0x34050`, `FArray::Remove`), keeping the
  original node whole. This is why a floor passing *below* a brush (split by the brush's side planes
  but wholly in front of its bottom plane) is not fragmented — all pieces are outside, none interior,
  so the splits are rolled back.

`NodeCleanup` (`0x34020`) and the relink helper (`0x34050`) both first call a `GObj`-notify vtbl slot
(`[0x100ce888]→[+8]`); `0x34050` then calls `FArray::Remove(index=GSavedNodeNum, count, stride 0x40)`
(`0x100ce7f4`) with range-check asserts. `0x34020` performs **no** array removal — it only marks the
node dead via the caller's `NumVertices=0`.

### 5.2 — worked shape of the FVert fattening 🔬

One straddling world face `Ed` (with its original *k* verts) is filtered through the brush's convex
temp BSP. `FilterEdPoly` splits `Ed` at each brush face plane it straddles; every resulting fragment
that lands in an **outside** brush leaf and carries bit31 (was cut) is re-added as its own node with
its own pooled FVerts, all sharing `Node.iSurf`. A convex face clipped against a convex hull yields up
to (hull-faces) outside convex pieces, so one ~4-vert world face can become several 4–6-vert nodes.
Summed over every straddling world face across every structural brush, this is the dominant source of
the editor's ~14-FVert/node pool (native `16163` vs the clip-to-one-fragment `4914`), and — because
interior faces are *deleted* and straddlers are *fully* re-partitioned rather than clipped-to-largest —
the source of the watertight solidity the clip approach loses.

---

## 6. `bspBuildFPolys` / `bspMergeCoplanars` / `FindBestSplit` 🔬

**`bspBuildFPolys` @0x36090** `(Model[+8], UBOOL bMergePolys[+0xc], EBspOptimization Opt[+0x10])`:
```c
Model->Polys->Element.Empty(0);                          // 0x360cd
if (Model->Nodes.Num > 0) MakeEdPolys(Model, Opt);       // 0x360dc -> 0x33bb0 : walk nodes, bspNodeToFPoly each, Polys.Add
if (!bMergePolys) for (i=0;i<Polys.Num;i++) Polys[i].iLink = i;   // reset link identity
```
`MakeEdPolys` (`0x33bb0`) recursively reconstructs **every node** into an FPoly via the same
`bspNodeToFPoly` recovery and appends to `Model->Polys` — so the repartition input retains every
CSG-fragmentation vertex (this is what feeds the ~14 FVerts/node fatness after re-split).

**`bspMergeCoplanars` @0x36200** `(Model[+8], UBOOL RemapSurfs[+0xc], UBOOL MergeDisparateTextures[+0x10])`:
```c
for each poly P: P.PolyFlags &= ~0x40000000;             // clear the transient "grouped" marker
PolyList = GMem scratch int[Polys.Num];
for (i=0; i<Polys.Num; i++) {
    Pi=&Polys[i]; if (Pi->NumVertices<=0 || (Pi->PolyFlags & 0x40000000)) continue;
    group=[i]; Pi->PolyFlags |= 0x40000000;
    for (j=i+1; j<Polys.Num; j++) {
        Pj=&Polys[j];
        if (Pj->iLink != Pi->iLink) continue;                              // same surf only
        d = Pi->Normal · (Pj->Base - Pi->Base);
        if (!(-0.001 < d && d < 0.001)) continue;                          // coplanar offset  [0x100dcb48/20]
        if (!(Pi->Normal · Pj->Normal > 0.9999)) continue;                 // same-facing normal [0x100dcb30]
        if (!MergeDisparateTextures) {
            if (!VectorsNear(Pi->TextureU,Pj->TextureU, 4e-4)) continue;   // 0x32b30, thresh 0x39d1b717
            if (!VectorsNear(Pi->TextureV,Pj->TextureV, 4e-4)) continue;
        }
        Pj->PolyFlags |= 0x40000000; group.push(j);
    }
    if (group.size > 1) MergeCoplanarPolys(Model, group, group.size);      // 0x33cb0
}
compact Polys (drop NumVertices==0);  if (RemapSurfs) remap iLinks;        // 0x364a0..0x36529
```
**`MergeCoplanarPolys` @0x33cb0** = iterate to fixpoint: `do { merged=false; for i,j in group:
if FPoly::TryToMerge(&Polys[gi],&Polys[gj]) merged=true; } while(merged);` — `TryToMerge` (`0x34b10`)
fuses two coplanar polys that share an edge into one, dropping the shared edge + colinear verts.
(`0x33dc0`, called around here, is a separate MergeNearPoints-style point dedup: pairwise squared
distance vs a threshold², builds a point remap, rewrites `Verts[].pVertex`/`Surfs[].pBase`/node
verts, and collapses consecutive duplicate FVerts `0x33f5a`.)

**`FindBestSplit` @0x335d0 — score op-order EXACT** (re-verified this session; matches
`bspbuild-splitpolylist-decode.md`): 🔬
```
Balance    = BalancePacked & 0xff;         PortalBias = (BalancePacked>>8)&0xff;   // /100.0 via divss
Inc = Opt==OPTIMAL(2)?1 : Opt==GOOD(1)?NumPolys/10 : NumPolys/4;  Inc=max(Inc,1);
if (NumPolys==1) return PolyList[0];
for each candidate (stride Inc), skip if (flags&0x28 && !PF_Portal(0x4000000) && !bAllNonStructural):
    Splits=Front=Back=0;
    for each other (stride Inc, !=candidate):
        r = candidate->SplitWithPlaneFast(other):
          SP_Front->Front++;  SP_Back->Back++;  SP_Coplanar->(coplanar++);
          SP_Split-> Splits += (other->PolyFlags & PF_Portal) ? 0x10 : 1;
    Score2 = (100 - Balance) * (float)Splits;                 // mulss
    Score  = (float)abs(Front-Back) * (float)Balance + Score2;// mulss then addss  (Score2 added last)
    if (candidate->PolyFlags & PF_Portal) Score -= Score2 * (PortalBias/100.0);   // mulss, subss
    if (Score < bestScore || best==NULL) { best=candidate; bestScore=Score; }     // STRICT-less; first ties keep earlier
return best;   // NULL -> appFailAssert
```
All FP is SSE-scalar (`cvtdq2ps`/`mulss`/`addss`/`subss`/`divss`/`comiss`); no x87.

> **⚠️ PARAM CORRECTION (2026-07-17):** "`Balance=50, PortalBias=70, Opt=OPTIMAL`" is **WRONG** for the
> REPARTITION. The actual call chain (`bspRepartition 0x49fc0 → bspBuild 0x35ef0 → SplitPolyList
> 0x34530`) pushes `BalancePacked=0xc, Opt=1` ⇒ **Balance=12, PortalBias=0, Opt=GOOD(1)** (stride
> `NumPolys/10`) ⇒ `Score = 88·Splits + 12·|F−B|`, no portal discount. VA-cited proof + empirical
> confirmation: `findbestsplit-params-decode.md`. This is the first-divergence root cause.

---

## 7. `SubtractBrushFromWorldFunc` @0x348c0 — line-transcribed (CORRECTS the "exact mirror") 🔬

The LOOP-2 subtract leaf func (brush poly filtered **down the world tree**) is **not** a symmetric
mirror of `AddBrushToWorldFunc`:
```c
void SubtractBrushFromWorldFunc(Model[+8], iNode[+0xc], EdPoly[+0x10], F[+0x14], place[+0x18]) {
  switch (F) {                                   // 0x348f2: sub eax,1;je / sub eax,2;jne skip
    case F_INSIDE/*1*/: case F_COPLANAR_INSIDE/*3*/:
      EdPoly->Reverse();                          // 0x34904  [0x100cee44] FPoly::Reverse()
      GEditor->bspAddNode(Model, iNode, place, NF_IsNew/*0x20*/, EdPoly);   // 0x3491e vtbl+0x224
      EdPoly->Reverse();                          // 0x34926  reverse back
      break;
    default: break;                               // 0/2/4/5 -> nothing
  }
}
```
Two differences from Add (`0x31770`, which adds on `{0,2,5&!PF_Semisolid}` with **no** Reverse):
1. **Subtract adds ONLY on `{F_INSIDE=1, F_COPLANAR_INSIDE=3}`** — there is **no `F_COSPATIAL_FACING_IN=4`
   case** and **no semisolid gate**. (Add's `5` case is semisolid-gated; subtract has no counterpart.)
2. **Subtract stores the face `Reverse()`d** — the carved wall's normal is flipped to face into the new
   void — then reverses it back so the temp poly is unchanged for the next filter step.

Because `Reverse` wraps only `bspAddNode`, the **descent (`FilterEdPoly`/`SplitWithPlane` front/back
classification) uses the brush face's ORIGINAL outward normal**; only the *stored* node is inward.
`ABrush::BuildCoords` (`Engine!0x111390`) returns Orientation = sign of the transform determinant
(`+1` for identity scale, independent of Add/Subtract), so LOOP-1 `FPoly::Transform` does **not** flip
an unscaled subtract brush — the single flip is exclusively this leaf-func `Reverse`.

## 7b. Coplanar cascade `FilterEdPoly` @0x32d91 — child-first order DECODED 🔬

`FCoplanarInfo` is the 5-field UE1 struct on `FilterEdPoly`'s frame (offsets are the args pushed to
`FilterLeaf`): `{+0x18 iOriginalNode, +0x1c iBackNode, +0x20 FrontLeafOutside, +0x24 BackNodeOutside,
+0x28 ProcessingBack}`. First coplanar hit (`iOriginalNode==-1`, `0x32df1`):
```c
// init (0x32df1): FrontLeafOutside=Outside; and a LOCAL FrontDescentOutside(temp -0x5bc)=Outside;
//                 working-Outside(-0x5a0)=Outside;  BackNodeOutside(+0x24) NOT set here.
iOriginalNode=iNode; iBackNode=-1; ProcessingBack=0; FrontLeafOutside=Outside; FrontDescentOutside=Outside;
Dot = Node.Normal · EdPoly.Normal;                          // FPlane::operator| 0x32e32; comiss/jb 0x32e57
if (Dot >= 0) { first=Node.iFront/*+0x24*/; other=Node.iBack/*+0x20*/;    // faces node FRONT
                if (IsCsg) { FrontLeafOutside(+0x20)=0; FrontDescentOutside=1; workingOutside=0; } }  // 0x32e86
else          { first=Node.iBack /*+0x20*/; other=Node.iFront/*+0x24*/;    // faces node BACK
                if (IsCsg) { FrontLeafOutside(+0x20)=1; FrontDescentOutside=0; workingOutside=1; } }  // 0x32efb
//   i.e. FrontDescentOutside = facing-side CSG-adjust (front->Out||csg, back->Out&&!csg);
//        FrontLeafOutside(+0x20) = OTHER-side CSG-adjust (the reverse).
if (first != -1) { iBackNode=other; ProcessingBack=0; iNode=first; Outside=FrontDescentOutside; goto FilterLoop; } // 0x32f33
else if (other != -1) { ProcessingBack=1; iBackNode=other; BackNodeOutside(+0x24)=FrontDescentOutside;
                        iNode=other; Outside=workingOutside(=other seed); goto FilterLoop; }                       // 0x32f15
else { ProcessingBack=1; BackNodeOutside(+0x24)=FrontDescentOutside; FilterLeaf(..., LeafOutside=FrontLeafOutside, NODE_Plane); } // 0x32ec3
```
(Earlier draft of these two branch lines mis-assigned the fields; the above matches the byte-level
disasm — `+0x20` gets the *other*-side seed, and `BackNodeOutside +0x24` is set to `FrontDescentOutside`
only on the facing-child-`==-1` paths, else it is overwritten by the facing-pass leaf in `FilterLeaf`.)
`FilterLeaf 0x33184` (facing-pass complete, first!=-1): `BackNodeOutside(+0x24)=LeafOutside`; then descend
`iBackNode` with `Outside=FrontLeafOutside(+0x20)`.
**Verdict (definitive):** the facing test is `Dot = Node.Normal · EdPoly.Normal`; **`Dot >= 0` descends
`iFront` first** (front pass), recording `iBack` as the back subtree; **`Dot < 0` descends `iBack`
first**, recording `iFront`. `FilterLeaf` (`0x33130`) then runs the **back pass** on `iBackNode` with
`Outside = FrontLeafOutside(+0x20)`, and on completion classifies cospatial from
`(frontOutside=BackNodeOutside +0x24, backOutside=leafOutside +0x2c)`:
`(in,in)→3`, `(out,in)→5`, `(in,out)→4`, `(out,out)→2` (`0x331cb`–`0x331ed`) — matching the native table.

**PINNED & PORTED (2026-07-17).** The IsCsg Outside-seeding is now fully instruction-decoded (the
disasm below) and fixed in `bspcsg.rs`. The two `FCoplanarInfo` fields have COUNTER-INTUITIVE roles:
**`+0x20 FrontLeafOutside` is the SEED for the *other* (non-facing) side's descent** (not a leaf
result), and **`+0x24 BackNodeOutside` is the classify `frontOutside`** (overwritten by the facing-pass
leaf result at `FilterLeaf 0x33184`, or pre-seeded to the facing side's own outside when the facing
child is `-1`). Each side's descent gets the SAME CSG adjust as the ordinary SP_Front/SP_Back branches:

```
Dot>=0 (0x32e59, faces front): facing=iFront seed=(outside||csg);  other=iBack  seed=(outside&&!csg)
                               FrontLeafOutside(+0x20)=other seed=(outside&&!csg);  FrontDescentOutside=(outside||csg)
Dot<0  (0x32ece, faces back) : facing=iBack  seed=(outside&&!csg); other=iFront seed=(outside||csg)
                               FrontLeafOutside(+0x20)=other seed=(outside||csg);   FrontDescentOutside=(outside&&!csg)
```
Facing side descends first with `FrontDescentOutside`; its leaf result overwrites `BackNodeOutside(+0x24)`
= `frontOutside`. Other side then descends with `FrontLeafOutside(+0x20)` = `backOutside`. Native's two
bugs (seeding the facing descent with raw `outside`, and seeding the other-side descent with the facing
leaf result rather than the independent `+0x20` seed) are both fixed; the `Coplanar` struct now carries
`back_seed`(=+0x20) + `front_outside`(=+0x24). **Live-verified** N=2 castle: WallBack floor `(0,0,-1,0)`
coplanar with the IsCsg room-floor node → `Dot<0`, facing=back, `facing_out=outside&&!csg=FALSE` →
`frontOutside=in`, other=front `outside||csg=TRUE` → `backOutside=out` ⇒ `(in,out)→FACING_IN(4)`,
dropped by Add (pre-fix native got `(out,out)→COPLANAR_OUTSIDE(2)`, kept → surplus node). N=2 15→14
nodes = editor; full-castle shared-planes 867→971, node count 1028→1158 (editor 1156). Full disasm
transcription of `0x32d91`/`0x33130` below.

## 7c. Lower-order items (unchanged) 📖

- **`FPoly::TryToMerge` @0x34b10** (pairwise edge-fuse inside `MergeCoplanarPolys`) — shared-edge test +
  vertex-splice is the standard `Engine.dll` FPoly method; portable from public UE1 source shape.
- **`bspNodeToFPoly` vtbl+0xf4 sub-call** (sets `iBrushPoly`) — brush-poly master lookup; affects only
  the `iBrushPoly` surf field, not topology.
