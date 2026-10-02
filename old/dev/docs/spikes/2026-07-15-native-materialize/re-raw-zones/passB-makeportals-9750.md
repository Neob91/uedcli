# Pass B decode — RVA 0xa9750 = `FEditorVisibility::MakePortals` (Editor.dll, UED22)

Decoded 2026-07-16 from the binary (adis.py/capstone). All function NAMES below are **ground
truth from the binary itself**: each function's MSVC `guard{}`-macro unwind funclet pushes a
UTF-16 name string into `appUnwindf` (`[0x100ce78c]`), and the assert in the FPortal helper
cites the source file `C:\GameDev\UnrealTournament\Editor\Src\UnVisi.cpp` (ANSI string @
0x100fe394). So this really is UnVisi.cpp lineage.

Function map for pass B (the "0xa9750 region" is FIVE functions + one 0x20-byte ctor):

| RVA | name (from unwind string) | role |
|---|---|---|
| 0xa9750 | `FEditorVisibility::MakePortals` (str @0x100fe5d8) | recursive per-node driver |
| 0xa7ae0 | `BuildInfiniteFPoly` (str @0x100feebc) | huge quad on a node's plane |
| 0xa9970 | `FEditorVisibility::MakePortalsClip` (str @0x100fe590) | clip poly to the node's cell via ancestor stack, then hand to FilterThroughSubtree |
| 0xa9030 | `FEditorVisibility::FilterThroughSubtree` (str @0x100fe540) | 2-phase back/front leaf-pair finder, invokes callback per fragment |
| 0xa72a0 | `FEditorVisibility::AddPortal` (str @0x100fe504) | callback: allocate + link an FPortal record |
| 0xa7870 | `FEditorVisibility::BlockPortal` (str @0x100fe4c4) | callback: stamp existing portals with a PF_Portal surf index |
| 0xa6ab0 | (no guard; trivial) FPortal ctor | fills the 0x200-byte portal record |
| 0xa9b70 | (no guard) `FPortal::Next(iLeaf)`-style helper, UnVisi.cpp:248 | per-leaf chain walker used by later passes |

## Bottom line (what pass B PRODUCES)

Pass B builds the **leaf-adjacency portal graph**: one 0x200-byte `FPortal` record per
(frontLeaf, backLeaf) polygon fragment of every BSP node plane, allocated on `GMem`
(`FMemStack::PushBytes(0x200, 0x10)`), threaded into FOUR intrusive singly-linked lists:

- `this+0x10044` — global list head (link field `portal+0x1e4`), 0-terminated.
- `this+0x1004c[iNode]` — per-node list heads (link `portal+0x1f0`); indexed by the node the
  portal's polygon lies on (only chain-HEAD tree nodes are ever used as index; the array's
  size `2*Nodes.Num+0x100` is headroom, no other index form appears in this pass).
- `this+0x10050[iLeaf]` — per-leaf list heads; each portal is in BOTH its leaves' lists
  (link is `portal+0x1e8` when you arrived via its front leaf, `portal+0x1ec` via its back
  leaf — that is exactly what helper 0xa9b70 implements).

It does **NOT touch the UModel at all** — no store goes through `this+0x10` (Model) in any of
these six functions; every write is to `this` (FEditorVisibility) fields or to portal records.
The zone flood (pass C, 0xa93c0) runs on this graph. `this+0x10054` (the second per-leaf
array) is NOT written by pass B — it belongs to the later light/volumetric passes.

PF_Portal handling: PF_Portal faces create **no geometry** in pass B. Instead, for every node
whose surf has `PolyFlags & 0x04000000`, the node's actual polygon (`bspNodeToFPoly`) is
re-filtered to leaf pairs, and every already-created adjacency portal joining the same
(unordered) leaf pair gets **stamped** `portal+0x1fc = iSurf` ("BlockPortal") — marking it
impassable for the zone flood. Solid space is excluded structurally: `AddPortal` drops any
fragment whose front or back leaf index is -1 (leaf -1 = solid subtree side; pass A only
assigned iLeaf to non-solid sides).

Counters:
- `this+0x10014` = number of FPortal records created (AddPortal) → "%i portals".
- `this+0x10034` = number of PF_Portal coplanar-chain nodes whose `bspNodeToFPoly` returned
  non-zero (counted once per node polygon, BEFORE filtering) → "%i zone portals".
