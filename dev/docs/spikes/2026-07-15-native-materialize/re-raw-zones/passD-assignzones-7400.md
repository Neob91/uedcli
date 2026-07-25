# Pass D — RVA 0xa7400 (Editor.dll): AssignAllZones (node/fragment zone assignment)

Decoded 2026-07-16 from `uned/UED22/Editor.dll` (base 0x10000000) via `adis.py`. All claims
instruction-anchored; addresses below are VAs (RVA = VA - 0x10000000).

**One-line role:** classic `FEditorVisibility::AssignAllZones(INT iNode, INT Outside)` — a
recursive node walk that, for every non-new node in each coplanar chain, filters the node's
polygon through the chain head's back- and front-subtrees to find the (backLeaf, frontLeaf)
pair(s) it touches, creates NF_IsNew coplanar fragment nodes tagged with the leaves' zone
numbers, and then either copies a consistent zone pair onto the original node (discarding the
fragments) or splits the node into its zone-tagged fragments (discarding the original).

**Headline answers to the assignment questions:**

1. **node.iZone[0/1] derivation** — NOT from descent state and NOT directly from child
   leaves. Each node's own polygon (rebuilt by `bspNodeToFPoly`) is *re-filtered from the
   chain head down the chain head's back subtree, and each back-landing fragment is then
   filtered down the chain head's front subtree*. Every (backLeaf, frontLeaf) landing creates
   a fragment node whose `iZone[back-side] = Leaves[backLeaf].iZone`,
   `iZone[front-side] = Leaves[frontLeaf].iZone` (0 if leaf index is -1), with back/front
   mapped onto iZone[0]/iZone[1] by the sign of `dot(chainHead.Plane.Normal, Poly.Normal)`.
   If all fragments agree per side, the fragments are destroyed (`NumVertices = 0`) and the
   **original** node gets `iZone[0] = Zone0, iZone[1] = Zone1`; otherwise the **original**
   node is destroyed (`NumVertices = 0`) and the fragments are kept (all-zero-zone fragments
   also destroyed).
2. **Coplanar-chain nodes** — the per-node body loops `for (i = iNode; i != -1; i = Nodes[i].iPlane)`
   and processes *every* chain node independently (each gets its own poly, filter run, and
   keep/split decision) — but always filtered through the chain **head**'s children
   (`iChild[0/1]`, `iLeaf[0/1]` of the node passed in) and oriented against the chain
   **head**'s plane. Nodes with `NodeFlags & 0x20` (NF_IsNew) are skipped — this is what keeps
   the walk from re-processing the fragments it just appended to the same chain.
3. **FBspSurf zone fields** — **pass D writes NOTHING into any FBspSurf.** There is no store
   through `Model+0x98` (Surfs) anywhere in 0xa7400 / 0xa9030 / 0xaa220. Fragment nodes reuse
   the original node's surf: `bspNodeToFPoly` sets `Poly.iLink(+0x1c4) = node.iSurf(+0x1c)`
   (0x100366a2, quoted in §6), so inside `bspAddNode` the `iLink == Surfs.Num` "new surf"
   branch is never taken and the new node just gets `iSurf = Poly.iLink` (0x100351b6). If a
   surf-side zone pair exists in this engine, it is not produced here.
4. **node.ZoneMask (u64 @ +0x10)** — **NOT computed in pass D.** Neither 0xa7400 nor the
   callback touches +0x10/+0x14 of any node. The only ZoneMask activity is *incidental,
   inside `bspAddNode`*: a newly created fragment node **copies the parent chain-tail node's
   ZoneMask verbatim** (`0x100351d7 mov eax,[edi+0x10] / mov ecx,[edi+0x14]` →
   `0x100351e5 mov [esi+0x10],eax / mov [esi+0x14],ecx`; root nodes get ~0). There is no
   child-mask OR recurrence anywhere in this pass; the real ZoneMask recurrence must live in a
   later pass (F/G) or in bspRefresh — out of this function's scope.