- `this+0x10038` = number of (fragment × matching-portal) stampings in BlockPortal (one
  fragment can match and count several records; re-stamping the same record counts again)
  → "(%i fragments)".

Node/leaf/surf flags: pass B never tests or sets NodeFlags, never tests NF_* bits, and the
ONLY PolyFlags test in the whole pass is `PF_Portal` (0x4000000) at 0x100a9870. No
solid/semisolid/invisible flag is consulted here (solidity was consumed by pass A's leaf
assignment).

---

## 0xa9750 `FEditorVisibility::MakePortals(INT iNode)` — thiscall, ret 4

Role: pre-order recursion over the BSP; per tree node it (a) builds the node-plane portal
fragments via the infinite-poly filter, (b) recurses into children while maintaining an
ancestor stack, (c) after the subtree is done, walks the node's coplanar chain and "blocks"
portals lying on PF_Portal surfaces.

### Pseudo-C

```c
void FEditorVisibility::MakePortals(INT iNode)   // this = ebx (from ecx)
{
    // 1. Infinite polygon on this node's plane, clipped to this node's cell,
    //    then split into per-leaf-pair fragments => AddPortal for each.
    FPoly Poly;                                    // [ebp-0x1ec]
    BuildInfiniteFPoly(&Poly, Model /*this+0x10*/, iNode);       // 0xa7ae0, cdecl
    MakePortalsClip(iNode, Poly /*byval*/, 0, &AddPortal_0xa72a0); // 0xa9970

    // 2. Recurse, maintaining ancestor stack at this+0x14[], depth this+0x1001c.
    //    Stack entry = ancestor iNode, with bit 0x40000000 set iff we descended
    //    into iChild[0] (BACK side).  NOTE: iChild[1]=front, iChild[0]=back.
    if (Nodes[iNode].iChild[1] != -1) {            // +0x24 front
        Stack[Depth++] = iNode;                    // no bit: subtree is on FRONT
        MakePortals(Nodes[iNode].iChild[1]);
        Depth--;
    }
    if (Nodes[iNode].iChild[0] != -1) {            // +0x20 back
        Stack[Depth++] = iNode | 0x40000000;       // bit: subtree is on BACK
        MakePortals(Nodes[iNode].iChild[0]);
        Depth--;
    }

    // 3. Block zone portals: walk the coplanar chain of iNode.
    for (INT i = iNode; i != -1; i = Nodes[i].iPlane /*+0x28*/) {
        FBspSurf* Surf = &Surfs[Nodes[i].iSurf];   // Surfs stride 0x40
        if (Surf->PolyFlags /*+4*/ & PF_Portal /*0x4000000*/) {
            if (GEditor->bspNodeToFPoly(Model, i, &Poly))  // vtbl+0x1f8, ret=#verts
            {
                this->0x10034++;                   // "zone portals" counter
                this->0x10040 = Nodes[i].iSurf;    // scratch: current portal surf
                // Filter the REAL node polygon to leaf pairs of the CHAIN-HEAD
                // node (iNode), phase 0 starts in head's BACK subtree:
                FilterThroughSubtree(0, /*arg2=*/i, /*arg3=*/iNode,
                                     Nodes[iNode].iLeaf[0] /*+0x38*/,
                                     Nodes[iNode].iChild[0] /*+0x20*/,
                                     Poly /*byval*/, &BlockPortal_0xa7870, -1);
            }
        }
    }
}
```

### Key instruction evidence