5. **Third argument (`Model->+0xf0`, RootOutside)** — pure recursion plumbing and **dead for
   this pass's output**. It is only combined into the child-recursion `Outside` values
   (front: `Outside || IsCsg(node,4)`, back: `Outside && !IsCsg(node,4)`); the per-node zoning
   body never reads `Outside`. The function shape (and the `IsCsg` calls) mirrors pass A,
   where Outside is load-bearing; here you could pass anything and get identical writes.
   (Consequence for the Rust port: pass D's result does not depend on RootOutside.)

---

## 1. 0xa7400 — `AssignAllZones(this=FEditorVisibility, INT iNode, INT Outside)` (thiscall, ret 8)

### Pseudo-C

```c
void AssignAllZones(FEditorVisibility* this /*ecx*/, INT iNode /*[ebp+8]*/, INT Outside /*[ebp+0xc]*/)
{
    UModel* Model = this->Model;                       // this+0x10
    FBspNode* Node = &Model->Nodes[iNode];             // Nodes.Data = Model+0x58

    // Recurse front child FIRST, then back child (children fully processed before this chain).
    if (Node->iChild[1] != -1)                         // +0x24 (FRONT)
        AssignAllZones(this, Node->iChild[1], Outside || Node->IsCsg(4));      // 4 = NF 0x04
    if (Node->iChild[0] != -1)                         // +0x20 (BACK)
        AssignAllZones(this, Node->iChild[0], Outside && !Node->IsCsg(4));

    INT iHead = iNode;                                 // chain head, cached ([ebp-0x208], [ebp-0x1f8]=iHead<<6)
    for (INT i = iHead; i != -1; i = Model->Nodes[i].iPlane)   // +0x28 coplanar chain
    {
        FPoly Poly;                                    // default ctor [0x100ceea4] each iteration
        FBspNode* N = &Model->Nodes[i];                // [ebp-0x1f4] = i<<6
        if (N->NodeFlags & 0x20) continue;             // NF_IsNew: skip fragments made below
        if (!GEditor->bspNodeToFPoly(Model, i, &Poly)) continue;   // vtbl+0x1f8; 0 verts -> skip

        INT OldNum = Model->Nodes.Num;                 // edi, snapshot BEFORE filtering
        FBspNode* Head = &Model->Nodes[iHead];
        // Filter this node's poly through the chain HEAD's back subtree (pass 0):
        FilterThroughSubtree_0xa9030(this, /*Pass=*/0, /*iNode=*/i, /*iHead=*/iHead,
                                     Head->iLeaf[0] /*+0x38*/, Head->iChild[0] /*+0x20*/,
                                     Poly /*by value 0x1d8*/,
                                     /*FilterFunc=*/0xaa220, /*iBackLeaf=*/-1);

        if (Model->Nodes.Num <= OldNum) continue;      // no fragments landed -> nothing to assign

        // Scan the fragment nodes [OldNum, Nodes.Num):
        INT Zone[2] = {0, 0};                          // [ebp-0x204], [ebp-0x200]
        INT AllSame = 1;                               // [ebp-0x214]
        for (INT j = OldNum; j < Nodes.Num; j++)
            for (INT k = 0; k < 2; k++)
                if (Nodes[j].iZone[k]) Zone[k] = Nodes[j].iZone[k];      // last nonzero wins
        for (INT j = OldNum; j < Nodes.Num; j++)
            for (INT k = 0; k < 2; k++)
                if (Nodes[j].iZone[k] && Nodes[j].iZone[k] != Zone[k]) AllSame = 0;

        if (AllSame) {
            for (INT j = OldNum; j < Nodes.Num; j++)   // discard ALL fragments
                Nodes[j].NumVertices = 0;              // byte +0x36
            for (INT k = 0; k < 2; k++)                // zone the ORIGINAL chain node
                Nodes[i].iZone[k] = (BYTE)Zone[k];     // bytes +0x34/+0x35
        } else {
            Nodes[i].NumVertices = 0;                  // discard the ORIGINAL node's geometry
            for (INT j = OldNum; j < Nodes.Num; j++)   // keep zoned fragments only
                if (Nodes[j].iZone[0] == 0 && Nodes[j].iZone[1] == 0)
                    Nodes[j].NumVertices = 0;
        }
    }
}
```

### Constants / key instructions (evidence)

- Child selection + Outside propagation (front `||`, back `&&!`, both via `IsCsg(4)`):
  ```
  0x100a745a  mov edi, [ecx+0x24]          ; iChild[1] FRONT
  0x100a7465  test esi, esi                ; Outside
  0x100a7467  jne 0x100a7485               ; Outside!=0 -> recurse(.,1)
  0x100a7469  push 4 / call 0x10033b80     ; IsCsg(node /*ecx*/, ExtraFlags=4)
  0x100a7472  jne 0x100a7485               ; IsCsg -> recurse(.,1)  else recurse(.,0)
  ...
  0x100a74ad  mov edi, [ecx+0x20]          ; iChild[0] BACK
  0x100a74b5  test esi,esi / je -> eax=0   ; !Outside -> 0
  0x100a74b9  push 4 / call 0x10033b80     ; Outside: IsCsg -> 0, else 1
  ```
  (Note ecx = `&Nodes[iNode]` at both IsCsg call sites: `0x100a744b shl ecx,6` +
  `0x100a7457 add ecx,[eax+0x58]`, re-formed at 0x100a74a1-0x100a74aa.)
- NF_IsNew skip: `0x100a7512 test byte ptr [eax+esi+0x37], 0x20 / jne 0x100a76e0`.
- bspNodeToFPoly gate: `0x100a752e call [eax+0x1f8]` (GEditor vtbl; args Model, i, &Poly),
  `0x100a7534 test eax,eax / je 0x100a76da`.
- Nodes.Num snapshot + growth test: `0x100a7545 mov edi,[eax+0x5c]` …
  `0x100a7590 cmp [ebx+0x5c], edi / jle 0x100a76e0`.
- Filter call w/ callback and -1 seed (stack args above the by-value FPoly):
  ```
  0x100a7551  push -1                      ; arg +0x1f8: initial iBackLeaf
  0x100a7553  push 0x100aa220              ; arg +0x1f4: FilterFunc (callback, §4)
  0x100a7558  sub esp,0x1d8 / FPoly copy-ctor [0x100cee94]
  0x100a756d  push [esi+0x20]              ; Head->iChild[0]  (esi = &Nodes[iHead]: [ebp-0x1f8])
  0x100a7570  push [esi+0x38]              ; Head->iLeaf[0]
  0x100a7573  push [ebp-0x208]             ; iHead
  0x100a7579  push ebx                     ; i (current chain node)
  0x100a757a  push 0                       ; Pass = 0
  0x100a7582  call 0x100a9030
  ```
- Fragment zone collect (bytes at +0x34/+0x35, zero-skipping):
  `0x100a75da mov al, byte ptr [eax+ecx+0x34] / test al,al / je … /
   0x100a75e5 mov [ebp+ecx*4-0x204], eax` and consistency check
  `0x100a7629 cmp eax, [ebp+ecx*4-0x204] / 0x100a7630 cmovne edx, [ebp-0x1fc]  ; =0`.
- AllSame branch: fragment kill `0x100a7663 mov byte ptr [eax+ecx+0x36], 0` (loop j),
  original-node zone write `0x100a7693 mov byte ptr [eax+edx+0x34], cl` (eax = Nodes.Data +
  i<<6 via `0x100a7691 add eax, ebx` with ebx=[ebp-0x1f4]).
- Split branch: original kill `0x100a76a3 mov byte ptr [eax+ecx+0x36], 0` (ecx = i<<6), and
  zoneless-fragment kill
  `0x100a76c4 cmp byte [eax+ecx+0x34],0 / 0x100a76cb cmp byte [eax+ecx+0x35],0 /
   0x100a76d2 mov byte [eax+ecx+0x36],0`.
- Chain advance: `0x100a76ec mov ebx, [eax+ecx+0x28] / jmp 0x100a74e0` (ecx = i<<6).

### State written by 0xa7400 itself

| target | write |
|---|---|
| `Nodes[i].iZone[0/1]` (+0x34/+0x35, bytes) | = consistent Zone[0/1] from fragments (AllSame branch) |
| `Nodes[i].NumVertices` (+0x36, byte) | = 0 (split branch: original node destroyed) |
| `Nodes[j].NumVertices` for each fragment j | = 0 (AllSame branch: all; split branch: only iZone[0]==iZone[1]==0 ones) |

Everything else (fragment creation, fragment iZone) happens in the callees below.
No write to Leaves, Surfs, Verts, ZoneMask, iLeaf, NodeFlags, or FEditorVisibility fields.

---

## 2. 0x33b80 — `FBspNode::IsCsg(DWORD ExtraFlags)` (thiscall ecx=&node, ret 4)

Role: "does this node's polygon seal space" test used only for the Outside plumbing.

```c
INT IsCsg(FBspNode* n, DWORD ExtraFlags)
{   return n->NumVertices > 0 && !(n->NodeFlags & (BYTE)(ExtraFlags | 0x21)); }
```

Evidence:
```
0x10033b83  cmp byte ptr [ecx+0x36], 0 / jbe ret0     ; NumVertices (unsigned byte) == 0 -> 0
0x10033b89  mov eax,[ebp+8] / or al, 0x21             ; mask = ExtraFlags | NF_NotCsg(0x01) | NF_IsNew(0x20)
0x10033b8e  test byte ptr [ecx+0x37], al / jne ret0   ; NodeFlags
0x10033b93  mov eax,1 / ret 4        ; fallthrough 0x10033b9c: xor eax,eax / ret 4
```
Pass D always calls it with ExtraFlags=4 → effective mask 0x25 (NF_NotCsg | 0x04 | NF_IsNew).
Note only `al` (low byte) of the mask matters since NodeFlags is a byte.

---

## 3. 0xa9030 — FilterThroughSubtree (thiscall, ret 0x1f4; recursive; poly BY VALUE)

Role: filters an FPoly down a subtree in two chained passes — pass 0 through the chain head's
back subtree, then (per back-landing) pass 1 through the chain head's front subtree — and at
each pass-1 leaf landing invokes the callback with the (frontLeaf, backLeaf) pair.

Signature (stack layout): `(INT Pass /*+8*/, INT iNode /*+0xc: chain node being zoned*/,
INT iHead /*+0x10*/, INT iLeaf /*+0x14: leaf-if-we-stop*/, INT iFilterNode /*+0x18*/,
FPoly Poly /*+0x1c, 0x1d8 bytes by value*/, void* FilterFunc /*+0x1f4*/,
INT iBackLeaf /*+0x1f8: -1 in pass 0, the landed back leaf in pass 1*/)`.

```c
void Filter(this, Pass, iNode, iHead, iLeaf, iFilter, FPoly Poly, FilterFunc, iBackLeaf)
{
    while (iFilter != -1) {                                  // descend
        if (Poly.NumVertices > 14) {                         // 0x100a9099 cmp [ebp+0x1dc], 0xe / jle
            FPoly Half;                                      // FPoly() [0x100ceea4]
            Poly.SplitInHalf(&Half);                         // Engine import [0x100cee40]
            Filter(this, Pass, iNode, iHead, iLeaf, iFilter, Half, FilterFunc, iBackLeaf); // 0x100a90ef
        }
        FPoly Front, Back;                                   // 0x100a90f4/0x100a9100 ctors
        INT r = Poly.SplitWithNode(Model, iFilter, &Front, &Back, /*VeryPrecise=*/1);
                                                             // [0x100ceaa8], push 1 @0x100a910c
        if (r == 1 || r == 3) {                              // front / split
            FPoly* P = (r == 1) ? &Poly : &Front;            // 0x100a9141 cmovne
            FBspNode* n = &Nodes[iFilter];
            Filter(this, Pass, iNode, iHead, n->iLeaf[1] /*+0x3c*/, n->iChild[1] /*+0x24*/,
                   *P, FilterFunc, iBackLeaf);               // 0x100a9186
        }
        if (r == 2 || r == 3) {                              // back / split: tail-descend back
            if (r == 3) Poly = Back;                         // FPoly::operator= [0x100cee28]
            iLeaf   = Nodes[iFilter].iLeaf[0];               // 0x100a91b2 [+0x38]
            iFilter = Nodes[iFilter].iChild[0];              // 0x100a91b6 [+0x20]
            continue;
        }
        return;   // r==0 (coplanar with a deeper node): fragment silently DROPPED (0x100a922d)
    }
    // Landed in leaf `iLeaf` (may be -1 for solid space).
    if (Pass == 0) {                                         // 0x100a91bf cmp [ebp+8],0
        FBspNode* Head = &Nodes[iHead];
        Filter(this, /*Pass=*/1, iNode, iHead, Head->iLeaf[1] /*+0x3c*/, Head->iChild[1] /*+0x24*/,
               Poly, FilterFunc, /*iBackLeaf=*/iLeaf);       // 0x100a9203; note ebx pushed as +0x1f8
    } else {
        // 0x100a9220: FilterFunc as thiscall(this): (&Poly, iFrontLeaf=iLeaf, iBackLeaf, iNode, iHead)
        FilterFunc(this, &Poly, iLeaf, iBackLeaf, iNode, iHead);
    }
}
```

Constants: vertex-split threshold **14** (`0x100a9099 cmp dword ptr [ebp+0x1dc], 0xe`;
+0x1dc = Poly@+0x1c + 0x1c0 = FPoly.NumVertices), `SplitWithNode(..., VeryPrecise=1)`
(`0x100a910c push 1`). Split result codes observed behaviorally: 1 → all-front, 2 → all-back,
3 → split, anything else (0) → drop (classic ESplitType names SP_Front/SP_Back/SP_Split/
SP_Coplanar — names inferred, behavior binary-anchored).

Callees:
- `FPoly::SplitInHalf(FPoly*)` — Engine.dll import `[0x100cee40]`
  (`?SplitInHalf@FPoly@@QAEXPAV1@@Z`).
- `FPoly::SplitWithNode(const UModel*, INT, FPoly*, FPoly*, INT)` — `[0x100ceaa8]`
  (`?SplitWithNode@FPoly@@QBEHPBVUModel@@HPAV1@1H@Z`).
- `FPoly::operator=` `[0x100cee28]`, FPoly ctors `[0x100ceea4]`/`[0x100cee94]`.
- itself (0xa9030) and the callback pointer.

State written: none directly (all model writes happen inside the callback).

---

## 4. 0xaa220 — the FilterFunc callback: create + zone one fragment node (thiscall, ret 0x14)

Role: for one (frontLeaf, backLeaf) landing of the node's poly, append a NF_IsNew fragment
node to the chain node's coplanar chain via `bspAddNode(NODE_Plane)` and stamp its iZone pair
from the two leaves' zones, orientation-corrected against the chain head's plane.

Signature: `(FPoly* Poly /*+8*/, INT iFrontLeaf /*+0xc*/, INT iBackLeaf /*+0x10*/,
INT iNode /*+0x14: chain node*/, INT iHead /*+0x18*/)`.

```c
void AddZoneFragment(this, Poly, iFrontLeaf, iBackLeaf, iNode, iHead)
{
    UModel* Model = this->Model;
    // 1. New coplanar node in iNode's chain, flags = chain node's flags | NF_IsNew:
    INT iNew = GEditor->bspAddNode(Model, iNode, /*ENodePlace=*/2 /*NODE_Plane*/,
                                   Nodes[iNode].NodeFlags | 0x20, Poly);      // vtbl+0x224
    // 2. Orientation: does the poly's normal agree with the chain HEAD's plane?
    float Dot = Nodes[iHead].Plane.X*Poly->Normal.X + Plane.Y*Normal.Y + Plane.Z*Normal.Z;
    INT k = (0.0f > Dot);                    // 1 if flipped, 0 if aligned (Dot==0 -> aligned)
    // 3. Zone pair from the landed leaves (0 for iLeaf == -1):
    Nodes[iNew].iZone[k]   = (BYTE)(iBackLeaf  == -1 ? 0 : Model->Leaves[iBackLeaf ].iZone);
    Nodes[iNew].iZone[k^1] = (BYTE)(iFrontLeaf == -1 ? 0 : Model->Leaves[iFrontLeaf].iZone);
}
```

Evidence:
```
0x100aa272  movzx eax, byte ptr [eax+0x37] / or eax, 0x20    ; chain node NodeFlags | NF_IsNew
0x100aa27a  push 2 / push esi(iNode) / push edi(Model) / call [edx+0x224]   ; bspAddNode NODE_Plane
0x100aa298  movss xmm1,[ecx+eax+4] / mulss xmm1,[ebx+0x10]   ; Head.Plane.Y * Poly.Normal.Y
0x100aa2a3  movss xmm0,[ecx+eax]   / mulss xmm0,[ebx+0xc]    ; + Plane.X * Normal.X
0x100aa2b1  movss xmm0,[ecx+eax+8] / mulss xmm0,[ebx+0x14]   ; + Plane.Z * Normal.Z
0x100aa2c5  comiss xmm0(0.0), xmm1 / seta dl                 ; dl = (0 > Dot)
0x100aa2d7  lea ecx,[eax+eax*4] / mov eax,[eax(Model)+0xd8] / mov ecx,[eax+ecx*4]
                                                             ; Leaves[iBackLeaf].iZone (stride 0x14, field +0)
0x100aa2ee  mov byte ptr [eax+edx+0x34], cl                  ; iZone[k]   = back zone
0x100aa310  xor edx,1 ... 0x100aa316 mov byte ptr [edx+esi+0x34], cl   ; iZone[k^1] = front zone
```
(vtbl slot +0x224 verified = `?bspAddNode@UEditorEngine@@UAEHPAVUModel@@HW4ENodePlace@@KPAVFPoly@@@Z`
via the UEditorEngine vftable at RVA 0xcf7cc, whose +0x264 slot is TestVisibility @0xaa940 —
matches the brief.)

State written: the new fragment node's `iZone[0]/iZone[1]` bytes (+0x34/+0x35). It does NOT
touch iLeaf, ZoneMask, NumVertices, surfs, or leaves. Note leaf iZone (i32) is truncated to a
byte on store (`mov byte ptr …, cl`).

---

## 5. `UEditorEngine::bspAddNode` @ 0x34e80 (vtbl+0x224) — what pass D's fragments inherit

Only the parts load-bearing for pass D (EdPoly with `iLink != Surfs.Num`, NODE_Plane):

- **Chain-tail attach:** for NodePlace==2 it first walks `iParent = Nodes[iParent].iPlane`
  until -1 (`0x10034ec2..0x10034ed5`), so the true parent is the current chain TAIL (possibly
  an earlier fragment), and links `Nodes[tail].iPlane = iNew` (`0x100352c5 mov [edi+0x28], eax`).
- **No new surf:** new surf is created only `if (Poly->iLink == Model->Surfs.Num)`
  (`0x10034eda mov eax,[esi+0x1c4] / 0x10034ee3 cmp eax,[ecx+0x9c]`). Pass D polys carry the
  original node's iSurf in iLink (§6), so this branch is never taken → **no FBspSurf write**.
  (For completeness, the new-surf branch pins FBspSurf mem layout: Texture +0 ←Poly+0x1b8,
  PolyFlags +4 ←Poly.PolyFlags&0x3cffffff, pBase +8, vNormal +0xc, vTextureU +0x10,
  vTextureV +0x14, iLightMap +0x18 = -1, iBrushPoly +0x1c ←Poly+0x1c8, PanU/PanV words
  +0x20/+0x22 ←Poly+0x1cc/+0x1ce, Actor +0x24 ←Poly+0x1b4; 0x10034f7d..0x10034fc0.)
- **NodeFlags augmentation from the surf's PolyFlags** (`0x10035020 mov edx,[edx+4]`):
  PF & 0x08 (PF_NotSolid) → NF |= 0x01; PF & 0x04000001 (PF_Portal|PF_Invisible) → NF |= 0x04;
  PF & 0x02 → NF |= 0x02; PF & 0x10020000 → NF |= 0x02 (0x1003502b/0x10035039/0x10035044/
  0x10035052). So fragments get chainNode.NodeFlags | 0x20 | surf-derived bits.
- **>16-vert split:** `0x10035058 cmp dword ptr [esi+0x1c0], 0x10 / jle` — polys with more
  than 16 verts are split into a 16-vert head + (N-14)-vert tail (shared edge; memmove of
  verts 15.. from Poly+0xe4) and added as two nodes (second one NODE_Plane under the first).
  Rarely hit in pass D because 0xa9030 already halves polys above 14 verts.
- **New node record** (`0x1003516b..`): iSurf +0x1c = Poly.iLink(+0x1c4); NodeFlags +0x37 =
  arg; iRenderBound/iCollisionBound = -1; **ZoneMask +0x10 (u64) = parent tail's ZoneMask**
  (root: ~0) — `0x100351d7/0x100351e5`; Plane = FPlane(Poly.Base, Poly.Normal)
  (`[0x100ce518]` = `FPlane::FPlane(FVector,FVector)`); iVertPool +0x18 = Verts.Add(NumVertices);
  iChild[0]=iChild[1]=iPlane=-1.
- **NODE_Plane leaf/zone pre-seed, then overwritten by the callback:**
  `k = (0 > (newNode.Plane | Nodes[tail].Plane))` (`[0x100ce510]` = `FPlane::operator|`,
  4-component dot; 0x1003527e..0x10035290), then `iLeaf[0] = tail.iLeaf[k]`,
  `iLeaf[1] = tail.iLeaf[k^1]` (0x10035293/0x100352a1: `[edi+(0xf-ecx)*4]` = +0x3c-k*4),
  `iZone[0] = tail.iZone[k]`, `iZone[1] = tail.iZone[k^1]` (0x100352a7/0x100352b3).
  The iZone pre-seed is immediately overwritten by 0xaa220; **the iLeaf inheritance
  survives** — fragment nodes carry the chain tail's (orientation-corrected) iLeaf pair.
- **Vertex fill** (0x100352c8..): bspAddPoint (vtbl+0x1f4) per poly vertex with consecutive-
  duplicate dropping; first==last dedupe; if final NumVertices < 3 → debugf (fmt @0x100dbca0)
  and NumVertices = 0 (degenerate node, still occupies its index — this is why pass D can see
  fragment nodes with 0 verts; their iZone bytes still count in the collect/compare loops).
- Undo hook: 0x10034020 = "if GUndo ([0x100ce888]) record Nodes[iParent] (stride 0x40)" —
  transaction bookkeeping, no model semantics.

Other callees seen: `0x10031cb0` = TArray add(n) on Nodes (returns first new index),
`0x10031680` = same on Verts, `FMemStack::PushBytes [0x100ce530]` / `FMemMark::Pop
[0x100ce52c]` for the temporary split polys, `appMemmove [0x100ce538]`.

## 6. `bspNodeToFPoly` @ 0x365b0 — the one fact used

`Poly.iLink(+0x1c4) = node.iSurf(+0x1c)`:
```
0x1003669c  mov edx, [ebp-0x1f8]        ; node ptr
0x100366a2  mov eax, [edx+0x1c]         ; node.iSurf
0x100366a5  mov [edi+0x1c4], eax        ; Poly.iLink
```
plus Poly.PolyFlags = surf.PolyFlags & 0x3cffffff (+0x1b0), Texture (+0x1b8), Actor (+0x1b4),
iBrushPoly (+0x1c8), PanU/PanV (+0x1cc/+0x1ce) all copied from the surf — confirming FPoly
slots +0x1c4 = iLink and +0x1c8 = iBrushPoly (refines the brief's "+0x1c8 link field" note).

---

## 7. Open questions / low-confidence spots

- ESplitType numeric names (0=coplanar etc.) are inferred from classic naming; the *behavior*
  per code (1 front, 2 back, 3 split, else drop) is binary-anchored. The r==0 "drop the
  fragment silently" path is real (`0x100a9196 jne 0x100a922d` exits without callback) — a
  poly fragment landing exactly coplanar with a deeper node contributes no fragment node.
- `PF 0x10020000 → NF 0x02` in bspAddNode: which PolyFlags those bits are (0x20000 |
  0x10000000) is not pinned here; only the bit constants are asserted.
- The "last nonzero wins" in the Zone[] collect loop is order-dependent in principle, but the
  second loop forces AllSame=0 on any nonzero disagreement, so the only ambiguity-free case is
  kept — no semantic hole for the port.
- Whether some LATER pass reads the fragment nodes' inherited iLeaf/ZoneMask values (from
  bspAddNode) before bspRefresh recomputes them: not examined here (passes E/F/G are other
  agents' scope). Within pass D they are write-only.
- `0x10034020`'s vcall arg list (serializer fn ptrs 0x10012f80/0x100344c0) interpreted as the
  standard GUndo array-item record; not fully decoded (no model effect either way unless a
  transaction is active — TestVisibility runs outside one during rebuilds).