Ancestor stack is INLINE in FEditorVisibility at +0x14 (this is the "big middle region":
0x14..0x10014 = 0x10000 bytes = 16384 entries max depth; **no bounds check**):
```
0x100a97e8  mov  eax, dword ptr [ebx + 0x1001c]        ; Depth
0x100a97ee  mov  dword ptr [ebx + eax*4 + 0x14], esi   ; Stack[Depth] = iNode (front)
0x100a97f2  inc  dword ptr [ebx + 0x1001c]
...
0x100a981c  mov  ecx, esi
0x100a981e  or   ecx, 0x40000000                       ; back-side marker bit
0x100a982a  mov  dword ptr [ebx + eax*4 + 0x14], ecx
```
Front child recursed first (`[eax+edi+0x24]` @0x100a97e1), then back (`[eax+edi+0x20]`
@0x100a9815). PF_Portal test:
```
0x100a9864  mov  eax, dword ptr [edi + 0x1c]           ; node.iSurf
0x100a9867  shl  eax, 6
0x100a986a  add  eax, dword ptr [edx + 0x98]           ; Surfs.Data
0x100a9870  test dword ptr [eax + 4], 0x4000000        ; Surf.PolyFlags & PF_Portal
```
(⇒ **FBspSurf in-memory: +0 Texture, +4 PolyFlags** — new pin for the brief's table.)
bspNodeToFPoly + counters:
```
0x100a9890  call dword ptr [eax + 0x1f8]               ; GEditor->bspNodeToFPoly(Model,i,&Poly)
0x100a9896  test eax, eax                              ; 0 verts -> skip
0x100a989a  mov  eax, dword ptr [ebx + 0x10034]
0x100a98a0  inc  eax                                   ; zone-portal count
0x100a98a7  mov  eax, dword ptr [edi + 0x1c]
0x100a98aa  mov  dword ptr [ebx + 0x10040], eax        ; this->iZonePortalSurf scratch
```
FilterThroughSubtree call for blocking uses the CHAIN-HEAD's children/leaves
(`[ebp-0x1f4] = original iNode<<6`, stored once at 0x100a97d5, never updated):
```
0x100a98b3  mov  esi, dword ptr [eax + 0x58]
0x100a98b6  add  esi, dword ptr [ebp - 0x1f4]          ; &Nodes[chain HEAD]
0x100a98bc  push -1                                    ; last arg (backLeaf slot)
0x100a98be  push 0x100a7870                            ; callback = BlockPortal
...  (FPoly byval copy via FPoly copy-ctor import [0x100cee94])
0x100a98d8  push dword ptr [esi + 0x20]                ; head.iChild[0] (back)
0x100a98db  push dword ptr [esi + 0x38]                ; head.iLeaf[0]  (back)
0x100a98de  push dword ptr [ebp - 0x1f8]               ; arg3 = chain head iNode
0x100a98e4  push dword ptr [ebp - 0x1f0]               ; arg2 = current chain node i
0x100a98ea  push 0                                     ; phase = 0
0x100a98ee  call 0x100a9030
```
Chain step: `0x100a98f3 mov esi, [edi + 0x28]` (iPlane), loop `cmp esi, -1` @0x100a9850.

---

## 0xa7ae0 `BuildInfiniteFPoly(FPoly* Out, UModel* Model, INT iNode)` — cdecl, ret Out

Role: writes into `Out` a 4-vertex square of half-extent **65536** (`WORLD_MAX`; raw:
`0x100a7b9e movss xmm0, [0x100dea10] ; f32=65536`) lying on the node's surf plane.

```c
FPoly* BuildInfiniteFPoly(FPoly* Out, UModel* M, INT iNode)
{
    FBspSurf* S = &M->Surfs[M->Nodes[iNode].iSurf];
    FVector Base   = M->Points [S->pBase   /*+0x08*/];
    FVector Normal = M->Vectors[S->vNormal /*+0x0c*/];
    FVector Axis1, Axis2;
    Normal.FindBestAxisVectors(Axis1, Axis2);   // Core import [0x100ce264]
    new(Out) FPoly();                            // [0x100ceea4] FPoly::FPoly()
    Out->Init();                                 // [0x100ceea0] FPoly::Init()
    Out->NumVertices /*+0x1c0*/ = 4;
    Out->Normal /*+0x0c*/ = Normal;
    Out->Base   /*+0x00*/ = Base;
    FVector A = Axis2 * 65536.f, B = Axis1 * 65536.f;
    Out->Vertex[0] /*+0x30*/ = Base + B + A;
    Out->Vertex[1] /*+0x3c*/ = Base - B + A;
    Out->Vertex[2] /*+0x48*/ = Base - B - A;
    Out->Vertex[3] /*+0x54*/ = Base + B - A;
    return Out;
}
```
Evidence for field sources: `0x100a7b2e mov eax,[ecx+8]` → pBase index ×3 into Points
(`[edx+0x88]`); `0x100a7b3a mov eax,[ecx+0xc]` → vNormal ×3 into Vectors (`[edx+0x78]`).
(⇒ **FBspSurf +0x8 = pBase, +0xc = vNormal** in memory.) Vertex arithmetic: e.g.
`0x100a7bfa..0x100a7c49` computes Base+B then +A into `[ecx+0x30..0x38]` (Vertex[0]);
`0x100a7c71..0x100a7cd2` Base−B+A → Vertex[1]; `0x100a7d0c..0x100a7d70` Base−B−A → Vertex[2];
`0x100a7daa..0x100a7e01` Base+B−A → Vertex[3]. Only OTHER FPoly fields written are
NumVertices(+0x1c0)=4, Normal, Base — TextureU/V etc. stay as Init() left them.

---

## 0xa9970 `FEditorVisibility::MakePortalsClip(INT iNode, FPoly Poly /*byval 0x1d8*/, INT StackStart, void (FEditorVisibility::*Cb)(...))` — thiscall, ret 0x1e4

Role: clips `Poly` (which lies on `Nodes[iNode]`'s plane) against every ancestor plane
recorded in the stack (entries `StackStart..Depth-1`), keeping the piece on the side the
current subtree lies on; the survivor is handed to FilterThroughSubtree rooted at `iNode`
itself with callback `Cb` (always AddPortal in this pass).

```c
void MakePortalsClip(INT iNode, FPoly Poly, INT i, CbT Cb)
{
    for (; i < Depth /*this+0x1001c*/; i++) {
        INT Entry = Stack[i];                    // this+0x14[i]
        INT iAnc  = Entry & 0xBFFFFFFF;          // strip side bit
        if (Poly.NumVertices >= 14) {            // FPoly::VERTEX_THRESHOLD
            FPoly Half;  Poly.SplitInHalf(&Half);       // Engine import [0x100cee40]
            MakePortalsClip(iNode, Half, i, Cb);        // other half, same stack pos
        }
        FPoly Front, Back;                       // [ebp-0x59c], [ebp-0x3c4]
        int R = Poly.SplitWithNode(Model, iAnc, &Front, &Back, 1); // [0x100ceaa8]
        // R: 0=coplanar 1=front 2=back 3=split (see confidence note below)
        bool SubtreeIsBack = Entry & 0x40000000;
        if      (R == 0)                 return;             // coplanar: poly dies
        else if (R == 1 &&  SubtreeIsBack) return;           // wrong side: dies
        else if (R == 2 && !SubtreeIsBack) return;           // wrong side: dies
        else if (R == 3) Poly = SubtreeIsBack ? Back : Front; // keep our side
        // R matching our side: keep whole Poly, next ancestor
    }
    // Survivor spans iNode's plane inside iNode's cell:
    FilterThroughSubtree(0, iNode, iNode,
                         Nodes[iNode].iLeaf[0], Nodes[iNode].iChild[0],
                         Poly, Cb, -1);
}
```
Evidence:
```
0x100a99d0  cmp  esi, dword ptr [ebx + 0x1001c]     ; i < Depth
0x100a99dc  mov  edi, dword ptr [ebx + esi*4 + 0x14]
0x100a99e0  and  edi, 0xbfffffff                    ; strip side bit
0x100a99e6  cmp  dword ptr [ebp + 0x1cc], 0xe       ; Poly.NumVertices >= 14 -> SplitInHalf
0x100a99ed  jl   0x100a9a34
...
0x100a9a4c  push 1                                  ; VeryPrecise
0x100a9a54  push eax        ; &Back  [ebp-0x3c4]
0x100a9a5b  push eax        ; &Front [ebp-0x59c]
0x100a9a5c  push edi        ; iAnc
0x100a9a5d  push dword ptr [ebx + 0x10]             ; Model
0x100a9a63  call dword ptr [0x100ceaa8]             ; FPoly::SplitWithNode
0x100a9a6d  cmp  eax, 1
0x100a9a72  test ecx, 0x40000000 / jne EXIT         ; R==1 && back-side -> die
0x100a9ab0  cmp  eax, 2
0x100a9ab5  test ecx, 0x40000000 / jne CONTINUE     ; R==2 && back-side -> keep
0x100a9a84  cmp  eax, 3 / cmove eax, edx            ; R==3: pick Front if bit clear
0x100a9a9e  call dword ptr [0x100cee28]             ; Poly = chosen half (FPoly::operator=)
0x100a9a80  test eax, eax / je EXIT                 ; R==0 coplanar -> die
```
Loop-exit tail (jge target 0x100a9adb, AFTER the `ret 0x1e4` — same function):
```
0x100a9ae9  mov  esi, dword ptr [eax + 0x58]        ; Nodes.Data
0x100a9aec  add  esi, ecx                           ; &Nodes[iNode]
0x100a9aee  push -1
0x100a9af0  push dword ptr [ebp - 0x5a4]            ; Cb
...  (byval copy of surviving Poly)
0x100a9b08  push dword ptr [esi + 0x20]             ; iChild[0] (back)
0x100a9b0b  push dword ptr [esi + 0x38]             ; iLeaf[0]  (back)
0x100a9b0e  push edi / push edi                     ; arg3 = arg2 = iNode
0x100a9b10  push 0                                  ; phase 0
0x100a9b14  call 0x100a9030
```

---

## 0xa9030 `FEditorVisibility::FilterThroughSubtree(INT Phase, INT iSourceNode, INT iHomeNode, INT iLeaf, INT iNode, FPoly Poly /*byval*/, CbT Cb, INT iBackLeaf)` — thiscall, ret 0x1f4

Role: the leaf-pair fragment generator. Phase 0 filters `Poly` down the BACK subtree of
`iHomeNode`; every back-leaf fragment is then re-filtered (Phase 1, back-leaf carried in the
last arg) down the FRONT subtree of `iHomeNode`; every front-leaf fragment triggers
`Cb(this, &Poly, iFrontLeaf, iBackLeaf, iSourceNode, iHomeNode)`.

Arg slots: `+8` Phase, `+0xc` iSourceNode (constant through recursion; = coplanar-chain node
for BlockPortal, = iNode for AddPortal), `+0x10` iHomeNode (the tree node whose front subtree
Phase 1 restarts from), `+0x14` iLeaf (leaf id paired with `+0x18` iNode child ptr), `+0x18`
iNode (current filter node, -1 ⇒ arrived at leaf `iLeaf`), `+0x1c..0x1f3` FPoly byval,
`+0x1f4` Cb, `+0x1f8` iBackLeaf (-1 during phase 0).

```c
void FilterThroughSubtree(INT Phase, INT iSrc, INT iHome, INT iLeaf, INT iNode,
                          FPoly Poly, CbT Cb, INT iBackLeaf)
{
    while (iNode != -1) {
        if (Poly.NumVertices > 14) {              // NOTE: > here, >= in MakePortalsClip
            FPoly Half; Poly.SplitInHalf(&Half);
            FilterThroughSubtree(Phase, iSrc, iHome, iLeaf, iNode, Half, Cb, iBackLeaf);
        }
        FPoly Front, Back;                        // [ebp-0x3c4], [ebp-0x59c]
        int R = Poly.SplitWithNode(Model, iNode, &Front, &Back, 1);
        if (R == 1 || R == 3)                     // front piece -> front child
            FilterThroughSubtree(Phase, iSrc, iHome,
                                 Nodes[iNode].iLeaf[1] /*+0x3c*/,
                                 Nodes[iNode].iChild[1] /*+0x24*/,
                                 (R==1) ? Poly : Front, Cb, iBackLeaf);
        if (R == 0 || R == 1) return;             // coplanar dropped; front fully handled
        if (R == 3) Poly = Back;                  // continue with back piece
        iLeaf = Nodes[iNode].iLeaf[0];            // +0x38
        iNode = Nodes[iNode].iChild[0];           // +0x20  (tail loop)
    }
    // Reached leaf `iLeaf` (possibly -1 = solid side):
    if (Phase == 0)                               // finished BACK descent
        FilterThroughSubtree(1, iSrc, iHome,
                             Nodes[iHome].iLeaf[1], Nodes[iHome].iChild[1],
                             Poly, Cb, /*iBackLeaf=*/iLeaf);
    else                                          // finished FRONT descent
        (this->*Cb)(&Poly, /*iFrontLeaf=*/iLeaf, iBackLeaf, iSrc, iHome);
}
```
Evidence (leaf paths):
```
0x100a91bf  cmp  dword ptr [ebp + 8], 0            ; Phase
0x100a91d0  mov  eax, dword ptr [esi + 0x10]       ; Model  (iHome<<6 into Nodes)
0x100a91d8  push ebx                               ; iBackLeaf = leaf just reached
0x100a91f1  push dword ptr [esi + 0x24]            ; Home.iChild[1] (front)
0x100a91f4  push dword ptr [esi + 0x3c]            ; Home.iLeaf[1]
0x100a91fb  push 1                                 ; Phase 1
0x100a9203  call 0x100a9030
--- phase 1:
0x100a920a  push dword ptr [ebp - 0x5a0]           ; iHome
0x100a9210  push dword ptr [ebp + 0xc]             ; iSrc
0x100a9213  push dword ptr [ebp + 0x1f8]           ; iBackLeaf
0x100a9219  push ebx                               ; iFrontLeaf
0x100a921d  push eax                               ; &Poly
0x100a9220  call dword ptr [ebp - 0x5a4]           ; Cb(this=ecx, ...)
```
Split-threshold: `0x100a9099 cmp dword ptr [ebp+0x1dc], 0xe / jle skip` (strictly `> 14`).
Descent: `0x100a916c push [esi+0x24] / 0x100a916f push [esi+0x3c]` (front, on R∈{1,3});
`0x100a91b2 mov ebx,[eax+edi+0x38] / 0x100a91b6 mov edi,[eax+edi+0x20]` (back, tail loop).

---

## 0xa72a0 `FEditorVisibility::AddPortal(FPoly* Poly, INT iFrontLeaf, INT iBackLeaf, INT iNode, INT iHome_unused)` — thiscall, ret 0x14

Role: materializes one portal record and threads it into all four lists; counts it.

```c
void AddPortal(FPoly* Poly, INT iF, INT iB, INT iNode, INT)
{
    if (iF == -1 || iB == -1) return;             // fragment borders solid space
    BYTE* Mem = GMem.PushBytes(0x200, 0x10);      // [0x100ce508]/[0x100ce530]
    FPortal* P = Mem ? new(Mem) FPortal(Poly, iF, iB, iNode,
                        /*GlobalNext*/ this->0x10044,
                        /*NodeNext*/   ((FPortal**)this->0x1004c)[iNode],
                        /*FrontNext*/  ((FPortal**)this->0x10050)[iF],
                        /*BackNext*/   ((FPortal**)this->0x10050)[iB]) : 0;
    ((FPortal**)this->0x1004c)[iNode] = P;
    ((FPortal**)this->0x10050)[iF]   = P;
    ((FPortal**)this->0x10050)[iB]   = P;
    this->0x10044 = P;                            // global head
    this->0x10014++;                              // "%i portals"
}
```
Evidence:
```
0x100a72ec  push 0x10 / push 0x200
0x100a72f3  mov  ecx, dword ptr [0x100ce508]       ; &GMem
0x100a72f9  call dword ptr [0x100ce530]            ; FMemStack::PushBytes(0x200,0x10)
0x100a730f  mov  ecx, dword ptr [esi + 0x10050]    ; per-leaf head array
0x100a7328  push dword ptr [ecx + ebx*4]           ; [iBackLeaf]
0x100a732b  push dword ptr [ecx + edi*4]           ; [iFrontLeaf]
0x100a732e  mov  eax, dword ptr [esi + 0x1004c]    ; per-node head array
0x100a7337  push dword ptr [eax + ecx]             ; [iNode*4]
0x100a733a  push dword ptr [esi + 0x10044]         ; global head
0x100a734a  call 0x100a6ab0                        ; FPortal ctor
0x100a737b  mov  dword ptr [edx + eax], ecx        ; 0x1004c[iNode] = P
0x100a7387/0x100a7393                              ; 0x10050[iF] = 0x10050[iB] = P
0x100a7396  mov  dword ptr [esi + 0x10044], ecx    ; global head = P
0x100a73a2  inc  eax / mov [esi+0x10014], eax      ; portal count++
```
(The `Mem==0` branch @0x100a7353 is the compiler's placement-new null guard;
FMemStack::PushBytes doesn't return null in practice, but if it did, all four heads would be
set to NULL — truncating the lists. Not a semantic path to port.)

### FPortal record (0x200 bytes, ctor 0xa6ab0, ret 0x20)

| off | field | ctor evidence |
|---|---|---|
| +0x000..0x1d7 | FPoly (fragment polygon, full copy) | `0x100a6ab9 call [0x100cee94]` FPoly copy-ctor |
| +0x1d8 | iFrontLeaf | `0x100a6ac2` (name proven by assert `iLeaf==iFrontLeaf \|\| iLeaf==iBackLeaf`, UnVisi.cpp:248, tested against +0x1d8 first @0x100a9b7a) |
| +0x1dc | iBackLeaf | `0x100a6acb` |
| +0x1e0 | iNode (plane the portal lies on) | `0x100a6ad4` |
| +0x1e4 | GlobalNext | `0x100a6add`; walked by BlockPortal @0x100a78fb |
| +0x1e8 | NextPortalInFrontLeafChain | `0x100a6ae6` (from old 0x10050[iF]) |
| +0x1ec | NextPortalInBackLeafChain | `0x100a6aef` (from old 0x10050[iB]) |
| +0x1f0 | NextPortalOnNode | `0x100a6af8` (from old 0x1004c[iNode]) |
| +0x1f4 | u16 = 0 (two flag bytes; pass B never reads — later passes will) | `0x100a6b00 mov word ptr [esi+0x1f4], 0` |
| +0x1f8 | u32 = 0 (unused in pass B) | `0x100a6b09` |
| +0x1fc | iZonePortalSurf, init -1; set by BlockPortal | `0x100a6b13 mov dword ptr [esi+0x1fc], -1` |

Per-leaf chain traversal helper 0xa9b70 (used by later passes): given (FPortal* this=ecx,
INT iLeaf): returns `+0x1e8` if `iLeaf == iFrontLeaf`, else asserts `iLeaf == iBackLeaf`
(appFailAssert, UnVisi.cpp line 0xf8=248) and returns `+0x1ec` (`0x100a9bb6 mov eax,[esi+0x1ec]`).

## 0xa7870 `FEditorVisibility::BlockPortal(FPoly* unused, INT iFrontLeaf, INT iBackLeaf, INT, INT)` — thiscall, ret 0x14

Role: for a fragment of a PF_Portal face joining (iF, iB), stamp EVERY existing portal with
the same unordered leaf pair with the current portal surf; count each stamp.

```c
void BlockPortal(FPoly*, INT iF, INT iB, INT, INT)
{
    if (iF == -1 || iB == -1) return;
    for (FPortal* P = this->0x10044; P; P = P->GlobalNext /*+0x1e4*/)
        if ((P->iFrontLeaf == iF && P->iBackLeaf == iB) ||
            (P->iFrontLeaf == iB && P->iBackLeaf == iF)) {
            P->iZonePortalSurf /*+0x1fc*/ = this->0x10040;  // surf set by MakePortals
            this->0x10038++;                                 // "(%i fragments)"
        }
}
```
Evidence: pair test @0x100a78c4..0x100a78e0; stamp `0x100a78e8 mov [ecx+0x1fc], eax` with
`eax = [edx+0x10040]`; counter `0x100a78f4 inc / mov [edx+0x10038]`; walk `0x100a78fb
mov ecx,[ecx+0x1e4]`. The fragment polygon itself is discarded (arg [ebp+8] never read).

---

## Initialization facts (verified so the lists/counters are well-founded)

- FEditorVisibility ctor 0xa6970 zeroes `+0x10014, +0x1001c, +0x10034, +0x10038, +0x10044,
  +0x10048` (`0x100a69bf/0x100a69c9/0x100a6a05/0x100a6a0f/0x100a6a22/0x100a6a2c`).
- The three arrays are allocated **zero-filled**: portalize @0x100aa488..0x100aa4e7 calls
  helper 0x10031450(4, &GMem, 1, count, 0x10) with counts `Leaves.Num` (+0x10050, +0x10054)
  and `Nodes.Num*2 + 0x100` (`0x100aa4cd lea eax,[eax*2+0x100]`, +0x1004c); 0x31450 =
  `PushBytes(4*count, 0x10)` then `memset(ptr, 0, 4*count)` (`0x1003146f call 0x100ae140`).
  So NULL is the terminator of every portal list. Pass B is called immediately after
  (`0x100aa4ed push 0 / call 0x100a9750` — root node 0, matching MakePortals(0)).

## Callee index

| RVA / slot | symbol | role in pass B |
|---|---|---|
| 0xa7ae0 | `BuildInfiniteFPoly` | 65536-half-extent quad on node plane |
| 0xa9970 | `FEditorVisibility::MakePortalsClip` | clip to cell via ancestor stack |
| 0xa9030 | `FEditorVisibility::FilterThroughSubtree` | back/front leaf-pair fragmentation |
| 0xa72a0 | `FEditorVisibility::AddPortal` | create + link FPortal |
| 0xa7870 | `FEditorVisibility::BlockPortal` | stamp iZonePortalSurf |
| 0xa6ab0 | FPortal ctor | fill 0x200-byte record |
| 0xa9b70 | FPortal per-leaf-chain next | (used by later passes; assert names fields) |
| GEditor vtbl+0x1f8 | `bspNodeToFPoly` | real polygon of a PF_Portal node |
| [0x100ceaa8] | Engine: `FPoly::SplitWithNode(UModel const*, int, FPoly*, FPoly*, int)` | plane classification/split |
| [0x100cee40] | Engine: `FPoly::SplitInHalf(FPoly*)` | vert-count overflow guard |
| [0x100cee94] | Engine: `FPoly::FPoly(FPoly const&)` | byval arg copies + record fill |
| [0x100cee28] | Engine: `FPoly::operator=(FPoly const&)` | keep chosen half |
| [0x100ceea4]/[0x100ceea0] | Engine: `FPoly::FPoly()` / `FPoly::Init()` | poly init |
| [0x100ce264] | Core: `FVector::FindBestAxisVectors(FVector&, FVector&)` | plane basis |
| [0x100ce508]/[0x100ce530] | Core: `GMem` / `FMemStack::PushBytes(int,int)` | portal alloc |
| 0x10031450 | local helper: zeroed GMem array alloc (PushBytes + memset0) | array alloc |
| [0x100ce78c]/[0x100ce788] | Core: `appUnwindf` / `appFailAssert` | guard/assert boilerplate |

## Constants / thresholds (all raw)

- `0x4000000` PF_Portal — `0x100a9870 test dword ptr [eax+4], 0x4000000` (only flag tested).
- `0x40000000` back-side marker bit in ancestor-stack entries; stripped with `and edi,
  0xbfffffff` (0x100a99e0).
- `65536.0f` (WORLD_MAX) — `movss xmm0, [0x100dea10]` (0x100a7b9e).
- Vertex split thresholds: `>= 14` in MakePortalsClip (`cmp [ebp+0x1cc],0xe / jl`,
  0x100a99e6), `> 14` in FilterThroughSubtree (`cmp [ebp+0x1dc],0xe / jle`, 0x100a9099).
  (FPoly max = 32 verts; SplitWithNode of a 14/15-vert poly can't overflow 32.)
- Portal record size `0x200`, align `0x10` (0x100a72ec).
- SplitWithNode VeryPrecise arg = 1 at both call sites (0x100a9a4c, 0x100a910c).

## Open questions / confidence notes

1. **SplitWithNode return-code mapping** (0=coplanar, 1=front, 2=back, 3=split) is inferred
   from the branch logic (piece passed to iChild[1] descent on R∈{1,3}, iChild[0]
   continuation on R∈{2,3}, drop on 0) combined with the established iChild[1]=front
   convention — fully self-consistent across BOTH call sites, but the Engine.dll callee
   itself was not disassembled. Verify from Engine.dll if the Rust port re-implements it
   rather than replicating classification behavior.
2. Winding/orientation of the BuildInfiniteFPoly quad relative to Normal depends on
   FindBestAxisVectors' handedness (not decoded). Irrelevant for leaf-pair membership (BSP
   filtering decides front/back), possibly relevant if later passes use the fragment
   polygon's area/winding.
3. Coplanar drop: a poly that lands EXACTLY on an ancestor/descendant plane is discarded
   (R==0 paths in both filters). For portal-fragment membership this means fragments
   coplanar with another node plane vanish — a Rust port must reproduce SplitWithNode's
   coplanarity epsilon exactly to match membership.
4. `this+0x10040` write happens once per PF_Portal chain node BEFORE FilterThroughSubtree,
   and BlockPortal reads it as ambient state — so the stamped `+0x1fc` is the LAST PF_Portal
   node's surf when several PF_Portal fragments hit the same leaf pair (later stamps
   overwrite earlier ones; each still increments +0x10038).
5. The ancestor stack `this+0x14[16384]` has NO overflow check (depth = BSP tree depth).
   `this+0x10048` (zeroed in ctor, untouched in pass B) presumably belongs to another pass.
6. `iHome` arg of AddPortal (5th, `[ebp+0x18]`) is never read — AddPortal always gets
   iSrc==iHome anyway. BlockPortal likewise ignores args 4-5 and its FPoly.
